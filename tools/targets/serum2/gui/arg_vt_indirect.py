#!/usr/bin/env python3
"""SR-82 #4930: ARG / ARG-CHILD の所属関数 F の vtable 位置 (表の先頭 h・index k) を、間接 call `call [reg+8k]` の候補として列挙する (静的)。

入力: Serum2_win64.vst3 (PE)。trace.tsv (receiver_this_trace.py --tsv 出力)。
方法:
  1. F の入口を指す .rdata/.data の 8 byte slot を探し、arg_vtable_callers.py と同じ窓 (HEAD_WINDOW) で表の先頭 h・index k を得る。
  2. .text 内の `call qword ptr [reg + 8k]` を列挙する (同じ disp を持つ別クラスの呼出も含むため候補)。
  3. 候補の呼出元 C が SerumController (R.SC) の関数かを数える。
限界: 候補の宛先 (reg の指す object の型) は確定しない。引数の型の確定には使えない。
usage: arg_vt_indirect.py <pe> <trace.tsv> [--tsv out.tsv]
"""
import contextlib
import io
import os
import re
import struct
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ARGS = sys.argv
pe_path, tsv_in = ARGS[1], ARGS[2]
TSV = ARGS[ARGS.index("--tsv") + 1] if "--tsv" in ARGS else None

sys.argv = [sys.argv[0], pe_path]
with contextlib.redirect_stdout(io.StringIO()):
    import receiver_this_trace as R

import pefile

HEAD_WINDOW = 4096
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


targets = set()
with open(tsv_in) as f:
    next(f)
    for line in f:
        cols = line.rstrip("\n").split("\t")
        if cols[4] in ("vptr:ARG", "vptr:ARG-CHILD"):
            targets.add(int(cols[1], 16))

slot_hits = defaultdict(list)
for name in (b".rdata", b".data"):
    s = sec(name)
    raw = data[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
    for o in range(0, len(raw) - 7, 8):
        v = struct.unpack_from("<Q", raw, o)[0]
        if v in targets:
            slot_hits[v].append(IMG + s.VirtualAddress + o)

ind_re = re.compile(r"qword ptr \[(\w+) \+ (0x[0-9a-f]+)\]")
sites_by_disp = defaultdict(list)
for ins in R.ins_all:
    if ins.mnemonic != "call":
        continue
    m = ind_re.search(ins.op_str)
    if m:
        sites_by_disp[int(m.group(2), 16)].append(ins.address)

rows = []
for F in sorted(targets):
    seen = set()
    for sv in slot_hits.get(F, []):
        h, k, cname = find_head(sv)
        if h is None or k in seen:
            continue
        seen.add(k)
        disp = 8 * k
        sites = sites_by_disp.get(disp, [])
        sc_sites = sum(1 for a in sites if R.func_of(a) in R.SC)
        rows.append((F, h, k, disp, len(sites), sc_sites, cname))

n_f = len(targets)
n_f_slot = len({r[0] for r in rows})
n_cand = sum(r[4] for r in rows)
n_cand_sc = sum(r[5] for r in rows)
print(f"ARG 系の所属関数 = {n_f} 個 / 表の slot に現れる = {n_f_slot} 個")
print(f"間接 call の候補 (slot × 先頭ごと) = {n_cand} 件 / うち呼出元が SerumController = {n_cand_sc} 件 (宛先の型は未確定)")
if TSV:
    with open(TSV, "w") as fh:
        fh.write("func\tvtable_head\tindex\tdisp\tn_sites\tn_sites_sc\trtti\n")
        for F, h, k, d, n, nsc, cname in rows:
            fh.write(f"{F:#x}\t{h:#x}\t{k}\t{d:#x}\t{n}\t{nsc}\t{cname}\n")
