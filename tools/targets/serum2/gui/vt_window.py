#!/usr/bin/env python3
"""SR-32 #2054: vtable 候補 (lo..hi の窓) を指す rip 相対参照を .text から列挙し、
RTTI の型名 (.?AV...) の TypeDescriptor とその COL (sig=1) を列挙する。
usage: vt_window.py <pe> <lo_hex> <hi_hex> [name_regex]"""
import re
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1])
data = open(sys.argv[1], "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
lo, hi = int(sys.argv[2], 16), int(sys.argv[3], 16)
sec = {s.Name.rstrip(b"\0"): s for s in pe.sections}
text = sec[b".text"]
rip_re = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
cs = Cs(CS_ARCH_X86, CS_MODE_64)
print(f"== .text: rip-relative refs into [{lo:#x}, {hi:#x}) ==")
for ins in cs.disasm(text.get_data(), IMG + text.VirtualAddress):
    m = rip_re.search(ins.op_str)
    if not m:
        continue
    d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
    tgt = ins.address + ins.size + d
    if lo <= tgt < hi:
        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}  -> {tgt:#x}")

print("== TypeDescriptor (.?AV) と COL (sig=1) ==")
rd = sec[b".rdata"]
rraw = data[rd.PointerToRawData:rd.PointerToRawData + rd.SizeOfRawData]
rbase = IMG + rd.VirtualAddress
for m in re.finditer(rb"\.\?AV[A-Za-z0-9_@$?]+@@", rraw):
    name_va = rbase + m.start()
    td_va = name_va - 16  # TypeDescriptor: vfptr(8) spare(8) name
    tdo = td_va - IMG - rd.VirtualAddress + rd.PointerToRawData
    cls = m.group().decode()
    # COL は pTypeDescriptor (RVA) を含む。RVA 形式で探す
    td_rva = td_va - IMG
    needle = struct.pack("<I", td_rva)
    cols = []
    for k in range(0, len(rraw) - 20, 4):
        if rraw[k + 12:k + 16] == needle and struct.unpack_from("<I", rraw, k)[0] == 1:
            cols.append(rbase + k)
    print(f"  {cls}  TD={td_va:#x}  COL={[hex(c) for c in cols]}")
