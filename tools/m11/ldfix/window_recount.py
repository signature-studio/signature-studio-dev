#!/usr/bin/env python3
"""window_recount.py — audit_lsf_ssa.py の機械語側 site 列挙の独立再計算 (#510 / LD-10)。
audit_lsf_ssa.py は CFG 上の前向きデータフロー (reg / frame slot 追跡) で LSF site を列挙する。本スクリプトは**データフローを使わず**、
関数の命令列 (再帰降下) を直線に舐めて「同一基本ブロック内で `mov rD,[rB]` (disp 0・index 無・rB ≠ rsp/rbp/rip) の後、rD を書き換える前に
`mov [m],rD` (同幅) がある」対を数える。ブロック境界 = jmp/jcc/call/ret の直後と jmp/jcc の飛び先 (直接分岐のみ)。
窓内の対は、データフローが列挙する site の部分集合のはず (データフローは reg コピー・spill 経由も含むため上位集合)。
検査: (a) 窓の対の store アドレスがデータフロー側 site 集合に全て含まれる (含まれない件数 = 0 を期待)
      (b) 窓の対の数とデータフロー側の store 数の比
使い方: python3 window_recount.py IR.ll IMAGE.bin 'CONFIG_GLOB' SSA.json"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_lsf as A  # noqa: E402
from ldmach import norm_reg  # noqa: E402
from ldmach_img import ImageMachine  # noqa: E402
import capstone  # noqa: E402

ir, img, cfg, sj = sys.argv[1:5]
text = open(ir, errors='replace').read()
mach = ImageMachine(img, cfg)
cs = mach.cs
ssa = json.load(open(sj))['functions']
dflow = {}
for v, r in ssa.items():
    for s in r['sites']:
        dflow[int(s['addr'], 16)] = (v, s)

pairs = {}
for va, _args, body in A.ir_functions(text):
    labels = [int(x, 16) for x in re.findall(r'^dec_label_pc_([0-9a-f]+)[:.]', body, re.M)]
    ins = A.descend(mach, va, labels)
    if not ins:
        continue
    leaders = {ins[0].address} | set(labels)
    for k, i in enumerate(ins):
        mn = i.mnemonic
        tgt = i.operands[0].imm if i.operands and i.operands[0].type == capstone.CS_OP_IMM else None
        if mn == 'jmp' or mn.startswith('j') or mn.startswith('loop'):
            if tgt is not None:
                leaders.add(tgt)
            if k + 1 < len(ins):
                leaders.add(ins[k + 1].address)
        if mn in ('call', 'ret', 'retn') and k + 1 < len(ins):
            leaders.add(ins[k + 1].address)
    live = {}
    for i in ins:
        if i.address in leaders:
            live = {}
        ops = i.operands
        mn = i.mnemonic
        if mn == 'mov' and len(ops) == 2 and ops[0].type == capstone.CS_OP_MEM and ops[1].type == capstone.CS_OP_REG:
            r = norm_reg(cs, ops[1].reg)
            w = ops[0].size * 8
            if r in live and live[r] == w and ops[1].size * 8 == w:
                pairs[i.address] = (va, w)
        try:
            _rd, wr = i.regs_access()
        except Exception:
            wr = ()
        for rid in wr:
            r = norm_reg(cs, rid)
            if r:
                live.pop(r, None)
        if mn == 'call':
            live = {}
        if mn == 'mov' and len(ops) == 2 and ops[0].type == capstone.CS_OP_REG and ops[1].type == capstone.CS_OP_MEM:
            m = ops[1].mem
            mb = norm_reg(cs, m.base) if m.base else None
            if m.index == 0 and m.disp == 0 and mb and mb not in ('rsp', 'rbp') and cs.reg_name(m.base) != 'rip' and ops[1].size in (4, 8) and ops[0].size == ops[1].size:
                live[norm_reg(cs, ops[0].reg)] = ops[1].size * 8
miss = [a for a in pairs if a not in dflow]
w_nonframe = sum(1 for a in pairs if a in dflow and not dflow[a][1]['frame'])
print(json.dumps(dict(window_pairs=len(pairs), window_fns=len({v for v, _ in pairs.values()}),
                      dataflow_sites=len(dflow), dataflow_nonframe=sum(1 for _a, (_v, s) in dflow.items() if not s['frame']),
                      window_not_in_dataflow=len(miss), window_in_dataflow_nonframe=w_nonframe), ensure_ascii=False))
if miss:
    print('NOT_IN_DATAFLOW', ' '.join('%x' % a for a in sorted(miss)[:40]))
