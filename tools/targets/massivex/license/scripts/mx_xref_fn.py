#!/usr/bin/env python3
"""N5/N6 文字列範囲への RIP 相対参照を確定する。

usage:
  python3 mx_xref_fn.py <disp_va> [<disp_va> ...]  指定 disp を含む関数を逆アセンブルし、参照を表示
  python3 mx_xref_fn.py --all                      全 .pdata 関数を逆アセンブルし、STR 各範囲への参照を表示
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

def rva2va(off):
    return IB + pe.get_rva_from_offset(off)

def cstr(va):
    """NUL 区切り (ASCII / UTF-8) の文字列範囲 [lo, hi)。"""
    off = pe.get_offset_from_rva(va - IB)
    s = off
    while s > 0 and data[s - 1] != 0:
        s -= 1
    e = data.index(b"\0", off)
    return rva2va(s), rva2va(e)

def wstr(va, text):
    """UTF-16LE で text を並べた既知長の範囲 [lo, hi)。前後の区切りは見ない。"""
    return va, va + 2 * len(text)

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True

# (範囲名, 文字列の VA, 符号化 or UTF-16 で置く既知文字列)  UTF-16 は wstr で既知長の範囲
STR = [
    ("N6-1", 0x184ffcf87, "ascii"), ("N6-2", 0x184ffcfe8, "ascii"), ("N6-3", 0x184ffd03f, "ascii"),
    ("N6-4", 0x184ffd092, "ascii"), ("N6-5", 0x184ffd0d6, "ascii"), ("N6-6", 0x184ffd131, "ascii"),
    ("N5-MXDemoPopup", 0x18415f411, "MXDemoPopup.qml"), ("N5-demoExpired", 0x184879407, "ascii"),
    ("N5-demoExpiredChanged", 0x1848792b9, "ascii"), ("N5-subscriptionExpired", 0x18487941a, "ascii"),
]
RANGES = {n: (wstr(v, enc) if enc.endswith(".qml") else cstr(v)) for n, v, enc in STR}
for n, (lo, hi) in RANGES.items():
    print(f"range {n:24s} [{lo:#x},{hi:#x})")

def refs_in(s, e):
    """関数 [s,e) 内で RANGES を指す RIP 相対メモリオペランドを (命令, 範囲名, 参照先) で返す。"""
    if not (T_VA <= s and e <= T_VA + T_SZ):
        return
    off = T_OFF + (s - T_VA)
    code = data[off: off + (e - s)]
    for ins in md.disasm(code, s):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                t = ins.address + ins.size + op.mem.disp
                for name, (lo, hi) in RANGES.items():
                    if lo <= t < hi:
                        yield ins, name, t

if sys.argv[1:] == ["--all"]:
    hits = {n: [] for n in RANGES}
    for s, e in funcs:
        for ins, name, t in refs_in(s, e):
            hits[name].append((s, ins.address, f"{ins.mnemonic} {ins.op_str}", t))
    print(f"== scanned {len(funcs)} pdata functions")
    for name in RANGES:
        print(f"== {name}: {len(hits[name])} refs")
        for fs, ia, txt, t in hits[name]:
            print(f"   fn {fs:#x} @ {ia:#x} {txt} -> {t:#x}")
else:
    for arg in sys.argv[1:]:
        p = int(arg, 16)
        fn = owner(p)
        if not fn:
            print(f"{p:#x}: pdata 外"); continue
        s, e = fn
        print(f"== disp {p:#x}  fn [{s:#x},{e:#x})")
        for ins, name, t in refs_in(s, e):
            print(f"   {ins.address:#x} {ins.mnemonic} {ins.op_str}  -> {t:#x} [{name}]")
