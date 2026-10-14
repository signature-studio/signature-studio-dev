#!/usr/bin/env python3
"""PY-53 (#1911): 0x1046a30 の ecx 分岐と r8d ビット判定箇所を抽出する (実機不要)。

  python3 analysis/py53_dispatch.py <PE.bin> <outdir>

出力:
  <outdir>/fn.txt         関数 0x1046a30〜0x104ccca の全命令 (capstone)
  <outdir>/ecx_dispatch.txt  0x104742a〜0x1047458 の ecx 分岐
  <outdir>/r8d_bits.txt   [rbp+0x5c0] (r8d 退避先) を test する全箇所
PE は fl-win64 素材の extracted/block00031_PE.bin を使う (work/ に展開して渡す)。
"""
import os
import re
import sys

import capstone
import pefile

FN_START = 0x1046A30
FN_END = 0x104CCCB
DISPATCH_START = 0x104742A
DISPATCH_END = 0x1047458 + 0x8


def disasm(path):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    with open(path, "rb") as f:
        data = f.read()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    off = text.PointerToRawData + (FN_START - base - text.VirtualAddress)
    size = FN_END - FN_START
    for ins in md.disasm(data[off:off + size + 16], FN_START):
        if ins.address >= FN_END:
            break
        yield ins


def main():
    path, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    lines = [f"{i.address:#x}: {i.mnemonic} {i.op_str}" for i in disasm(path)]
    with open(os.path.join(outdir, "fn.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")

    def in_range(line, lo, hi):
        return lo <= int(line.split(":")[0], 16) <= hi

    dispatch = [ln for ln in lines if in_range(ln, DISPATCH_START, DISPATCH_END)]
    with open(os.path.join(outdir, "ecx_dispatch.txt"), "w") as f:
        f.write("\n".join(dispatch) + "\n")

    # r8d は 0x1046d71 で [rbp+0x5c0] に退避される。以後 test/and する箇所を拾う。
    pat = re.compile(r"\[rbp \+ 0x5c0\]")
    bits = []
    for idx, ln in enumerate(lines):
        if pat.search(ln) and ln.split(": ")[1].startswith("mov eax") and idx + 1 < len(lines):
            nxt = lines[idx + 1]
            if " test eax, " in nxt or "test eax," in nxt:
                bits.append(f"{nxt.split(':')[0]}  {nxt.split(': ')[1]}  (直前: {ln.split(': ')[0]})")
        elif pat.search(ln) and "and dword ptr" in ln:
            bits.append(f"{ln.split(':')[0]}  {ln.split(': ')[1]}  (書換え)")
    with open(os.path.join(outdir, "r8d_bits.txt"), "w") as f:
        f.write("\n".join(bits) + "\n")
    print(f"fn={len(lines)} dispatch={len(dispatch)} r8d_tests={len(bits)}")


if __name__ == "__main__":
    main()
