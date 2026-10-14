#!/usr/bin/env python3
# DLL の .text を全バイト位置 (命令境界に依らない) で走査し、disp32/rel32 の指す先が対象 VA に入る箇所を列挙する。
# 線形・関数単位の逆アセンブルは desync (partial decode) で取りこぼすため、その穴を埋める。
# 各ヒットは「位置 q から 1 命令が復号でき、その末尾が disp32 の直後 (q+size == p+extra)」を満たすものだけ採用する。
# usage: python3 license/scripts/mx_dll_relscan.py [PE path]
import bisect
import struct
import sys

import capstone
import numpy as np
import pefile

PATH = sys.argv[1] if len(sys.argv) > 1 else "work/key/extracted/Native Instruments/Massive X.dll"
TARGETS = {
    "N6-1 0x180167a70": 0x180167A70,
    "N6-2 0x180f84920": 0x180F84920,
    "N6-3 0x181130b20": 0x181130B20,
    "N6-4 0x181130d30": 0x181130D30,
    "N6-5 0x181131000": 0x181131000,
    "N6-6 0x1811325c0": 0x1811325C0,
    "N6-7 0x181132f30": 0x181132F30,
    "N6-8 0x181133db0": 0x181133DB0,
    "N6 str 0x184fe8fa0": 0x184FE8FA0,
    "N6 str 0x184fe83b7": 0x184FE83B7,
    "N6 str 0x184fe83fc": 0x184FE83FC,
    "N6 str 0x184fe845c": 0x184FE845C,
    "N6 str 0x184fe84b3": 0x184FE84B3,
    "N6 str 0x184fe8506": 0x184FE8506,
    "N6 str 0x184fe854a": 0x184FE854A,
    "N6 str 0x184fe7870": 0x184FE7870,
    "N5 demoExpired 0x184862d19": 0x184862D19,
    "N5 demoExpiredChanged 0x184862e67": 0x184862E67,
    "N5 subscriptionExpired 0x184862e7a": 0x184862E7A,
    "N5 UTF16 MXDemoPopup 0x18414cd91": 0x18414CD91,
    "control call 0x183b27dda": 0x183B27DDA,
    "control call 0x184021d48": 0x184021D48,
}
EXTRAS = (4, 5, 8)

data = open(PATH, "rb").read()
pe = pefile.PE(data=data, fast_load=True)
IB = pe.OPTIONAL_HEADER.ImageBase
S = {}
for s in pe.sections:
    S.setdefault(s.Name.rstrip(b"\0").decode(errors="replace"), []).append(s)
text = S[".text"][0]
tva = IB + text.VirtualAddress
toff = text.PointerToRawData
tbytes = data[toff: toff + text.Misc_VirtualSize]
pd = S[".pdata"][0]
praw = data[pd.PointerToRawData: pd.PointerToRawData + pd.SizeOfRawData]
funcs = sorted({(IB + b, IB + e) for b, e, _ in struct.iter_unpack("<III", praw[: len(praw) // 12 * 12]) if b and e > b})
fst = [f[0] for f in funcs]


def owner(va):
    i = bisect.bisect_right(fst, va) - 1
    if i >= 0 and funcs[i][0] <= va < funcs[i][1]:
        return hex(funcs[i][0])
    return "outside-pdata"


md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
b = np.frombuffer(tbytes, dtype=np.uint8)
tset = np.array(sorted(TARGETS.values()), dtype=np.int64)
rev = {v: k for k, v in TARGETS.items()}
raw = {(e, t): [] for e in EXTRAS for t in TARGETS.values()}
CH = 1 << 23
n = len(b) - 3
for s in range(0, n, CH):
    e = min(n, s + CH)
    w = np.zeros(e - s, dtype=np.uint32)
    for k in range(4):
        w |= b[s + k: e + k].astype(np.uint32) << (8 * k)
    rel = w.view(np.int32).astype(np.int64)
    pos = tva + np.arange(s, e, dtype=np.int64)
    for ex in EXTRAS:
        tgt = pos + ex + rel
        for i in np.nonzero(np.isin(tgt, tset))[0]:
            raw[(ex, int(tgt[i]))].append(int(pos[i]))

def data_ptr_hits(target_va):
    # 絶対 8B (VA) / RVA 4B を全ファイルの全バイト位置で走査する (間接参照・関数ポインタ・文字列 index 表の候補)
    out = []
    arr = np.frombuffer(data, dtype=np.uint8)
    for width, val in ((8, target_va), (4, target_va - IB)):
        if val < 0 or val >= 1 << (8 * width):
            continue
        want = np.frombuffer(val.to_bytes(width, "little"), dtype=np.uint8)
        m = np.ones(len(arr) - width + 1, dtype=bool)
        for k in range(width):
            m &= arr[k: len(arr) - width + 1 + k] == want[k]
        for off in np.nonzero(m)[0]:
            out.append((width, int(off)))
    return out


def sec_of(off):
    for s in pe.sections:
        if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
            return s.Name.rstrip(b"\0").decode(errors="replace"), IB + s.VirtualAddress + off - s.PointerToRawData
    return "?", None


print("scan bytes", len(tbytes), "functions(pdata0)", len(funcs))
for name, t in TARGETS.items():
    hs = data_ptr_hits(t)
    desc = []
    for width, off in hs:
        sn, va = sec_of(off)
        desc.append(f"abs8/rva4 {'8B' if width == 8 else '4B'} at {va:#x} in {sn}" if va else f"{width}B at file off {off:#x}")
    print(f"ptr {name}: {len(hs)} hits", desc)
for t in sorted(TARGETS.values()):
    line = []
    print(f"{rev[t]}:")
    for ex in EXTRAS:
        ps = raw[(ex, t)]
        ok = []
        for p in ps:
            off = p - tva
            for q in range(max(0, off - 12), off + 1):
                ins = next(md.disasm(tbytes[q: q + 15], tva + q), None)
                if ins and ins.address + ins.size == p + ex and ins.address <= p:
                    ok.append((p, ex, ins.mnemonic, ins.op_str, owner(p)))
                    break
        line.append((ex, len(ps), len(ok)))
        for p, ex_, mn, op, ow in ok:
            print(f"   insn {p:#x} extra{ex_} {mn} {op} in {ow}")
    print("   raw/insn by extra:", line)
