#!/usr/bin/env python3
# DLL の .text を全バイト位置 (命令境界に依らない) で走査し、disp32/rel32 の指す先が対象 VA に入る箇所を列挙する。
# 線形・関数単位の逆アセンブルは desync (partial decode) で取りこぼすため、その穴を埋める。
# 各ヒットは「位置 q から 1 命令が復号でき、先頭が disp32 より前 (q < p)・その末尾が disp32 の直後 (q+size == p+extra)」を満たすものだけ採用する。
# 絶対 8B・RVA 4B・自己相対 4B は全ファイルの全バイト位置で走査する。
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
    "N6 blob-head 0x184fe8fa0": 0x184FE8FA0,
    "N6 blob-head 0x184fe83b7": 0x184FE83B7,
    "N6 blob-head 0x184fe83fc": 0x184FE83FC,
    "N6 blob-head 0x184fe845c": 0x184FE845C,
    "N6 blob-head 0x184fe84b3": 0x184FE84B3,
    "N6 blob-head 0x184fe8506": 0x184FE8506,
    "N6 blob-head 0x184fe854a": 0x184FE854A,
    "N6 blob-head 0x184fe7870": 0x184FE7870,
    "N6 str 0x184fe83de": 0x184FE83DE,
    "N6 str 0x184fe843e": 0x184FE843E,
    "N6 str 0x184fe8495": 0x184FE8495,
    "N6 str 0x184fe84e8": 0x184FE84E8,
    "N6 str 0x184fe852c": 0x184FE852C,
    "N6 str 0x184fe8587": 0x184FE8587,
    "N5 demoExpired 0x184862d19": 0x184862D19,
    "N5 demoExpiredChanged 0x184862e67": 0x184862E67,
    "N5 subscriptionExpired 0x184862e7a": 0x184862E7A,
    "N5 UTF16 MXDemoPopup 0x18414cd91": 0x18414CD91,
    "control call 0x183b27dda": 0x183B27DDA,
    "control call 0x184021d48": 0x184021D48,
}
EXTRAS = (4, 5, 6, 8)

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


maxend = []
for _, e in funcs:
    maxend.append(max(e, maxend[-1]) if maxend else e)


def owner(va):
    # 不正な長い範囲 (end が .text の外) に入る関数も拾うため、end の前方最大値が va を超える間は手前へ遡る
    i = bisect.bisect_right(fst, va) - 1
    while i >= 0 and maxend[i] > va:
        if funcs[i][0] <= va < funcs[i][1]:
            return hex(funcs[i][0])
        i -= 1
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


def selfrel_hits():
    # 自己相対 4B: フィールド自身の VA f に対し、4B 値 v が f + v == 対象 VA を満たす箇所を全セクションの生データで走査する
    out = {t: [] for t in TARGETS.values()}
    arr = np.frombuffer(data, dtype=np.uint8)
    for sec in pe.sections:
        r0 = sec.PointerToRawData
        r1 = min(r0 + sec.SizeOfRawData, len(data)) - 3
        f0 = IB + sec.VirtualAddress
        for s in range(r0, r1, CH):
            e = min(r1, s + CH)
            w = np.zeros(e - s, dtype=np.uint32)
            for k in range(4):
                w |= arr[s + k: e + k].astype(np.uint32) << (8 * k)
            fva = f0 + np.arange(s - r0, e - r0, dtype=np.int64)
            tgt = fva + w.view(np.int32).astype(np.int64)
            for i in np.nonzero(np.isin(tgt, tset))[0]:
                out[int(tgt[i])].append(s + int(i))
    return out


def neighbors(off, va):
    # 自己相対の表と見なせるか: 前後 24 entry (4B 刻み) のうち、値が .text を指す数と関数先頭 (.pdata の begin) を指す数
    nt = nf = 0
    fset = set(fst)
    for k in list(range(-24, 0)) + list(range(1, 25)):
        o = off + 4 * k
        if 0 <= o and o + 4 <= len(data):
            t = va + 4 * k + struct.unpack_from("<i", data, o)[0]
            nt += tva <= t < tva + len(tbytes)
            nf += t in fset
    return nt, nf


def sec_of(off):
    for s in pe.sections:
        if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
            return s.Name.rstrip(b"\0").decode(errors="replace"), IB + s.VirtualAddress + off - s.PointerToRawData
    return "?", None


def pdata_report():
    t0, t1 = tva, tva + len(tbytes)
    xs = S[".xdata"][0]
    x0, x1 = IB + xs.VirtualAddress, IB + xs.VirtualAddress + xs.Misc_VirtualSize
    for i, ps in enumerate(S[".pdata"]):
        raw = data[ps.PointerToRawData: ps.PointerToRawData + ps.SizeOfRawData]
        ents = list(struct.iter_unpack("<III", raw[: len(raw) // 12 * 12]))
        nz = sum(1 for b, e, u in ents if b or e or u)
        val = sorted((IB + b, IB + e, IB + u) for b, e, u in ents if b and e > b)
        bt = sum(t0 <= b < t1 for b, _, _ in val)
        et = sum(t0 <= e < t1 for _, e, _ in val)
        ux = sum(x0 <= IB + u < x1 for b, e, u in ents if b or e or u)
        bad = [not (t0 <= e < t1) for _, e, _ in val]
        ov = [a for a in range(len(val) - 1) if val[a + 1][0] < val[a][1]]
        ov_bad = sum(1 for a in ov if bad[a] or bad[a + 1])
        uv = sorted({(b, e) for b, e, _ in val})
        ov_u = sum(1 for (_, e1), (b2, _) in zip(uv, uv[1:]) if b2 < e1)
        print(f"pdata#{i} VA {IB + ps.VirtualAddress:#x} vsize {ps.Misc_VirtualSize:#x} raw {ps.PointerToRawData:#x} "
              f"file-entries {len(ents)} nonzero {nz} valid {len(val)} begin-in-text {bt} end-in-text {et} "
              f"bad-end {len(val) - et} unwind-in-xdata {ux} overlap-adjacent {len(ov)} (with-bad-end {ov_bad}) "
              f"unique {len(uv)} unique-overlap-adjacent {ov_u}")


print("scan bytes", len(tbytes), "functions(pdata0)", len(funcs))
pdata_report()
for name, t in TARGETS.items():
    hs = data_ptr_hits(t)
    desc = []
    for width, off in hs:
        sn, va = sec_of(off)
        desc.append(f"abs8/rva4 {'8B' if width == 8 else '4B'} at {va:#x} in {sn}" if va else f"{width}B at file off {off:#x}")
    print(f"ptr {name}: {len(hs)} hits", desc)
SR = selfrel_hits()
for t in TARGETS.values():
    desc = []
    for off in SR[t]:
        sn, va = sec_of(off)
        nt, nf = neighbors(off, va)
        desc.append(f"at {va:#x} in {sn} (va%4={va % 4}, neighbors24 in-.text={nt} func-start={nf})")
    print(f"selfrel4 {rev[t]}: {len(SR[t])} hits", desc)
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
                if ins and ins.address + ins.size == p + ex and ins.address < p:
                    ok.append((p, ex, ins.mnemonic, ins.op_str, owner(p)))
                    break
        line.append((ex, len(ps), len(ok)))
        for p, ex_, mn, op, ow in ok:
            print(f"   insn {p:#x} extra{ex_} {mn} {op} in {ow}")
    print("   raw/insn by extra:", line)
