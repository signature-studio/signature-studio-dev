#!/usr/bin/env python3
"""PY-321 (#4347) 第 3 run: TMessage 組立て 0x60c220 の [rbx+0x80] (メソッドポインタ Code) に 0x410090 が入る経路の否定的確認。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py321b_rbx80.py

確認すること:
  1. 0x60c220 は rbx = rcx (受信オブジェクト) で、[rbx+0x80] (Code) を呼ぶ (間接呼出し)。
  2. .text 内の 0x410090 の絶対 qword (8 バイト整列) は、RIP 相対オペランドで直接読まれない
     (= 関数ポインタ表を RIP 経由で参照する経路は無い)。
  3. 0x410090 の絶対 qword の表の 8 バイト整列エントリを disp32 で読む命令は無い。
終了 0 = 全 PASS。
"""
import os
import re
import struct
import sys
from collections import Counter

import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph as pc  # noqa: E402

TARGET = 0x410090
RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("PASS" if ok else "FAIL", name, detail)


def aligned_table_entries(raw, pe):
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    tva = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    hits = []
    off = raw.find(struct.pack("<Q", TARGET))
    while off != -1:
        if text.PointerToRawData <= off < text.PointerToRawData + text.SizeOfRawData:
            va = tva + (off - text.PointerToRawData)
            if (va - tva) % 8 == 0:
                hits.append(va)
        off = raw.find(struct.pack("<Q", TARGET), off + 1)
    return hits


def main():
    raw = open(pc.PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    rows = sorted(pc.load())
    by_va = {a: (m, o) for a, m, o in rows}

    check("0x60c220 で rbx = rcx (受信オブジェクト)", by_va.get(0x60C229) == ("mov", "rbx, rcx"),
          f"got={by_va.get(0x60C229)}")
    check("0x60c220 で [rbx+0x80] (Code) を間接呼出し", by_va.get(0x60C24F) == ("call", "qword ptr [rbx + 0x80]"),
          f"got={by_va.get(0x60C24F)}")

    tables = aligned_table_entries(raw, pe)
    check("0x410090 の絶対 qword (8 バイト整列) が .text 内に存在する", len(tables) > 0, f"件数={len(tables)}")

    rip_hits = Counter()
    for k, (a, m, o) in enumerate(rows):
        mm = RIP.search(o)
        if not mm:
            continue
        nxt = rows[k + 1][0] if k + 1 < len(rows) else a + 7
        d = int(mm.group(2), 16) * (1 if mm.group(1) == "+" else -1)
        rip_hits[nxt + d] += 1
    direct = [t for t in tables if rip_hits.get(t)]
    check("表の 8 バイト整列エントリは RIP 相対で読まれない", not direct,
          f"読まれる表エントリ={[hex(x) for x in direct[:10]]}")

    print()
    print("PASS 件数", sum(RESULTS), "/", len(RESULTS))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
