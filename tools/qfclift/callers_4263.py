#!/usr/bin/env python3
# callers_4263.py — QuickFontCache (block24350_PE.bin) の longjmp 相当 0x40f9c0 の呼出元と、
# 状態変数 [0x5aa000]・[0x5d0db0]・[0x5d0ddc]・[0x5d0cb0] の書込み元を .pdata の関数単位で列挙する (T-SH-107 / #4263)。
# 使い方: python3 callers_4263.py <block24350_PE.bin>   (出力は標準出力。REPORT_APPENDIX_4263.md の表の根拠)
# 依存: pip install pefile capstone
import bisect, sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1])
IMG = pe.OPTIONAL_HEADER.ImageBase
text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
data = text.get_data()
base = IMG + text.VirtualAddress
funcs = sorted((IMG + e.struct.BeginAddress, IMG + e.struct.EndAddress) for e in pe.DIRECTORY_ENTRY_EXCEPTION)
starts = [f[0] for f in funcs]
md = Cs(CS_ARCH_X86, CS_MODE_64)


def func_of(a):
    i = bisect.bisect_right(starts, a) - 1
    return funcs[i][0] if i >= 0 and funcs[i][0] <= a < funcs[i][1] else None


ins = []
for a, b in funcs:
    if a >= base and b <= base + len(data):
        ins.extend(md.disasm(data[a - base:b - base], a))

print("## 呼出元 (call 命令の VA と所属関数)")
for tgt in (0x40FA40, 0x40FB80, 0x40FD10, 0x40FD30, 0x40F430):
    for i in ins:
        if i.mnemonic == "call" and i.op_str.startswith("0x") and int(i.op_str, 16) == tgt:
            f = func_of(i.address)
            print(f"  call {tgt:#x} at {i.address:#x} in fn {hex(f) if f else '?'}")

print("## rip 相対の参照 (読み/書き)")
for va in (0x5AA000, 0x5AA008, 0x5D0DB0, 0x5D0DDC, 0x5D0CB0, 0x5D0C80, 0x5D0C88):
    for i in ins:
        if "[rip" in i.op_str:
            s = i.op_str.split("[rip")[1].split("]")[0]
            d = int(s.split("+")[1], 16) if "+" in s else -int(s.split("-")[1], 16)
            if i.address + i.size + d == va:
                f = func_of(i.address)
                print(f"  {va:#x} <- {i.address:#x} fn {hex(f) if f else '?'}: {i.mnemonic} {i.op_str}")
