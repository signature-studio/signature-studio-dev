#!/usr/bin/env python3
"""value_flow_5243.py — #5243 (LD-260): site ↔ IR i32 読み出しの対応を修復報告に依らず機械語の値の流れから作る方式の計測。

link_d17.py の規則 (同一 dec_label ブロックで IR 読み出し 1 本・機械 chain 1 本・幅一致なら結ぶ) は変えず、
chain の「rD が後続で使われるか」の判定だけを差し替えて、結べ数の変化を測る。
  --use-rule base: link_d17 と同じ (宛先レジスタは使用と数えない)
  --use-rule rmw : 2 オペランド形 (`imul r32,m32` 等) の宛先レジスタも被演算子として使用と数える (本計測の提案規則)
修復は行わない。結べた K 組・load を出すだけ (修復への組み込みは別 issue)。
使い方: python3 value_flow_5243.py IR.ll IMAGE.bin 'CFG_GLOB' [--use-rule base|rmw] [--fn 100b890] [--json OUT]
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capstone  # noqa: E402
import audit_lsf_ssa as S  # noqa: E402
import link_d17 as L  # noqa: E402
import fix_d17 as F  # noqa: E402

RMW_MN = ('imul', 'add', 'sub', 'and', 'or', 'xor', 'cmp', 'test', 'adc', 'sbb')


def reads_reg(m, rD, rule):
    """命令 m が rD を読むか。base: operand1 以降のみ。rmw: 2 オペランドの RMW 形は operand0 も読む。"""
    for idx, o in enumerate(m.operands):
        if o.type != capstone.CS_OP_REG or o.reg != rD:
            continue
        if idx >= 1:
            return True
        if rule == 'rmw' and len(m.operands) == 2 and m.mnemonic in RMW_MN:
            return True
    return False


def mach_chains(mach, labels, want, rule):
    """link_d17.mach_chains と同じ抽出。使用判定だけを rule で切り替える。"""
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
        j = L.bisect.bisect_right(labels, i.address) - 1
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
            res[k].append((blk, None, why, None, i.address))
            continue
        rD = ins_list[d].operands[0].reg
        used = None
        for m in ins_list[d + 1:d + 9]:
            if L.is_stop(m.mnemonic):
                break
            if reads_reg(m, rD, rule):
                used = m.mnemonic
                break
            if m.operands and m.operands[0].type == capstone.CS_OP_REG and m.operands[0].reg == rD:
                break
        if used is None:
            res[k].append((blk, None, 'dst_unused', None, i.address))
            continue
        res[k].append((blk, ins_list[d].operands[0].size * 8, None, used, i.address))
    return res


def ir_consumer(lines, name):
    """IR の SSA 名 name の最初の使用行の命令種 (mul/icmp/store/call/他)"""
    pat = re.compile(r'(?<![\w.$-])%s(?![\w.$-])' % re.escape(name))
    for ln in lines:
        if ln.lstrip().startswith(name + ' ='):
            continue
        if pat.search(ln):
            m = re.search(r'=\s*(\w+)', ln)
            if m:
                return m.group(1)
            return ln.split()[0]
    return None


def link_fn(lines, mach, labels, ks, rule):
    loads = L.ir_loads(lines)
    by_k = collections.defaultdict(list)
    for x in loads:
        by_k[x[3]].append(x)
    cand = {k for k in ks if len(by_k.get(k, [])) > 1}
    if not cand:
        return []
    chains = mach_chains(mach, labels, cand, rule)
    out = []
    for k in sorted(cand):
        ir_by_blk = collections.defaultdict(list)
        for (n, blk, w, _k, nm) in by_k[k]:
            ir_by_blk[blk].append((n, w, nm))
        m_by_blk = collections.defaultdict(list)
        for (blk, w, why, used, _a) in chains.get(k, []):
            m_by_blk[blk].append((w, why, used))
        for blk in set(ir_by_blk) | set(m_by_blk):
            irs = ir_by_blk.get(blk, [])
            ms = m_by_blk.get(blk, [])
            good = [x for x in ms if x[1] is None]
            if len(irs) == 1 and len(ms) == 1 and good and good[0][0] == irs[0][1]:
                out.append(dict(k='%x' % k, blk=blk, ir=irs[0][2], ir_use=ir_consumer(lines, irs[0][2]),
                                mach_use=good[0][2], n=irs[0][0]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('image')
    ap.add_argument('cfg')
    ap.add_argument('--use-rule', default='base', choices=['base', 'rmw'])
    ap.add_argument('--fn')
    ap.add_argument('--json')
    a = ap.parse_args()
    text = open(a.ir, errors='replace').read()
    mach = S.ImageMachine(a.image, a.cfg)
    # 対象 K: link_d17 と同じく、audit の store 宛 CELL_COLLAPSED の K 集合 (修復前)。--fn 指定時はその関数の K を全部対象にする
    audit_path = os.environ.get('AUDIT_JSON')
    audit = json.load(open(audit_path)) if audit_path else None
    rows = []
    for m in F.DEF_RE.finditer(text):
        va = m.group(1)
        if a.fn and va != a.fn:
            continue
        if audit is not None:
            v = audit['functions'].get(va)
            if not v:
                continue
            ks = set(int(s['cell']['k'], 16) for s in v['sites']
                     if s.get('cell') and s['cell'].get('verdict') == 'CELL_COLLAPSED' and not s.get('frame'))
        else:
            ks = set(int(x[3]) for x in L.ir_loads(text[m.start():text.index('\n}', m.end()) + 2].split('\n')))
        if not ks:
            continue
        end = text.index('\n}', m.end()) + 2
        lines = text[m.start():end].split('\n')
        labels = sorted(int(mm.group(1), 16) for mm in (L.LABEL.match(ln) for ln in lines) if mm)
        if not labels:
            continue
        for r in link_fn(lines, mach, labels, ks, a.use_rule):
            r['fn'] = va
            rows.append(r)
    print(json.dumps(dict(rule=a.use_rule, linked=len(rows)), ensure_ascii=False))
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))
    if a.json:
        json.dump(rows, open(a.json, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
