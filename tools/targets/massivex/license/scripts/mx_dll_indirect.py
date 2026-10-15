#!/usr/bin/env python3
# usage: python3 license/scripts/mx_dll_indirect.py [PE path] [--selftest]   (tools/targets/massivex 直下で実行)
# MX-32 (#2195): N5 文字列の読み手と N6 読み手の呼び出し元を、間接参照の形式で走査する。
#   S1 文字列領域 (N5 / N6 blob) の任意 offset を指す RIP 相対参照 (変位 4・5・6・8・命令境界は後追いで検証)。
#      領域内の base + index 式の基準も拾う。絶対 8B・RVA 4B の領域内ヒット数も数える。
#   S2 RIP 相対 mem の実効先を基準 B とし、B から N 個のエントリ (4B 符号付き / 2B 符号付き・符号なし) の差分 B + d が
#      対象 VA に一致する表を列挙する。対照 VA (.pdata の関数先頭) で偶然一致率を測る。
#   S3 読み出し経路: 指定 VA (`0x181733070` ・ 表基準 `0x184021d48`) を指す RIP 相対・絶対・RVA 参照。
# 自己検査 (--selftest) は既知の参照・2B 表を検出できなければ exit 1。
import bisect
import struct
import sys

import capstone
import numpy as np
import pefile

ENTRIES = 2048
EXTRAS = (4, 5, 6, 8)
N5 = {
    "N5 demoExpired 0x184862d19": 0x184862D19,
    "N5 demoExpiredChanged 0x184862e67": 0x184862E67,
    "N5 subscriptionExpired 0x184862e7a": 0x184862E7A,
    "N5 UTF16 MXDemoPopup 0x18414cd91": 0x18414CD91,
}
N6 = {
    "N6-1 0x180167a70": 0x180167A70,
    "N6-2 0x180f84920": 0x180F84920,
    "N6-3 0x181130b20": 0x181130B20,
    "N6-4 0x181130d30": 0x181130D30,
    "N6-5 0x181131000": 0x181131000,
    "N6-6 0x1811325c0": 0x1811325C0,
    "N6-7 0x181132f30": 0x181132F30,
    "N6-8 0x181133db0": 0x181133DB0,
    "N6 blob 0x184fe8fa0": 0x184FE8FA0,
    "N6 blob 0x184fe83b7": 0x184FE83B7,
    "N6 blob 0x184fe83fc": 0x184FE83FC,
    "N6 blob 0x184fe845c": 0x184FE845C,
    "N6 blob 0x184fe84b3": 0x184FE84B3,
    "N6 blob 0x184fe8506": 0x184FE8506,
    "N6 blob 0x184fe854a": 0x184FE854A,
    "N6 blob 0x184fe7870": 0x184FE7870,
}
REGIONS = {
    "N5 blob": (0x184862000, 0x184863000),
    "N5 UTF16": (0x18414C000, 0x18414E000),
    "N6 blob": (0x184FE7000, 0x184FE9000),
    "N6 blob2": (0x184FFC000, 0x184FFE000),
}
READPATH = {"0x181733070 (self4 元)": 0x181733070, "0x184021d48 (表基準)": 0x184021D48}


