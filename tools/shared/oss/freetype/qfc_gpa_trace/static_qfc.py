#!/usr/bin/env python3
# #2220 / #3257: x64 QuickFontCache (block24350_PE.bin) の FT 解決 0x563000 と関数ポインタ表の静的数値。
# アドレスは objdump と同じ VA (ImageBase + RVA)。表 = VA 0x59c7e0 (RVA 0x19c7e0) から 16 B 単位の対。
# usage: static_qfc.py PE_FILE
import re
import struct
import subprocess
import sys

TARGET = 0x563000
TBL_LO, TBL_HI = 0x59C7E0, 0x59CCF0

path = sys.argv[1]
d = open(path, "rb").read()
pe = struct.unpack_from("<I", d, 0x3C)[0]
ib = struct.unpack_from("<Q", d, pe + 24 + 24)[0]
nsec = struct.unpack_from("<H", d, pe + 6)[0]
optsz = struct.unpack_from("<H", d, pe + 20)[0]
secs = []
for i in range(nsec):
    s = pe + 24 + optsz + i * 40
    vsz, va, rsz, rp = struct.unpack_from("<IIII", d, s + 8)
    secs.append((va, vsz, rp, rsz))


def file_off(va_abs):
    rva = va_abs - ib
    for va, vsz, rp, rsz in secs:
        if va <= rva < va + max(vsz, rsz):
            return rp + (rva - va)
    raise SystemExit(f"VA {va_abs:#x} not in any section")


text_va, text_vsz, _, _ = secs[0]
code_lo, code_hi = ib + text_va, ib + text_va + text_vsz

dis = subprocess.run(
    ["objdump", "-d", "-M", "intel", path], capture_output=True, text=True, check=True
).stdout
callers = re.findall(rf"^\s*([0-9a-f]+):.*\bcall\s+{TARGET:#x}$", dis, re.M)
jumps = re.findall(rf"^\s*([0-9a-f]+):.*\bjmp\s+{TARGET:#x}$", dis, re.M)
print(f"call {TARGET:#x} (直接): {len(callers)} 件 {[f'{int(c, 16):#x}' for c in callers]}")
print(f"jmp {TARGET:#x} (直接): {len(jumps)} 件")

o = file_off(TBL_LO)
pairs = []
while True:
    a, b = struct.unpack_from("<QQ", d, o + 16 * len(pairs))
    if not (code_lo <= a < code_hi and code_lo <= b < code_hi):
        break
    pairs.append((a, b))
print(
    f"表 VA {TBL_LO:#x} から 16 B 対 (両方が .text の VA): {len(pairs)} 組"
    f" (先頭 {pairs[0][0]:#x}/{pairs[0][1]:#x}, 末尾 {hex(TBL_LO + 16 * (len(pairs) - 1))})"
)
FINI = 0x563840
print(f"  先頭が {FINI:#x} (fini, {TARGET:#x} を呼ぶ) の対: {[hex(TBL_LO + 16 * i) + '=' + hex(p[1]) for i, p in enumerate(pairs) if p[0] == FINI]}")

refs_ins = re.findall(rf"#\s*0x([0-9a-f]+)", dis)
n_ins = sum(1 for r in refs_ins if TBL_LO <= int(r, 16) <= TBL_HI)
n4 = sum(
    1
    for i in range(0, len(d) - 3, 4)
    if TBL_LO <= struct.unpack_from("<I", d, i)[0] <= TBL_HI
)
n8 = sum(
    1
    for i in range(0, len(d) - 7, 8)
    if TBL_LO <= struct.unpack_from("<Q", d, i)[0] <= TBL_HI
)
print(
    f"表を指す参照: 命令の rip 注記 {n_ins} 件 / 4 B 値 {n4} 件 / 8 B 値 {n8} 件"
    f" (区間 {TBL_LO:#x}〜{TBL_HI:#x})"
)
