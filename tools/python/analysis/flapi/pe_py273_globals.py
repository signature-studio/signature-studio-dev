#!/usr/bin/env python3
"""PY-273 (#3927): 0x128f9e0 の edx 基底 (MEM 38) の上流で出る大域 G と、rbp スロットの直前 store を照合する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py273_globals.py

大域 G (RIP 相対で読まれるポインタ) の .data 初期値、RIP 相対の書込み件数、
rbp スロット基底の直前 store を出す。終了 0 = 完了。
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

GLOBALS = [0x15E26A0, 0x15E2218, 0x15E22D8]
SLOT_SITES = [0xF69A52, 0x1289443, 0x128E904, 0x12A1B09, 0x12A1C21, 0x12A4A09]


def data_init(pe, raw, va):
    base = pe.OPTIONAL_HEADER.ImageBase
    rva = va - base
    sec = next((x for x in pe.sections if x.VirtualAddress <= rva < x.VirtualAddress + x.Misc_VirtualSize), None)
    if sec is None:
        return None, None
    name = sec.Name.rstrip(b"\0").decode()
    off = sec.PointerToRawData + (rva - sec.VirtualAddress)
    if off + 8 > len(raw):
        return name, "(raw 外)"
    return name, hex(int.from_bytes(raw[off:off + 8], "little"))


def main():
    B.setup()
    raw = open(cg.PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    txt = {a: f"{m} {o}".strip() for a, m, o in E.INS}
    ok = True
    for g in GLOBALS:
        name, init = data_init(pe, raw, g)
        writes = []
        for a, m, o in E.INS:
            t = None
            mm = re.search(r"\[rip ([+-]) (0x[0-9a-f]+)\]", txt[a])
            if mm:
                nxt = E.INS[E.ADDR_IDX[a] + 1][0]
                d = int(mm.group(2), 16) * (1 if mm.group(1) == "+" else -1)
                t = nxt + d
            if t == g and m.startswith("mov") and E.split_ops(o)[0].find("[rip") >= 0:
                writes.append(hex(a))
        imm = [hex(a) for a, m, o in E.INS if "[rip" not in o and f"0x{g:x}" in o.lower()]
        lea = [hex(a) for a, m, o in E.INS if m == "lea" and f"0x{g:x}" in o.lower()]
        print(f"G 0x{g:x}\tsection={name}\tinit={init}\trip_writes={len(writes)}\timm_hits={len(imm)}\tlea={len(lea)}")
        ok = ok and name == ".data" and not writes and not imm and not lea
    for c in SLOT_SITES:
        fn = E.func_of(c)
        s, i = E.ADDR_IDX[fn], E.ADDR_IDX[c]
        lw = E.last_writer(s, i, "rdx")
        _, m, o = E.INS[lw[0]]
        mm, oo, _ = E.norm(m, o)
        src = E.split_ops(oo)[1]
        slot = E.norm_mem(src)
        j = E.last_store(s, lw[0], slot)
        print(f"SLOT call=0x{c:x}\tsetter=0x{E.INS[lw[0]][0]:x}\tfn=0x{fn:x}\t{slot}\tlast_store={'0x%x %s' % (E.INS[j][0], txt[E.INS[j][0]]) if j is not None else '-'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
