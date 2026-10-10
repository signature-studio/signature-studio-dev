#!/usr/bin/env python3
"""Disassemble one pdata function with IAT names + string annotations. usage: disasm_fn.py <pe> <VA hex> [max_insn]"""
import sys, struct, bisect, re
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP
pe = pefile.PE(sys.argv[1]); IMG = pe.OPTIONAL_HEADER.ImageBase
va = int(sys.argv[2], 16); mx = int(sys.argv[3]) if len(sys.argv) > 3 else 400
S = {s.Name.rstrip(b'\0').decode(): s for s in pe.sections}
T = S['.text']; TB = T.get_data(); TVA = T.VirtualAddress
pd = S['.pdata'].get_data(); funcs = []
for i in range(0, len(pd) - 11, 12):
    b, e, u = struct.unpack_from('<III', pd, i)
    if b and TVA <= b < TVA + len(TB): funcs.append((b, e))
funcs.sort(); starts = [b for b, e in funcs]
i = bisect.bisect_right(starts, va - IMG) - 1; b, e = funcs[i]
iat = {imp_.address - IMG: imp_.name.decode() for d in pe.DIRECTORY_ENTRY_IMPORT for imp_ in d.imports if imp_.name}
dm = pe.get_memory_mapped_image()
def cstr(rva):
    if not (0 < rva < len(dm)): return None
    s = dm[rva:rva + 80].split(b'\0')[0]
    return s.decode('latin1') if len(s) >= 3 and all(32 <= c < 127 for c in s) else None
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
print(f"function {hex(IMG + b)} size {e - b}")
n = 0
for ins in md.disasm(TB[b - TVA:e - TVA], IMG + b):
    note = ''
    for o in ins.operands:
        if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
            t = ins.address + ins.size + o.mem.disp - IMG
            if t in iat: note = ' ; ' + iat[t]
            else:
                s = cstr(t)
                if s: note = ' ; "' + s + '"'
    print(f"{ins.address:x}: {ins.mnemonic} {ins.op_str}{note}")
    n += 1
    if n >= mx: print('...'); break
