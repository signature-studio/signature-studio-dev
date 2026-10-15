#!/usr/bin/env python3
"""PY-275 (#4995): map の格納配列 (qword ptr [base + idx*8 + 8]) を直接読む関数と、
同じ関数内の slot 1 呼出し (call qword ptr [reg+8]) の対応を確認する (解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py275_map_slot1.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'

出力は候補の列挙 (同一関数内の共存) のみ。受け手の同インスタンス性は本 probe では確定しない
(REPORT_PY275.md §5 の手作業確認)。
"""
import bisect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe_callgraph as pc  # noqa: E402

ENTRY_LOAD = re.compile(r"^(r\w+), qword ptr \[(r\w+) \+ (r\w+)\*8 \+ 8\]$")
SLOT1 = re.compile(r"^qword ptr \[(r\w+) \+ (?:0x8|8)\]$")
NAMED = [0xC3B930, 0xC3BC00, 0x1046A30]
NO_LOAD = 0x1304060
FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" :: {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def main():
    insns = pc.load()
    starts = pc.function_starts(insns)

    def fstart(a):
        i = bisect.bisect_right(starts, a) - 1
        return starts[i] if i >= 0 else None

    loads = [a for a, m, o in insns if m == "mov" and ENTRY_LOAD.match(o)]
    slot1 = [a for a, m, o in insns if m == "call" and SLOT1.match(o)]
    check("Q1 格納配列の値読出しは 360 件 (前段 PY-269 と同じ数え方)", len(loads) == 360, f"{len(loads)} 件")
    check("Q2 call [reg+8] は 1638 件", len(slot1) == 1638, f"{len(slot1)} 件")

    load_fn = {fstart(a) for a in loads}
    both = sorted(f for f in load_fn if any(fstart(c) == f for c in slot1))
    print("同一関数に格納配列読出しと slot 1 呼出しが共存する関数: " + ", ".join(hex(f) for f in both))
    check("Q3 issue が挙げた 4 関数のうち 0xc3b930・0xc3bc00・0x1046a30 は共存側に入る",
          all(f in both for f in NAMED), f"{len(both)} 関数")
    check("Q4 0x1304060 は格納配列の読出しを持たない (共存側に入らない)",
          fstart(NO_LOAD) not in load_fn and fstart(NO_LOAD) not in both,
          f"関数 {hex(fstart(NO_LOAD))}")
    check("Q5 共存する関数の候補は 7 件 (0x69b640・0x8c9d20・0xb70190・0xd328f0 を含む)",
          len(both) == 7 and 0xD328F0 in both, ", ".join(hex(f) for f in both))

    print(f"\nsummary: {'ALL PASS' if not FAILS else 'FAIL: ' + ', '.join(FAILS)}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
