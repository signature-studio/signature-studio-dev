#!/usr/bin/env python3
"""disasm_img.py VA[:size] ... / VA 0xLEN : work/m11_image.bin (M11_LB_BASE=0 の .text, offset = RVA) から capstone で逆アセンブルする (#482, #483).
PE (fl-win64) が無い runner 用の disasm_fn.py 代替. 引数 (VA は 16 進, 0x 無し可):
  VA:size   size (10 進/0x16 進) を明示. boot closure 外の関数はこれで指定する (#483)
  VA 0xLEN  直前の VA から LEN バイトを線形に出す (#482。`disasm_img.py 5c03d0 0x70`)
  VA        work/boot_fns.json (decimal VA → size) にあればそのサイズ. 無ければ最初の ret (c3) まで (#483)
環境変数: M11_IMAGE (既定 work/m11_image.bin)"""
import sys, os, json
import capstone
HERE = os.path.dirname(os.path.abspath(__file__)); W = os.path.join(HERE, '..', 'work')
IMG = open(os.environ.get('M11_IMAGE', os.path.join(W, 'm11_image.bin')), 'rb').read()
FNS_PATH = os.path.join(W, 'boot_fns.json')
FNS = {int(k): v for k, v in json.load(open(FNS_PATH)).items()} if os.path.exists(FNS_PATH) else {}
BASE = 0x400000
cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); cs.detail = False

reqs = []
for a in sys.argv[1:]:
    if reqs and ':' not in a and a.lower().startswith('0x'):
        reqs[-1][1] = int(a, 0)
    else:
        va_s, _, sz_s = a.partition(':')
        reqs.append([int(va_s, 16), int(sz_s, 0) if sz_s else None])

for va, size in reqs:
    if size is None:
        size = FNS.get(va)
    lva = va - BASE
    if size is None:
        ins = []
        for i in cs.disasm(IMG[lva:lva + 0x400], va):
            ins.append(i)
            if i.mnemonic == 'ret': break
        size = (ins[-1].address + ins[-1].size - va) if ins else 0
        print('== function_%x size=%d (ret まで)' % (va, size))
    else:
        print('== function_%x size=%d' % (va, size))
    for i in cs.disasm(IMG[lva:lva + size], va): print('  %x: %-8s %s' % (i.address, i.mnemonic, i.op_str))
