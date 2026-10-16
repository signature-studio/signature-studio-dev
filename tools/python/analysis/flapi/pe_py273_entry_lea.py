#!/usr/bin/env python3
"""PY-273 3 段目 (#5407): rbx ENTRY 4 件の関数ポインタ取得 (lea) と、直後の直接呼出し先を数える。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py273_entry_lea.py

各 ENTRY (0xd5e6c0・0xd615a0・0xd626c0・0x1185840) について、
(1) .text 内で ENTRY の番地を RIP 相対 `lea` で取る命令 (件数と VA)、
(2) その lea から 16 命令以内の最初の直接 `call` の宛先、
(3) .data・.rdata・.text 内で ENTRY の 8 バイト・4 バイト絶対値として現れる件数、
を出す。終了 0 = 完了。
"""
import os
import re
import struct
import sys

import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph as cg  # noqa: E402
import pe_py203_edx_sites as E  # noqa: E402
import pe_py273_base as B  # noqa: E402

ENTRIES = [0xD5E6C0, 0xD615A0, 0xD626C0, 0x1185840]
WINDOW = 16


def main():
    B.setup()
    raw = open(cg.PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    rip_re = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
    idx_of = E.ADDR_IDX
    for entry in ENTRIES:
        leas = []
        for i, (a, m, o) in enumerate(E.INS):
            if m != "lea" or "[rip" not in o:
                continue
            mm = rip_re.search(f"{m} {o}")
            if mm is None:
                continue
            nxt = E.INS[idx_of[a] + 1][0]
            t = nxt + int(mm.group(2), 16) * (1 if mm.group(1) == "+" else -1)
            if t == entry:
                call = None
                for j in range(i + 1, min(i + 1 + WINDOW, len(E.INS))):
                    ca, cm, co = E.INS[j]
                    if cm == "call" and co.startswith("0x"):
                        call = co
                        break
                leas.append((a, call))
        absf = {"dq": 0, "dd": 0}
        q, d = struct.pack("<Q", entry), struct.pack("<I", entry)
        for name, pat in [("dq", q), ("dd", d)]:
            absf[name] = raw.count(pat)
        print(f"ENTRY\t0x{entry:x}\trip_lea={len(leas)}\tabs_qword={absf['dq']}\tabs_dword={absf['dd']}")
        for a, call in leas:
            print(f"  lea\t0x{a:x}\tnext_direct_call={call}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