def load(path):
    data = open(path, "rb").read()
    pe = pefile.PE(data=data, fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    secs = {}
    for s in pe.sections:
        secs.setdefault(s.Name.rstrip(b"\0").decode(errors="replace"), s)
    text = secs[".text"]
    tva = ib + text.VirtualAddress
    tbytes = data[text.PointerToRawData: text.PointerToRawData + text.Misc_VirtualSize]
    pd = secs[".pdata"]
    praw = data[pd.PointerToRawData: pd.PointerToRawData + pd.SizeOfRawData]
    funcs = sorted({(ib + b, ib + e) for b, e, _ in struct.iter_unpack("<III", praw[: len(praw) // 12 * 12]) if b and e > b})
    return {"data": data, "pe": pe, "ib": ib, "secs": secs, "tva": tva, "tbytes": tbytes, "funcs": funcs}


def owner_fn(funcs, va):
    fst = [f[0] for f in funcs]
    maxend = []
    for _, e in funcs:
        maxend.append(max(e, maxend[-1]) if maxend else e)
    i = bisect.bisect_right(fst, va) - 1
    while i >= 0 and maxend[i] > va:
        if funcs[i][0] <= va < funcs[i][1]:
            return hex(funcs[i][0])
        i -= 1
    return "outside-pdata"


def tbytes_ok(t, tva, tbytes):
    # call/jmp の先は .text 内でなければならない (.rdata への call は復号の誤りとして除く)
    return tva <= t < tva + len(tbytes)


def insn_ends_at(md, tbytes, tva, p, ex):
    # p の disp32 を含む RIP 相対 mem (op に rip) か、.text 内を指す rel32 の call/jmp/jcc (ex == 4) だけを採用する
    off = p - tva
    for q in range(max(0, off - 12), off + 1):
        ins = next(md.disasm(tbytes[q: q + 15], tva + q, 1), None)
        if not (ins and ins.address < p and ins.address + ins.size == p + ex):
            continue
        if "rip" in ins.op_str:
            return ins
        if ex == 4 and ins.mnemonic.startswith(("call", "j")) and ins.op_str.startswith("0x"):
            tgt = int(ins.op_str, 16)
            if tbytes_ok(tgt, tva, tbytes):
                return ins
    return None


def rip_refs(md, tbytes, tva, lo, hi, dec=True):
    # 全バイト位置 p で disp32 を変位 ex の RIP 相対 (実効先 p+ex+d) として評価し、[lo, hi) に入るものを列挙する
    b = np.frombuffer(tbytes, dtype=np.uint8)
    n = len(b) - 3
    out = []
    CH = 1 << 23
    for s in range(0, n, CH):
        e = min(n, s + CH)
        w = np.zeros(e - s, dtype=np.uint32)
        for k in range(4):
            w |= b[s + k: e + k].astype(np.uint32) << (8 * k)
        rel = w.view(np.int32).astype(np.int64)
        pos = tva + np.arange(s, e, dtype=np.int64)
        for ex in EXTRAS:
            tgt = pos + ex + rel
            for i in np.nonzero((tgt >= lo) & (tgt < hi))[0]:
                p = int(pos[i])
                ins = insn_ends_at(md, tbytes, tva, p, ex) if dec else True
                if ins:
                    out.append((p, ex, int(tgt[i]), ins if dec else None))
    return out


def ptr_hits_in_region(data, ib, sections, lo, hi):
    # 絶対 8B / RVA 4B の値が領域内 [lo, hi) に入る位置を全セクションの生データで数える
    res = {"abs8": [], "rva4": []}
    for sec in sections:
        raw = data[sec.PointerToRawData: sec.PointerToRawData + sec.SizeOfRawData]
        if not raw:
            continue
        a = np.frombuffer(raw, dtype=np.uint8)
        base = ib + sec.VirtualAddress
        for width in (8, 4):
            if len(a) < width:
                continue
            vals = np.zeros(len(a) - width + 1, dtype=np.uint64)
            for k in range(width):
                vals |= a[k: len(a) - width + 1 + k].astype(np.uint64) << np.uint64(8 * k)
            v = vals.astype(np.int64) if width == 8 else (vals + np.uint64(ib)).astype(np.int64)
            m = np.nonzero((v >= lo) & (v < hi))[0]
            key = "abs8" if width == 8 else "rva4"
            for i in m:
                res[key].append((base + int(i), sec.Name.rstrip(b"\0").decode(errors="replace"), int(v[i])))
    return res


def table_hits(bases, sec_va, sec_raw, targets, entries=ENTRIES):
    # bases: {B: site}. 各 B から entries 個の 4B 符号付き / 2B 符号付き・符号なし差分 d を読み、B + d ∈ targets を列挙する
    arr = np.frombuffer(sec_raw, dtype=np.uint8)
    tv = np.array(sorted(targets), dtype=np.int64)
    out = []
    kinds = (("4s", 4, np.int32), ("2s", 2, np.int16), ("2u", 2, np.uint16))
    cand = [b for b in bases if sec_va <= b and b + 4 * entries <= sec_va + len(arr)]
    ba = np.array(cand, dtype=np.int64)
    for label, width, dt in kinds:
        span = width * entries
        for c0 in range(0, len(ba), 2048):
            bb = ba[c0: c0 + 2048]
            off = bb - sec_va
            idx = off[:, None] + width * np.arange(entries, dtype=np.int64)[None, :]
            idx = np.clip(idx, 0, len(arr) - width)
            g = np.zeros(idx.shape, dtype=np.uint64)
            for k in range(width):
                g |= arr[idx + k].astype(np.uint64) << np.uint64(8 * k)
            vals = g.astype(np.uint32).view(np.int32).astype(np.int64) if width == 4 else (
                g.astype(np.uint16).view(dt).astype(np.int64))
            sums = bb[:, None] + vals
            pos = np.searchsorted(tv, sums)
            pos = np.clip(pos, 0, len(tv) - 1)
            hit = tv[pos] == sums
            for r, c in zip(*np.nonzero(hit)):
                out.append((int(tv[pos[r, c]]), int(bb[r]), label, int(c), int(bb[r]) + width * int(c), cand_site(bases, int(bb[r]))))
        del span
    return out, len(cand)


def cand_site(bases, b):
    return bases.get(b, "?")


def selftest(md):
    tva = 0x180001000
    rd = 0x180100000
    t0 = 0x180100000 + 0x40  # 対象 (2B 表で検出させる)
    code = bytearray(b"\x90" * 0x10)
    base = 0x180100000 + 0x100
    code += b"\x48\x8d\x05" + (base - (tva + len(code) + 7)).to_bytes(4, "little", signed=True)
    code += b"\x90" * 0x10
    tb = bytes(code)
    refs = rip_refs(md, tb, tva, base, base + 1, dec=True)
    ok1 = len(refs) == 1 and refs[0][2] == base
    data = bytearray(b"\x00" * 0x400)
    data[0x100 + 2 * 5: 0x100 + 2 * 5 + 2] = (t0 - base).to_bytes(2, "little", signed=True)
    hits, _ = table_hits({base: "site"}, rd, bytes(data), {t0}, entries=8)
    ok2 = any(h[0] == t0 and h[2] == "2s" and h[3] == 5 for h in hits)
    print(f"selftest rip_refs={len(refs)} (期待 1) table2s={[(hex(h[0]), h[2], h[3]) for h in hits]} (期待 2s/5)")
    ok = ok1 and ok2
    print("selftest:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(path):
    d = load(path)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False
    tva, tb, ib, funcs = d["tva"], d["tbytes"], d["ib"], d["funcs"]
    print(f"DLL {path} .text {tva:#x} size {len(tb):#x} functions(pdata#0) {len(funcs)}")
    named = {**N5, **N6}
    print("\n== S1 文字列領域を指す RIP 相対 (変位 4・5・6・8、復号できる命令のみ)")
    allrefs = []
    for rn, (lo, hi) in REGIONS.items():
        refs = rip_refs(md, tb, tva, lo, hi)
        allrefs += refs
        print(f"region {rn} [{lo:#x},{hi:#x}): {len(refs)} 件")
        for p, ex, t, ins in refs[:40]:
            print(f"   {p:#x} ex{ex} -> {t:#x} {ins.mnemonic} {ins.op_str} in {owner_fn(funcs, p)}")
    for rn, (lo, hi) in REGIONS.items():
        pr = ptr_hits_in_region(d["data"], ib, d["pe"].sections, lo, hi)
        print(f"region {rn}: abs8 {len(pr['abs8'])} 件 / rva4 {len(pr['rva4'])} 件 (全セクション・領域内の任意 offset)")
        for w, sn, v in (pr["abs8"][:8] + pr["rva4"][:8]):
            print(f"   at {w:#x} in {sn} value {v:#x}")
    print("\n== S3 読み出し経路 (指定 VA への RIP 相対・絶対・RVA)")
    for rn, t in READPATH.items():
        refs = rip_refs(md, tb, tva, t, t + 1)
        pr = ptr_hits_in_region(d["data"], ib, d["pe"].sections, t, t + 1)
        print(f"{rn} {t:#x}: RIP {len(refs)} 件 / abs8 {len(pr['abs8'])} 件 / rva4 {len(pr['rva4'])} 件")
        for p, ex, _, ins in refs[:10]:
            print(f"   {p:#x} ex{ex} {ins.mnemonic} {ins.op_str} in {owner_fn(funcs, p)}")
    print("\n== S2 表基準 (RIP 相対 mem の実効先 B → B + d が対象に一致)")
    bases = {}
    lo_ro = min(ib + s.VirtualAddress for n, s in d["secs"].items() if n in (".rdata", ".data"))
    hi_ro = max(ib + s.VirtualAddress + s.Misc_VirtualSize for n, s in d["secs"].items() if n in (".rdata", ".data"))
    for p, ex, t, ins in rip_refs(md, tb, tva, lo_ro, hi_ro):
        if "rip" not in ins.op_str:
            continue
        bases.setdefault(t, f"{p:#x}")
    print(f"base 候補 (RIP mem・.rdata/.data): {len(bases)} 件, entries = {ENTRIES} (4B 符号付き / 2B 符号付き・符号なし)")
    ctrl = {f"control N5-near {v:#x}": v for v in (0x184862D19 + 0x3 + 0x40 * k for k in range(1, 9))}
    ctrl.update({f"control N6-near {v:#x}": v for v in (0x184FE83B7 + 0x3 + 0x40 * k for k in range(1, 9))})
    targets = {**named, **ctrl}
    rev = {v: k for k, v in targets.items()}
    per = {}
    for sn, s in d["secs"].items():
        if sn not in (".rdata", ".data"):
            continue
        sva = ib + s.VirtualAddress
        raw = d["data"][s.PointerToRawData: s.PointerToRawData + s.SizeOfRawData]
        hits, nb = table_hits(bases, sva, raw, set(targets.values()))
        print(f"section {sn} base 内 {nb} 件 -> hit {len(hits)} 件")
        for h in hits:
            per.setdefault(h[0], []).append(h)
    for t, name in rev.items():
        hs = per.get(t, [])
        kind = "control" if name.startswith("control") else "target"
        print(f"{kind} {name}: {len(hs)} 件")
        for h in hs[:6]:
            print(f"   base {h[1]:#x} (site {h[5]}) {h[2]} idx {h[3]} entry@{h[4]:#x}")
    print("\n== S4 0x1838544f0 の 0x1838545bc 付近の復号 (関数先頭からの線形と、別の起点からの再同期)")
    fva = 0x1838544F0
    fo = fva - tva
    seq = []
    q = fo
    while q < fo + 0x100 and tva + q < 0x1838545d0:
        ins = next(md.disasm(tb[q: q + 15], tva + q, 1), None)
        if ins is None:
            seq.append((tva + q, "??", 1))
            q += 1
            continue
        seq.append((ins.address, ins.mnemonic + " " + ins.op_str, ins.size))
        q += ins.size
    for a, txt, sz in seq[-8:]:
        print(f"   {a:#x} {sz}B {txt}")
    target = 0x1838545BC
    for s0 in range(target - 12, target):
        q = s0 - tva
        chain = []
        while q < target + 8 - tva:
            ins = next(md.disasm(tb[q: q + 15], tva + q, 1), None)
            if ins is None:
                break
            chain.append(tva + q)
            q += ins.size
        hits_b = target in chain
        print(f"   start {s0:#x}: 境界に載る={hits_b} (0x1838545bc)  chain={[hex(x) for x in chain[-4:]]}")
    return 0


if __name__ == "__main__":
    md0 = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    if "--selftest" in sys.argv:
        sys.exit(selftest(md0))
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(main(args[0] if args else "work/key/extracted/Native Instruments/Massive X.dll"))
