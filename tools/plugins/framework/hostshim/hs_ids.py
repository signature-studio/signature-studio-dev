#!/usr/bin/env python3
"""hs_ids.py — Host Dispatcher (slot0) の ID 別「呼出文脈・戻り値使用」実測スキャナ (CAB-195).

A検収資産 work/host_calls_raw.json (host_calls.py が収集した site 一覧) のうち disp==0
(= TFruityHost.Dispatcher) の site を、上位 ID について逆アセンブルし直し、
  * 呼出直後の戻り値 (rax/eax) の使われ方 (store / reg 保持 / test / 無視)
  * 引数即値 (r9d=Index, [rsp+0x20]=Value)
を実測して hostshim/hs_ids.json に出力する。shim (hostshim.c) の Dispatcher 応答表の根拠。

  python3 hs_ids.py [--top 30] [--per-id 4]

機械実測のみ (推定なし)。ret 分類:
  store   直後 mov [mem], rax/eax 系 (結果を保存。以後の deref は別途 deref フラグで判定)
  reg     mov reg, rax 系 (レジスタ保持 → 遅れて使用)
  test    test/cmp eax 系 (BOOL 判定)
  ignore  直後が call / 他レジスタ書き込み (戻り未使用の可能性が高い)
"""
import os, sys, json, collections, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_REG, X86_OP_IMM

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, '..', '..', 'work')
EXT = '/home/ubuntu/work/analysis/win64/extracted'


def load_pes():
    import pefile
    pes = {}
    def mk(fn):
        if fn in pes: return pes[fn]
        p = pefile.PE(data=open(os.path.join(EXT, fn), 'rb').read(), fast_load=True)
        text = [s for s in p.sections if s.Name.startswith(b'.text')][0]
        pes[fn] = (p, text.get_data(), text.VirtualAddress)
        return pes[fn]
    return mk


def scan_fn(md, code, tv, fstart, fend, want_id):
    """関数内の `call [reg]` で直前の r8 即値 == want_id の site を返す (host_calls.py と同じ taint)"""
    out = []
    vt = set()
    lastimm = {}
    insns = list(md.disasm(code[fstart - tv: fend - tv], fstart))
    for idx, ins in enumerate(insns):
        mn, ops = ins.mnemonic, ins.operands
        if mn == 'call' and ops and ops[0].type == X86_OP_MEM and ops[0].mem.base != 0 and ops[0].mem.index == 0:
            base = ins.reg_name(ops[0].mem.base)
            ident = lastimm.get('r8') if (base in vt and ops[0].mem.disp == 0) else None
            if ident == want_id:
                out.append((ins.address, insns[max(0, idx - 8):idx], insns[idx + 1:idx + 5]))
            for r in ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'):
                vt.discard(r); lastimm.pop(r, None)
            continue
        if len(ops) == 2 and ops[0].type == X86_OP_REG:
            dst = ins.reg_name(ops[0].reg)
            if mn == 'mov' and ops[1].type == X86_OP_MEM and ops[1].mem.base != 0 and ops[1].mem.index == 0:
                sb = ins.reg_name(ops[1].mem.base)
                if ops[1].mem.disp == 0 and sb in vt:
                    vt.add(dst)
                elif ops[1].mem.disp == 0xbc and ops[0].size == 8:
                    vt.add(dst)   # Host = [this+0xbc]
                else:
                    vt.discard(dst)
            elif mn == 'mov' and ops[1].type == X86_OP_REG:
                sr = ins.reg_name(ops[1].reg)
                (vt.add if sr in vt else vt.discard)(dst)
                lastimm[dst] = lastimm[sr] if sr in lastimm else None if dst in lastimm else lastimm.get(dst)
            else:
                if dst in ('r8d', 'r8'):
                    lastimm['r8'] = ops[1].imm if (mn == 'mov' and ops[1].type == X86_OP_IMM) else (0 if (mn == 'xor') else None)
                vt.discard(dst)
        elif mn == 'xor' and len(ops) == 2 and ops[0].type == X86_OP_REG and ins.reg_name(ops[0].reg) == 'r8d':
            lastimm['r8'] = 0
    return out


