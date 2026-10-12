// dbg_u18.mjs — FLE-2 unit#18 診断: boot raise 時の guest stack から呼出連鎖を復元する。
//   node dbg_u18.mjs <boot.cjs> [pe.bin]
// guest stack 上の .text qword を retaddr 候補として収集し、.pdata 関数境界 + capstone で
// 呼出元を特定する (再ビルド不要)。結果は JSON でも出力 (work/boot/u18_chain.json)。
import { readFileSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { FL_WIN64_DIR } from '../../shared/paths.mjs';

const cjs = process.argv[2];
const PE = process.argv[3] || `${FL_WIN64_DIR}/extracted/block00031_PE.bin`;
const mod = await import(cjs);
const m = await (mod.default ? mod.default() : mod());
const U8 = m.HEAPU8;

function q(a) { let v = 0n; for (let i = 7; i >= 0; i--) v = (v << 8n) | BigInt(U8[a + i]); return v; }
const hex = (v) => '0x' + v.toString(16);

let threw = null;
try { m._fle_boot_enter(0); } catch (e) { threw = e; }
console.error('[dbg] boot threw:', threw && (threw.fle_kind || threw.message),
    'units_run=' + m._fle_units_run(), 'freemem=' + m._fle_n_freemem(), 'getmem=' + m._fle_n_getmem());

const rsp = Number(m._fle_rget(4) & 0xffffffffn) >>> 0;
console.error('[dbg] emulated RSP =', hex(rsp));

// ---- .pdata 関数境界 + PE image を python で照会 (capstone) ----
const LO = 0x401000, HI = 0x13a44b0;
const cand = [];
for (let off = 0; off < 0x2000; off += 8) {
    const a = (rsp + off) >>> 0;
    const v = q(a);
    if (v >= BigInt(LO) && v < BigInt(HI)) cand.push([off, Number(v)]);
}
// ユニーク化しつつ python へ渡す
const uniq = [...new Set(cand.map(x => x[1]))].sort((a, b) => a - b);
const pysrc = `
import struct, pefile, bisect, sys, json
pe = pefile.PE(${JSON.stringify(PE)})
img = pe.get_memory_mapped_image()
IMG = 0x400000
for s in pe.sections:
    if s.Name.startswith(b'.pdata'):
        raw = s.get_data(); break
starts = []
for i in range(0, len(raw)//12*12, 12):
    b,e,u = struct.unpack_from('<III', raw, i)
    if b==0 and e==0: break
    starts.append((IMG+b, IMG+e))
ss = [x[0] for x in starts]
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
md = Cs(CS_ARCH_X86, CS_MODE_64)
out = {}
for va_s in sys.argv[1:]:
    va = int(va_s, 16)
    idx = bisect.bisect_right(ss, va) - 1
    if idx < 0 or not (starts[idx][0] <= va < starts[idx][1]):
        out[va_s] = {'fn': None}
        continue
    b, e = starts[idx]
    rec = {'fn': hex(b), 'end': hex(e), 'ret': hex(va)}
    # 直前 10B を逆アセンブルして呼出命令を確認 (value-10..value の窗口を lenient に解釈)
    code = bytes(img[max(b, va-10)-IMG: va-IMG])
    try:
        ins_l = list(md.disasm(code, max(b, va-10)))
        if ins_l:
            last = ins_l[-1]
            rec['prev_ins'] = '%s %s (at 0x%x)' % (last.mnemonic, last.op_str, last.address)
    except Exception:
        pass
    out[va_s] = rec
print(json.dumps(out))
`;
const pyout = execFileSync('python3', ['-c', pysrc, ...uniq.map(hex)], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 });
const info = JSON.parse(pyout);

console.error('[dbg] live chain candidates (rsp+off -> retaddr in fn, prev insn):');
const rows = cand.map(([off, v]) => ({ off, va: hex(v), ...info[hex(v)] }));
for (const r of rows) {
    console.error('  rsp+' + String(r.off).padEnd(5) + ' ' + r.va + '  fn=' + (r.fn || '(no pdata)') + '  ' + (r.prev_ins || ''));
}
// 疑似 retaddr (fle_ov_getmem/freemem が push する定数) をスタックから探す
console.error('[dbg] fake retaddr search (0x409424/33 getmem, 0x409454/61 freemem, 0x412129 unit):');
for (const t of [0x409424, 0x409433, 0x409454, 0x409461, 0x412129, 0xdead0000]) {
    for (let off = -0x800; off < 0x2000; off += 8) {
        const a = (rsp + off) >>> 0;
        if (Number(q(a)) === t) console.error('  ' + hex(t) + ' at rsp+' + off);
    }
}
const outp = new URL('../work/boot/u18_chain.json', 'file://' + import.meta.dirname + '/');
writeFileSync(outp, JSON.stringify({ rsp: hex(rsp), rows }, null, 1));
console.error('[dbg] chain written:', outp.pathname);
