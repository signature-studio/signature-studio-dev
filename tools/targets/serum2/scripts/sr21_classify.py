#!/usr/bin/env python3
"""SR-21: classify the non-.pdata code blocks (out/sr3_gap_blocks.tsv, 20,467 blocks) and give the evidence per class.
Padding inside a block: leading/trailing instructions that are nop / int3 / xchg ax,ax are trimmed (pad_head / pad_tail).
A block that is only padding is class 'padding' (its bytes are not code). Everything else is classified on its core.
Classes (first match wins, on the core start):
  entry_call    : start is the target of a direct call (kind 1)                                  -> function entry (strong)
  entry_rip     : start is only the target of rip-relative lea/mov (kind 0)                       -> function entry? (weak: data loads also use kind 0)
  branch_only   : start is only the target of jmp/jcc (kind 2/3), no call/rip/pointer          -> split fragment (strict: see REPORT_SR21 s2)
  data          : no code reference and the core does not decode cleanly to its end            -> data candidate
  table_ptr     : no code reference, but in a run of >=2 consecutive 8-byte values in .rdata/.data that point at block starts (vtable/fn-table like)
  ptr_single    : no code reference, a single 8-byte pointer hit in .rdata/.data                  -> weak
  unref         : no code reference, no pointer hit, cleanly decoded                              -> 未確定 (cannot tell function vs. fragment)
  padding       : block consists only of padding instructions (nop / int3 / xchg ax,ax)
References: the .pdata-side index (work/index.npz refs) united with every instruction of every gap block
(the index only decodes the .pdata chunks, so gap-side sources are missing there).
Between blocks, runs of 0xCC/0x90/0x00 are padding too (not blocks): counted as runs in the summary.
usage: sr21_classify.py <pe> <index.npz> <gap_blocks.tsv> <cut_table.tsv> <out_dir>"""
import sys, bisect, collections, csv, struct
import numpy as np
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_REG_RIP

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

md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True


def is_pad(ins):
    return ins.mnemonic in ('nop', 'int3') or (ins.mnemonic == 'xchg' and ins.op_str.replace(' ', '') in ('ax,ax', 'eax,eax', 'rax,rax'))


gref = set(); blocks = []
with open(GAP) as f:
    for r in csv.DictReader(f, delimiter='\t'):
        blocks.append((int(r['block_va'], 16) - IMG, int(r['bytes']), r['cut_library']))
blocks.sort()

rows = []
for rva0, sz0, lib in blocks:
    ins = list(md.disasm(TB[rva0 - TVA:rva0 - TVA + sz0], rva0))
    for i in ins:
        m = i.mnemonic
        for op in i.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                gref.add((i.address, i.address + i.size + op.mem.disp, 0))
            elif op.type == X86_OP_IMM and (m == 'call' or m.startswith('j')):
                gref.add((i.address, op.imm, 1 if m == 'call' else 2 if m == 'jmp' else 3))
    end_ok = bool(ins) and ins[-1].address + ins[-1].size == rva0 + sz0
    h = 0
    while h < len(ins) and is_pad(ins[h]): h += 1
    if end_ok:
        tt = len(ins)
        while tt > h and is_pad(ins[tt - 1]): tt -= 1
        if h == len(ins):
            rows.append(dict(rva=rva0, sz=sz0, blk=sz0, cls='padding', lib=lib, pad=sz0, clean=1, core=[]))
            continue
        cs = ins[h].address; ce = ins[tt - 1].address + ins[tt - 1].size
        core = ins[h:tt]
    else:
        cs = ins[h].address if h < len(ins) else (ins[-1].address + ins[-1].size if ins else rva0)
        ce = rva0 + sz0
        core = ins[h:]
    rows.append(dict(rva=cs, sz=ce - cs, blk=sz0, cls=None, lib=lib, pad=(cs - rva0) + (rva0 + sz0 - ce),
                     clean=int(end_ok), core=core))

allr = set(map(tuple, refs.tolist())) | gref
cnt = collections.defaultdict(collections.Counter)
for s, d, k in allr:
    cnt[d]['k%d' % k] += 1
    cnt[d]['from_pdata' if in_pdata(s) else 'from_gap'] += 1

for r in rows:
    if r['cls'] == 'padding':
        continue
    c = cnt.get(r['rva'], collections.Counter())
    r['k0'] = c['k0']; r['k1'] = c['k1']; r['k2'] = c['k2']; r['k3'] = c['k3']
    r['src_pdata'] = c['from_pdata']; r['src_gap'] = c['from_gap']
    r['ptr'] = 1 if r['rva'] in ptrs else 0
    r['ptr_run'] = 1 if r['rva'] in runp else 0
    r['ninsn'] = len(r['core']); r['nret'] = sum(1 for i in r['core'] if i.mnemonic in ('ret', 'retf'))
    r['last'] = r['core'][-1].mnemonic if r['core'] else ''
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
for r in rows:
    if r['cls'] == 'padding':
        r.update(k0=0, k1=0, k2=0, k3=0, src_pdata=0, src_gap=0, ninsn=0, nret=0, last='', ptr=0, ptr_run=0)
