#!/usr/bin/env python3
"""SR-33 #2055: 関数 VA から direct call (call rel32) だけで到達できる関数を深さ制限付きで列挙する (静的)。

入力: Serum2_win64.vst3 (PE, x64 MSVC)。
限界: 間接 call (call [reg+disp]・call rax) は辿らない。よって「到達しない」は direct call 経路に限った結論。
usage: direct_reach.py <pe> <root_va_hex> <max_depth> <target_va_hex> [...]
"""
import bisect
import struct
import sys
from collections import deque

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1])
data = open(sys.argv[1], "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
root = int(sys.argv[2], 16)
maxd = int(sys.argv[3])
targets = {int(a, 16) for a in sys.argv[4:]}

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
code = text.get_data()
md = Cs(CS_ARCH_X86, CS_MODE_64)
cache = {}


def func_range(va):
    k = bisect.bisect_right(starts, va) - 1
    if k >= 0 and funcs[k][0] <= va < funcs[k][1]:
        return funcs[k]
    return None


def callees(fstart):
    if fstart in cache:
        return cache[fstart]
    lo, hi = func_range(fstart)
    out = set()
    for ins in md.disasm(code[lo - t_base:hi - t_base], lo):
        if ins.mnemonic == "call" and ins.op_str.startswith("0x"):
            try:
                out.add(int(ins.op_str, 16))
            except ValueError:
                pass
    cache[fstart] = out
    return out


seen = {root: 0}
q = deque([root])
while q:
    f = q.popleft()
    if seen[f] >= maxd:
        continue
    for c in callees(f):
        if func_range(c) and func_range(c)[0] == c and c not in seen:
            seen[c] = seen[f] + 1
            q.append(c)

print(f"root {root:#x} max_depth={maxd} reached_functions={len(seen)}")
for t in sorted(targets):
    hit = t in seen
    print(f"  target {t:#x}: {'REACHED depth=' + str(seen[t]) if hit else 'not reached (direct call only)'}")
