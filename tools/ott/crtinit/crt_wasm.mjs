// entry_wasm.mjs — VST 入口 scenarios を lift 済み wasm (x64c, tools/ott/entry/lift_entry.sh 産物) で実行し
// entry_nat.py と同一 schema の JSON を吐く。
//   MOD=tools/ott/work/entrylift/ottl_entry.cjs SCEN=tools/ott/work/entrylift/scen.json OUT=result.json node entry_wasm.mjs
//   APISET_READBACK=1 のときだけ api-set 表 (34 entry) を init 直後 (apiset_init) と実行後 (apiset_after) に出す (ICALL-76・REPORT §10)。
// ott_run(va, a0..a3, x0..x3): MS x64 ABI の整数引数 → R[RCX..R9], float 引数 → X[xmm 位置]。
// 5/6 引数目 (dispatcher の ptr/opt) は _ott_set_stackarg(0/1) で guest stack に置く。
import fs from 'fs';

const SH = 0x150000000;                    // 0x180000000 → 0x30000000 (tools/ott/lift/x64c.py SHIFT)
const sh = (va) => va - SH;
const IMG = 0x180000000;
const STR = 0x30320000, OUT_F = 0x30321000, CKPT = 0x30322000, CHUNK = 0x30323000;
const IN_A = 0x30330000, OU_A = 0x30331000, BUF = 0x30340000;
const STR_FILL = new Uint8Array(0x201); '0.50\0'.split('').forEach((c, i) => STR_FILL[i] = c.charCodeAt(0));
for (let i = 5; i < 0x201; i++) STR_FILL[i] = 0xcc;
const AM_TRAMP = sh(0x1802f8000);          // audioMaster 仮想入口 (ovr_am_shim)

// CAB-138: data install 後に encoded slot 初期化 (OTT_CRTINIT=0 で skip → 陰性対照 = 旧 fail-fast 再現)
const CRT_INIT = process.env.OTT_CRTINIT !== '0';
const { load } = await import('../diff/api.mjs');
const all = JSON.parse(fs.readFileSync(process.env.SCEN, 'utf8'));
const NAME = process.env.NAME;
const spec = NAME ? all.find((s) => s.name === NAME) : all[0];
if (!spec) throw new Error('scenario not found: ' + NAME);
const api = await load(process.env.MOD);
const mod = api.mod;
const U8 = mod.HEAPU8, U32 = mod.HEAPU32, F32 = mod.HEAPF32, dv = new DataView(U8.buffer, U8.byteOffset, U8.length);
mod._ott_data_install();
if (CRT_INIT) mod._ott_crt_init_tables();
const APISET = sh(0x18026c9f0), APISET_N = 34;   // ICALL-76: 表は 34 entry (0x110 B)
const readApiset = () => Array.from({ length: APISET_N }, (_, i) => dv.getBigUint64(APISET + 8 * i, true));
const APISET_RB = process.env.APISET_READBACK === '1';
const apiset_init = APISET_RB ? readApiset() : null;

const f32b = api.f32b;                      // float → BigInt bits
const big = (v) => BigInt.asUintN(64, BigInt(v));
const hex = (a, n) => Buffer.from(U8.subarray(a, a + n)).toString('hex');

function run1(va, a = [], x = []) {
  const g = [0n, 0n, 0n, 0n];
  for (let i = 0; i < Math.min(4, a.length); i++) g[i] = big(a[i]);
  const xx = [0n, 0n, 0n, 0n];
  for (let i = 0; i < Math.min(4, x.length); i++) xx[i] = typeof x[i] === 'bigint' ? x[i] : big(x[i]);
  return { rax: BigInt.asUintN(64, mod._ott_run(va, ...g, ...xx)), xmm0: BigInt.asUintN(64, mod._ott_xmm0()) };
}
const stackarg = (i, v) => mod._ott_set_stackarg(i, big(v));

let eff = 0, obj = 0;
const calls = [];

