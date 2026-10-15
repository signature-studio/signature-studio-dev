#!/usr/bin/env python3
"""ks_filter_scen_cmp.py <sc.txt> <kh.txt> — Filter の SC (native_filter) と KH (ks_semantic_filter_kh scen) を同一シナリオの出力で比べる。
出力の並びは両側とも call ごとに " |" + S+0x98(8B) + S+0xa0(0x200) + S+0x4a0(0x200) + S+0xca0(0x670) + " " L " " R。
判定は bit 一致 (hex 文字列の一致)。state 領域の差は領域名ごとに数える。
語 (4 B) 単位の不一致数も数える。相対差は float32 として読んだ値で |SC−KH|/|KH| (KH 基準。KH が 0 なら SC≠0 を無限大扱い)。
相対差 > 1e-3 の語数は整数型・ポインタを含む領域でも同じ式で数える (意味のある相対差は arr 領域の浮動小数点語)。"""
import math
import struct
import sys

HEAD = [("sr S+0x98/KH+0x60", 16), ("arr S+0xa0/KH+0x70", 0x400), ("arr S+0x4a0/KH+0x470", 0x400), ("ctx S+0xca0/KH+0xc70", 0x670 * 2)]

def rel_gt(xa, xb, tol=1e-3):
    a = struct.unpack("<f", bytes.fromhex(xa))[0]
    b = struct.unpack("<f", bytes.fromhex(xb))[0]
    if math.isnan(a) or math.isnan(b):
        return True
    if b == 0.0:
        return a != 0.0
    return abs(a - b) / abs(b) > tol

def calls(line):
    parts = line.rstrip("\n").split(" |")
    head_id, body = parts[0], parts[1:]
    out = []
    for seg in body:
        off = 0; fields = []
        for name, ln in HEAD:
            fields.append((name, seg[off:off + ln])); off += ln
        rest = seg[off:].split(" ")
        out.append((fields, rest[1], rest[2]))
    return head_id, out

sc = open(sys.argv[1]).read().splitlines()
kh = open(sys.argv[2]).read().splitlines()
assert len(sc) == len(kh), (len(sc), len(kh))
ncall = 0; lr_bad = 0; fld_bad = {n: 0 for n, _ in HEAD}; first_bad = {}
word_bad = {n: 0 for n, _ in HEAD}; word_rel = {n: 0 for n, _ in HEAD}
for a, b in zip(sc, kh):
    ida, ca = calls(a); idb, cb = calls(b)
    assert ida == idb and len(ca) == len(cb), (ida, idb)
    for (fa, la, ra), (fb, lb, rb) in zip(ca, cb):
        ncall += 1
        if la != lb or ra != rb: lr_bad += 1
        for (name, xa), (_, xb) in zip(fa, fb):
            if xa != xb:
                fld_bad[name] += 1
                if name not in first_bad:
                    i = next(i for i in range(min(len(xa), len(xb))) if xa[i] != xb[i]) // 2
                    first_bad[name] = (ida, i)
                for w in range(0, min(len(xa), len(xb)), 8):
                    if xa[w:w + 8] != xb[w:w + 8]:
                        word_bad[name] += 1
                        if rel_gt(xa[w:w + 8], xb[w:w + 8]):
                            word_rel[name] += 1
print(f"scenarios={len(sc)} calls={ncall}")
print(f"L/R bit mismatch calls={lr_bad}")
for n, _ in HEAD:
    print(f"state field mismatch [{n}]: calls={fld_bad[n]} first(scen,byte)={first_bad.get(n)}")
for n, _ in HEAD:
    print(f"state word mismatch [{n}]: words={word_bad[n]} rel>1e-3 (|SC-KH|/|KH|)={word_rel[n]}")
