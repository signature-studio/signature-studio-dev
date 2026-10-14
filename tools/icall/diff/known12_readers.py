#!/usr/bin/env python3
# known12_readers.py — 既知 12 encoded slot (0x1813068d0〜0x181307418) を読む・書く命令を objdump の全数から列挙する (ICALL-64 / #2224)。
#   (1) RIP 相対で直接指す命令 (読出し・書込みの種別と、含む関数の VA)。
#   (2) 添字付き参照 [base+idx*scale+disp] のうち disp が .data の表候補 (0x125c000〜0x13068d0) にあるもの。
#       base が r14・r15 の場合は image base 0x180000000 と仮定し、その添字 n で各 slot に届くかを出す。
#   列挙しない形: disp が無い [base+idx*scale]・disp が範囲外の添字参照・非 slot 基底を lea で作る形 (REPORT_APPENDIX_2224.md §1)。
#   入力: work/core64_dis.txt (objdump -d -M intel の出力)・SlateCore.core_64 (.pdata の関数境界)。
#   依存: python3 -m pip install pefile==2024.8.26
#   用法: python3 tools/icall/diff/known12_readers.py work/core64_dis.txt "<SlateCore.core_64>"
import bisect
import re
import sys
from pathlib import Path

import pefile

KNOWN = [0x1813068D0, 0x1813068F8, 0x181306900, 0x181306908, 0x181306910, 0x1813072B0,
         0x1813073F0, 0x1813073F8, 0x181307400, 0x181307408, 0x181307410, 0x181307418]
IMAGE_BASE = 0x180000000
INS = re.compile(r"\s*([0-9a-f]+):\t(?:[0-9a-f]{2} )+\s*\t?(.*)$")
RIP = re.compile(r"\[rip\+0x[0-9a-f]+\].*# 0x([0-9a-f]+)$")
IDX = re.compile(r"\[(?P<base>[a-z0-9]+)\+(?P<idx>[a-z0-9]+)\*(?P<sc>[1248])\+0x(?P<disp>[0-9a-f]+)\]")

dis_path, exe_path = Path(sys.argv[1]), sys.argv[2]
order, ins = [], {}
for line in dis_path.read_text(errors="replace").splitlines():
    m = INS.match(line)
    if m:
        va = int(m.group(1), 16)
        ins[va] = m.group(2)
        order.append(va)

pe = pefile.PE(exe_path, fast_load=True)
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])
funcs = sorted((IMAGE_BASE + e.struct.BeginAddress, IMAGE_BASE + e.struct.EndAddress)
               for e in pe.DIRECTORY_ENTRY_EXCEPTION)
starts = [a for a, _ in funcs]


def fn_of(va):
    i = bisect.bisect_right(starts, va) - 1
    if i >= 0 and funcs[i][0] <= va < funcs[i][1]:
        return "%x(pdata)" % funcs[i][0]
    # .pdata 外: 直前の int3 埋めの後ろを関数先頭とみなす (推定)
    idx = order.index(va)
    j = idx
    while j > 0 and ins.get(order[j - 1], "").strip() != "int3":
        j -= 1
    return "%x(int3推定)" % order[j]


def access(text):
    mnem = text.split()[0] if text.split() else ""
    if mnem == "xchg":
        return "RW"
    if mnem == "mov" and re.match(r"mov\s+[A-Z]* ?PTR \[rip", text):
        return "W"
    return "R"


print("== (1) RIP 相対で既知 12 を指す命令")
for k in KNOWN:
    for va in order:
        m = RIP.search(ins[va])
        if m and int(m.group(1), 16) == k:
            print("slot %x  %s  insn %x  fn %s  %s" % (k, access(ins[va]), va, fn_of(va), ins[va]))

print("== (2) 添字付き参照 (disp in [0x125c000, 0x13068d0])。n = 添字 (base=image base 仮定)")
for va in order:
    if "rip" in ins[va]:
        continue
    for m in IDX.finditer(ins[va]):
        disp = int(m.group("disp"), 16)
        if not (0x125C000 <= disp <= 0x13068D0):
            continue
        sc = int(m.group("sc"))
        base = m.group("base")
        ns = []
        for k in KNOWN:
            d = k - IMAGE_BASE - disp
            ns.append(d // sc if d >= 0 and d % sc == 0 else None)
        ok = {hex(k): n for k, n in zip(KNOWN, ns) if n is not None}
        tag = "image-base 仮定" if base in ("r14", "r15") else "基底未確認"
        print("insn %x  [%s+%s*%d+0x%x] (%s)  届く既知 slot と添字: %s  %s" % (
            va, base, m.group("idx"), sc, disp, tag, ok if ok else "なし", ins[va]))
