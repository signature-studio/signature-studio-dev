#!/usr/bin/env python3
"""PY-275 (#3944) 受入 2 後半: 格納配列 [map+8] を直接読み得る関数の候補列挙 (解析補助・上限ではない)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py275_map_readers.py

候補の条件 (関数単位): ① `[reg+0x40]` (map の位置) を読む ② 同関数内に配列要素読み
`[base+idx*8+8]` がある ③ 同関数内に `call [reg+8]` (slot 1) がある。
0x102bb20 を呼ぶ関数 (キー取り出し) は ①③ を満たしても別経路として別計上する。
"""
import bisect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe_callgraph as pc  # noqa: E402

MAP_GET = 0x102BB20
MAP_FIND = 0x102B610
MAP_STORE = 0x102B750
MAP_OFF = re.compile(r"qword ptr \[(r\w+) \+ 0x40\]")
ARR = re.compile(r"qword ptr \[(r\w+) \+ (r\w+)\*8 \+ (?:0x)?8\]")
SLOT1 = re.compile(r"^qword ptr \[(r\w+) \+ (?:0x)?8\]$")
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

    by_fn = {}
    for a, m, o in insns:
        f = fstart(a)
        if f is None:
            continue
        by_fn.setdefault(f, []).append((a, m, o))

    cand = []
    for f, body in by_fn.items():
        has_map = any(m == "mov" and MAP_OFF.search(o) for _, m, o in body)
        has_arr = any(m == "mov" and ARR.search(o) for _, m, o in body)
        has_slot1 = any(m == "call" and SLOT1.match(o) for _, m, o in body)
        if has_map and has_arr and has_slot1:
            cand.append(f)

    callers_get = sorted({fstart(a) for a, m, o in insns if m == "call" and o == hex(MAP_GET)})
    callers_find = sorted({fstart(a) for a, m, o in insns if m == "call" and o == hex(MAP_FIND)})
    callers_store = sorted({fstart(a) for a, m, o in insns if m == "call" and o == hex(MAP_STORE)})

    check("M1 0x102bb20 の呼出し元は 27 関数 (REPORT §2 と一致)",
          len(callers_get) == 27, f"{len(callers_get)} 関数")
    check("M2 0x102b750 (格納) の呼出し元は 1 関数 (0x102bb80)",
          callers_store == [0x102BB80], str([hex(x) for x in callers_store if x]))
    print(f"INFO 候補 (map 位置 + 配列読み + slot1 呼出しの同居): {len(cand)} 関数")
    for f in cand:
        tag = []
        if f in callers_get:
            tag.append("キー取り出しあり")
        if f in callers_find:
            tag.append("find 呼出しあり")
        print(f"  {hex(f)} {' / '.join(tag) or '直接読みのみ'}")
    print("summary: " + ("ALL PASS" if not FAILS else f"FAIL {FAILS}"))
    sys.exit(0 if not FAILS else 1)


if __name__ == "__main__":
    main()
