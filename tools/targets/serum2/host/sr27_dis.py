import sys
import pefile
from capstone import CS_ARCH_X86, CS_MODE_64, Cs

dll = sys.argv[1]
pe = pefile.PE(dll, fast_load=True)
IB = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_64)
text = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
tbase = IB + text.VirtualAddress
tdata = text.get_data()

start = int(sys.argv[2], 16)
end = int(sys.argv[3], 16)
off = start - text.VirtualAddress
blob = tdata[off:off + (end - start)]
for ins in md.disasm(blob, IB + start):
    print(f"{ins.address - IB:#x}: {ins.mnemonic} {ins.op_str}")
