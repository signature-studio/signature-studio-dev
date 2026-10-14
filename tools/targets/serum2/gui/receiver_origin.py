#!/usr/bin/env python3
"""SR-41 #2135: 間接 call [reg+disp] (disp = 0x30/0x38/0x88) の受信レジスタの直前の定義元を分類する (静的・ヒューリスティック)。

入力: Serum2_win64.vst3 (PE, x64 MSVC)。
方法: 候補 call ごとに、所属関数内で call より前にある命令を後ろから走査し、受信レジスタ reg を最後に書いた命令を探す。
  load[base+disp]: mov/movzx 等で qword ptr [base+disp] から読んだ (base は別レジスタ)
  copy(src):       reg <- src のレジスタ複写
  call-ret:        直前の call の戻り値 (rax)
  arith-*:         演算結果
  entry:           関数内で定義元が見つからない (引数・関数先頭からの値)
受信型は証明しない。load[base+disp] の base が this か子オブジェクトかは判定していない。
usage: receiver_origin.py <pe> [--top N]
"""
import bisect
import re
import struct
import sys
from collections import Counter, defaultdict

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1])
data = open(sys.argv[1], "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
DISPS = {0x30, 0x38, 0x88}
TOP = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 40


def sec(name):
    return next(s for s in pe.sections if s.Name.rstrip(b"\0") == name)


text = sec(b".text")
t_base = IMG + text.VirtualAddress
pdata = sec(b".pdata")
pd = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.SizeOfRawData]
funcs = []
for i in range(0, len(pd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pd, i)
    if b == 0:
        break
    funcs.append((IMG + b, IMG + e))
funcs.sort()
starts = [f[0] for f in funcs]


def func_of(va):
    k = bisect.bisect_right(starts, va) - 1
    if k >= 0 and funcs[k][0] <= va < funcs[k][1]:
        return funcs[k][0]
    return None


W64 = {"rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp"} | {f"r{i}" for i in range(8, 16)}
md = Cs(CS_ARCH_X86, CS_MODE_64)
ins_all = list(md.disasm(text.get_data(), t_base))
by_func = defaultdict(list)
for ins in ins_all:
    f = func_of(ins.address)
    if f is not None:
        by_func[f].append(ins)

mem_re = re.compile(r"^qword ptr \[(r(?!ip\b)[a-z0-9]+)(?: \+ (0x[0-9a-f]+))?\]$")
load_re = re.compile(r"^qword ptr \[(r[a-z0-9]+)(?: \+ (0x[0-9a-f]+))?\]$")


def origin(f, call_va, reg):
    seq = [i for i in by_func[f] if i.address < call_va]
    for ins in reversed(seq):
        if ins.mnemonic == "call":
            if reg == "rax":
                return "call-ret"
            continue
        ops = ins.op_str.split(", ", 1)
        dst = ops[0].strip()
        if dst != reg or ins.mnemonic in ("cmp", "test"):
            continue
        if ins.mnemonic in ("mov", "movzx", "movsxd", "lea") and len(ops) == 2:
            src = ops[1].strip()
            m = load_re.match(src)
            if m:
                return f"load[{m.group(1)}+{m.group(2) or '0x0'}]"
            if src in W64:
                return f"copy({src})"
            return "other-" + ins.mnemonic
        return "arith-" + ins.mnemonic
    return "entry"


cls = Counter()
for ins in ins_all:
    if ins.mnemonic != "call":
        continue
    c = mem_re.search(ins.op_str.strip())
    if not c or not c.group(2) or int(c.group(2), 16) not in DISPS:
        continue
    cls[origin(func_of(ins.address), ins.address, c.group(1))] += 1

print(f"candidates (disp 0x30/0x38/0x88): {sum(cls.values())}")
for k, n in cls.most_common(TOP):
    print(f"{n:5d}  {k}")
