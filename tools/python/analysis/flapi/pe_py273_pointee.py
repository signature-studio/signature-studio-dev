#!/usr/bin/env python3
"""PY-273 2 段目 (#5407): 大域 3 種が指す .bss の実アドレスを、.text の RIP 相対参照で数える。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py273_pointee.py

各大域の初期値 (.bss の実アドレス) について、.text 内の RIP 相対参照 (読込み・書込み別) と
即値・lea での直接参照を数える。.bss 全体の RIP 相対書込み件数も出す。終了 0 = 完了。
"""
import os
import re
import sys

import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph as cg  # noqa: E402
import pe_py203_edx_sites as E  # noqa: E402
import pe_py273_base as B  # noqa: E402

POINTEES = {0x193FA10: "G1", 0x16BAFC8: "G2", 0x16BD450: "G3"}


def main():
    B.setup()
    pe = pefile.PE(data=open(cg.PE, "rb").read(), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    bss = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".bss")
    lo, hi = base + bss.VirtualAddress, base + bss.VirtualAddress + bss.Misc_VirtualSize
    txt = {a: f"{m} {o}".strip() for a, m, o in E.INS}
    rip_re = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
    ptr = {t: {"read": [], "write": [], "imm": [], "lea": []} for t in POINTEES}
    bss_rip_write = 0
    for a, m, o in E.INS:
        mm = rip_re.search(txt[a])
        t = None
        if mm:
            nxt = E.INS[E.ADDR_IDX[a] + 1][0]
            d = int(mm.group(2), 16) * (1 if mm.group(1) == "+" else -1)
            t = nxt + d
            if lo <= t < hi and m.startswith("mov") and E.split_ops(o)[0].find("[rip") >= 0:
                bss_rip_write += 1
        for g in POINTEES:
            if t == g:
                kind = "write" if (m.startswith("mov") and E.split_ops(o)[0].find("[rip") >= 0) else "read"
                ptr[g][kind].append(a)
            elif "[rip" not in o and f"0x{g:x}" in o.lower():
                ptr[g]["lea" if m == "lea" else "imm"].append(a)
    print(f"bss\t{hex(lo)}-{hex(hi)}\trip_writes_total={bss_rip_write}")
    for g, name in POINTEES.items():
        r = ptr[g]
        print(f"{name}\t0x{g:x}\tread={len(r['read'])}\twrite={len(r['write'])}\timm={len(r['imm'])}\tlea={len(r['lea'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
