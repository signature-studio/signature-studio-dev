#!/usr/bin/env python3
"""PY-99 (#2874) 受入 2: call 0x10469f0 の本体を逆アセンブルし、読解した式と照合する (実機不要)。

  python3 analysis/py99_call10469f0.py <PE.bin> [--negctl]

本体 0x10469f0〜0x1046a1d (17 命令) は edx + rint(K · ecx · (r8d − edx)) を返す。
  K = RIP 相対で読む qword (0x1046a03 + 0x1d = 0x1046a20 = 2^-30)、rint = call 0x40c660 (cvtsd2si rax, xmm0)。
照合が 1 つでも外れたら exit 1。--negctl は期待列の 1 命令を書き換えて FAIL を確認する。
"""
import struct
import sys

import capstone
import pefile

FN = 0x10469F0
RINT = 0x40C660
EXPECT = [
    "push rbx",
    "sub rsp, 0x20",
    "mov ebx, edx",
    "cvtsi2sd xmm0, ecx",
    "mulsd xmm0, qword ptr [rip + 0x1d]",
    "sub r8d, ebx",
    "cvtsi2sd xmm1, r8d",
    "mulsd xmm0, xmm1",
    "call 0x40c660",
    "add ebx, eax",
    "mov eax, ebx",
    "add rsp, 0x20",
    "pop rbx",
    "ret",
]


def main():
    args = sys.argv[1:]
    neg = "--negctl" in args
    path = next(a for a in args if not a.startswith("--"))
    expect = list(EXPECT)
    if neg:
        expect[9] = "sub ebx, eax"
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    data = open(path, "rb").read()

    def off(va):
        return text.PointerToRawData + (va - base - text.VirtualAddress)

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    got, ins_list = [], []
    for ins in md.disasm(data[off(FN):off(FN) + 0x40], FN):
        ins_list.append(ins)
        got.append(f"{ins.mnemonic} {ins.op_str}".strip())
        if ins.mnemonic == "ret":
            break
    ok_seq = got == expect
    for i, (g, _) in enumerate(zip(got, expect)):
        print(f"{ins_list[i].address:#x}: {g}")
    ok_len = len(got) == len(expect)

    mul = ins_list[4]
    k_va = mul.address + mul.size + int("0x1d", 16)
    k = struct.unpack("<d", data[off(k_va):off(k_va) + 8])[0]
    ok_k = k == 2.0 ** -30

    rint = md.disasm(data[off(RINT):off(RINT) + 0x10], RINT)
    rl = [f"{i.mnemonic} {i.op_str}".strip() for i in rint][:2]
    ok_rint = rl == ["cvtsd2si rax, xmm0", "ret"]

    print(f"K@{k_va:#x} = {k!r} (2^-30 = {2.0 ** -30!r}) ok={ok_k}")
    print(f"rint@{RINT:#x} = {rl} ok={ok_rint}")
    print(f"sequence ok={ok_seq and ok_len} (n={len(got)})")
    ok = ok_seq and ok_len and ok_k and ok_rint
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
