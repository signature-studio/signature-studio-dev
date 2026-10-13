#!/usr/bin/env python3
"""disasm_img.py VA [長さ(既定 0x200)] : work/m11_image.bin (M11_LB_BASE=0 の image, offset = RVA) を capstone で逆アセンブルする (#482).
PE (fl-win64) が無い環境用. disasm_fn.py と違い .pdata の関数境界は使わず, VA から長さ分を線形に出す (関数末尾の int3/次関数まで出る)."""
import sys, os
import capstone
img = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'work', 'm11_image.bin'), 'rb').read()
va = int(sys.argv[1], 16); n = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x200
cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
for i in cs.disasm(img[va - 0x400000:va - 0x400000 + n], va): print('  %x: %-8s %s' % (i.address, i.mnemonic, i.op_str))
