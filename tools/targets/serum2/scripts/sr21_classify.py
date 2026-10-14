#!/usr/bin/env python3
"""SR-21: classify the non-.pdata code blocks (out/sr3_gap_blocks.tsv, 20,467 blocks) and give the evidence per class.
Classes (first match wins):
  entry_call    : start is the target of a direct call (kind 1)                                  -> function entry (strong)
  entry_rip     : start is only the target of rip-relative lea/mov (kind 0)                       -> function entry? (weak: data loads also use kind 0)
  branch_only   : start is only the target of jmp/jcc (kind 2/3)                                  -> split/tail candidate
  data          : no code reference and does not decode cleanly to its end                        -> data candidate
  table_ptr     : no code reference, but in a run of >=2 consecutive 8-byte values in .rdata/.data that point at block starts (vtable/fn-table like)
  ptr_single    : no code reference, a single 8-byte pointer hit in .rdata/.data                  -> weak
  unref         : no code reference, no pointer hit, cleanly decoded                              -> 未確定 (cannot tell function vs. fragment)
Padding is not a block: it is counted separately as runs of 0xCC/0x90/0x00 inside the .pdata gaps.
Note: blocks are cut only at 0xCC 0xCC, so two blocks are never byte-adjacent; adjacency cannot
identify split continuations, which is why no split_fall class exists.
usage: sr21_classify.py <pe> <index.npz> <gap_blocks.tsv> <cut_table.tsv> <out_dir>"""
import sys, bisect, collections, csv
import numpy as np
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

PE_PATH, IDX, GAP, CUT, OUT = sys.argv[1:6]
IMG = 0x180000000
pe = pefile.PE(PE_PATH, fast_load=True)
t = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
TB, TVA = t.get_data(), t.VirtualAddress
z = np.load(IDX)
funcs = z['funcs']; refs = z['refs']
pstart = funcs[:, 0].tolist(); pend = funcs[:, 1].tolist()


def in_pdata(rva):
    i = bisect.bisect_right(pstart, rva) - 1
    return i >= 0 and rva < pend[i]


import struct
ptrs = set(); runp = set()
for s in pe.sections:
    if s.Name.rstrip(b'\0') in (b'.rdata', b'.data', b'_RDATA'):
        d = s.get_data(); prev = None
        for off in range(0, len(d) - 7, 8):
            v = struct.unpack_from('<Q', d, off)[0] - IMG
            if TVA <= v < TVA + len(TB):
                ptrs.add(v)
                if prev is not None: runp.add(prev); runp.add(v)
                prev = v
            else:
                prev = None

cnt = collections.defaultdict(lambda: collections.Counter())
for s, d, k in refs.tolist():
    c = cnt[d]
    c['k%d' % k] += 1
    c['from_pdata' if in_pdata(s) else 'from_gap'] += 1

md = Cs(CS_ARCH_X86, CS_MODE_64)
rows = []
with open(GAP) as f:
    for r in csv.DictReader(f, delimiter='\t'):
        rva = int(r['block_va'], 16) - IMG
        sz = int(r['bytes'])
        blk = TB[rva - TVA:rva - TVA + sz]
        last = ''; ninsn = 0; nret = 0
        for ins in md.disasm(blk, rva):
            ninsn += 1; last = ins.mnemonic
            if ins.mnemonic in ('ret', 'retf'): nret += 1
        rows.append(dict(rva=rva, sz=sz, clean=int(r['clean_decode']), last=last, ninsn=ninsn, nret=nret,
                         lib=r['cut_library']))
rows.sort(key=lambda x: x['rva'])

cut = []
for ln in list(open(CUT))[1:]:
    va, by, lib, tag = ln.rstrip('\n').split('\t')
    cut.append((int(va, 16) - IMG, lib))

for r in rows:
    c = cnt.get(r['rva'], collections.Counter())
    r['k0'] = c['k0']; r['k1'] = c['k1']; r['k2'] = c['k2']; r['k3'] = c['k3']
    r['src_pdata'] = c['from_pdata']; r['src_gap'] = c['from_gap']
    r['ptr'] = 1 if r['rva'] in ptrs else 0
    r['ptr_run'] = 1 if r['rva'] in runp else 0
    if r['k1'] > 0:
        cls = 'entry_call'
    elif r['k0'] > 0:
        cls = 'entry_rip'
    elif r['k2'] + r['k3'] > 0:
        cls = 'branch_only'
    elif not r['clean']:
        cls = 'data'
    elif r['ptr_run']:
        cls = 'table_ptr'
    elif r['ptr']:
        cls = 'ptr_single'
    else:
        cls = 'unref'
    r['cls'] = cls

agg = collections.OrderedDict()
for k in ['entry_call', 'entry_rip', 'branch_only', 'table_ptr', 'ptr_single', 'unref', 'data']:
    rs = [r for r in rows if r['cls'] == k]
    agg[k] = dict(blocks=len(rs), bytes=sum(r['sz'] for r in rs), ret_blocks=sum(1 for r in rs if r['nret']),
                  insns=sum(r['ninsn'] for r in rs))

tot_b = sum(v['blocks'] for v in agg.values()); tot_B = sum(v['bytes'] for v in agg.values())
ref_b = sum(agg[k]['blocks'] for k in ['entry_call', 'entry_rip', 'branch_only'])
ref_B = sum(agg[k]['bytes'] for k in ['entry_call', 'entry_rip', 'branch_only'])
ptr_b = sum(agg[k]['blocks'] for k in ['table_ptr', 'ptr_single'])
ptr_B = sum(agg[k]['bytes'] for k in ['table_ptr', 'ptr_single'])

with open(OUT + '/sr21_classify.tsv', 'w') as f:
    f.write('block_va\tbytes\tclass\tcall\trip\tjmp\tjcc\tsrc_pdata\tsrc_gap\tinsns\tret\tlast\tcut_library\n')
    for r in rows:
        f.write(f"{hex(IMG + r['rva'])}\t{r['sz']}\t{r['cls']}\t{r['k1']}\t{r['k0']}\t{r['k2']}\t{r['k3']}\t"
                f"{r['src_pdata']}\t{r['src_gap']}\t{r['ninsn']}\t{r['nret']}\t{r['last']}\t{r['lib']}\n")

lines = []
lines.append('class\tblocks\tbytes\tret_blocks\tinsns')
for k, v in agg.items():
    lines.append(f"{k}\t{v['blocks']}\t{v['bytes']}\t{v['ret_blocks']}\t{v['insns']}")
lines.append(f"TOTAL\t{tot_b}\t{tot_B}\t{sum(v['ret_blocks'] for v in agg.values())}\t{sum(v['insns'] for v in agg.values())}")
lines.append(f"referenced(entry_call+entry_rip+branch_only)\t{ref_b}\t{ref_B}")
lines.append(f"pointer_only(table_ptr+ptr_single)\t{ptr_b}\t{ptr_B}")
lines.append('cut_window_blocks\t' + str(sum(1 for r in rows if r['lib'] != '-')) + '\t' +
             str(sum(r['sz'] for r in rows if r['lib'] != '-')))
lines.append('cut_window_by_class\t' + str(dict(collections.Counter(r['cls'] for r in rows if r['lib'] != '-'))))
with open(OUT + '/sr21_summary.txt', 'w') as f:
    f.write('\n'.join(lines) + '\n')
print('\n'.join(lines))
