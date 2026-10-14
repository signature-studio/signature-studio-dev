#!/usr/bin/env python3
"""SR-30 #2000: 指定関数 (.pdata 境界) の逆アセンブルを、対象 call の前後 N 命令だけ抜粋する。

入力: Serum2_win64.vst3 (PE, x64 MSVC)。
usage: splice_disasm.py <pe> <func_va_hex> [<before_n>] [<after_n>] [<call_target_hex>]
  call_target_hex を指定すると、その VA への direct call の前後のみ出す。省略時は関数全体 (先頭 80 命令)。
"""
import bisect
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1])
data = open(sys.argv[1], "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
fva = int(sys.argv[2], 16)
before = int(sys.argv[3]) if len(sys.argv) > 3 else 6
after = int(sys.argv[4]) if len(sys.argv) > 4 else 3
ctgt = int(sys.argv[5], 16) if len(sys.argv) > 5 else None

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
k = bisect.bisect_right(starts, fva) - 1
lo, hi = funcs[k]
code = text.get_data()[lo - t_base:hi - t_base]
ins = list(Cs(CS_ARCH_X86, CS_MODE_64).disasm(code, lo))
print(f"== func [{lo:#x}, {hi:#x}) size={hi - lo} insns={len(ins)}")
if ctgt is None:
    for i in ins[:80]:
        print(f"  {i.address:#x}: {i.mnemonic} {i.op_str}")
else:
    idx = [n for n, i in enumerate(ins) if i.mnemonic == "call" and i.op_str == f"{ctgt:#x}"]
    for n in idx:
        print(f"-- call {ctgt:#x} at {ins[n].address:#x}")
        for i in ins[max(0, n - before):n + after + 1]:
            print(f"  {i.address:#x}: {i.mnemonic} {i.op_str}")
