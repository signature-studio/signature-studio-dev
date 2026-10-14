#!/usr/bin/env python3
# pe_disasm_va.py: PE (block00031_PE.bin) の VA を逆アセンブルする (#942 §14-3・lift 誤りの照合用)。
# 使い方: python3 tools/m11/ldfix/pe_disasm_va.py "$FL_WIN64_DIR/extracted/block00031_PE.bin" 0x450560 [行数]
import sys
import capstone
import pefile

path, va = sys.argv[1], int(sys.argv[2], 0)
n = int(sys.argv[3]) if len(sys.argv) > 3 else 40
pe = pefile.PE(path, fast_load=True)
code = pe.get_data(va - pe.OPTIONAL_HEADER.ImageBase, 16 * n)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
for i, ins in enumerate(md.disasm(code, va)):
    print('0x%x: %s %s' % (ins.address, ins.mnemonic, ins.op_str))
    if i + 1 >= n:
        break
