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
# 第 1 オペランド (Intel 記法の宛先) が RIP 相対でも、メモリへ書かない命令。
# 比較・分岐・呼出し・読込み専用の x87 演算・単一オペランドの乗除算 (idiv 等は読込み) など。
NOT_WRITE = {
    "cmp", "test", "call", "push", "bt", "lea", "nop", "prefetchnta",
    "ucomiss", "ucomisd", "comiss", "comisd", "lar", "lsl", "verr", "verw",
    "fcom", "fcomp", "ficom", "ficomp", "fld", "fild", "fldcw", "fldenv", "frstor", "ldmxcsr", "lldt", "ltr",
    "fadd", "fsub", "fsubr", "fmul", "fdiv", "fdivr", "fiadd", "fisub", "fisubr", "fimul", "fidiv", "fidivr",
    "mul", "imul", "div", "idiv",
}


def writes_dest(m, o):
    m = m.replace("lock ", "")
    return m not in NOT_WRITE and not m.startswith("j") and E.split_ops(o)[0].find("[rip") >= 0


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
            if lo <= t < hi and writes_dest(m, o):
                bss_rip_write += 1
        for g in POINTEES:
            if t == g:
                kind = "write" if writes_dest(m, o) else "read"
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
