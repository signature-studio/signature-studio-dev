#!/usr/bin/env python3
"""plugins.getColor (0xd80a40) の呼出し形を PE の逆アセンブルで確かめる (PY-5361 / #5490)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/plugins_getcolor_facts.py

確認する事実 (block00031_PE.bin):
- 0xd80b8d・0xd80c8c: obj.vtable[+8](obj, 0x21, flag, paramIndex) の呼出し (edx=0x21・r8=[rbp+0xa4]・r9=[rbp+0xa0])。
- 戻り値 eax は BGR→RGB 入替え (0xff00ff・0xff00ff00 のマスク) をしてから [rip+0x8636ce] の関数へ渡す。alpha は付与しない。
- 対象 obj は 0x1331340 の出力 [rbp+0x78] を vtable[+0x20] に通して得る (vtbl[+8] の型は未同定)。
- 0x1331340 は this+0x38 の参照先の +0x48 を out 引数へ代入し、代入ヘルパ 0x41a7b0 は新値に [rax+8] (AddRef)・旧値に [rax+0x10] (Release) を呼ぶ。
  this+0x38 の書込み元 (型) は未確認。

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

    body = insns(0xD80B3F, 41) + insns(0xD80C60, 30)
    text = {a: s for a, s in body}
    results = []
    for va in CALLS:
        results.append((f"call qword ptr [rax + 8] at {va:#x}", text.get(va) == "call qword ptr [rax + 8]" if va in text else False))
        results.append((f"edx=0x21 before {va:#x}", any(s == "mov edx, 0x21" and a < va and a > va - 0x20 for a, s in body)))
    results.append(("mask 0xff00ff in result path", any(s == "and ecx, 0xff00ff" for _, s in body)))
    results.append(("mask 0xff00ff00 in result path", any(s == "and eax, 0xff00ff00" for _, s in body)))
    results.append(("0x1331340 obtains obj", any(s == "call 0x1331340" for _, s in body)))
    results.append(("vtable[+0x20] before vtbl[+8]", any(s == "call qword ptr [rax + 0x20]" for _, s in body)))
    chain = insns(0x1331340, 14)
    results.append(("0x1331340 reads this+0x38", any(s == "mov rax, qword ptr [rcx + 0x38]" for _, s in chain)))
    results.append(("0x1331340 passes [this+0x38]+0x48 as new value", any(s == "lea rdx, [rax + 0x48]" for _, s in chain)))
    helper = insns(0x41A7B0, 25)
    fallback = insns(0x1331362, 5)
    results.append(("0x1331340 re-stores default when out is NULL", fallback[0][1] == "cmp qword ptr [rbx], 0" and fallback[3][1] == "mov rdx, qword ptr [rip + 0x63d9c6]"))
    results.append(("0x41a7b0 AddRef new value via [rax+8]", any(s == "call qword ptr [rax + 8]" for _, s in helper)))
    results.append(("0x41a7b0 Release old value via [rax+0x10]", any(s == "call qword ptr [rax + 0x10]" for _, s in helper)))

    full = [s for _, s in insns(0xD80A40, 200)]
    results.append(("getColor channel path gated by 0x132f780", "call 0x132f780" in full))
    results.append(("getColor channel obj from 0x1005730", "call 0x1005730" in full))
    results.append(("0x132f780 = cmp [obj+0x64], 0 (setge)", any(s == "cmp dword ptr [rcx + 0x64], 0" for _, s in insns(0x132F780, 2))))
    results.append(("slot path obj = [mixer + index*0x28f*8 + slot*8 + 0x134c]", "imul rcx, rcx, 0x28f" in full and "mov rsi, qword ptr [rax + rcx*8 + 0x134c]" in full))
    results.append(("0xd80b3f loads obj out pointer [rbp+0x90] as 64 bit", text.get(0xD80B3F) == "mov rcx, qword ptr [rbp + 0x90]"))
    arr = insns(0xFE8BB0, 16)
    results.append(("0xfe8bb0 bounds-checks [rcx+0x10] and reads element [rcx+8][edx]", arr[0][1] == "mov eax, dword ptr [rcx + 0x10]" and any(s == "mov rax, qword ptr [rcx + 8]" for _, s in arr) and any(s == "mov rax, qword ptr [rax + rdx*8]" for _, s in arr)))

    pre = dict(insns(0xD80B1B, 2))
    results.append(("channel obj out to [rbp+0x90] via 0x1005730", pre.get(0xD80B1B) == "lea r8, [rbp + 0x90]" and pre.get(0xD80B22) == "call 0x1005730"))
    results.append(("0x1331340 out = &[rbp+0x78] with obj from [rbp+0x90]", text.get(0xD80B46) == "lea rdx, [rbp + 0x78]" and text.get(0xD80B4F) == "mov rcx, qword ptr [rbp + 0x78]"))
    results.append(("obj2 = [rbp+0x78]->vtbl[+0x20]() before vtbl[+8]", text.get(0xD80B5A) == "call qword ptr [rax + 0x20]" and text.get(0xD80B8D) == "call qword ptr [rax + 8]"))

    ok = True
    for name, passed in results:
        print(("PASS" if passed else "FAIL"), name)
        ok = ok and passed
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