for (const st of spec.steps) {
  const c = st['c'];
  let rec = {};
  if (c === 'vstmain') {
    const r = run1(sh(0x180128ba0), [AM_TRAMP]);
    eff = Number(r.rax); rec = { ...r, buf: null };
    if (eff) {
      const u32 = (o) => dv.getUint32(eff + o, true), u64 = (o) => Number(dv.getBigUint64(eff + o, true));
      const WB = 0x30000000; // shift 後 image base
      const rva = (v) => (WB <= v && v < WB + 0x308000) ? v - WB : (IMG <= v && v < IMG + 0x308000 ? v - IMG : v);
      rec.eff = { magic: u32(0), dispatcher_rva: rva(u64(8)), process_rva: rva(u64(0x10)),
        setp_rva: rva(u64(0x18)), getp_rva: rva(u64(0x20)), num_programs: u32(0x28), num_params: u32(0x2c),
        num_inputs: u32(0x30), num_outputs: u32(0x34), flags: u32(0x38), initial_delay: u32(0x50),
        io_ratio_bits: u32(0x5c), unique_id: u32(0x70), version: u32(0x74),
        procr_rva: rva(u64(0x78)), procd_rva: rva(u64(0x80)), obj_ok: u64(0x60) !== 0 };
      obj = u64(0x60);
    }
  } else if (c === 'editorctor') {
    rec = { ...run1(sh(0x180120ff0), [obj || 0x30350000]), buf: null, editor_null: true };
    rec.editor_null = Number(rec.rax) === 0;
  } else if (c === 'disp') {
    if (st.buf) U8.set(STR_FILL, STR);
    stackarg(0, st.buf ? STR : 0);
    stackarg(1, f32b(st.opt ?? 0.0));
    rec = { ...run1(sh(0x180126c00), [eff, st.op, st.idx ?? 0, st.val ?? 0]),
            buf: st.buf ? hex(STR, 0x201) : null };
  } else if (c === 'setp') {
    rec = { ...run1(sh(0x180127520), [eff, st.idx], [0n, 0n, f32b(st.fv), 0n]), buf: null };
  } else if (c === 'getp') {
    U8.fill(0, OUT_F, OUT_F + 4);
    rec = { ...run1(sh(0x1801271a0), [eff, st.idx, OUT_F]), buf: null,
            out_f: dv.getUint32(OUT_F, true) };
  } else if (c === 'virt') {
    if (st.buf) U8.set(STR_FILL, STR);
    const x = [0n, 0n, 0n, 0n];
    for (const [pos, fv] of Object.entries(st.xmm ?? {})) x[Number(pos)] = f32b(fv);
    rec = { ...run1(sh(IMG + st.rva), [obj, st.rdx ?? 0, st.r8 ?? 0, st.r9 ?? 0], x),
            buf: st.buf ? hex(STR, 0x201) : null };
    const reads = st.reads ?? [];
    if (reads.includes('out_f')) rec.out_f = dv.getUint32(OUT_F, true);
    if (reads.includes('ckpt')) rec.ckpt = Number(dv.getBigUint64(CKPT, true));
  } else if (c === 'proc') {
    const n = st.n;
    for (let i = 0; i < n * 8 * 4; i++) U8[BUF + i] = i % 256;      // native (entry_nat.py) と同一 byte 列
    for (let i = 0; i < n * 8; i++) F32[(BUF + n * 8) / 4 + i] = 0;
    dv.setBigUint64(IN_A, BigInt(BUF), true); dv.setBigUint64(IN_A + 8, BigInt(BUF + n * 4), true);
    dv.setBigUint64(OU_A, BigInt(BUF + n * 8), true); dv.setBigUint64(OU_A + 8, BigInt(BUF + n * 12), true);
    rec = { ...run1(sh(0x180127450), [eff, IN_A, OU_A, n]), buf: null, out: hex(BUF + n * 8, n * 8) };
  } else if (c === 'setchunk') {
    stackarg(0, CHUNK); stackarg(1, 0n);
    rec = { ...run1(sh(0x180126c00), [eff, 24, st.is_preset ?? 0, 16]), buf: null };
  } else if (c === 'getchunk') {
    U8.fill(0, CKPT, CKPT + 8);
    stackarg(0, CKPT); stackarg(1, 0n);
    rec = { ...run1(sh(0x180126c00), [eff, 23, st.is_preset ?? 0, 0]), buf: null,
            ckpt: Number(dv.getBigUint64(CKPT, true)) };
  } else throw new Error('unknown step ' + c);
  rec.kind = c;
  if (st.raxok) rec.raxok = true;
  calls.push(rec);
}

const alog = [];
{ const na = U32[0x35f00000 / 4];
  for (let i = 0; i < na; i++) alog.push([U32[0x35f00000 / 4 + 2 + 2 * i], U32[0x35f00000 / 4 + 3 + 2 * i]]); }
const amBase = mod._ott_am_counts();
const am = Array.from(new Uint32Array(U8.buffer, U8.byteOffset + amBase, 64));
const out = { calls, obj: obj ? hex(obj, 0x328) : null, eff_ptr: eff, obj_ptr: obj, alog, am };
if (APISET_RB) {
  const hx = (v) => v.toString(16).padStart(16, '0');
  out.apiset_init = apiset_init.map(hx);
  out.apiset_after = readApiset().map(hx);
}
const jrepl = (k, v) => {
  if (typeof v !== 'bigint') return v;
  const n = Number(BigInt.asUintN(64, v));
  return Number.isSafeInteger(n) ? n : BigInt.asUintN(64, v).toString();   // u64 を f64 で丸めない
};
fs.writeFileSync(process.env.OUT, JSON.stringify({ result: out, alog }, jrepl));
console.log('[crt_wasm] %s ok calls=%d alog=%d am_ver=%d', spec.name, calls.length, alog.length, am[1]);