def classify(after):
    """呼出直後命令列から戻り値使用を分類 + Index/Value 即値"""
    use, deref = 'ignore', False
    idx = val = None
    for ins in after[:3]:
        mn, ops = ins.mnemonic, ins.operands
        if mn == 'mov' and len(ops) == 2:
            d, s = ops
            sn = ins.reg_name(s.reg) if s.type == X86_OP_REG else None
            if sn in ('rax', 'eax') and d.type == X86_OP_MEM:
                use = 'store'
                break
            if sn in ('rax', 'eax') and d.type == X86_OP_REG:
                use = 'reg'
                continue
            if d.type == X86_OP_REG and ins.reg_name(d.reg) in ('rax', 'eax'):
                break   # rax 破壊 → それ以前の分類で確定
        if mn in ('test', 'cmp') and ops and ops[0].type == X86_OP_REG and ins.reg_name(ops[0].reg) in ('rax', 'eax', 'al'):
            use = 'test'
            break
        if mn == 'jmp' or mn.startswith('j'):
            break
    for ins in after:
        if ins.mnemonic == 'mov' and len(ins.operands) == 2:
            d, s = ins.operands
            if d.type == X86_OP_REG and s.type == X86_OP_IMM:
                dn = ins.reg_name(d.reg)
                if dn == 'r9d' and idx is None: idx = s.imm
                if dn == 'edx' and idx is None: pass
    return use, deref, idx, val


def main():
    top = 30
    per = 4
    for i, a in enumerate(sys.argv):
        if a == '--top': top = int(sys.argv[i + 1])
        if a == '--per-id': per = int(sys.argv[i + 1])
    hc = json.load(open(os.path.join(WORK, 'host_calls.json')))
    ids_total = {int(k): v for k, v in hc['unique_ids_total'].items() if k != 'None'}
    top_ids = [i for i, _ in sorted(ids_total.items(), key=lambda kv: -kv[1])[:top]]
    raw = json.load(open(os.path.join(WORK, 'host_calls_raw.json')))
    # site が多い plugin 順にサンプル候補を集める
    cands = collections.defaultdict(list)
    for fn, res in raw.items():
        for (rva, disp, ident) in res:
            if disp == 0 and ident in top_ids:
                cands[ident].append((fn, rva))
    getpe = load_pes()
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    import pefile
    out = {}
    total_sites = sum(ids_total.values())
    cov = 0
    for ident in top_ids:
        cov += ids_total.get(ident, 0)
        samples = []
        plugins = set()
        usecnt = collections.Counter()
        for (fn, rva) in cands.get(ident, [])[:400]:
            if len(samples) >= per: break
            if fn in [s['plugin'] for s in samples]: continue
            try:
                p, code, tv = getpe(fn)
                pd = [s for s in p.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
                data = pd.get_data()[:pd.Misc_VirtualSize]
                fend = None
                for k in range(len(data) // 12):
                    b, e, u = struct.unpack_from('<III', data, 12 * k)
                    if b == rva: fend = e; break
                if fend is None: continue
                for (site, pre, post) in scan_fn(md, code, tv, rva, fend, ident):
                    use, deref, idx, val = classify(post)
                    usecnt[use] += 1
                    plugins.add(fn)
                    if len(samples) < per:
                        samples.append({
                            'plugin': fn, 'func': '0x%x' % rva, 'site': '0x%x' % site,
                            'ret_use': use,
                            'pre': ['%s %s' % (i.mnemonic, i.op_str) for i in pre[-4:]],
                            'post': ['%s %s' % (i.mnemonic, i.op_str) for i in post[:3]],
                        })
                    break
            except Exception as e:
                continue
        out[str(ident)] = {'sites': ids_total.get(ident, 0), 'plugins': len(plugins),
                           'ret_use': dict(usecnt), 'samples': samples}
    js = {'top_n': top, 'identified_sites_total': total_sites,
          'top30_cover': cov, 'top30_cover_pct': round(100.0 * cov / total_sites, 1),
          'ids': out}
    json.dump(js, open(os.path.join(HERE, 'hs_ids.json'), 'w'), indent=1)
    print('[hs_ids] top%d cover %d/%d (%.1f%%) -> hs_ids.json' % (top, cov, total_sites, js['top30_cover_pct']))
    for ident in top_ids:
        e = out[str(ident)]
        print('  ID %3d: sites %3d  ret_use %s' % (ident, e['sites'], e['ret_use']))


if __name__ == '__main__':
    main()
