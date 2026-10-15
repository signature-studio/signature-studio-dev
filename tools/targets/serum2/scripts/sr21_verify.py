#!/usr/bin/env python3
"""SR-21 independent check (no capstone).
Evidence classes it checks, separately from sr21_classify.py:
  (a) raw byte scan of .text for E8 rel32 (call) / E9 rel32 + 0F 8x rel32 (jmp/jcc) -> target set (not instruction-aligned: superset)
  (b) data pointers: 8-byte little-endian values in .rdata/.data that equal a gap-block start (vtable / fn-pointer tables)
Negative control: the same check on block_start+1 (should be ~0 hits).
usage: sr21_verify.py <pe> <sr21_classify.tsv> <cut_table.tsv>"""
import sys, bisect, csv, struct
import pefile

PE_PATH, CLS, CUT = sys.argv[1:4]
IMG = 0x180000000
pe = pefile.PE(PE_PATH, fast_load=True)
t = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
TB, TVA = t.get_data(), t.VirtualAddress
n = len(TB)

calls = set(); jmps = set()
for i in range(n - 5):
    op = TB[i]
    if op == 0xE8:
        calls.add(TVA + i + 5 + int.from_bytes(TB[i + 1:i + 5], 'little', signed=True))
    elif op == 0xE9:
        jmps.add(TVA + i + 5 + int.from_bytes(TB[i + 1:i + 5], 'little', signed=True))
    elif op == 0x0F and i + 6 <= n and 0x80 <= TB[i + 1] <= 0x8F:
        jmps.add(TVA + i + 6 + int.from_bytes(TB[i + 2:i + 6], 'little', signed=True))

ptrs = set(); runp = set()
for s in pe.sections:
    nm = s.Name.rstrip(b'\0')
    if nm in (b'.rdata', b'.data', b'_RDATA'):
        d = s.get_data()
        prev = None
        for off in range(0, len(d) - 7, 8):
            v = struct.unpack_from('<Q', d, off)[0] - IMG
            if TVA <= v < TVA + n:
                ptrs.add(v)
                if prev is not None:
                    runp.add(prev); runp.add(v)
                prev = v
            else:
                prev = None

blocks = []
with open(CLS) as f:
    for r in csv.DictReader(f, delimiter='\t'):
        blocks.append((int(r['block_va'], 16) - IMG, int(r['bytes']), r['class']))
blocks.sort()

def hits(shift):
    c = j = p = 0
    for va, sz, cls in blocks:
        q = va + shift
        if q in calls: c += 1
        if q in jmps: j += 1
        if q in ptrs: p += 1
    return c, j, p

for cls in ['entry_call', 'entry_rip', 'branch_only', 'unref', 'data']:
    rs = [b for b in blocks if b[2] == cls]
    cc = sum(1 for b in rs if b[0] in calls)
    jj = sum(1 for b in rs if b[0] in jmps)
    pp = sum(1 for b in rs if b[0] in ptrs)
    print('%-12s blocks=%-6d call_hit=%-6d jmp_hit=%-6d ptr_hit=%-6d' % (cls, len(rs), cc, jj, pp))
c, j, p = hits(0)
cn, jn, pn = hits(1)
print('ALL          blocks=%d call_hit=%d jmp_hit=%d ptr_hit=%d' % (len(blocks), c, j, p))
print('NEG_CONTROL  (start+1) call_hit=%d jmp_hit=%d ptr_hit=%d' % (cn, jn, pn))
unref_any = [b for b in blocks if b[2] in ('unref', 'data') and (b[0] in calls or b[0] in jmps or b[0] in ptrs)]
print('unref/data blocks with ANY byte-scan or ptr hit: %d' % len(unref_any))
ptr_only = [b for b in blocks if b[2] == 'table_ptr' and b[0] in ptrs]
print('table_ptr blocks hit by data pointer: %d bytes=%d' % (len(ptr_only), sum(b[1] for b in ptr_only)))
in_run = [b for b in ptr_only if b[0] in runp]
print('  of which in a consecutive pointer run (table-like, >=2 adjacent qwords): %d bytes=%d' % (len(in_run), sum(b[1] for b in in_run)))
for b in ptr_only[:10]: print('  ', hex(IMG + b[0]), b[1])

cut = []
for ln in list(open(CUT))[1:]:
    va, by, lib, tag = ln.rstrip('\n').split('\t')
    b = int(va, 16) - IMG; cut.append((b, b + int(by)))
cut.sort()
merged = []
for b, e in cut:
    if merged and b <= merged[-1][1]: merged[-1][1] = max(merged[-1][1], e)
    else: merged.append([b, e])
ms = [m[0] for m in merged]
ov = 0
for va, sz, cls in blocks:
    i = bisect.bisect_right(ms, va + sz - 1) - 1
    if i >= 0 and merged[i][1] > va: ov += 1
print('cut-table overlap with gap blocks (merged %d cut intervals): %d' % (len(merged), ov))
# negative control: shift every cut interval by +0x2000 and expect hits
ov2 = 0
for va, sz, cls in blocks:
    i = bisect.bisect_right([m[0] + 0x2000 for m in merged], va + sz - 1) - 1
    if i >= 0 and merged[i][1] + 0x2000 > va: ov2 += 1
print('negative control (cut shifted +0x2000): %d' % ov2)
