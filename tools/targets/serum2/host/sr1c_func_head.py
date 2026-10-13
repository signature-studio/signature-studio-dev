#!/usr/bin/env python3
# SR-1c (#256): 指定 RVA を含む関数の先頭を .pdata (RUNTIME_FUNCTION) から求め、その先頭の数命令を逆アセンブルする。
# usage: python3 sr1c_func_head.py <Serum2_win64.vst3> <rva_hex> [n_insn]
import struct
import sys

import pefile
from capstone import CS_ARCH_X86, CS_MODE_64, Cs

dll, rva_s = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 12
rva = int(rva_s, 16)
pe = pefile.PE(dll, fast_load=True)
image_base = pe.OPTIONAL_HEADER.ImageBase
pdata = None
for sec in pe.sections:
    if sec.Name.rstrip(b"\0") == b".pdata":
        pdata = sec.get_data()
        pdata_va = sec.VirtualAddress
assert pdata is not None
found = None
for off in range(0, len(pdata) - 11, 12):
    b, e, _u = struct.unpack_from("<III", pdata, off)
    if b <= rva < e:
        found = (b, e)
        break
if not found:
    print("pdata に該当なし")
    sys.exit(1)
b, e = found
print(f"function RVA 0x{b:x}-0x{e:x} (size {e - b})")
md = Cs(CS_ARCH_X86, CS_MODE_64)
for sec in pe.sections:
    if sec.VirtualAddress <= b < sec.VirtualAddress + sec.SizeOfRawData:
        data = sec.get_data()
        start = b - sec.VirtualAddress
        code = data[start:start + (e - b)]
        for i, ins in enumerate(md.disasm(code, image_base + b)):
            if i >= n:
                break
            print(f"  {ins.address:x}: {ins.mnemonic} {ins.op_str}")
        break
