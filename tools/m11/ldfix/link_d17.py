#!/usr/bin/env python3
"""link_d17.py — #1740 (LD-61): 複数 load の K 組を機械語の値の流れで 1 対 1 に結んで D17 を修復する pass。

対象: audit_lsf_ssa.py の store 宛 CELL_COLLAPSED の K 組のうち、IR で K を読む load (cellp を除く) が 2 本以上のもの
(1 本の K は fix_d17.py が担当する。両 pass は触る load が重ならない)。

機械語側 (chain): `mov rA,[rip+X]` (K = X のセル) の直後 3 命令以内に、rA を基底にした `mov rD,[rA]` (disp 0・index 0) があり、
  その間に rA を触る命令・分岐・call が無く、rD が後続で読まれる。chain の幅 = rD の幅。
IR 側 (load): 同じ dec_label ブロック内の `load T, ptr inttoptr (K)`。

結ぶ条件 (ブロック単位・順序に依らない): そのブロックで IR load がちょうど 1 本、chain がちょうど 1 本、かつ幅が一致。
  これ以外 (本数が複数・幅不一致・chain が見つからない) は結ばず、理由を report に書く。

修復: `%v = load T, ptr inttoptr K` → `%cellp.K.<行> = load ptr, ptr inttoptr K` / `%v = load T, ptr %cellp.K.<行>`。
使い方: python3 link_d17.py IN.ll AUDIT.json IMAGE.bin 'CFG_GLOB' OUT.ll [--report OUT.json]
"""
import argparse
import bisect
import collections
import json
import os
import re
import sys

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_lsf_ssa as S  # noqa: E402
import fix_d17 as F  # noqa: E402

LABEL = re.compile(r'^dec_label_pc_([0-9a-f]+)[:.]')
LOAD_LINE = re.compile(r'^(\s*)(%\S+) = load (\S+), ptr inttoptr \(i64 (\d+) to ptr\)([^\n]*)$')
STOP = ('call', 'ret', 'retn', 'ud2', 'int3', 'hlt')


def is_stop(mn):
    return mn in STOP or mn.startswith('j') or mn.startswith('loop')


def ir_loads(lines):
    """関数本体 -> [(行番号, ブロック, 幅, K, 名前)] (cellp 行は除く)"""
    out = []
    cur = 'entry'
    for n, ln in enumerate(lines):
        m = LABEL.match(ln)
        if m:
            cur = m.group(1)
        m = LOAD_LINE.match(ln)
        if m and not m.group(2).startswith('%cellp.'):
            out.append((n, cur, S.A.width_of(m.group(3)), int(m.group(4)), m.group(2)))
    return out


def mach_chains(mach, labels, want):
    """K -> [(ブロック, 幅 or None, 理由)]。幅 None は結べない chain (理由付き)。"""
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
            if is_stop(m.mnemonic):
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
        for m in ins_list[d + 1:d + 9]:
            if is_stop(m.mnemonic):
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


def link_fn(lines, mach, labels, ks):
    """1 関数分 -> (linked: [(行番号, K, 幅, 名前)], report: {K: {...}})"""
    loads = ir_loads(lines)
    by_k = collections.defaultdict(list)
    for x in loads:
        by_k[x[3]].append(x)
    cand = {k for k in ks if len(by_k.get(k, [])) > 1}
    if not cand:
        return [], {}
    chains = mach_chains(mach, labels, cand)
    linked = []
    rep = {}
    for k in sorted(cand):
        ir_by_blk = collections.defaultdict(list)
        for (n, blk, w, _k, nm) in by_k[k]:
            ir_by_blk[blk].append((n, w, nm))
        m_by_blk = collections.defaultdict(list)
        for (blk, w, why) in chains.get(k, []):
            m_by_blk[blk].append((w, why))
        r = dict(ir_loads=len(by_k[k]), mach_chains=len(chains.get(k, [])), linked=0, reasons=collections.Counter())
        for blk in set(ir_by_blk) | set(m_by_blk):
            irs = ir_by_blk.get(blk, [])
            ms = m_by_blk.get(blk, [])
            good = [w for (w, why) in ms if why is None]
            if len(irs) == 1 and len(ms) == 1 and good and good[0] == irs[0][1]:
                linked.append((irs[0][0], k, irs[0][1], irs[0][2]))
                r['linked'] += 1
                continue
            if not irs:
                r['reasons']['mach_only'] += len(ms)
            elif not ms:
                r['reasons']['ir_only'] += len(irs)
            elif len(irs) != 1 or len(ms) != 1:
                r['reasons']['multi_in_block'] += len(irs)
            else:
                r['reasons']['width_or_chain'] += 1
        r['reasons'] = dict(r['reasons'])
        rep['%x' % k] = r
    return linked, rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('audit')
    ap.add_argument('image')
    ap.add_argument('cfg')
    ap.add_argument('outfile')
    ap.add_argument('--report')
    a = ap.parse_args()
    audit = json.load(open(a.audit))
    text = open(a.ir, errors='replace').read()
    mach = S.ImageMachine(a.image, a.cfg)
    out = []
    last = 0
    rep = {}
    nlink = ntot = 0
    for m in F.DEF_RE.finditer(text):
        va = m.group(1)
        v = audit['functions'].get(va)
        if not v:
            continue
        ks = set(int(s['cell']['k'], 16) for s in v['sites']
                 if s.get('cell') and s['cell'].get('verdict') == 'CELL_COLLAPSED' and not s.get('frame'))
        if not ks:
            continue
        end = text.index('\n}', m.end()) + 2
        body = text[m.start():end]
        lines = body.split('\n')
        labels = sorted(int(mm.group(1), 16) for mm in (LABEL.match(ln) for ln in lines) if mm)
        if not labels:
            continue
        linked, r = link_fn(lines, mach, labels, ks)
        if r:
            rep[va] = r
            ntot += sum(x['ir_loads'] for x in r.values())
            nlink += sum(x['linked'] for x in r.values())
        if not linked:
            continue
        for (n, k, w, nm) in sorted(linked, reverse=True):
            mm = LOAD_LINE.match(lines[n])
            ind, name, ty, rest = mm.group(1), mm.group(2), mm.group(3), mm.group(5)
            p = '%%cellp.%x.%d' % (k, n)
            lines[n:n + 1] = [ind + p + ' = load ptr, ptr inttoptr (i64 ' + str(k) + ' to ptr)' + rest,
                              ind + name + ' = load ' + ty + ', ptr ' + p + rest]
        out.append(text[last:m.start()])
        out.append('\n'.join(lines))
        last = end
    out.append(text[last:])
    open(a.outfile, 'w').write(''.join(out))
    print('ir_loads_in_multi_groups=%d linked=%d' % (ntot, nlink))
    if a.report:
        json.dump(dict(linked=nlink, ir_loads=ntot, functions=rep), open(a.report, 'w'), indent=1)


if __name__ == '__main__':
    main()
