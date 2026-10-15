#!/usr/bin/env python3
# #3052 §19: FLEngine_x64.dll の関数 (.pdata 境界) を逆アセンブルし、指定した関数を直接呼ぶ箇所を、周辺 N 命令付きで出す。
# 使い方: uv run --with pefile --with capstone python3 tools/flp/s4_xref.py <block00031_PE.bin> <VA hex,...> [周辺命令数=5] [fn]
# 出力は REPORT_APPENDIX_3052.md §19 の呼出し元の数値の根拠。fn を付けると、各 VA を含む関数の全命令を出す (§19 の関数本文の根拠)。repo には素材を置かない。
import bisect
import collections
import struct
import sys

import capstone
import pefile

P = sys.argv[1]
TARGETS = [int(x, 16) for x in sys.argv[2].split(",")]
CTX = int(sys.argv[3]) if len(sys.argv) > 3 else 5
FN = len(sys.argv) > 4 and sys.argv[4] == "fn"
pe = pefile.PE(P, fast_load=False)
base = pe.OPTIONAL_HEADER.ImageBase
sec = {s.Name.rstrip(b"\0"): s for s in pe.sections}
text = sec[b".text"]
tva = base + text.VirtualAddress
tdata = text.get_data()
pd = sec[b".pdata"].get_data()
funcs = set()
for i in range(0, len(pd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pd, i)
    if b:
        funcs.add((base + b, base + e))
funcs = sorted(funcs)
fstart = [f[0] for f in funcs]
fend = dict(funcs)


def fn_of(va):
    k = bisect.bisect_right(fstart, va) - 1
    if k >= 0 and funcs[k][0] <= va < funcs[k][1]:
        return funcs[k][0]
    return None


md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
insns = []
calls = collections.defaultdict(list)
for fs, fe in funcs:
    o1, o2 = fs - tva, fe - tva
    if o1 < 0 or o2 > len(tdata):
        continue
    for ins in md.disasm(tdata[o1:o2], fs):
        insns.append(ins)
        if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
            t = int(ins.op_str, 16)
            if t in TARGETS:
                calls[t].append(ins.address)
if FN:
    for t in TARGETS:
        f = fn_of(t)
        print(f"== fn {hex(f) if f else '?'} (contains {hex(t)})")
        if f is None:
            continue
        for ins in insns:
            if f <= ins.address < fend[f]:
                print(f"  {hex(ins.address)}: {ins.mnemonic} {ins.op_str}")
    sys.exit(0)
index = {ins.address: i for i, ins in enumerate(insns)}
for t in TARGETS:
    print(f"== target {hex(t)} direct callers={len(calls[t])}")
    for c in calls[t]:
        f = fn_of(c)
        print(f"  call@{hex(c)} in fn {hex(f) if f else '?'}")
        i = index.get(c)
        if i is None:
            continue
        for ins in insns[max(0, i - CTX):i + 2]:
            print(f"      {hex(ins.address)}: {ins.mnemonic} {ins.op_str}")
