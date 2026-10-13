#!/usr/bin/env python3
"""NC2 の識別力を示す合成入力 (#879)。 実データは即値辺 0 件のため、即値辺を 2 件持つ小さな関数列で同じ検査を行う。

  nc2_imm_synth.py [--drop-imm-bfs]
    既定 (対照)            : BFS の辺に命令内即値を含める → U2 PASS (rc 0)
    --drop-imm-bfs (NC2 変異): BFS の辺から命令内即値を外す (U2 の検証側は残す) → U2 FAIL (rc 1)

合成入力 (base = 0x140000000、VA = base + RVA):
  E   0x1200 (total2): ret
  R   0x1000 (根 = RVA32 表から載る outside 関数): mov eax, 0x1100 (imm_rva → F) / mov rcx, 0x140001300 (imm_va → G) / ret
  F   0x1100 (outside・参照は R の即値のみ): ret
  G   0x1300 (outside・参照は R の即値のみ): ret
定義は closure_unreached.py と同じ (根 = (a) ∪ (b_live)、辺 = call/jmp ∪ lea ∪ 即値、U2 = 固定点の漏れ・根の漏れ)。
即値の検出は closure_unreached.imm_capstone (実物) を使う。 BFS と U2 の式だけは本ファイルに複製している。
"""
import argparse, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from capstone import Cs, CS_ARCH_X86, CS_MODE_64  # noqa: E402
import closure_unreached as CU  # noqa: E402

BASE = 0x140000000
CODE = {
    0x1200: b'\xc3',
    0x1000: b'\xb8\x00\x11\x00\x00' + b'\x48\xb9\x00\x13\x00\x40\x01\x00\x00\x00' + b'\xc3',
    0x1100: b'\xc3',
    0x1300: b'\xc3',
}


class FakeX:
    def __init__(self):
        self.base = BASE
        self.md = Cs(CS_ARCH_X86, CS_MODE_64)
        self.md.detail = True
        self.nonfw = set(CODE)

    def body(self, f):
        return CODE[f]

    def edges(self, f):
        return set(), set()


def bfs(roots, edge, nonfw):
    seen, q = set(), list(roots)
    while q:
        f = q.pop()
        if f in seen or f not in nonfw:
            continue
        seen.add(f)
        q.extend(edge(f))
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--drop-imm-bfs', action='store_true')
    a = ap.parse_args()
    x = FakeX()
    total2 = {0x1200}
    A = {0x1000}
    IMM = {f: CU.imm_capstone(x, f, x.nonfw) for f in x.nonfw}
    n_va = sum(len(v[0]) for v in IMM.values())
    n_rva = sum(len(v[1]) for v in IMM.values())
    if n_va == 0 or n_rva == 0:
        print('FAIL synth: 即値辺が足りない (va %d / rva %d)' % (n_va, n_rva), file=sys.stderr)
        sys.exit(1)
    B_live = {t for f in total2 for t in (IMM[f][0] | IMM[f][1])} & x.nonfw
    roots = A | B_live

    def edge_full(f):
        i = IMM.get(f, (set(), set()))
        e = x.edges(f)
        return (e[0] | e[1] | i[0] | i[1]) & x.nonfw

    def edge_bfs(f):
        return edge_full(f) if not a.drop_imm_bfs else (x.edges(f)[0] | x.edges(f)[1]) & x.nonfw

    total3 = bfs(sorted(total2 | roots), edge_bfs, x.nonfw)
    miss = sum(1 for f in total3 for t in edge_full(f) if t not in total3)
    root_miss = len(roots - total3)
    ok = miss == 0 and root_miss == 0
    print('nc2 synth: 即値辺 va %d / rva %d、total3 = %s、%s' % (
        n_va, n_rva, ','.join('0x%x' % f for f in sorted(total3)), '--drop-imm-bfs' if a.drop_imm_bfs else '対照'))
    print('%s U2 (漏れ %d・根の漏れ %d)' % ('PASS' if ok else 'FAIL', miss, root_miss), file=sys.stdout if ok else sys.stderr)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
