#!/usr/bin/env python3
"""leafscan.py — HeartCore から微小 leaf (this+disp 返却 / [rdx] 16B copy+addref) を探す (読取専用)。
usage: leafscan.py"""
import os as _os, sys as _sys
_sys.path.append(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..', '..', '..', 'shared'))
from paths import REPO_ROOT
import struct
import pefile
import capstone

P = _os.path.join(REPO_ROOT, 'tools/targets/kilohearts/work/winpkg/HeartCore.core_64')
pe = pefile.PE(P, fast_load=True)
data = open(P, 'rb').read()
BASE = pe.OPTIONAL_HEADER.ImageBuffer if hasattr(pe, 'ImageBuffer') else pe.OPTIONAL_HEADER.ImageBase


def rd(va, n):
    rva = va - BASE
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            o = s.PointerToRawData + rva - s.VirtualAddress
            return data[o:o + n]
    raise ValueError(hex(va))


md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = False

# .text 走査: 'ret' で終わる ≤9 命令の tail を見て、(a) lea/mov rax,[rcx+disp]; ret (b) mov rdx-sink 16B copy を探す
TEXT_VA = 0x180001000
TEXT_SZ = 0x139f8ac
code = rd(TEXT_VA, TEXT_SZ)

hits_ret = []
hits_shared = []
i = 0
step = 0x10000
# 全走査は重いので capstone をスライドしつつ 'mov rax,[rcx+X]; ret' / 'lea rax,[rcx+X]; ret' /
# 'mov rXX,rdx; movups xmm0,[rcx+Y]; movups [rdx],xmm0' のパターンをバイト検索 → capstone で確認
import re

# A) 48 8D 81 disp32 C3 / 48 8B 81 disp32 C3 (lea/mov rax,[rcx+disp32]; ret), 48 8D 41 disp8 C3 ...
for m in re.finditer(rb'\x48\x8[BbDd](?:\x81|\x41)(.)\xc3', code, re.DOTALL) if False else []:
    pass

pat_lea32 = re.compile(rb'\x48\x8d\x81(....)\xc3', re.DOTALL)
pat_mov32 = re.compile(rb'\x48\x8b\x81(....)\xc3', re.DOTALL)
for pat, kind in ((pat_lea32, 'lea'), (pat_mov32, 'mov')):
    for m in pat.finditer(code):
        off = m.start()
        disp = struct.unpack('<i', m.group(1))[0]
        va = TEXT_VA + off
        ins = list(md.disasm(rd(va - 8, 16), va - 8))
        # 直前が ret/int3 群 (関数先頭) であること
        prev_ok = any(x.mnemonic in ('ret', 'int3', 'nop') for x in ins[:3])
        if prev_ok:
            hits_ret.append((va, kind, disp))

# B) shared getter: 4C 8B C2 (mov r8,rdx) or 48 8B C2 (mov rax,rdx) ... F3 0F 10 81 disp32 (movups xmm0,[rcx+disp]) ...
#    F3 0F 11 02 (movups [rdx],xmm0)
pat_get = re.compile(rb'\xf3\x0f\x10\x81(....)\xf3\x0f\x11\x02', re.DOTALL)
for m in pat_get.finditer(code):
    off = m.start()
    disp = struct.unpack('<i', m.group(1))[0]
    va = TEXT_VA + off - 0x20
    ins = list(md.disasm(rd(va, 0x40), va))
    # movups [rdx],xmm0 を含む短い関数の先頭を探す
    seq = [x for x in ins]
    for k, x in enumerate(seq):
        if x.mnemonic == 'movups' and x.op_str.startswith('xmm0, xmmword ptr [rcx'):
            # 先頭方向へ: 前の命令が rcx/rdx の退避のみなら OK
            head = k
            while head > 0 and seq[head - 1].mnemonic in ('mov', 'push') and 'rsp' not in seq[head - 1].op_str:
                head -= 1
            fnva = seq[head].address
            if fnva in (0, None):
                continue
            body = seq[head:k + 6]
            text = '; '.join('%s %s' % (y.mnemonic, y.op_str) for y in body)
            if 'movups' in text and ('r9' in text or 'inc' in text or 'test' in text):
                hits_shared.append((fnva, disp, text[:150]))

print('== lea/mov rax,[rcx+disp32]; ret (disp 0x30..0x4000 or >=0x19e0):')
seen = set()
for va, kind, disp in sorted(hits_ret):
    key = (va, disp)
    if key in seen:
        continue
    seen.add(key)
    if 0x30 <= disp <= 0x4000 or disp >= 0x19e0:
        print('  %x %s +0x%x' % (va, kind, disp))

print('== shared getter candidates (movups [rdx],xmm0 from [rcx+disp]):')
seen = set()
for fnva, disp, text in sorted(hits_shared):
    if (fnva, disp) in seen:
        continue
    seen.add((fnva, disp))
    if 0x30 <= disp <= 0x4000 or disp >= 0x19e0:
        print('  %x disp +0x%x : %s' % (fnva, disp, text))
