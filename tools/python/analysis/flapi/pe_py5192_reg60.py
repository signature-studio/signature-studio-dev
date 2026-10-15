#!/usr/bin/env python3
"""FLEngine PE の間接 call `call qword ptr [reg+0x60]` (vt+0x60 = 0x1262970) の箇所 (517 件) を、所属関数・レジスタ別に列挙する (#5192 / #4432 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py5192_reg60.py [list]

- 所属関数: pe_callgraph.function_starts (int3 パディング直後の命令を関数先頭とみなす)。
- 既定 (引数なし): 件数・関数数・レジスタ別件数・箇所数の多い関数 10 件を出す。
- list: 全箇所を `箇所 レジスタ 所属関数` の形で出す。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import bisect
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe_callgraph as pc  # noqa: E402

PAT = re.compile(r"^qword ptr \[(\w+) \+ 0x60\]$")


def main():
    insns = pc.load()
    starts = pc.function_starts(insns)

    def func_of(va):
        i = bisect.bisect_right(starts, va) - 1
        return starts[i] if i >= 0 else None

    sites = []
    for a, m, o in insns:
        if m != "call":
            continue
        mm = PAT.match(o)
        if mm:
            sites.append((a, mm.group(1), func_of(a)))
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        for a, r, f in sites:
            print(f"{hex(a)} {r} {hex(f) if f is not None else None}")
        return
    by_func = collections.Counter(f for _, _, f in sites)
    by_reg = collections.Counter(r for _, r, _ in sites)
    print(f"sites {len(sites)} functions {len(by_func)}")
    print("regs " + ", ".join(f"{k} {v}" for k, v in by_reg.most_common()))
    for f, n in by_func.most_common(10):
        print(f"  func {hex(f) if f is not None else None}: {n}")


if __name__ == "__main__":
    main()
