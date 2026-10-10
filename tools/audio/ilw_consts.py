#!/usr/bin/env python3
"""ILWASAPI2ASIO_x64.dll の定数・WASAPI 呼出面を実測する補助 (ilw_vtable.py 併用)。"""
import sys, struct
sys.argv = [sys.argv[0]]
from ilw_vtable import *

def f64(va):
    return struct.unpack_from("<d", data, va2off(va))[0]

def cstr(va, n=64):
    b = data[va2off(va): va2off(va) + n]
    return b.split(b"\0")[0]

vt = [vt for _, vt, off in find_vtable(".?AVILWasapiToAsioDriver@@") if off == 0][0]
slots = read_vt(vt)
print("canSampleRate constants:", [f64(0x180003380 + 8 + 0x62 * 0 + x) for x in ()])
# rip-relative targets in canSampleRate
code = data[va2off(slots[12]):va2off(slots[12]) + 0x60]
import re
for ins in md.disasm(code, slots[12]):
    if "rip" in ins.op_str and ins.mnemonic == "ucomisd":
        d = int(re.search(r"rip \+ (0x[0-9a-f]+)", ins.op_str).group(1), 16)
        print(f"  canSampleRate: {f64(ins.address + ins.size + d)}")
for k in (4, 15, 18):
    code = data[va2off(slots[k]):va2off(slots[k]) + 0x120]
    for ins in md.disasm(code, slots[k]):
        if "rip" in ins.op_str and ins.mnemonic in ("lea", "movsd", "mov", "movzx"):
            m = re.search(r"rip ([+-]) (0x[0-9a-f]+)", ins.op_str)
            d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
            tgt = ins.address + ins.size + d
            if base <= tgt < base + len(data):
                print(f"  slot{k} {ins.mnemonic} rip-> {tgt:#x}: {cstr(tgt)!r}")
        if ins.mnemonic == "ret":
            break
