"""#1360: 値 2 の由来 (0x180037600 の QI 分岐) を逆アセンブルで表示する。
usage: python3 sr1e_qi_map.py <Serum2_win64.vst3> 0x180037600
"""
import sys
import pefile
import capstone

pe = pefile.PE(sys.argv[1], fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
data = pe.get_memory_mapped_image()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
for a in sys.argv[2:]:
    va = int(a, 16)
    rva = va - base
    print(f"== {a}")
    for i in md.disasm(bytes(data[rva:rva + 0x60]), va):
        print(f"{i.address:x}: {i.mnemonic} {i.op_str}")
