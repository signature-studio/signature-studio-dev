#!/usr/bin/env python3
# N5/N6 文字列 blob (NUL 区切り範囲) を読む関数 (読み手) と、その呼び出し元を走査する。
# usage: python3 work/dll_scan.py [PE path]
import bisect
import struct
import sys

import capstone
import numpy as np
import pefile

PATH = sys.argv[1] if len(sys.argv) > 1 else "work/key/extracted/Native Instruments/Massive X.dll"
data = open(PATH, "rb").read()
pe = pefile.PE(data=data, fast_load=True)
IB = pe.OPTIONAL_HEADER.ImageBase
print("PE", PATH, "ImageBase", hex(IB), "size", len(data))
secs = []
for s in pe.sections:
    name = s.Name.rstrip(b"\0").decode(errors="replace")
    secs.append((name, IB + s.VirtualAddress, s.SizeOfRawData, s.PointerToRawData))


def va2off(v):
    for name, va, rsz, roff in secs:
        if va <= v < va + rsz:
            return roff + (v - va)
    return None


def off2va(o):
    for name, va, rsz, roff in secs:
        if roff <= o < roff + rsz:
            return va + (o - roff)
    return None


STR_NEEDLES = [
    "Native Access to re-activate.",
    "Native Access to activate.",
    "Native Access can't be found.",
    "Native Access to enter the correct serial number.",
    "demoExpired",
    "demoExpiredChanged",
    "subscriptionExpired",
]
blobs = {}  # (lo, hi) -> needle
for n in STR_NEEDLES:
    i = data.find(n.encode())
    while i != -1:
        va = off2va(i)
        if va is not None:
            s = i
            while s > 0 and data[s - 1] != 0:
                s -= 1
            e = data.find(b"\0", i)
            lo, hi = off2va(s), off2va(s) + (e - s)
            blobs.setdefault((lo, hi), []).append(n)
        i = data.find(n.encode(), i + 1)
for (lo, hi), ns in sorted(blobs.items()):
    print(f"BLOB [{lo:#x},{hi:#x}) len {hi - lo}: {sorted(set(ns))}")

blo = sorted(blobs.keys())
blo_starts = [b[0] for b in blo]


def blob_of(v):
    i = bisect.bisect_right(blo_starts, v) - 1
    if i >= 0 and blo[i][0] <= v < blo[i][1]:
        return blo[i]
    return None


pdata = [s for s in secs if s[0] == ".pdata"][0]
raw = data[pdata[3]: pdata[3] + pdata[2]]
funcs = []
for k in range(0, len(raw) - 11, 12):
    b, e, _ = struct.unpack_from("<III", raw, k)
    if b and e > b:
        funcs.append((IB + b, IB + e))
funcs.sort()
fstarts = [f[0] for f in funcs]


def func_of(va):
    i = bisect.bisect_right(fstarts, va) - 1
    if i >= 0 and funcs[i][0] <= va < funcs[i][1]:
        return funcs[i][0]
    return None


text = [s for s in secs if s[0] == ".text"][0]
tva, toff = text[1], text[3]
tsz = text[2]
code = data[toff: toff + tsz]
print(".text", hex(tva), "size", tsz, "pdata funcs", len(funcs))

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True

refs = []         # (ins_va, dst, mnemonic, kind, blob)
call_refs = []    # (ins_va, target, mnemonic)
decoded = 0
bad = 0
pos = 0
while pos < len(code):
    chunk = code[pos: pos + 0x100000]
    base_va = tva + pos
    end = 0
    for ins in md.disasm(chunk, base_va):
        end = ins.address - base_va + ins.size
        decoded += 1
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                dst = ins.address + ins.size + op.mem.disp
                b = blob_of(dst)
                if b:
                    refs.append((ins.address, dst, ins.mnemonic, "rip", b))
            elif op.type == capstone.x86.X86_OP_IMM:
                b = blob_of(op.imm & 0xFFFFFFFFFFFFFFFF)
                if b:
                    refs.append((ins.address, op.imm, ins.mnemonic, "imm", b))
        if ins.mnemonic in ("call", "jmp") and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            call_refs.append((ins.address, ins.operands[0].imm, ins.mnemonic))
    if end == 0:
        bad += 1
    pos += end if end else 1
print(f"linear sweep: decoded {decoded} insns, bad-resync {bad}, covered {pos}/{len(code)}")

print("blob refs in .text:", len(refs))
for a, d, m, k, b in refs:
    f = func_of(a)
    print(f"  {a:#x} {m:8s} {k} -> {d:#x} blob [{b[0]:#x},{b[1]:#x}) in func {hex(f) if f else None}")

readers = sorted({func_of(a) for a, *_ in refs if func_of(a)})
print("reader funcs:", [hex(r) for r in readers])
for r in readers:
    cs = [(hex(a), m) for a, t, m in call_refs if t == r]
    print(f"  direct call/jmp to {r:#x}: {cs}")

def scan_indirect(va_targets):
    out = {t: {"abs8": [], "rva4": [], "self4": []} for t in va_targets}
    for name, va, rsz, roff in secs:
        buf = data[roff: roff + rsz]
        for t in va_targets:
            q = struct.pack("<Q", t)
            i = buf.find(q)
            while i != -1:
                out[t]["abs8"].append((name, hex(va + i)))
                i = buf.find(q, i + 1)
        for k in range(4):
            arr = np.frombuffer(buf[k: k + (len(buf) - k) // 4 * 4], dtype="<i4")
            off = va + k
            p_va = off + np.arange(arr.size, dtype=np.int64) * 4
            cand = p_va + arr.astype(np.int64)
            for t in va_targets:
                r = np.uint32((t - IB) & 0xFFFFFFFF)
                for j in np.nonzero(arr.view(np.uint32) == r)[0]:
                    out[t]["rva4"].append((name, hex(off + int(j) * 4)))
                for j in np.nonzero(cand == t)[0]:
                    out[t]["self4"].append((name, hex(int(p_va[j]))))
    return out


if readers:
    ind = scan_indirect(list(readers))
    for r in readers:
        print(f"indirect to reader {r:#x}:", {k: len(v) for k, v in ind[r].items()}, {k: v[:6] for k, v in ind[r].items()})

for b in blo:
    ind = scan_indirect([b[0]])
    print(f"indirect to blob start {b[0]:#x}:", {k: len(v) for k, v in ind[b[0]].items()}, {k: v[:4] for k, v in ind[b[0]].items()})
