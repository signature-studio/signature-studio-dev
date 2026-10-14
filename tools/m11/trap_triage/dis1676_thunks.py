# #1676/#1931: PE の指定 VA を逆アセンブルし、間接 call の形を見る (IR に脱落した call の確認用)。
# 使い方: python3 trap_triage/dis1676_thunks.py <block00031_PE.bin> 0x410320 0x410360
# 出力は VA・命令。call qword ptr [reg±disp] が見えれば IR からの脱落候補になる。
import pefile, capstone, sys

pe = pefile.PE(sys.argv[1], fast_load=True)
ib = pe.OPTIONAL_HEADER.ImageBase
data = pe.get_memory_mapped_image()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
for va in [int(x, 16) for x in sys.argv[2:]]:
    rva = va - ib
    print('== func VA', hex(va))
    for ins in md.disasm(bytes(data[rva:rva + 0x100]), va):
        print(f'  {ins.address:#x}: {ins.mnemonic} {ins.op_str}')
        if ins.mnemonic == 'ret':
            break
