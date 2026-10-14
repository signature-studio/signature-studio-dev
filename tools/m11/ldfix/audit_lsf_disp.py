#!/usr/bin/env python3
"""audit_lsf_disp.py — 「load 値の変位 (disp) の取り違え」の検出信号 (#735 LD-13 / #911 / #1091 LD-33)。

41a670 型: 機械語 `mov rax,[rax]` (rax = argN、変位 0) の値を store しているのに、IR はその store 値を
`load (argN + c)` (c≠0) から取っている。audit_lsf.py の既存判定は変位を追跡しないため検出できない (REPORT_911 §6b)。
本スクリプトは audit_lsf.py の use_events / descend / 不動点の枠組みを流用し、機械語側の argN 基底 load に
変位を持たせる (state = ('ld', n, w, disp))。既存の判定 (SUSPECT_VAS / SUSPECT_USE_VAS) と audit_lsf_ssa.py は変えない。
audit_lsf.py は #2396 (LD-111) から、判定の本体 (disp_suspects) を本ファイルから呼んで SUSPECT_DISP_VAS として並べて出力する (単体実行も可)。

  機械語 LSF site: 非 frame 宛の `mov [m],rD` で rD が argN 基底 zero-disp 以外の load (変位 disp_m, 幅 w) の値
                   → (n, w) ごとに disp_m の集合 (機械語が argN+disp_m を読んで書いている)
  IR   load 由来 store: 非 alloca 宛の `store iW %v` で %v が `load iW, ptr (inttoptr (add %argN, c))` (c≠0)
                   → (n, w) ごとに c の集合
  SIGNAL (関数単位): IR の c のうち、機械語の同じ (n, w) の disp_m 集合に無いものが 1 つ以上ある
                     (機械語が argN+c を読んでいないのに IR は argN+c の値を書く)

  文字列転送 (#2396 LD-111): `lea rsi,[argN+k]` → `movsq/movsd [rdi],[rsi]` (rep 無し) を LSF site として列挙する (disp = k, 以降 rsi/rdi は幅ぶん進む)。
                   これが無いと 6677a0 / d237e0 / de1da0 の `argN+36/244` が機械語側に無く、誤検出になる (REPORT_2396 §2)。--no-strmov で #2316 時点の列挙に戻す。

使い方: python3 audit_lsf_disp.py IR.ll IMAGE.bin 'CONFIG_GLOB' [--json OUT] [--only VA,VA] [--pe PE] [--no-strmov]
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_lsf as A  # noqa: E402
from ldmach import norm_reg, Machine  # noqa: E402
from ldmach_img import ImageMachine  # noqa: E402
import capstone  # noqa: E402

STRMOV = True  # --no-strmov で False (#2316 時点の列挙)
ADD_RE = re.compile(r'^\s*(%[\w.$-]+) = add i64 (%arg\d+), (\d+)\s*$', re.M)
ITP_RE = re.compile(r'^\s*(%[\w.$-]+) = inttoptr i64 (%[\w.$-]+) to ptr\s*$', re.M)
LDP_RE = re.compile(r'^\s*(%[\w.$-]+) = load i(\d+), ptr (%[\w.$-]+)', re.M)


def transfer(cs, i, state, homes, ev):
    """audit_lsf.transfer と同じ規則。argN 基底の load は変位を保持する ('ld', n, w, disp)。"""
    mn = i.mnemonic
    ops = i.operands
    if ev is not None:
        ev.extend(A.use_events(cs, i, state, A.ARITY))
    newv = None
    dest = None
    if mn == 'mov' and len(ops) == 2:
        o0, o1 = ops
        if o0.type == capstone.CS_OP_REG and o1.type == capstone.CS_OP_REG:
            dest = norm_reg(cs, o0.reg)
            if o0.size == 8 and o1.size == 8:
                newv = state.get(norm_reg(cs, o1.reg))
        elif o0.type == capstone.CS_OP_REG and o1.type == capstone.CS_OP_MEM:
            dest = norm_reg(cs, o0.reg)
            mb = norm_reg(cs, o1.mem.base) if o1.mem.base else None
            slot = ('m', mb, o1.mem.disp)
            if o1.mem.index == 0 and mb in ('rbp', 'rsp') and o1.size == 8 and (mb, o1.mem.disp) in homes:
                newv = ('arg', homes[(mb, o1.mem.disp)])
            elif o1.mem.index == 0 and mb in ('rbp', 'rsp') and o1.size == 8 and slot in state:
                newv = state[slot]
            elif o1.mem.index == 0 and mb and cs.reg_name(o1.mem.base) != 'rip' and o1.size in (4, 8):
                sv = state.get(mb)
                if sv and sv[0] == 'arg':
                    newv = ('ld', sv[1], o1.size * 8, o1.mem.disp)
                elif STRMOV and sv and sv[0] == 'argoff':
                    newv = ('ld', sv[1], o1.size * 8, sv[2] + o1.mem.disp)
                else:
                    newv = ('ldu', o1.size * 8)
        elif o0.type == capstone.CS_OP_MEM and o1.type == capstone.CS_OP_REG:
            sv = state.get(norm_reg(cs, o1.reg))
            mb = norm_reg(cs, o0.mem.base) if o0.mem.base else None
            frame = mb in ('rbp', 'rsp') and cs.reg_name(o0.mem.base) != 'rip'
            w = o0.size * 8
            if frame and o0.mem.index == 0:
                if sv and w == 64:
                    state[('m', mb, o0.mem.disp)] = sv
                else:
                    state.pop(('m', mb, o0.mem.disp), None)
            if ev is not None and not frame and sv and sv[0] == 'ld' and sv[2] == w:
                ev.append(('dlsf', i.address, sv[1], w, sv[3]))
    post = {}
    if STRMOV and mn == 'lea' and len(ops) == 2 and ops[0].type == capstone.CS_OP_REG and ops[1].type == capstone.CS_OP_MEM:
        m = ops[1].mem
        mb = norm_reg(cs, m.base) if m.base else None
        sv = state.get(mb) if mb and m.index == 0 and cs.reg_name(m.base) != 'rip' else None
        dest = norm_reg(cs, ops[0].reg)
        if sv and sv[0] == 'arg':
            newv = ('argoff', sv[1], m.disp)
        elif sv and sv[0] == 'argoff':
            newv = ('argoff', sv[1], sv[2] + m.disp)
        elif mb in ('rbp', 'rsp') and m.index == 0:
            newv = ('frm',)
    if STRMOV and mn.startswith('movs') and len(ops) == 2 and ops[0].type == capstone.CS_OP_MEM and ops[1].type == capstone.CS_OP_MEM \
            and ops[0].mem.base and ops[1].mem.base and norm_reg(cs, ops[0].mem.base) == 'rdi' and norm_reg(cs, ops[1].mem.base) == 'rsi' \
            and not any(p in (0xf2, 0xf3) for p in i.prefix):
        w = ops[1].size * 8
        ssv, dsv = state.get('rsi'), state.get('rdi')
        soff = (0 if ssv[0] == 'arg' else ssv[2]) if ssv and ssv[0] in ('arg', 'argoff') else None
        if ev is not None and soff is not None and not (dsv and dsv[0] == 'frm'):
            ev.append(('dlsf', i.address, ssv[1], w, soff))
        if soff is not None:
            post['rsi'] = ('argoff', ssv[1], soff + w // 8)
        if dsv and dsv[0] == 'argoff':
            post['rdi'] = ('argoff', dsv[1], dsv[2] + w // 8)
    if mn == 'call':
        for r in A.VOLATILE:
            state.pop(r, None)
    else:
        try:
            _rd, wr = i.regs_access()
        except Exception:
            wr = ()
        for rid in wr:
            r = norm_reg(cs, rid)
            if r:
                state.pop(r, None)
    if dest and newv:
        state[dest] = newv
    state.update(post)


def machine_sites(mach, va, labels):
    """audit_lsf.machine_sites と同じ CFG 不動点 (transfer のみ変位保持版)。LSF site: [(addr, n, w, disp)]。"""
    ins = A.descend(mach, va, labels)
    if not ins:
        return None
    cs = mach.cs
    idx = {i.address for i in ins}
    leaders = {ins[0].address}
    succ = {}
    for k, i in enumerate(ins):
        mn = i.mnemonic
        nxt = ins[k + 1].address if k + 1 < len(ins) else None
        tgt = i.operands[0].imm if i.operands and i.operands[0].type == capstone.CS_OP_IMM else None
        if mn == 'jmp':
            succ[i.address] = [tgt] if tgt in idx else []
            if nxt:
                leaders.add(nxt)
        elif mn.startswith('j') or mn.startswith('loop'):
            succ[i.address] = [x for x in (tgt, nxt) if x in idx]
            if nxt:
                leaders.add(nxt)
        elif mn in ('ret', 'retn', 'ud2', 'int3', 'hlt'):
            succ[i.address] = []
            if nxt:
                leaders.add(nxt)
        else:
            succ[i.address] = [nxt] if nxt else []
        for t in succ[i.address]:
            if t != nxt or mn == 'jmp':
                leaders.add(t)
    homes = {}
    st = {r: ('arg', n) for r, n in A.ARG.items()}
    for i in ins:
        if i.mnemonic == 'call' or i.mnemonic.startswith('j') or i.mnemonic in ('ret', 'retn'):
            break
        ops = i.operands
        if i.mnemonic == 'mov' and len(ops) == 2 and ops[0].type == capstone.CS_OP_MEM and ops[1].type == capstone.CS_OP_REG:
            sv = st.get(norm_reg(cs, ops[1].reg))
            mb = norm_reg(cs, ops[0].mem.base) if ops[0].mem.base else None
            if sv and sv[0] == 'arg' and mb in ('rbp', 'rsp') and ops[0].mem.index == 0 and ops[0].size == 8:
                homes[(mb, ops[0].mem.disp)] = sv[1]
        transfer(cs, i, st, homes, None)
    blocks = []
    cur = []
    for i in ins:
        if i.address in leaders and cur:
            blocks.append(cur)
            cur = []
        cur.append(i)
    if cur:
        blocks.append(cur)
    bidx = {b[0].address: k for k, b in enumerate(blocks)}
    IN = {0: {r: ('arg', n) for r, n in A.ARG.items()}}
    work = [0]
    guard = 0
    while work and guard < 20000:
        guard += 1
        k = work.pop()
        state = dict(IN[k])
        for i in blocks[k]:
            transfer(cs, i, state, homes, None)
        for t in succ[blocks[k][-1].address]:
            tk = bidx.get(t)
            if tk is None:
                continue
            if tk not in IN:
                IN[tk] = dict(state)
                work.append(tk)
            else:
                m = {r: v for r, v in IN[tk].items() if state.get(r) == v}
                if m != IN[tk]:
                    IN[tk] = m
                    work.append(tk)
    sites = []
    for k, b in enumerate(blocks):
        if k not in IN:
            continue
        state = dict(IN[k])
        for i in b:
            ev = []
            transfer(cs, i, state, homes, ev)
            for (kind, ad, n, w, d) in ev:
                if kind == 'dlsf':
                    sites.append((ad, n, w, d))
    return sites


def ir_off_stores(body):
    """IR: [(n, w, c)] = 非 alloca 宛 `store iW %v` で %v が `load iW, ptr (inttoptr (add %argN, c))` (c≠0) の結果。"""
    allocas = set(A.ALLOCA_RE.findall(body))
    add = {m.group(1): (int(m.group(2)[4:]), int(m.group(3))) for m in ADD_RE.finditer(body)}
    itp = {m.group(1): add[m.group(2)] for m in ITP_RE.finditer(body) if m.group(2) in add}
    off_ld = {}
    for m in LDP_RE.finditer(body):
        p = m.group(3)
        if p in itp and itp[p][1] != 0:
            off_ld[m.group(1)] = (itp[p][0], int(m.group(2)), itp[p][1])
    out = []
    for m in A.STORE_RE.finditer(body):
        ty, val, dst = m.group(1), m.group(2), m.group(3).strip()
        if dst in allocas or val not in off_ld:
            continue
        n, lw, c = off_ld[val]
        if lw == A.width_of(ty):
            out.append((n, lw, c))
    return out


def disp_suspects(mach, va, body):
    """関数 va の SIGNAL 判定。(機械語に LSF site があったか, SUSPECT のリスト) を返す。
    audit_lsf.py の --disp と本スクリプトの main が共有する (判定の定義は 1 箇所)。"""
    labels = [int(x, 16) for x in re.findall(r'^dec_label_pc_([0-9a-f]+)[:.]', body, re.M)]
    sites = machine_sites(mach, va, labels)
    if not sites:
        return False, []
    mach_d = collections.defaultdict(set)
    for (_ad, n, w, d) in sites:
        mach_d[(n, w)].add(d)
    ir = collections.defaultdict(set)
    for (n, w, c) in ir_off_stores(body):
        ir[(n, w)].add(c)
    sus = []
    for key in sorted(ir):
        if key not in mach_d:
            continue
        miss = sorted(c for c in ir[key] if c not in mach_d[key])
        if miss:
            sus.append(dict(arg=key[0], width=key[1], machine_disps=sorted(mach_d[key]),
                            ir_offsets=sorted(ir[key]), miss=miss))
    return True, sus


def main():
    global STRMOV
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('image')
    ap.add_argument('cfg')
    ap.add_argument('--json')
    ap.add_argument('--only')
    ap.add_argument('--pe')
    ap.add_argument('--no-strmov', action='store_true', help='文字列転送 (movs) と lea 経由の変位を列挙しない (#2316 時点の挙動)')
    a = ap.parse_args()
    STRMOV = not a.no_strmov
    only = set(int(x, 16) for x in a.only.split(',')) if a.only else None
    text = open(a.ir, errors='replace').read()
    mach = Machine(a.pe) if a.pe else ImageMachine(a.image, a.cfg)
    for m in A.DEF_RE.finditer(text):
        A.ARITY[int(m.group(1), 16)] = len([x for x in m.group(2).split(',') if x.strip()])
    out = collections.OrderedDict()
    tot = collections.Counter()
    for va, _args, body in A.ir_functions(text):
        if only and va not in only:
            continue
        tot['functions'] += 1
        has_sites, sus = disp_suspects(mach, va, body)
        if not has_sites:
            continue
        tot['mach_fns'] += 1
        if sus:
            out['%x' % va] = sus
            tot['suspect_fns'] += 1
            tot['suspect_keys'] += len(sus)
    print(json.dumps(dict(tot)))
    print('SUSPECT_DISP_VAS ' + ' '.join(sorted(out, key=lambda x: int(x, 16))))
    if a.json:
        json.dump(out, open(a.json, 'w'), indent=1)


if __name__ == '__main__':
    main()
