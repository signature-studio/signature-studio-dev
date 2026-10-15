#!/usr/bin/env python3
"""表 T0 の補助オブジェクト P (0x53de80() の戻り値) の vtable を PE から確定する (PY-316 / #4319)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py316_p_vtable.py

検査 (1 つでも外れたら FAIL・終了 1):
- 0x478453 が lea で P = 0x13b21f0 を返し、その先頭 qword (静的 .data) が vtable 0x13b21b8 を指す。
- vtable +0x18 = 0x478310 は cmp edx, r8d; sete al (sub == key の 32 bit 一致判定)。
- vtable +0x20 = 0x478320 は key を 4 byte に積み、FNV-1a (seed 0x811c9dc5) 0x475ba0 を呼ぶ。
- 0x475ba0 は xor → imul 0x1000193 の FNV-1a 1 段ループ。
- 0xf8e4a0 は vtable +0x20 の戻り値を and 0x7fffffff・add 1・and 0x7fffffff して id とする。

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> extracted/block00031_PE.bin
"""
import os
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
P_CTOR_RET = 0x478453
P_OBJ = 0x13B21F0
P_VT = 0x13B21B8
SLOT18 = 0x478310
SLOT20 = 0x478320
FNV_SEED = 0x811C9DC5
FNV_PRIME = 0x1000193
HASH_FN = 0x475BA0
ID_FN = 0xF8E4A0


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData), s.PointerToRawData)
            for s in pe.sections]

    def fo(va):
        rva = va - base
        for vaddr, size, praw in secs:
            if vaddr <= rva < vaddr + size:
                return praw + (rva - vaddr)
        sys.exit(f"VA {va:#x} が section 外")

    def q(va):
        return struct.unpack_from("<Q", raw, fo(va))[0]

    def disasm(va, n):
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        return [(i.address, i.mnemonic, i.op_str)
                for i, _ in zip(md.disasm(raw[fo(va):fo(va) + n * 16], va), range(n))]

    fails = []

    def check(ok, msg):
        print(("PASS " if ok else "FAIL ") + msg)
        if not ok:
            fails.append(msg)

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    lea = next(i for i in md.disasm(raw[fo(P_CTOR_RET):fo(P_CTOR_RET) + 16], P_CTOR_RET))
    check(lea.mnemonic == "lea" and lea.address + lea.size + lea.operands[1].mem.disp == P_OBJ,
          f"{P_CTOR_RET:#x} が RIP 相対 lea で P {P_OBJ:#x} を指す")
    check(q(P_OBJ) == P_VT, f"P {P_OBJ:#x} の先頭 qword = vtable {P_VT:#x} (静的 .data)")
    check(q(P_VT + 0x18) == SLOT18, f"vtable +0x18 = {SLOT18:#x}")
    check(q(P_VT + 0x20) == SLOT20, f"vtable +0x20 = {SLOT20:#x}")

    ins18 = [(m, s) for _, m, s in disasm(SLOT18, 3)]
    check(ins18[0] == ("cmp", "edx, r8d") and ins18[1] == ("sete", "al") and ins18[2][0] == "ret",
          f"{SLOT18:#x} は cmp edx, r8d; sete al; ret (sub == key)")

    ins20 = disasm(SLOT20, 8)
    check(any(m == "mov" and s == f"edx, 4" for _, m, s in ins20),
          f"{SLOT20:#x} は 4 byte (u32) を積む (mov edx, 4 で hash を呼ぶ)")
    check(any(m == "mov" and s == f"r8d, {FNV_SEED:#x}" for _, m, s in ins20),
          f"{SLOT20:#x} の seed は {FNV_SEED:#x}")
    check(any(m == "call" and s == f"{HASH_FN:#x}" for _, m, s in ins20),
          f"{SLOT20:#x} は {HASH_FN:#x} を呼ぶ")

    hbody = disasm(HASH_FN, 10)
    check(any(m == "xor" and s == "eax, r8d" for _, m, s in hbody)
          and any(m == "imul" and s == f"eax, eax, {FNV_PRIME:#x}" for _, m, s in hbody),
          f"{HASH_FN:#x} は FNV-1a (xor → imul {FNV_PRIME:#x}) の 1 段ループ")

    idbody = disasm(ID_FN, 10)
    seq = [(m, s) for _, m, s in idbody]
    check(("call", "qword ptr [rax + 0x20]") in seq, f"{ID_FN:#x} は vtable +0x20 を呼ぶ")
    tail = seq[seq.index(("call", "qword ptr [rax + 0x20]")) + 1:][:4]
    check(tail == [("and", "eax, 0x7fffffff"), ("add", "eax, 1"), ("and", "eax, 0x7fffffff"), ("add", "rsp, 0x28")],
          f"{ID_FN:#x} は戻り値を and 0x7fffffff・add 1・and 0x7fffffff して id とする")

    print(f"summary: {len(fails)} FAIL")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
