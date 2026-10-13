#!/usr/bin/env python3
"""icall_sites_check.py : m11_ov.c の ICALL_AT(<VA>, ...) の VA が, work/m11_image.bin (M11_LB_BASE=0 の image, offset = RVA) 上で間接 call 命令を指すか機械語から検査する (#494).
site の VA 誤記 (別命令・命令の途中) は hit 数の意味を壊すため, 全 site を capstone で 1 命令ずつ確認する. 不一致があれば exit 1.
期待: `call qword ptr [...]` または `call <reg>` (直接 call `call 0x...` は不一致). M11_SITE_NONE (survey ドライバ) は対象外."""
import os, re, sys
import capstone
HERE = os.path.dirname(os.path.abspath(__file__))
img = open(os.path.join(HERE, '..', 'work', 'm11_image.bin'), 'rb').read()
src = open(os.path.join(HERE, '..', 'm11_ov.c'), encoding='utf-8').read()
cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
bad = 0
for m in re.finditer(r'ICALL_AT\((0x[0-9a-fA-F]+),', src):
    va = int(m.group(1), 16)
    ins = next(iter(cs.disasm(img[va - 0x400000:va - 0x400000 + 16], va)), None)
    ok = ins is not None and ins.mnemonic == 'call' and not re.fullmatch(r'0x[0-9a-f]+', ins.op_str)
    bad += not ok
    print('%s %#x: %s' % ('OK  ' if ok else 'NG  ', va, '%s %s' % (ins.mnemonic, ins.op_str) if ins else '(逆アセンブル不能)'))
sys.exit(1 if bad else 0)
