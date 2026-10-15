#!/usr/bin/env python3
"""WaveformColouring 閉包の SEH except 本体 (0x1b8eb1–0x1b8ec9) と閉包混入 0x1ac9b8 の到達を計算する (T-SH-134 / #5090)。

usage: seh_reach.py PE CLOSURE_JSON
  PE           : block24360_PE.bin
  CLOSURE_JSON : ildsp_closure.py の出力 (既定 tools/shared/work/raw/ildsp_closure.json)
出力はすべて計算結果。判定文は出さない (解釈は REPORT に書く)。
  A. 0x1b8e68 の SEH スコープ表
  B. filter 0x1ccb00 の cmp 比較値
  C. try 関数 0x1b8e68 の直接 call 元
  D. 閉包の根 (export 入口 + vtable slot 先) から、閉包内の直接 edge で到達する命令集合 R
     - 直接 call/jmp/jcc の先が閉包外なら辿らず記録する。間接 call/jmp は記録して止まる
  E. except 本体への直接参照 (E8/E9/0F 8x を .text 全体で走査)
  F. except 本体 RVA / 絶対アドレスを値として持つ 4/8 バイトの出現 (全 section・未判定)
直接参照は E8/E9 と 0F 8x のバイト走査で数える (リニア逆アセンブルは同期ずれで取りこぼすため)。
"""
import sys, struct, bisect, json
import pefile, capstone

PE, CLO = sys.argv[1], sys.argv[2]
TRY_FN = 0x1b8e68
FILTER = 0x1ccb00
EXCEPT_LO, EXCEPT_HI = 0x1b8eb1, 0x1b8ec9
ENTRY = 0x1ac460
ALLOC = 0x1ac9b0
DEAD = 0x1ac9b8

