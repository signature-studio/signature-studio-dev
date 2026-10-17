#!/usr/bin/env python3
"""PY-6005 (#6005): 0x104b305 (G4) の py88 式の値を、py88・ExpSlicer を通さずに独立に検算する。

  python3 analysis/py6005_g4_value_check.py <work/py53/fn.txt> <block00031_PE.bin>

1. fn.txt の線形列から、[rbp+0x5b8] への store のうち 0x104b2f2 へ届くものを簡易 CFG で数える (期待 1 本 = 0x1046d6b)。
2. その store の値 (edx) が 0x1046d6b までに書き換わらないことを、区間内の命令で確かめる。
3. 0x10469f0 の命令 (cvtsi2sd・mulsd・cvtsd2si) を、PE の定数 M64[0x1046a20] を読んだ値で模し、
   手計算式 0 + rint(M64[0x1046a20] · d_in · (0x3e80 − 0)) と値で比べる。
exit 0 = 一致、1 = 不一致。
"""
import re
import struct
import sys

import pefile

STORE_ECX = 0x104B2F2  # mov ecx, [rbp+0x5b8] (G4 の ecx)
STORE_HAND = 0x1046D6B  # mov [rbp+0x5b8], edx (届く store の期待値)
CONST_VA = 0x1046A20
RANGE = (0x1046A30, 0x1046D6B)  # 関数先頭から store まで


def load_rows(path):
    rows = []
    for ln in open(path):
        m = re.match(r"(0x[0-9a-f]+): (.*)", ln.rstrip("\n"))
        if m:
            rows.append((int(m.group(1), 16), m.group(2)))
    return rows


def reaching_stores(rows, target):
    addrs = [a for a, _ in rows]
    text = dict(rows)
    succ = {}
    for i, (a, t) in enumerate(rows):
        nxt = addrs[i + 1] if i + 1 < len(addrs) else None
        mn = t.split()[0]
        m = re.search(r"0x([0-9a-f]+)", t)
        tgt = int(m.group(1), 16) if mn.startswith("j") and m else None
        if mn == "jmp":
            s = [tgt] if tgt else []
        elif mn.startswith("j"):
            s = [x for x in (tgt, nxt) if x is not None]
        elif mn in ("ret", "int3"):
            s = []
        else:
            s = [nxt] if nxt is not None else []
        succ[a] = s

    def is_store(t):
        return t.startswith("mov dword ptr [rbp + 0x5b8]")

    hits = []
    for s0, t0 in rows:
        if not is_store(t0):
            continue
        seen, stack, hit = set(), list(succ.get(s0, [])), False
        while stack:
            x = stack.pop()
            if x is None or x in seen:
                continue
            seen.add(x)
            if x == target:
                hit = True
                continue
            if is_store(text.get(x, "")):
                continue
            stack.extend(succ.get(x, []))
        if hit:
            hits.append(s0)
    return hits


def edx_untouched(rows, lo, hi):
    implicit = ("call", "cdq", "cqo", "cwd", "mul", "div", "idiv")
    for a, t in rows:
        if not (lo <= a < hi):
            continue
        mn = t.split()[0]
        dst = t[len(mn):].split(",")[0]
        if mn in implicit or re.search(r"\b(edx|rdx)\b", dst) and mn not in ("cmp", "test"):
            return False, a
    return True, None


def const_m64(pe_path):
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.startswith(b".text")][0]
    off = CONST_VA - (base + text.VirtualAddress)
    return struct.unpack("<d", text.get_data()[off:off + 8])[0]


def callee(ecx, edx, r8d, c):
    # 0x10469f0: ebx=edx; xmm0=(double)ecx*c; r8d-=ebx; xmm0*=(double)r8d; call 0x40c660 (cvtsd2si = RN); eax=ebx+rounded
    ebx = edx & 0xFFFFFFFF
    r = (r8d - ebx) & 0xFFFFFFFF
    rs = r - 0x100000000 if r >= 0x80000000 else r
    x = float(ecx) * c * float(rs)
    return (ebx + round(x)) & 0xFFFFFFFF


def hand(d_in, c):
    return round(c * float(d_in) * float(0x3E80 - 0)) & 0xFFFFFFFF


def main():
    rows = load_rows(sys.argv[1])
    hits = reaching_stores(rows, STORE_ECX)
    ok_reach = hits == [STORE_HAND]
    print(f"# 到達定義 0x104b2f2 <- {[hex(h) for h in hits]} (期待 [0x1046d6b]) {'一致' if ok_reach else '不一致'}")
    ok_edx, bad = edx_untouched(rows, RANGE[0], RANGE[1])
    print(f"# 0x{RANGE[0]:x}..0x{RANGE[1]:x} で edx を書く命令: {'無し' if ok_edx else hex(bad)}")
    c = const_m64(sys.argv[2])
    print(f"# M64[0x{CONST_VA:x}] = {c!r} (2^-30 = {2.0 ** -30!r})")
    import random
    random.seed(6005)
    vals = [0, 1, -1, 2, -2, 7, 8, 9, 15, 16, 17, 1000, -1000, 2**31 - 1, -(2**31), 2**30, -(2**30)]
    vals += [random.randint(-(2**31), 2**31 - 1) for _ in range(200000)]
    mism = [v for v in vals if callee(v, 0, 0x3E80, c) != hand(v, c)]
    print(f"# 値の突合 n={len(vals)} mismatch={len(mism)}")
    ok = ok_reach and ok_edx and not mism and c == 2.0 ** -30
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
