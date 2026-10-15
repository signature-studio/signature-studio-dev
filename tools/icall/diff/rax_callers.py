#!/usr/bin/env python3
"""rax_callers.py VA [VA...] — 指定関数の全直接 call/jmp 元について、戻り直後の命令列で rax/eax/ax/al を「読む」前に「書く」かを静的に判定する。
1801a9a6c (sqrt wrapper) の rax は native でも scratch (0x7fffffffffffff00 | al) で、戻り値は xmm0 のみ。呼出し元が rax を読まないことの根拠。
出力: call 元ごとに先読み 8 命令内の最初の rax 系アクセス (read / write / none) と、read が 1 件でもあれば exit 1。"""
import os, re, sys
import capstone, pefile
from capstone import x86
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from paths import PLUGINS_DIR
DLL = os.path.join(PLUGINS_DIR, 'ott', 'binaries', 'OTT_vst2_win64.dll')
pe = pefile.PE(DLL)
base = pe.OPTIONAL_HEADER.ImageBase
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
RAX = {x86.X86_REG_RAX, x86.X86_REG_EAX, x86.X86_REG_AX, x86.X86_REG_AL, x86.X86_REG_AH}
txt = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
data = txt.get_data()
tb = base + txt.VirtualAddress
rc = 0
for arg in sys.argv[1:]:
    tgt = int(arg, 16)
    print('target %x' % tgt)
    for m in re.finditer(rb'[\xe8\xe9]', data):
        o = m.start()
        if o + 5 > len(data):
            continue
        rel = int.from_bytes(data[o + 1:o + 5], 'little', signed=True)
        if tb + o + 5 + rel != tgt:
            continue
        site = tb + o
        if data[o] == 0xe9:
            print('  %x: jmp (tail; 戻り値はそのまま呼出し元の呼出し元へ)' % site)
            continue
        verdict = 'none(8 命令内に rax アクセス無し)'
        for k, i in enumerate(md.disasm(data[o + 5:o + 5 + 64], site + 5)):
            if k >= 8 or i.mnemonic in ('ret', 'jmp', 'call') and k > 0:
                break
            regs_r, regs_w = i.regs_access()
            rr = any(r in RAX for r in regs_r)
            ww = any(r in RAX for r in regs_w)
            if rr:
                verdict = 'READ  @%x %s %s' % (i.address, i.mnemonic, i.op_str); rc = 1; break
            if ww:
                verdict = 'write @%x %s %s' % (i.address, i.mnemonic, i.op_str); break
            if i.mnemonic == 'ret':
                break
        print('  %x: %s' % (site, verdict))
sys.exit(rc)
