#!/usr/bin/env python3
# SR-1c (#256): ゲートフィールドへの書込命令を .text 全体から静的に列挙する。
# REPORT §3-3 は同一ゲートを decomp 基準 +0x10c、IEditController this 基準 +0xdc と記載 (差分 0x30)。
# usage: python3 sr1c_writer_scan.py <Serum2_win64.vst3> <disp> <out.tsv>
#   disp: 16 進のオフセット (例 0xdc / 0x10c)
# 検出対象: [reg+disp] を宛先に持つ mov/add/sub/or/and/xor/inc/dec/lea 命令 (store 側は mov のみ)。
# 注: 間接参照・複数段の base 計算は拾えない (下限)。
import sys

import pefile
from capstone import CS_ARCH_X86, CS_MODE_64, Cs

dll, disp_s, out = sys.argv[1], sys.argv[2], sys.argv[3]
disp = int(disp_s, 16)
pe = pefile.PE(dll, fast_load=True)
image_base = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True

hits = []
for sec in pe.sections:
    if not (sec.Characteristics & 0x20000000):  # IMAGE_SCN_MEM_EXECUTE
        continue
    name = sec.Name.rstrip(b"\0").decode(errors="replace")
    code = sec.get_data()
    base = image_base + sec.VirtualAddress
    for ins in md.disasm(code, base):
        if ins.mnemonic not in ("mov", "add", "sub", "or", "and", "xor", "inc", "dec", "adc", "sbb", "bts", "btr", "btc"):
            continue
        ops = ins.operands
        if not ops:
            continue
        dst = ops[0]
        if dst.type != 3:  # X86_OP_MEM
            continue
        if dst.mem.disp != disp:
            continue
        base_reg = ins.reg_name(dst.mem.base) if dst.mem.base else "-"
        hits.append((ins.address, name, ins.mnemonic, base_reg, ins.op_str))

with open(out, "w") as f:
    f.write("va\tsection\tmnemonic\tbase\top\n")
    for h in hits:
        f.write(f"0x{h[0]:x}\t{h[1]}\t{h[2]}\t{h[3]}\t{h[4]}\n")
print(f"disp=0x{disp:x} 宛先メモリ書込候補 {len(hits)} 件")
