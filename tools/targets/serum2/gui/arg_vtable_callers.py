#!/usr/bin/env python3
"""SR-59 #4122: 所属関数 F の入口アドレスがデータ表 (.rdata/.data の 8 byte 値) に現れる箇所を列挙し、その表 (vtable 形) の先頭・RTTI クラス名を得る (静的)。

入力: Serum2_win64.vst3 (PE, x64 MSVC)。receiver_this_trace.py の --tsv 出力 (cat_strict) を読む。
対象の分類は --cats (既定 vptr:ARG,vptr:ARG-CHILD)。
出力: 関数ごとの TSV (データ表の出現数・vtable head・index・RTTI)。
限界: F が表に現れることは「仮想関数として登録されている」ことまでしか示さない。F を呼ぶ側の引数 (rdx/r8/r9) の型は確定しない。
usage: arg_vtable_callers.py <pe> <trace.tsv> [--cats vptr:THIS,vptr:THIS-CHILD] [--tsv out.tsv]
"""
import bisect
import struct
import sys
from collections import defaultdict

import pefile

ARGS = sys.argv
pe_path, tsv_in = ARGS[1], ARGS[2]
TSV = ARGS[ARGS.index("--tsv") + 1] if "--tsv" in ARGS else None
CATS = ARGS[ARGS.index("--cats") + 1].split(",") if "--cats" in ARGS else ["vptr:ARG", "vptr:ARG-CHILD"]

pe = pefile.PE(pe_path)
data = open(pe_path, "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase


def sec(name):
    return next(s for s in pe.sections if s.Name.rstrip(b"\0") == name)


def rva_to_off(va):
    rva = va - IMG
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return rva - s.VirtualAddress + s.PointerToRawData
    return None


def rq(va):
    return struct.unpack_from("<Q", data, rva_to_off(va))[0]


def cstr(va):
    off = rva_to_off(va)
    return data[off:data.index(b"\0", off)].decode(errors="replace")


HEAD_WINDOW = 4096


def find_head(slot):
    for k in range(HEAD_WINDOW):
        h = slot - 8 * k
        col = rq(h - 8)
        if IMG <= col < IMG + 0x10000000:
            o = rva_to_off(col)
            sig, _, _, td_rva, _ = struct.unpack_from("<IIIII", data, o)
            if sig == 1:
                return h, k, cstr(IMG + td_rva + 16)
    return None, None, "?"


# 対象の関数 (ARG / ARG-CHILD の所属関数)
targets = set()
with open(tsv_in) as f:
    next(f)
    for line in f:
        cols = line.rstrip("\n").split("\t")
        if cols[4] in CATS:
            targets.add(int(cols[1], 16))

# 全データ表 (.rdata / .data) 上の 8 byte 値のうち、対象関数の入口と一致するもの
hits = defaultdict(list)
for name in (b".rdata", b".data"):
    s = sec(name)
    base_off = s.PointerToRawData
    raw = data[base_off:base_off + s.SizeOfRawData]
    for o in range(0, len(raw) - 7, 8):
        v = struct.unpack_from("<Q", raw, o)[0]
        if v in targets:
            slot_va = IMG + s.VirtualAddress + o
            hits[v].append(slot_va)

rows = []
for f in sorted(targets):
    slots = hits.get(f, [])
    if not slots:
        rows.append((f, 0, "-", None, "-"))
        continue
    for sv in slots:
        h, k, cname = find_head(sv)
        rows.append((f, len(slots), f"{h:#x}" if h else "-", k, cname))

n_hit = sum(1 for f in targets if hits.get(f))
print(f"ARG 系の所属関数 = {len(targets)} 個 / データ表に現れる = {n_hit} 個 / 現れない = {len(targets) - n_hit} 個")
sc = [r for r in rows if r[4] and "SerumController" in r[4]]
print(f"RTTI が SerumController の表に現れる関数 = {len({r[0] for r in sc})} 個")
out = sys.stdout
if TSV:
    out = open(TSV, "w")
out.write("func\tn_tables\tvtable_head\tindex\trtti\n")
for f, n, h, k, c in rows:
    out.write(f"{f:#x}\t{n}\t{h}\t{'' if k is None else k}\t{c}\n")
