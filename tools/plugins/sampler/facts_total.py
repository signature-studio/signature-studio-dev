#!/usr/bin/env python3
"""閉包の拡張段 (base → #537 total → #627 total2) ごとに host 呼出面 (Dispatcher ID / vtable slot) と SIMD kernel 依存を再計測する (#627)。 closure_facts.py (base 限定) の total 版。

  facts_total.py [--out PATH] [--facts PATH]   前提: closure_lea.py 実行済み (work/sampler/lea/) + sampler_e2e.sh の facts.json (closure_facts.py の出力 = base の正本) + `source sampler/env.sh`

測定: host_calls.scan (taint: Host=[this+0xbc] → vt=[Host] → call [vt+disp]) と p0c/kernel_matrix.scan_dll を DLL ごとに 1 回走らせ、結果を関数開始 VA で段ごとに分類する (closure_facts.py と同じ走査・同じ分類)。
別算法: ids_crosscheck.py と同じ線形走査 (`mov r8d, imm` の後 8 命令以内の `call [reg]` disp 0) を total2 の全関数に掛け、taint 版の即値 ID を取りこぼしていないかを見る。
検査 (全て満たさなければ exit 1):
  F1 base 段の集計が closure_facts.py の facts.json (host ids / slot_disps / kernel callsites_in_closure / kernels_in_closure) と一致 (分類の再現)
  F2 段の単調性: base ⊆ total ⊆ total2 の関数集合で、host site・kernel site が減らない
  F3 別算法 (線形走査) が total2 の taint 版 即値 ID を全て再現 (件数 ≥)
  F4 検出力: scan 結果が空でないこと (host call site 計・kernel callsite 計が各段で 0 のままの plugin が全 7 本というような無効計測を落とす。 7 本中 1 本以上で total2 の host site > 0)
出力: work/sampler/facts_total.json と stdout の表
"""
import argparse, collections, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(P, 'inventory'))
sys.path.insert(0, os.path.join(P, 'p0c'))
sys.path.insert(0, os.path.join(P, '..', 'shared'))
import targets  # noqa: E402
from paths import FL_WIN64_DIR  # noqa: E402
import pefile  # noqa: E402
import host_calls  # noqa: E402
import kernel_matrix as KM  # noqa: E402
from capstone import Cs, CS_ARCH_X86, CS_MODE_64  # noqa: E402
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG  # noqa: E402

WORK = os.path.join(P, 'work')
STAGES = ('base', 'total', 'total2')


def starts(txt):
    return {int(r.split('-')[0], 16) for r in open(txt).read().strip().split(',') if r}


def host_by_stage(res, base, sets):
    out = {}
    for st, S in sets.items():
        ids, slots = collections.Counter(), collections.Counter()
        for rva, disp, ident in res:
            if base + rva not in S:
                continue
            slots[disp] += 1
            if disp == 0:
                ids['dyn' if ident is None else ident] += 1
        out[st] = {'ids': {str(k): v for k, v in sorted(ids.items(), key=lambda x: -x[1])},
                   'slot_disps': {hex(k): v for k, v in sorted(slots.items())},
                   'sites': sum(slots.values()), 'disp0_sites': sum(ids.values()),
                   'imm_id_sites': sum(v for k, v in ids.items() if k != 'dyn'), 'dyn_id_sites': ids.get('dyn', 0)}
    return out


def kernel_by_stage(blk, sets, frontier):
    _, r = KM.scan_dll(blk)
    if not r.get('init_found'):
        return {'init_found': False}
    inv = {v: k for k, v in r.get('kernel_va_map', {}).items() if v}
    cs = r.get('callsites', [])
    out = {'init_found': True, 'callsites_dll_unique_scan': len(cs)}
    for st, S in sets.items():
        inn = [s for s in cs if int(s['func'], 16) in S]
        infr = [s for s in cs if int(s['func'], 16) in frontier[st]]
        out[st] = {'callsites': len(inn), 'callsites_in_frontier': len(infr),
                   'kernels': dict(sorted(collections.Counter(inv.get(s['kernel'], s['kernel']) for s in inn).items())),
                   'kernels_frontier': dict(sorted(collections.Counter(inv.get(s['kernel'], s['kernel']) for s in infr).items())),
                   'ret_used': sum(1 for s in inn if s.get('ret_used'))}
    return out