pe = pefile.PE(PE, fast_load=True)
img = pe.get_memory_mapped_image()
IB = pe.OPTIONAL_HEADER.ImageBase
text = {s.Name.rstrip(b"\0").decode(): s for s in pe.sections}[".text"]
T0 = text.VirtualAddress
T1 = T0 + text.Misc_VirtualSize
exc = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]]
funcs = {}
for i in range(exc.Size // 12):
    b, e, u = struct.unpack_from("<III", img, exc.VirtualAddress + i * 12)
    funcs[b] = (e, u)
fs = sorted(funcs)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
row = next(r for r in json.load(open(CLO))["exports"] if r["export"] == "WaveformColouring_CreateInstance")
clo = {int(x, 16) for x in row["vtable"]["function_rvas"]}


def owner(t):
    i = bisect.bisect_right(fs, t) - 1
    return fs[i] if i >= 0 and t < funcs[fs[i]][0] else None


def in_clo(t):
    return t in clo or owner(t) in clo


def where(f):
    return "閉包内" if f in clo else "閉包外"


def insn(a):
    for i in md.disasm(bytes(img[a:a + 16]), IB + a):
        return i
    return None


def direct_refs(targets):
    """.text 内の E8/E9 (call/jmp rel32) と 0F 8x (jcc rel32) を走査し、target 集合への参照 (site, kind) を返す。"""
    data = bytes(img[T0:T1])
    out = []
    for k in range(len(data) - 6):
        op = data[k]
        if op in (0xE8, 0xE9):
            t = T0 + k + 5 + struct.unpack_from("<i", data, k + 1)[0]
            if t in targets:
                out.append((T0 + k, "call" if op == 0xE8 else "jmp"))
        elif op == 0x0F and 0x80 <= data[k + 1] <= 0x8F:
            t = T0 + k + 6 + struct.unpack_from("<i", data, k + 2)[0]
            if t in targets:
                out.append((T0 + k, "jcc"))
    return out


def reach(roots):
    R, ext, ind = set(), [], []
    work = list(roots)
    while work:
        a = work.pop()
        if a in R:
            continue
        i = insn(a)
        if i is None:
            continue
        R.add(a)
        m, nxt = i.mnemonic, a + i.size
        if m in ("ret", "int3", "ud2"):
            continue
        if not (m == "call" or m == "jmp" or m.startswith("j")):
            work.append(nxt)
            continue
        if not i.op_str.startswith("0x"):
            ind.append(a)
            if m == "call":
                work.append(nxt)
            continue
        t = int(i.op_str, 16) - IB
        if in_clo(t):
            work.append(t)
        else:
            ext.append((a, m, t))
        if m != "jmp":
            work.append(nxt)
    return R, ext, ind


print("## A. SEH スコープ表 (try 関数 0x%x)" % TRY_FN)
_, u = funcs[TRY_FN]
flags = img[u] >> 3
ncodes = img[u + 2]
p = u + 4 + (((ncodes + 1) & ~1) * 2)
if flags & 1:
    handler = struct.unpack_from("<I", img, p)[0]
    n = struct.unpack_from("<I", img, p + 4)[0]
    print("handler 0x%x scope=%d" % (handler, n))
    for k in range(n):
        beg, end, filt, tgt = struct.unpack_from("<IIII", img, p + 8 + 16 * k)
        print("try 0x%x-0x%x filter=0x%x except=0x%x" % (beg, end, filt, tgt))
else:
    print("EHANDLER なし")

print("\n## B. filter 0x%x の cmp 比較値" % FILTER)
ins = list(md.disasm(bytes(img[FILTER:FILTER + 0x30]), IB + FILTER))
codes = [i.op_str.split(", ")[1] for i in ins if i.mnemonic == "cmp" and i.op_str.startswith("dword ptr [rax], ")]
print("cmp 比較値:", codes)

print("\n## C. try 関数 0x%x の直接 call 元" % TRY_FN)
for site, kind in direct_refs({TRY_FN}):
    if kind == "call":
        f = owner(site)
        print("call 0x%x (owner 0x%x, %s)" % (site, f or 0, where(f) if f else "pdata 外"))

print("\n## D. 閉包の根から閉包内の直接 edge で到達する命令集合")
ROOTS = sorted({int(row["entry_rva"], 16)} | {int(t["target_rva"], 16) for t in row["vtable"]["targets"]})
print("根: %d 件 (export 入口 %s + vtable slot 先)" % (len(ROOTS), row["entry_rva"]))
R, ext_edges, indirect = reach(ROOTS)
print("到達命令数: %d" % len(R))
print("0x%x (ALLOC) ∈ R: %s" % (ALLOC, ALLOC in R))
print("0x%x (DEAD) ∈ R: %s" % (DEAD, DEAD in R))
print("R 内で except 本体 0x%x–0x%x に入る命令: %s" % (EXCEPT_LO, EXCEPT_HI, sorted(hex(x) for x in R if EXCEPT_LO <= x < EXCEPT_HI) or "なし"))
print("閉包外への直接 call/jmp/jcc: %d 件 (辿らない)" % len(ext_edges))
for a, m, t in ext_edges[:10]:
    print("  0x%x %s -> 0x%x" % (a, m, t))
print("R 内の間接 call/jmp: %d 件" % len(indirect))
print("ALLOC 0x%x の命令: %s %s" % (ALLOC, insn(ALLOC).mnemonic, insn(ALLOC).op_str))

for tgt_name, tgt in (("ALLOC", ALLOC), ("DEAD", DEAD)):
    print("\n## D'. 0x%x (%s) への直接参照 (全 .text)" % (tgt, tgt_name))
    refs = direct_refs({tgt})
    n_in = 0
    for site, kind in refs:
        f = owner(site)
        if site in R or (f in clo):
            n_in += 1
        print("  0x%x (%s) owner=%s %s" % (site, kind, hex(f) if f else "pdata 外", where(f) if f else ""))
    print("%d 件 (うち参照元が閉包内: %d 件)" % (len(refs), n_in))

print("\n## E. except 本体 0x%x–0x%x への直接参照 (全 .text)" % (EXCEPT_LO, EXCEPT_HI))
ex = direct_refs(set(range(EXCEPT_LO, EXCEPT_HI)))
print("%d 件 (call/jmp/jcc のみ)" % len(ex))
for site, kind in ex:
    print("  0x%x (%s)" % (site, kind))

print("\n## F. except 本体 RVA / 絶対アドレスを値として持つ 4/8 バイトの出現 (全 section・未判定)")
hits = []
for sec in pe.sections:
    name = sec.Name.rstrip(b"\0").decode(errors="replace")
    base = sec.VirtualAddress
    data = bytes(img[base:base + sec.Misc_VirtualSize])
    for r in range(EXCEPT_LO, EXCEPT_HI):
        for pat, width in ((struct.pack("<I", r), 4), (struct.pack("<Q", IB + r), 8)):
            pos = data.find(pat)
            while pos >= 0:
                hits.append((name, base + pos, r, width))
                pos = data.find(pat, pos + 1)
print("%d 件" % len(hits))
for name, at, r, width in hits:
    print("  %s 0x%x: %d byte 値 0x%x" % (name, at, width, r))
