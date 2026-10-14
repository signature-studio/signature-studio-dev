#!/usr/bin/env python3
"""survey_d17_multiload.py — #1375 (LD-47) 用の調査 script。複数 load の CELL_COLLAPSED K 組について、
IR の K 読み出し本数と機械語の rip セル → deref 連鎖の本数を、dec_label_pc ブロック単位で比べる。

入力: audit_lsf_ssa.py の --json 出力 / IR / image / cfg (cfg は glob をクォートして渡す)。
使い方: python3 survey_d17_multiload.py AUDIT.json IR.ll IMAGE.bin 'CFG_GLOB'
出力: 複数 load の K 組数、ブロック単位で本数一致した K 組数、K 組ごとの表。
"""
import argparse
import bisect
import collections
import glob
import json
import os
import re
import sys

import capstone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_lsf_ssa as S  # noqa: E402

LABEL = re.compile(r'^dec_label_pc_([0-9a-f]+)[:.]', re.M)


def fn_bodies(text):
    out = {}
    for m in re.finditer(r'^define [^\n]*@function_([0-9a-f]+)\(', text, re.M):
        end = text.index('\n}', m.end()) + 2
        out[m.group(1)] = text[m.start():end]
    return out


def ir_blocks(body):
    """K -> {block_pc: K を読む load の本数}"""
    res = collections.defaultdict(collections.Counter)
    cur = 'entry'
    for ln in body.split('\n'):
        m = re.match(r'^dec_label_pc_([0-9a-f]+)[:.]', ln)
        if m:
            cur = m.group(1)
        if ' load ' in ln:
            for _t, c in S.IR_CONST_LOAD.findall(ln):
                res[int(c)][cur] += 1
    return res


def mach_chains(mach, labels, lo, hi, want):
    """K -> {block_pc: (rip セル読み出し本数, そのうち直後 3 命令内に deref があった本数)}"""
    ins_list = []
    addr = lo
    while addr < hi:
        ins = list(mach.cs.disasm(mach.read(addr - mach.base, 16), addr, 1))
        if not ins:
            addr += 1
            continue
        ins_list.append(ins[0])
        addr += ins[0].size
    res = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    for n, i in enumerate(ins_list):
        j = bisect.bisect_right(labels, i.address) - 1
        blk = '%x' % labels[j] if j >= 0 else 'entry'
        if not (i.mnemonic == 'mov' and len(i.operands) == 2):
            continue
        o0, o1 = i.operands
        if not (o1.type == capstone.CS_OP_MEM and o1.mem.base and mach.cs.reg_name(o1.mem.base) == 'rip'):
            continue
        if o0.type != capstone.CS_OP_REG:
            continue
        k = i.address + i.size + o1.mem.disp - mach.base
        if k not in want:
            continue
        rA = o0.reg
        deref = False
        for m in ins_list[n + 1:n + 4]:
            if m.mnemonic == 'mov' and len(m.operands) == 2:
                b = m.operands[1]
                if b.type == capstone.CS_OP_MEM and b.mem.base == rA and b.mem.index == 0:
                    deref = True
                    break
            if any(o.type == capstone.CS_OP_REG and o.reg == rA for o in m.operands) and m.mnemonic != 'mov':
                break
        res[k][blk][0] += 1
        res[k][blk][1] += int(deref)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('audit')
    ap.add_argument('ir')
    ap.add_argument('image')
    ap.add_argument('cfg')
    a = ap.parse_args()
    audit = json.load(open(a.audit))
    text = open(a.ir, errors='replace').read()
    bodies = fn_bodies(text)
    mach = S.ImageMachine(a.image, a.cfg)
    tot_k = match_k = 0
    rows = []
    for va, v in audit['functions'].items():
        ks = set(int(s['cell']['k'], 16) for s in v['sites']
                 if s.get('cell') and s['cell'].get('verdict') == 'CELL_COLLAPSED' and not s.get('frame'))
        body = bodies.get(va)
        if not ks or body is None:
            continue
        labels = sorted(int(x, 16) for x in LABEL.findall(body))
        if not labels:
            continue
        irb = ir_blocks(body)
        mc = mach_chains(mach, labels, labels[0], labels[-1] + 0x400, ks)
        for k in sorted(ks):
            n_ir = sum(irb[k].values())
            if n_ir <= 1:
                continue
            tot_k += 1
            n_m = sum(c[1] for c in mc[k].values())
            blk_ok = all(irb[k].get(b, 0) == mc[k][b][1] for b in set(irb[k]) | set(mc[k]))
            if blk_ok and n_ir == n_m:
                match_k += 1
            rows.append((va, '%x' % k, n_ir, n_m, blk_ok))
    print('multi-load K組 %d / ブロック単位で本数一致 %d' % (tot_k, match_k))
    for r in rows:
        print('fn=%s K=%s IR_load=%d MACH_deref=%d block_match=%s' % r)


if __name__ == '__main__':
    main()