rows.sort(key=lambda x: x['rva'])

cut = []
for ln in list(open(CUT))[1:]:
    va, by, lib, tag = ln.rstrip('\n').split('\t')
    cut.append((int(va, 16) - IMG, lib))

CLASSES = ['entry_call', 'entry_rip', 'branch_only', 'table_ptr', 'ptr_single', 'unref', 'data', 'padding']
agg = collections.OrderedDict()
for k in CLASSES:
    rs = [r for r in rows if r['cls'] == k]
    agg[k] = dict(blocks=len(rs), bytes=sum(r['sz'] for r in rs), ret_blocks=sum(1 for r in rs if r['nret']),
                  insns=sum(r['ninsn'] for r in rs))

tot_b = sum(v['blocks'] for v in agg.values()); tot_B = sum(v['bytes'] for v in agg.values())
blk_B = sum(r['blk'] for r in rows)
edge = [r for r in rows if r['cls'] != 'padding' and r['pad'] > 0]
edge_B = sum(r['pad'] for r in edge)
assert tot_B + edge_B == blk_B, (tot_B, edge_B, blk_B)

gaps = []; cur = TVA
for b, e in funcs.tolist():
    if b > cur: gaps.append((cur, b))
    cur = max(cur, e)
if cur < TVA + len(TB): gaps.append((cur, TVA + len(TB)))
ib_runs = 0; ib_B = 0
bstart = [b for b, _, _ in blocks]
for g0, g1 in gaps:
    pos = g0
    for b, sz, _ in blocks[bisect.bisect_left(bstart, g0):bisect.bisect_left(bstart, g1)]:
        if b > pos: ib_runs += 1; ib_B += b - pos
        pos = b + sz
    if pos < g1: ib_runs += 1; ib_B += g1 - pos
gap_B = sum(g1 - g0 for g0, g1 in gaps)
assert ib_B + blk_B == gap_B, (ib_B, blk_B, gap_B)

ref_b = sum(agg[k]['blocks'] for k in ['entry_call', 'entry_rip', 'branch_only'])
ref_B = sum(agg[k]['bytes'] for k in ['entry_call', 'entry_rip', 'branch_only'])
ptr_b = sum(agg[k]['blocks'] for k in ['table_ptr', 'ptr_single'])
ptr_B = sum(agg[k]['bytes'] for k in ['table_ptr', 'ptr_single'])

with open(OUT + '/sr21_classify.tsv', 'w') as f:
    f.write('block_va\tbytes\tclass\tcall\trip\tjmp\tjcc\tsrc_pdata\tsrc_gap\tinsns\tret\tlast\tcut_library\tpad_bytes\tblk_bytes\n')
    for r in rows:
        f.write(f"{hex(IMG + r['rva'])}\t{r['sz']}\t{r['cls']}\t{r.get('k1', 0)}\t{r.get('k0', 0)}\t{r.get('k2', 0)}\t{r.get('k3', 0)}\t"
                f"{r.get('src_pdata', 0)}\t{r.get('src_gap', 0)}\t{r['ninsn']}\t{r['nret']}\t{r['last']}\t{r['lib']}\t{r['pad']}\t{r['blk']}\n")

lines = []
lines.append('class\tblocks\tbytes\tret_blocks\tinsns')
for k, v in agg.items():
    lines.append(f"{k}\t{v['blocks']}\t{v['bytes']}\t{v['ret_blocks']}\t{v['insns']}")
lines.append(f"TOTAL_blocks_incl_padding\t{tot_b}\t{tot_B}\t{sum(v['ret_blocks'] for v in agg.values())}\t{sum(v['insns'] for v in agg.values())}")
lines.append(f"edge_padding_in_code_blocks\t{len(edge)}\t{edge_B}")
lines.append(f"sr3_block_bytes_total\t{len(rows)}\t{blk_B}")
lines.append(f"interblock_padding_runs\t{ib_runs}\t{ib_B}")
lines.append(f"gap_bytes_total\t{len(gaps)}\t{gap_B}")
lines.append(f"referenced(entry_call+entry_rip+branch_only)\t{ref_b}\t{ref_B}")
lines.append(f"pointer_only(table_ptr+ptr_single)\t{ptr_b}\t{ptr_B}")
cw = [r for r in rows if r['lib'] != '-']
lines.append('cut_window_blocks\t' + str(len(cw)) + '\t' + str(sum(r['blk'] for r in cw)))
lines.append('cut_window_by_class\t' + str(dict(collections.Counter(r['cls'] for r in cw))))
with open(OUT + '/sr21_summary.txt', 'w') as f:
    f.write('\n'.join(lines) + '\n')
print('\n'.join(lines))
