#!/usr/bin/env python3
"""#529 (PLG-F3-5): waiver 関数 W から、閉包外 (framework frontier) を含む PE 全体の直接 call/jmp (rel32) で
trap 命令 (div/idiv/int/ud2) または例外 API (IAT の RaiseException 系) に到達するかを調べる。

  raise_reach.py は閉包内の直接 call だけを辿る (下界)。本スクリプトは閉包外の関数も .pdata の範囲で辿る。
  - 関数範囲は .pdata (非チェイン) の [begin, end)。範囲の無い VA への直接 call は「未解決 (unresolved)」として数える。
  - 間接 call (`call [reg+disp]`・`call reg`・`call [rip+slot]` で IAT 以外) は辺にしない。件数のみ出す。
  - 到達判定は BFS の全探索 (上限 --max-funcs まで)。上限に達したら結果は「不完全」と明記する。

出力: work/f2/raise_reach_frontier_<block>.json と標準出力。
使い方: python3 tools/plugins/f2/raise_reach_frontier.py <block> [--max-funcs N]
"""
import json, os, sys, struct, collections, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

W = os.path.join(HERE, '..', 'work')
TRAP = ('div', 'idiv', 'int', 'int3', 'ud2', 'into')
RAISE_NAMES = ('RaiseException', 'RtlRaiseException', 'CxxThrowException', 'abort', 'exit', 'ExitProcess',
               'TerminateProcess', 'RaiseFloatException')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('block', type=int)
    ap.add_argument('--max-funcs', type=int, default=20000)
    ap.add_argument('--roots', choices=('waived', 'closure'), default='waived')
    a = ap.parse_args()
    block = a.block
    pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % block), fast_load=True)
    pe.parse_data_directories()
    base = pe.OPTIONAL_HEADER.ImageBase
    iat = {}
    for d in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        for i in d.imports:
            if i.address:
                iat[i.address] = (d.dll.decode(errors='replace'), (i.name or b'?').decode(errors='replace'))
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    funcs = {}
    for i in range(len(pd) // 12):
        b, e, u = struct.unpack_from('<III', pd, 12 * i)
        if b and not (u & 1):
            funcs[base + b] = base + e
    starts = sorted(funcs)
    import bisect

    def func_of(va):
        k = bisect.bisect_right(starts, va) - 1
        if k >= 0 and starts[k] <= va < funcs[starts[k]]:
            return starts[k]
        return None

    def thunk_import(t):
        # .pdata の無い `jmp [rip+slot]` (IAT thunk) を import 名に解決する。IAT 以外や jmp 以外は None。
        b = pe.get_data(t - base, 6)
        if b[:2] != b'\xff\x25':
            return None
        slot = t + 6 + struct.unpack('<i', b[2:6])[0]
        return iat.get(slot)

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    info = {}   # func -> {'traps': [...], 'raise_api': [...], 'calls': set(), 'unresolved': set(), 'indirect': n}
    wv = json.load(open(os.path.join(HERE, 'icall_gate_waivers.json')))
    roots = sorted({int(w['function'], 16) for w in wv if int(w['block']) == block})
    if a.roots == 'closure':
        roots = sorted(int(r.split('-')[0], 16) for r in
                       open(os.path.join(W, 'closure', 'block%05d.ranges.txt' % block)).read().replace(',', '\n').split() if r)
    seen = set(roots)
    queue = list(roots)
    truncated = False
    while queue:
        f = queue.pop()
        if len(info) >= a.max_funcs:
            truncated = True
            break
        end = funcs.get(f)
        rec = {'traps': [], 'raise_api': [], 'calls': set(), 'unresolved': set(), 'indirect': 0, 'indirect_sites': []}
        if end is None:
            rec['unresolved'].add(f)
            info[f] = rec
            continue
        data = pe.get_data(f - base, end - f)
        for ins in md.disasm(data, f):
            if ins.mnemonic in TRAP:
                rec['traps'].append([hex(ins.address), ins.mnemonic])
            if ins.mnemonic in ('call', 'jmp') and ins.operands:
                o = ins.operands[0]
                if o.type == X86_OP_IMM:
                    t = o.imm
                    if func_of(t) is None:
                        th = thunk_import(t)
                        if th is not None:
                            if any(k in th[1] for k in RAISE_NAMES):
                                rec['raise_api'].append([hex(ins.address), th[0], th[1]])
                        else:
                            rec['unresolved'].add(t)
                    elif t != f:
                        rec['calls'].add(t)
                elif o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
                    tgt = ins.address + ins.size + o.mem.disp
                    if tgt in iat:
                        dll, name = iat[tgt]
                        if any(k in name for k in RAISE_NAMES):
                            rec['raise_api'].append([hex(ins.address), dll, name])
                    else:
                        rec['indirect'] += 1
                        rec['indirect_sites'].append([hex(ins.address), ins.op_str])
                else:
                    rec['indirect'] += 1
                    rec['indirect_sites'].append([hex(ins.address), ins.op_str])
        info[f] = rec
        for c in rec['calls']:
            g = func_of(c)
            if g is not None and g not in seen:
                seen.add(g)
                queue.append(g)
    hits = {hex(f): r for f, r in info.items() if r['traps'] or r['raise_api']}
    unresolved = sorted({hex(x) for r in info.values() for x in r['unresolved'] if isinstance(x, int)})
    res = {'block': block, 'roots': [hex(r) for r in roots], 'visited_funcs': len(info), 'truncated': truncated,
           'indirect_calls_total': sum(r['indirect'] for r in info.values()),
           'indirect_sites': {hex(f): r['indirect_sites'] for f, r in info.items() if r['indirect_sites']},
           'unresolved_direct_targets': unresolved,
           'trap_or_raise_functions': {k: {'traps': v['traps'], 'raise_api': v['raise_api']} for k, v in hits.items()}}
    os.makedirs(os.path.join(W, 'f2'), exist_ok=True)
    json.dump(res, open(os.path.join(W, 'f2', 'raise_reach_frontier_%d.json' % block), 'w'), ensure_ascii=False, indent=1)
    print('block %d: roots=%d visited=%d truncated=%s indirect=%d unresolved_direct=%d trap_or_raise_fn=%d' % (
        block, len(roots), len(info), truncated, res['indirect_calls_total'], len(unresolved), len(hits)))
    for k, v in list(hits.items())[:20]:
        print(' ', k, 'traps=%d raise_api=%d' % (len(v['traps']), len(v['raise_api'])))


if __name__ == '__main__':
    main()