def linear_ids(pe, ranges_txt):
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    base = pe.OPTIONAL_HEADER.ImageBase
    found = collections.Counter()
    for r in open(ranges_txt).read().strip().split(','):
        a, b = (int(x, 16) for x in r.split('-'))
        code = pe.get_data(a - base, b - a + 1)
        r8, age = None, 99
        for ins in md.disasm(code, a):
            age += 1
            if ins.mnemonic == 'call':
                op = ins.operands[0]
                if op.type == X86_OP_MEM and op.mem.disp == 0 and op.mem.index == 0 and ins.reg_name(op.mem.base) not in ('rip', ''):
                    found['dyn' if (r8 is None or age > 8) else r8] += 1
                r8 = None
                continue
            if len(ins.operands) == 2 and ins.operands[0].type == X86_OP_REG and ins.reg_name(ins.operands[0].reg) == 'r8d':
                if ins.mnemonic == 'mov' and ins.operands[1].type == X86_OP_IMM:
                    r8, age = ins.operands[1].imm, 0
                elif ins.mnemonic == 'xor' and ins.operands[1].type == X86_OP_REG and ins.reg_name(ins.operands[1].reg) == 'r8d':
                    r8, age = 0, 0
                else:
                    r8 = None
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(WORK, 'sampler', 'facts_total.json'))
    ap.add_argument('--facts', default=os.path.join(WORK, 'sampler', 'facts.json'))
    ap.add_argument('--lea-dir', default=os.path.join(WORK, 'sampler', 'lea'))
    ap.add_argument('--only', default='', help='カンマ区切りの plugin 名だけ測る (ネガコン用。 既定は全 7 本)')
    a = ap.parse_args()
    F = json.load(open(a.facts))
    hs = json.load(open(os.path.join(P, 'framework', 'hostshim', 'hs_ids.json')))['ids']
    out, bad = {}, []
    sel = [t for t in targets.SHELLS if not a.only or t[0] in a.only.split(',')]
    for name, blk, _ in sel:
        fn = 'block%05d_PE.bin' % blk
        pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', fn), fast_load=True)
        base = pe.OPTIONAL_HEADER.ImageBase
        clo = json.load(open(os.path.join(WORK, 'closure', 'block%05d.json' % blk)))
        sets = {'base': starts_from_closure(clo),
                'total': starts(os.path.join(a.lea_dir, 'block%05d.total.ranges.txt' % blk)),
                'total2': starts(os.path.join(a.lea_dir, 'block%05d.ranges.txt' % blk))}
        fr = json.load(open(os.path.join(a.lea_dir, 'block%05d.frontier.json' % blk)))
        frontier = {'base': {int(x, 16) for x in clo['frontier']}, 'total': set(fr['total']), 'total2': set(fr['total2'])}
        _, res = host_calls.scan(fn)
        h = host_by_stage(res, base, sets)
        k = kernel_by_stage(blk, sets, frontier)
        lin = linear_ids(pe, os.path.join(a.lea_dir, 'block%05d.ranges.txt' % blk))
        f = F[name]
        f1 = (h['base']['ids'] == f['host']['ids'] and h['base']['slot_disps'] == f['host']['slot_disps'] and
              (not k.get('init_found') or (k['base']['callsites'] == f['kernel']['callsites_in_closure'] and k['base']['kernels'] == f['kernel']['kernels_in_closure'])))
        f2 = (sets['base'] <= sets['total'] <= sets['total2'] and
              all(h[x]['sites'] <= h[y]['sites'] for x, y in (('base', 'total'), ('total', 'total2'))) and
              (not k.get('init_found') or all(k[x]['callsites'] <= k[y]['callsites'] for x, y in (('base', 'total'), ('total', 'total2')))))
        miss = {i: v for i, v in h['total2']['ids'].items() if i != 'dyn' and lin.get(int(i), 0) < v}
        f3 = not miss
        extra = {str(i): v for i, v in sorted(lin.items(), key=lambda t: str(t[0])) if i != 'dyn' and str(i) not in h['total2']['ids']}
        for tag, ok in (('F1 base 段が closure_facts.py と一致', f1), ('F2 段の単調性', f2), ('F3 線形走査が taint 版 ID を再現 (取りこぼし %s)' % miss, f3)):
            if not ok:
                bad.append('%s: %s' % (name, tag))
        imm = {s: {i: v for i, v in h[s]['ids'].items() if i != 'dyn'} for s in STAGES}
        out[name] = {'block': blk, 'funcs': {s: len(sets[s]) for s in STAGES}, 'host': h, 'host_ids_not_in_hs_ids': {
            s: {i: v for i, v in imm[s].items() if i not in hs} for s in STAGES}, 'kernel': k,
            'linear_scan_ids_total2': {str(i): v for i, v in sorted(lin.items(), key=lambda t: str(t[0]))}, 'linear_only_ids_total2': extra,
            'checks': {'F1': f1, 'F2': f2, 'F3': f3}}
        print('done', name, file=sys.stderr)
    f4 = any(v['host']['total2']['sites'] > 0 for v in out.values())
    if not f4:
        bad.append('F4 total2 の host call site が全 plugin で 0 (計測が成立していない)')
    print('| プラグイン | host site base → total → total2 | 即値 ID の種類 base → total → total2 | 動的 ID site base → total → total2 | total2 の hs_ids.json に無い ID (site) | kernel site base → total → total2 | total2 の kernel 種 | total2 の frontier 内 kernel site |')
    print('|---|---|---|---|---|---|---|--:|')
    for name, _, _ in sel:
        o = out[name]
        h, k = o['host'], o['kernel']
        arrow = lambda g: ' → '.join(str(g(s)) for s in STAGES)
        ks = arrow(lambda s: k[s]['callsites']) if k.get('init_found') else 'init 無し'
        print('| %s | %s | %s | %s | %s | %s | %s | %s |' % (
            name, arrow(lambda s: h[s]['sites']), arrow(lambda s: len([i for i in h[s]['ids'] if i != 'dyn'])), arrow(lambda s: h[s]['dyn_id_sites']),
            ', '.join('%s (%d)' % kv for kv in o['host_ids_not_in_hs_ids']['total2'].items()) or '無し', ks,
            len(k['total2']['kernels']) if k.get('init_found') else '-', k['total2']['callsites_in_frontier'] if k.get('init_found') else '-'))
    json.dump(out, open(a.out, 'w'), indent=1, ensure_ascii=False)
    for b in bad:
        print('FAIL', b, file=sys.stderr)
    print('facts_total: %s' % ('FAIL %d' % len(bad) if bad else 'PASS 4 checks x %d plugins' % len(sel)))
    sys.exit(1 if bad else 0)


def starts_from_closure(clo):
    return {int(r.split('-')[0], 16) for r in clo['ranges']}


if __name__ == '__main__':
    main()
