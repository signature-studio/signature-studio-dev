#!/usr/bin/env python3
"""disasm_img.py VA[:size] ... : work/m11_image.bin (M11_LB_BASE=0 の .text) から capstone で逆アセンブルする (#483).
PE (fl-win64) が無い runner 用の disasm_fn.py 代替. 関数サイズは work/boot_fns.json (decimal VA → size) から引く.
boot closure 外の関数は VA:size (size は 10 進/0x16 進) を明示する. 無指定かつ未収録は最初の ret (c3) まで.
環境変数: M11_IMAGE (既定 work/m11_image.bin)"""
import sys, os, json
import capstone
HERE = os.path.dirname(os.path.abspath(__file__)); W = os.path.join(HERE, '..', 'work')
IMG = open(os.environ.get('M11_IMAGE', os.path.join(W, 'm11_image.bin')), 'rb').read()
FNS = {int(k): v for k, v in json.load(open(os.path.join(W, 'boot_fns.json'))).items()}
BASE = 0x400000
cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); cs.detail = False
for a in sys.argv[1:]:
    va_s, _, sz_s = a.partition(':'); va = int(va_s, 16)
    size = int(sz_s, 0) if sz_s else FNS.get(va)
    lva = va - BASE
    if size is None:
        code = IMG[lva:lva + 0x400]
        ins = []
        for i in cs.disasm(code, va):
            ins.append(i)
            if i.mnemonic == 'ret': break
        size = (ins[-1].address + ins[-1].size - va) if ins else 0
        print('== function_%x size=%d (ret まで)' % (va, size))
    else:
        print('== function_%x size=%d' % (va, size))
    for i in cs.disasm(IMG[lva:lva + size], va): print('  %x: %s %s' % (i.address, i.mnemonic, i.op_str))
