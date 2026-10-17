#!/usr/bin/env python3
"""SR-102 #6182: `load[reg+other]` の vtable disp (0x30・0x38・0x50・0x58・0x2f8 等) に対し、
コード中の `lea rip` で構築される候補 vptr V のうち、V+disp が R (target の direct 逆閉包) の関数を指すものを列挙する。

usage: vt_disp_match.py <pe> <target_va_hex> <disp_hex>...
出力: disp ごとの候補 V・R 関数・V を構築する lea の位置・lea を含む関数。
限界: V が lea で構築されない vptr (データ中の定数・別経路の書込み) は見ない。
      候補が呼出し元の receiver に一致するかは見ない (receiver の供給元は別途確認が要る)。
"""
import re
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe_path, target = sys.argv[1], int(sys.argv[2], 16)
DISPS = [int(x, 16) for x in sys.argv[3:]]
pe = pefile.PE(pe_path)
data = open(pe_path, "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
sec = {s.Name.rstrip(b"\0"): s for s in pe.sections}
text = sec[b".text"]
tb = IMG + text.VirtualAddress
raw = text.get_data()
pdata = sec[b".pdata"]
pd = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.SizeOfRawData]
funcs = []
for i in range(0, len(pd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pd, i)
    if b:
        funcs.append((IMG + b, IMG + e))
sset = {f[0] for f in funcs}
secs = [(IMG + s.VirtualAddress, s.get_data()) for s in pe.sections if s.SizeOfRawData]
cs = Cs(CS_ARCH_X86, CS_MODE_64)
rip_re = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")

fwd, lea_site = {}, {}
for lo, hi in funcs:
    fwd[lo] = set()
    for ins in cs.disasm(raw[lo - tb:hi - tb], lo):
        if ins.mnemonic in ("jmp", "call") and ins.op_str.startswith("0x"):
            t = int(ins.op_str, 16)
            if t in sset and t != lo:
                fwd[lo].add(t)
        if ins.mnemonic == "lea":
            m = rip_re.search(ins.op_str)
            if m:
                V = ins.address + ins.size + int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
                lea_site.setdefault(V, []).append((lo, ins.address))
rev = {}
for f, ts in fwd.items():
    for t in ts:
        rev.setdefault(t, set()).add(f)
R = {target}
q = [target]
while q:
    x = q.pop()
    for g in rev.get(x, ()):
        if g not in R:
            R.add(g)
            q.append(g)
print(f"R={len(R)} " + " ".join(f"{x:#x}" for x in sorted(R)))


def qword_at(va):
    for base, sraw in secs:
        if base <= va and va + 8 <= base + len(sraw):
            return struct.unpack_from("<Q", sraw, va - base)[0]
    return None


for d in DISPS:
    hits = []
    for V, sites in lea_site.items():
        v = qword_at(V + d)
        if v is not None and v in R:
            hits.append((V, v, sites))
    print(f"disp={d:#x}: lea-installed V with R at V+disp: {len(hits)}")
    for V, v, sites in hits:
        print(f"   V={V:#x} R_fn={v:#x} lea_sites={[f'{a:#x}' for _, a in sites][:4]} in_fns={sorted({f'{f:#x}' for f, _ in sites})[:3]}")
