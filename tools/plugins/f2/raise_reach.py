#!/usr/bin/env python3
"""#529: waiver 4 site の関数 (Delphi handler を持つ関数) が、閉包内の直接 call 経由で trap 命令 (idiv 等) から到達するかを調べる。

  閉包 ranges = 関数単位 (.pdata)。各関数の直接 call/jmp (rel32) 先が閉包内の関数開始 VA なら辺を張る。
  - 逆方向に waiver 関数の呼出元を閉包全体で辿り、trap 命令を含む関数が呼出元に含まれるかを出す。
  - 間接 call (vtable / 関数ポインタ) と閉包外 (frontier) への call は辺にならないので、結果は下界。
  出力: work/f2/raise_reach_<block>.json と標準出力。

使い方: python3 tools/plugins/f2/raise_reach.py <block>
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM

W = os.path.join(HERE, '..', 'work')
TRAP = ('div', 'idiv')


def main(block):
    pe_path = os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % block)
    wv = json.load(open(os.path.join(HERE, 'icall_gate_waivers.json')))
    waived = {int(w['function'], 16) for w in wv if int(w['block']) == block}
    ranges = [tuple(int(x, 16) for x in r.split('-')) for r in
              open(os.path.join(W, 'closure', 'block%05d.ranges.txt' % block)).read().replace(',', '\n').split() if r]
    starts = {lo for lo, _ in ranges}
    pe = pefile.PE(pe_path, fast_load=True)
    pe.parse_data_directories()
    base = pe.OPTIONAL_HEADER.ImageBase
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    callees = {}   # caller -> set(callee)
    trap_in = {}   # func -> [insn]
    for lo, hi in ranges:
        for i in md.disasm(pe.get_data(lo - base, hi - lo + 1), lo):
            if i.mnemonic in TRAP:
                trap_in.setdefault(lo, []).append([hex(i.address), i.mnemonic, i.op_str])
            if i.mnemonic in ('call', 'jmp') and i.operands and i.operands[0].type == X86_OP_IMM:
                t = i.operands[0].imm
                if t in starts and t != lo:
                    callees.setdefault(lo, set()).add(t)
    # 例外は trap 関数 F で起きる。F の unwind で pad が走るのは、waiver 関数 W が呼出しスタック上 (W から F へ到達) にあるとき。
    # よって W から閉包内の直接 call で到達できる関数を求め、trap 関数との積を取る。
    seen, stack = set(), list(waived)
    while stack:
        f = stack.pop()
        for c in callees.get(f, ()):
            if c not in seen:
                seen.add(c)
                stack.append(c)
    trap_callers = sorted(f for f in trap_in if f in seen)
    res = {'block': block, 'waived_functions': sorted(hex(f) for f in waived),
           'closure_funcs': len(starts), 'trap_functions': {hex(f): trap_in[f] for f in sorted(trap_in)},
           'waived_transitive_callees': sorted(hex(f) for f in seen),
           'trap_functions_reachable_from_waived': [hex(f) for f in trap_callers]}
    os.makedirs(os.path.join(W, 'f2'), exist_ok=True)
    json.dump(res, open(os.path.join(W, 'f2', 'raise_reach_%d.json' % block), 'w'), ensure_ascii=False, indent=1)
    print('block %d: closure_funcs=%d waived_fn=%d trap_fn=%d transitive_callers=%d trap_reachable_from_waived=%s' % (
        block, len(starts), len(waived), len(trap_in), len(seen), res['trap_functions_reachable_from_waived']))


if __name__ == '__main__':
    main(int(sys.argv[1]))
