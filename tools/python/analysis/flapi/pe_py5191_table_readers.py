#!/usr/bin/env python3
"""FLEngine PE の .text で、関数ポインタ表 0xfe2c80〜0xfe2ea0・0xd14800・0xd147d0 を参照する命令を列挙する (#5191)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py5191_table_readers.py

pe_py322_probe.py の補完。判定は厳密一致:
- rip : [rip+disp] の有効アドレス (次命令 + disp) が標的範囲に入る。
- abs : 非 RIP のメモリ・オペランドの disp が標的範囲に入る (分岐命令は除く)。
- ind : 間接 call / jmp の箇所 (全件)。表の添字で引かれた先の候補。
所属関数は int3 直後の命令を先頭とみなして推定する。
"""
import bisect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe_callgraph as cg  # noqa: E402

RANGES = {"table": (0xFE2C80, 0xFE2EA0 + 8),
          "d14800": (0xD14800, 0xD14808),
          "d147d0": (0xD147D0, 0xD147D8),
          "ctrl": (0xD1AF20, 0xD1AF28)}
BRANCH = re.compile(r"^(j|loop|call|xbegin)")
HEX = re.compile(r"0x[0-9a-f]+")
RIP = re.compile(r"\[rip\s*([+-])\s*(0x[0-9a-f]+)\]")


def name_of(v):
    for k, (lo, hi) in RANGES.items():
        if lo <= v < hi:
            return k
    return None


def main():
    insns = cg.load()
    starts = cg.function_starts(insns, callee_starts=False)

    def func_of(va):
        i = bisect.bisect_right(starts, va) - 1
        return starts[i] if i >= 0 else None

    rows = []
    ind = []
    for idx, (a, m, o) in enumerate(insns):
        nxt = insns[idx + 1][0] if idx + 1 < len(insns) else a
        if "[rip" in o:
            for sign, d in RIP.findall(o):
                tgt = nxt + int(d, 16) * (-1 if sign == "-" else 1)
                n = name_of(tgt)
                if n:
                    rows.append((a, n, "rip", m, o, hex(tgt)))
        elif not BRANCH.match(m) and "[" in o:
            for tok in HEX.findall(o):
                n = name_of(int(tok, 16))
                if n:
                    rows.append((a, n, "abs", m, o, tok))
        if m in ("call", "jmp") and not o.startswith("0x"):
            ind.append((a, m, o))

    print("## 標的範囲への参照 (rip/abs・厳密一致)")
    for a, n, kind, m, o, tgt in sorted(rows):
        f = func_of(a)
        print(f"0x{a:x} {n:7s} {kind:4s} tgt={tgt} {m} {o} func={hex(f) if f is not None else None}")
    print(f"hits={len(rows)}")
    print("## 間接 call/jmp")
    for a, m, o in ind:
        f = func_of(a)
        print(f"0x{a:x} {m} {o} func={hex(f) if f is not None else None}")
    print(f"indirect={len(ind)}")


if __name__ == "__main__":
    main()
