#!/usr/bin/env python3
"""window_survey_1980.py — #1980 (LD-73): link_d17.py の chain 走査窓を変えたときの 1:1 結べ数の再計算 (一時診断をコミットした版)。

link_d17.py の mach_chains は rD の使用先を後続 8 命令内で探す (dst_unused 判定)。本スクリプトはその走査幅 W を引数にし、
W ごとに「IR 1 本・chain 1 本のブロック」の結べ数と結べない理由を数える。link_d17.py 本体は変更しない (測定 commit の差分 0 を保つため)。
基底の探索窓 (no_deref 判定) は link_d17.py と同じ 3 命令。

使い方: python3 window_survey_1980.py IR.ll AUDIT.json IMAGE.bin 'CFG_GLOB' [--windows 8,16,32,64]
  IR は fix_d17 適用後 (tools/m11/work 配下の boot_d17.ll 相当) を想定。素材 (work-m11) が無い環境では実行できない。
"""
import argparse
import bisect
import collections
import json
import os
import sys

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_lsf_ssa as S  # noqa: E402
import fix_d17 as F  # noqa: E402
import link_d17 as L  # noqa: E402


def chains_w(mach, labels, want, win):
    """link_d17.mach_chains と同じ規則。rD の使用先の走査幅だけ win (命令数) にする。"""
    lo, hi = labels[0], labels[-1] + 0x400
    ins_list = []
    addr = lo
    while addr < hi:
        got = list(mach.cs.disasm(mach.read(addr - mach.base, 16), addr, 1))
        if not got:
            addr += 1
            continue
        ins_list.append(got[0])
        addr += got[0].size
    res = collections.defaultdict(list)
    for n, i in enumerate(ins_list):
        if not (i.mnemonic == 'mov' and len(i.operands) == 2):
            continue
        o0, o1 = i.operands
        if not (o0.type == capstone.CS_OP_REG and o1.type == capstone.CS_OP_MEM
                and o1.mem.base and mach.cs.reg_name(o1.mem.base) == 'rip'):
            continue
        k = i.address + i.size + o1.mem.disp - mach.base
        if k not in want:
            continue
        j = bisect.bisect_right(labels, i.address) - 1
        blk = '%x' % labels[j] if j >= 0 else 'entry'
        rA = o0.reg
        d = None
        why = 'no_deref'
        for p in range(n + 1, min(n + 4, len(ins_list))):
            m = ins_list[p]
            if L.is_stop(m.mnemonic):
                break
            ops = m.operands
            if (m.mnemonic == 'mov' and len(ops) == 2 and ops[0].type == capstone.CS_OP_REG
                    and ops[1].type == capstone.CS_OP_MEM and ops[1].mem.base == rA
                    and ops[1].mem.index == 0 and ops[1].mem.disp == 0):
                d = p
                break
            if any(o.type == capstone.CS_OP_REG and o.reg == rA for o in ops):
                why = 'base_clobbered'
                break
        if d is None:
            res[k].append((blk, None, why))
            continue
        rD = ins_list[d].operands[0].reg
        used = False
        for m in ins_list[d + 1:d + 1 + win]:
            if L.is_stop(m.mnemonic):
                break
            if any(o.type == capstone.CS_OP_REG and o.reg == rD for o in m.operands[1:]):
                used = True
                break
            if m.operands and m.operands[0].type == capstone.CS_OP_REG and m.operands[0].reg == rD:
                break
        if not used:
            res[k].append((blk, None, 'dst_unused'))
            continue
        res[k].append((blk, ins_list[d].operands[0].size * 8, None))
    return res


def survey(ir_text, audit, mach, win):
    """窓 win での集計: 結べた load 数と、IR 1 本・chain 1 本のブロックの結べない理由。"""
    linked = 0
    reasons = collections.Counter()
    multi_blocks = 0
    multi_ir_eq_chain = 0
    for m in F.DEF_RE.finditer(ir_text):
        va = m.group(1)
        v = audit['functions'].get(va)
        if not v:
            continue
        ks = set(int(s['cell']['k'], 16) for s in v['sites']
                 if s.get('cell') and s['cell'].get('verdict') == 'CELL_COLLAPSED' and not s.get('frame'))
        if not ks:
            continue
        end = ir_text.index('\n}', m.end()) + 2
        lines = ir_text[m.start():end].split('\n')
        labels = sorted(int(mm.group(1), 16) for mm in (L.LABEL.match(ln) for ln in lines) if mm)
        if not labels:
            continue
        loads = L.ir_loads(lines)
        by_k = collections.defaultdict(list)
        for x in loads:
            by_k[x[3]].append(x)
        cand = {k for k in ks if len(by_k.get(k, [])) > 1}
        if not cand:
            continue
        chains = chains_w(mach, labels, cand, win)
        for k in cand:
            ir_by_blk = collections.defaultdict(list)
            for (_n, blk, w, _k, _nm) in by_k[k]:
                ir_by_blk[blk].append(w)
            m_by_blk = collections.defaultdict(list)
            for (blk, w, why) in chains.get(k, []):
                m_by_blk[blk].append((w, why))
            for blk in set(ir_by_blk) | set(m_by_blk):
                irs = ir_by_blk.get(blk, [])
                ms = m_by_blk.get(blk, [])
                if len(irs) > 1 or len(ms) > 1:
                    multi_blocks += 1
                    if len(irs) == len(ms):
                        multi_ir_eq_chain += 1
                    continue
                if len(irs) == 1 and len(ms) == 1:
                    w, why = ms[0]
                    if why is None and w == irs[0]:
                        linked += 1
                    elif why is not None:
                        reasons[why] += 1
                    else:
                        reasons['width'] += 1
    return dict(window=win, linked=linked, reasons=dict(reasons),
                multi_blocks=multi_blocks, multi_ir_eq_chain=multi_ir_eq_chain)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('audit')
    ap.add_argument('image')
    ap.add_argument('cfg')
    ap.add_argument('--windows', default='8,16,32,64')
    a = ap.parse_args()
    audit = json.load(open(a.audit))
    ir_text = open(a.ir, errors='replace').read()
    mach = S.ImageMachine(a.image, a.cfg)
    for w in (int(x) for x in a.windows.split(',')):
        print(json.dumps(survey(ir_text, audit, mach, w), ensure_ascii=False))


if __name__ == '__main__':
    main()
