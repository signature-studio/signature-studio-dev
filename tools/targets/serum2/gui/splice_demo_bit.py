#!/usr/bin/env python3
"""SR-30 #2000: 指定関数群の中で、オブジェクト offset (既定 0x22792) を参照する命令を列挙する。

入力: Serum2_win64.vst3 (PE, x64 MSVC)。
方法: 各関数を .pdata 境界で切り、capstone で逆アセンブルし、オペランドの
      disp が対象 offset (または対象 offset を含む 64bit 即値) の命令を出す。
usage: splice_demo_bit.py <pe> <func_va_hex> [...] [--off 0x22792]
"""
import bisect
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

args = sys.argv[1:]
off = 0x22792
if "--off" in args:
    i = args.index("--off")
    off = int(args[i + 1], 16)
    del args[i:i + 2]
pe = pefile.PE(args[0])
data = open(args[0], "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
funcs_q = [int(a, 16) for a in args[1:]]

text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
t_base = IMG + text.VirtualAddress
pdata = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".pdata")
pd = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.SizeOfRawData]
funcs = []
for i in range(0, len(pd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pd, i)
    if b == 0:
        break
    funcs.append((IMG + b, IMG + e))
funcs.sort()
starts = [f[0] for f in funcs]
md = Cs(CS_ARCH_X86, CS_MODE_64)
code = text.get_data()
for fva in funcs_q:
    k = bisect.bisect_right(starts, fva) - 1
    lo, hi = funcs[k]
    ins = list(md.disasm(code[lo - t_base:hi - t_base], lo))
    hits = [i for i in ins if f"+ {off:#x}]" in i.op_str or f"+{off:#x}]" in i.op_str]
    print(f"== func {lo:#x} size={hi - lo}: {len(hits)} hits for +{off:#x}")
    for i in hits:
        print(f"  {i.address:#x}: {i.mnemonic} {i.op_str}")
