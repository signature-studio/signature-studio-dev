#!/usr/bin/env python3
"""plugins.getColor (0xd80a40) の呼出し形を PE の逆アセンブルで確かめる (PY-5361 / #5490)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/plugins_getcolor_facts.py

確認する事実 (block00031_PE.bin):
- 0xd80b8d・0xd80c8c: obj.vtable[+8](obj, 0x21, flag, paramIndex) の呼出し (edx=0x21・r8=[rbp+0xa4]・r9=[rbp+0xa0])。
- 戻り値 eax は BGR→RGB 入替え (0xff00ff・0xff00ff00 のマスク) をしてから [rip+0x8636ce] の関数へ渡す。alpha は付与しない。
- 対象 obj は 0x1331340 の出力 [rbp+0x78] を vtable[+0x20] に通して得る (vtbl[+8] の型は未同定)。

vtbl[+8] の先と ID 0x21 の意味は未確定 (REPORT_PY5350.md §4 に未確認として残す)。
実行すると PASS/FAIL を出し、1 つでも FAIL なら非 0 で終わる。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
CALLS = (0xD80B8D, 0xD80C8C)


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData) for s in pe.sections]

    def v2o(va):
        rva = va - base
        for v, vs, p, rs in secs:
            if v <= rva < v + max(vs, rs):
                return p + (rva - v)
        return None

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def insns(va, n):
        fo = v2o(va)
        return [(i.address, f"{i.mnemonic} {i.op_str}".strip()) for _, i in zip(range(n), md.disasm(raw[fo:fo + n * 12], va))]

    body = insns(0xD80B40, 40) + insns(0xD80C60, 30)
    text = {a: s for a, s in body}
    results = []
    for va in CALLS:
        results.append((f"call qword ptr [rax + 8] at {va:#x}", text.get(va) == "call qword ptr [rax + 8]" if va in text else False))
        results.append((f"edx=0x21 before {va:#x}", any(s == "mov edx, 0x21" and a < va and a > va - 0x20 for a, s in body)))
    results.append(("mask 0xff00ff in result path", any(s == "and ecx, 0xff00ff" for _, s in body)))
    results.append(("mask 0xff00ff00 in result path", any(s == "and eax, 0xff00ff00" for _, s in body)))
    results.append(("0x1331340 obtains obj", any(s == "call 0x1331340" for _, s in body)))
    results.append(("vtable[+0x20] before vtbl[+8]", any(s == "call qword ptr [rax + 0x20]" for _, s in body)))

    ok = True
    for name, passed in results:
        print(("PASS" if passed else "FAIL"), name)
        ok = ok and passed
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
