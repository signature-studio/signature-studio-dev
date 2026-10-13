#!/usr/bin/env python3
"""SR-3 step 5: independent check of a library window with upstream string literals (different evidence class from the
window growth, which only uses call-graph linkage).
For each upstream C string literal (len>=MINLEN, from <upstream .c>) found in the binary's .rdata, find the functions that
reference it (rip-relative index).  Report how many of those functions fall inside the cut-table window of <lib>
(precision) and how many upstream-literal-referencing functions lie in the window (coverage of window by evidence).
Negative control: same count for same-size windows placed at shifted positions (+-1x, +-2x, +-3x window span).
usage: sr3_verify_strings.py <pe> <index.npz> <cut_table.tsv> <lib> <upstream.c> [--minlen N]"""
import sys, re, bisect
import numpy as np
import pefile

PATH, IDX, CUT, LIB, SRC = sys.argv[1:6]
MINLEN = int(sys.argv[sys.argv.index('--minlen') + 1]) if '--minlen' in sys.argv else 10
IMG = 0x180000000
pe = pefile.PE(PATH, fast_load=True)
raw = open(PATH, 'rb').read()
S = {s.Name.rstrip(b'\0').decode(): s for s in pe.sections}
rd = S['.rdata']; ro, rs, rv = rd.PointerToRawData, rd.SizeOfRawData, rd.VirtualAddress
rdata = raw[ro:ro + rs]
z = np.load(IDX); funcs = z['funcs']; refs = z['refs']; fs = funcs[:, 0].tolist()
rip = refs[refs[:, 2] == 0]; order = np.argsort(rip[:, 1], kind='stable'); rt = rip[order, 1]; rsrc = rip[order, 0]


def fi(rva):
    i = bisect.bisect_right(fs, rva) - 1
    return i if i >= 0 and funcs[i][0] <= rva < funcs[i][1] else -1


src = open(SRC, encoding='latin1').read()
lits = set()
for m in re.finditer(r'"((?:[^"\\\n]|\\.){%d,})"' % MINLEN, src):
    s = m.group(1)
    if '\\' in s or '%' in s: continue
    lits.add(s)
win = {}  # func idx -> True for lib
for ln in list(open(CUT))[1:]:
    va, by, lib, tag = ln.rstrip('\n').split('\t')
    if lib == LIB: win[fi(int(va, 16) - IMG)] = tag
widx = sorted(win)
print(f"{LIB}: upstream literals(len>={MINLEN}, no escapes/%)={len(lits)}  window funcs={len(widx)}")

lit_funcs = {}  # literal -> set(func idx)
for s in lits:
    b = s.encode('latin1')
    for m in re.finditer(re.escape(b + b'\0'), rdata):
        if m.start() > 0 and rdata[m.start() - 1] != 0: continue  # whole-literal start only
        rva = rv + m.start()
        lo = np.searchsorted(rt, rva, 'left'); hi = np.searchsorted(rt, rva + 1, 'left')  # exact start only: lld tail-merges suffixes (e.g. '...qualified name' -> 'name')
        fl = {fi(int(x)) for x in rsrc[lo:hi]} - {-1}
        if fl: lit_funcs.setdefault(s, set()).update(fl)
tot_f = {f for v in lit_funcs.values() for f in v}
inw = {f for f in tot_f if f in win}
print(f"literals present in .rdata and referenced from code: {len(lit_funcs)}; distinct referencing funcs: {len(tot_f)}; inside window: {len(inw)} ({100*len(inw)/max(1,len(tot_f)):.1f}%)")
cov = len([f for f in widx if f in tot_f])
print(f"window funcs referencing >=1 upstream literal: {cov}/{len(widx)} ({100*cov/max(1,len(widx)):.1f}%)")
outside = sorted(tot_f - set(win))
ob = sum(int(funcs[f][1] - funcs[f][0]) for f in outside)
print(f"outside-window referencing funcs: {len(outside)} ({ob} B)")
for f in outside:
    ls_ = [s for s, fl in lit_funcs.items() if f in fl]
    print(f"  OUT {hex(IMG + fs[f])} {int(funcs[f][1] - funcs[f][0])}B  {ls_[0][:48]!r}{' +%d' % (len(ls_) - 1) if len(ls_) > 1 else ''}")
span = widx[-1] - widx[0] + 1
print("negative control (same-size index window shifted; upstream-literal-referencing funcs inside):")
for sh in (-3, -2, -1, 1, 2, 3):
    lo = widx[0] + sh * span; hi = lo + span - 1
    if lo < 0 or hi >= len(fs): continue
    n = len([f for f in tot_f if lo <= f <= hi])
    print(f"  shift {sh:+d}x -> {n} funcs")
