#!/usr/bin/env python3
# AggCreateInstance の呼び出し元の手がかりを探す (T-SH-02, #146)。
# 使い方: FL_WIN64_DIR=<fl-win64 展開先> python3 agg2d_callers.py [block 名 (既定 block18797_PE.bin)]
# 依存: pefile, capstone。
# 1) UTF-16 で "Blend2D.dll" と "AggCreateInstance" を両方含む block を数える (import 表は ANSI なので、ここは別経路)。
# 2) 指定 block 内で両文字列を指す RIP 相対参照を探し、その直後の `mov [rip+X], rax` の格納先 (関数ポインタの保持先) を求める。
# 3) その格納先を指す RIP 相対参照を探す (disp32 の後に imm が続く形 cmp qword ptr [rip+X], imm8 も拾う)。
import glob
import os
import re
import struct
import sys

import capstone
import pefile

NAMES = ["Blend2D.dll", "AggCreateInstance"]
RIP = re.compile(r"\[rip \+ (0x[0-9a-f]+)\]")
MOV_STORE = re.compile(r"^mov qword ptr \[rip \+ 0x[0-9a-f]+\], rax$")


def rip_target(insn):
    m = RIP.search(insn.op_str)
    return insn.address + insn.size + int(m.group(1), 16) if m else None


def main():
    root = os.environ.get("FL_WIN64_DIR")
    if not root:
        sys.exit("FL_WIN64_DIR が未設定")
    ext = os.path.join(root, "extracted")
    pats = [n.encode("utf-16le") for n in NAMES]
    both = []
    for f in sorted(glob.glob(os.path.join(ext, "block*_PE.bin"))):
        with open(f, "rb") as fh:
            d = fh.read()
        if all(p in d for p in pats):
            both.append(os.path.basename(f))
    print(f"UTF-16 で両文字列を含む block: {len(both)} 件 (block*_PE.bin 全 {len(glob.glob(os.path.join(ext, 'block*_PE.bin')))} 件中)")

    block = sys.argv[1] if len(sys.argv) > 1 else "block18797_PE.bin"
    pe = pefile.PE(os.path.join(ext, block), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    img = pe.get_memory_mapped_image()
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    lo, hi = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize
    targets = {}
    for n in NAMES:
        targets[base + pe.get_rva_from_offset(pe.__data__.find(n.encode("utf-16le")))] = n
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    stores = []
    for p in range(lo, hi - 4):
        disp = struct.unpack_from("<i", img, p)[0]
        if base + p + 4 + disp not in targets:
            continue
        start = base + p - 3
        ins = list(md.disasm(img[start - base:start - base + 40], start, count=6))
        ref_name = targets[base + p + 4 + disp]
        print(f"{block} ref {hex(start)} {ref_name}: " + " ; ".join(f"{x.mnemonic} {x.op_str}" for x in ins[:3]))
        if ref_name != "AggCreateInstance":
            continue
        for x in ins[1:]:
            if MOV_STORE.match(f"{x.mnemonic} {x.op_str}"):
                stores.append(rip_target(x))
                break
    for g in sorted(set(s for s in stores if s)):
        print(f"格納先 (関数ポインタ) VA {hex(g)}")
        hits = []
        for p in range(lo, hi - 4):
            disp = struct.unpack_from("<i", img, p)[0]
            for k in (0, 1, 2, 4, 5, 8):
                if base + p + 4 + k + disp == g:
                    hits.append((base + p - 3, k))
        for h, k in hits:
            print(f"  参照 {hex(h)} (disp 後の残り {k} B)")
        print(f"  参照件数 {len(hits)}")


if __name__ == "__main__":
    main()
