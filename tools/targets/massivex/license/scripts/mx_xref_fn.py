#!/usr/bin/env python3
"""候補 disp を含む関数を線形逆アセンブルし、N5/N6 文字列範囲への RIP 相対参照を確定する。

usage: python3 mx_xref_fn.py <disp_va> [<disp_va> ...]
"""
import bisect, sys
import capstone
import pefile

PE = "../work/extracted/VST3/Massive X.vst3"
data = open(PE, "rb").read()
pe = pefile.PE(data=data, fast_load=True)
IB = pe.OPTIONAL_HEADER.ImageBase
text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
T_OFF, T_VA, T_SZ = text.PointerToRawData, IB + text.VirtualAddress, text.SizeOfRawData
pd = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".pdata"][0]
funcs = []
for i in range(0, pd.SizeOfRawData - 11, 12):
    b = int.from_bytes(data[pd.PointerToRawData + i: pd.PointerToRawData + i + 4], "little")
    e = int.from_bytes(data[pd.PointerToRawData + i + 4: pd.PointerToRawData + i + 8], "little")
    if b and e > b:
        funcs.append((IB + b, IB + e))
funcs.sort()
starts = [f[0] for f in funcs]

def owner(va):
    i = bisect.bisect_right(starts, va) - 1
    return funcs[i] if i >= 0 and funcs[i][0] <= va < funcs[i][1] else None

def cstr(va):
    off = pe.get_offset_from_rva(va - IB)
    s = off
    while s > 0 and data[s - 1] != 0:
        s -= 1
    e = data.index(b"\0", off)
    return IB + pe.get_rva_from_offset(s), IB + pe.get_rva_from_offset(e)

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True

STR = {"N6-1": 0x184ffcf87, "N6-2": 0x184ffcfe8, "N6-3": 0x184ffd03f, "N6-4": 0x184ffd092,
       "N6-5": 0x184ffd0d6, "N6-6": 0x184ffd131,
       "N5-MXDemoPopup": 0x18415f411, "N5-demoExpired": 0x184879407,
       "N5-demoExpiredChanged": 0x1848792b9, "N5-subscriptionExpired": 0x18487941a}
RANGES = {k: cstr(v) for k, v in STR.items()}

for arg in sys.argv[1:]:
    p = int(arg, 16)
    fn = owner(p)
    if not fn:
        print(f"{p:#x}: pdata 外"); continue
    s, e = fn
    off = T_OFF + (s - T_VA)
    code = data[off: off + (e - s)]
    print(f"== disp {p:#x}  fn [{s:#x},{e:#x})")
    for ins in md.disasm(code, s):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                t = ins.address + ins.size + op.mem.disp
                for name, (lo, hi) in RANGES.items():
                    if lo <= t < hi:
                        print(f"   {ins.address:#x} {ins.mnemonic} {ins.op_str}  -> {t:#x} [{name}]")
