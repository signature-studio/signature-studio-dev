#!/usr/bin/env python3
"""audit_lsf.py — 「load→store 転送の deref 脱落」(D4 store 形) の全数監査 (#484 / LD-8)。

対象の形 (5c0270 の unlink = `node.next` を別の場所へ書く操作):
  機械語  `mov rD,[rB]` (disp 0)  →  rD を壊さず  `mov [m],rD`      (rB の値は argN に解決できる)
  脱落形  IR が `load` を落とし、`store iW %argN, ptr m` (= ポインタ rB 自身) を書く
ldfix.fix_f3c とは**別算法**: IR ブロックと機械語ブロックの対応 (block-local) を使わず、関数単位の個数収支で判定する。
  M_lsf[n,w]   機械語: argN に解決できる rB からの zero-disp load の値が、そのまま w ビットで store される site 数
  M_ptr[n,w]   機械語: argN そのもの (load 無し) を w ビットで store する site 数 (正当なポインタ store。frame (rbp/rsp) 宛は除外)
  IR_st[n,w]   IR: `store iW %argN` (trunc/zext 経由含む) の行数 (alloca 宛は除外)
  SUSPECT      M_lsf[n,w] >= 1 かつ IR_st[n,w] > M_ptr[n,w]   (excess = IR_st - M_ptr)
機械語の値追跡は straight-line の簡易記号実行 (レジスタ→('arg',n) | ('ld',n,w) | ('ldu',w))。分岐先 (jmp/jcc の直接 target) で
レジスタ状態を全消去し (stack home は維持)、call は volatile reg を消去する。

使い方: python3 audit_lsf.py IR.ll IMAGE.bin 'CONFIG_GLOB' [--json OUT] [--only VA,VA] [--pe PE]    (--pe 指定時は PE の .pdata を使う)
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach import Machine, norm_reg  # noqa: E402
from ldmach_img import ImageMachine  # noqa: E402
import capstone  # noqa: E402

ARG = {'rcx': 1, 'rdx': 2, 'r8': 3, 'r9': 4}
VOLATILE = ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11')
DEF_RE = re.compile(r'^define [^@]*@function_([0-9a-f]+)\(([^)]*)\)[^{]*\{', re.M)
ALLOCA_RE = re.compile(r'^\s*(%[\w.$-]+) = alloca ', re.M)
CAST_RE = re.compile(r'^\s*(%[\w.$-]+) = (trunc|zext|inttoptr|ptrtoint|bitcast) (?:i\d+|ptr) (%arg\d+) to (i\d+|ptr)\s*$', re.M)
STORE_RE = re.compile(r'^\s*store (i\d+|ptr) (%[\w.$-]+), ptr ([^,\n]+)', re.M)
LOAD_RE = re.compile(r'^\s*(%[\w.$-]+) = load (i\d+), ptr ([^,\n]+)', re.M)


def width_of(t):
    return 64 if t == 'ptr' else int(t[1:])


def transfer(cs, i, state, homes, ev):
    """命令 1 個の記号実行 (state を破壊更新)。ev (list) があれば site を記録する。"""
    mn = i.mnemonic
    ops = i.operands
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
            elif o1.mem.index == 0 and o1.mem.disp == 0 and mb and cs.reg_name(o1.mem.base) != 'rip' and o1.size in (4, 8):
                sv = state.get(mb)
                newv = ('ld', sv[1], o1.size * 8) if sv and sv[0] == 'arg' else ('ldu', o1.size * 8)
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
            if ev is None:
                sv = None
            if sv and sv[0] == 'ld' and sv[2] == w:
                ev.append(('lsf', i.address, sv[1], w, '%s %s' % (mn, i.op_str)))
            elif sv and sv[0] == 'ldu' and sv[1] == w:
                ev.append(('unk', i.address, 0, w, ''))
            elif sv and sv[0] == 'arg' and not frame:
                ev.append(('ptr', i.address, sv[1], w, ''))
    if mn == 'call':
        for r in VOLATILE:
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


def descend(mach, va, labels):
    """再帰降下で関数の命令列を得る。root = 関数 entry + IR の dec_label_pc_* (RetDec が見つけたブロック先頭)。
    直接 jmp/jcc の target は [va, limit) の内側だけ辿る (tail call の誤追跡防止)。
    limit = max(区間表の end, 最大 IR ラベル + 1)。RetDec config の endAddr は 537/7421 関数で IR ラベルより短い (REPORT_484 §2) ため、
    区間表 (config / .pdata) をそのまま使わずラベルで補う。"""
    ent = mach.fns.get(va)
    if not ent:
        return None
    limit = max(va + ent[1], max(labels, default=0) + 1)
    cs = mach.cs
    seen = {}
    todo = [va] + [x for x in labels if va <= x < limit]
    while todo:
        a = todo.pop()
        while va <= a < limit and a not in seen:
            code = mach.read(a - mach.base, 16)
            got = list(cs.disasm(code, a, 1))
            if not got:
                break
            i = got[0]
            seen[a] = i
            mn = i.mnemonic
            tgt = i.operands[0].imm if i.operands and i.operands[0].type == capstone.CS_OP_IMM else None
            if (mn == 'jmp' or mn.startswith('j') or mn.startswith('loop')) and tgt is not None and va <= tgt < limit:
                todo.append(tgt)
            if mn in ('jmp', 'ret', 'retn', 'ud2', 'int3', 'hlt'):
                break
            a += i.size
    return [seen[k] for k in sorted(seen)]


def machine_sites(mach, va, labels=()):
    """関数 va の CFG 上の前向きデータフロー (join は一致する値のみ残す) →
    (lsf: list[(addr,n,w,text)], ptr: Counter[(n,w)], lsf_unk: int)"""
    ins = descend(mach, va, labels)
    if not ins:
        return None
    cs = mach.cs
    idx = {i.address: k for k, i in enumerate(ins)}
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
    # phase 1: prologue の stack home (mov [rbp|rsp+d], argreg) を最初の分岐/call まで線形に収集
    homes = {}
    st = {r: ('arg', n) for r, n in ARG.items()}
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
    # phase 2: 基本ブロック単位の不動点
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
    IN = {0: {r: ('arg', n) for r, n in ARG.items()}}
    work = [0]
    guard = 0
    while work and guard < 20000:
        guard += 1
        k = work.pop()
        state = dict(IN[k])
        for i in blocks[k]:
            transfer(cs, i, state, homes, None)
        last = blocks[k][-1]
        for t in succ[last.address]:
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
    lsf, ptr, unk = [], collections.Counter(), 0
    for k, b in enumerate(blocks):
        if k not in IN:
            continue
        state = dict(IN[k])
        for i in b:
            ev = []
            transfer(cs, i, state, homes, ev)
            for (kind, ad, n, w, t) in ev:
                if kind == 'lsf':
                    lsf.append((ad, n, w, t))
                elif kind == 'ptr':
                    ptr[(n, w)] += 1
                else:
                    unk += 1
    return lsf, ptr, unk


def ir_functions(text):
    for m in DEF_RE.finditer(text):
        end = text.index('\n}', m.end()) + 2
        yield int(m.group(1), 16), m.group(2), text[m.start():end]


def ir_stores(body):
    """IR: Counter[(n,w)] = `store iW %argN` 行数 (alloca 宛除外) と、argN を zero offset で読む load 数"""
    allocas = set(ALLOCA_RE.findall(body))
    alias = {}
    ptr_alias = {}
    for name, op, arg, to in CAST_RE.findall(body):
        n = int(arg[4:])
        if op in ('trunc', 'zext'):
            alias[name] = (n, width_of(to))
        elif op == 'inttoptr':
            ptr_alias[name] = n
    st = collections.Counter()
    lines = {}
    for ty, val, dst in STORE_RE.findall(body):
        dst = dst.strip()
        if dst in allocas:
            continue
        if re.fullmatch(r'%arg\d+', val):
            k = (int(val[4:]), width_of(ty))
        elif val in alias and alias[val][1] == width_of(ty):
            k = alias[val]
        else:
            continue
        st[k] += 1
        lines.setdefault(k, []).append('store %s %s, ptr %s' % (ty, val, dst))
    ld = collections.Counter()
    for _nm, ty, src in LOAD_RE.findall(body):
        src = src.strip()
        if re.fullmatch(r'%arg\d+', src):
            ld[(int(src[4:]), width_of(ty))] += 1
        elif src in ptr_alias:
            ld[(ptr_alias[src], width_of(ty))] += 1
    return st, ld, lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('image')
    ap.add_argument('cfg')
    ap.add_argument('--json')
    ap.add_argument('--only')
    ap.add_argument('--pe')
    a = ap.parse_args()
    only = set(int(x, 16) for x in a.only.split(',')) if a.only else None
    text = open(a.ir, errors='replace').read()
    mach = Machine(a.pe) if a.pe else ImageMachine(a.image, a.cfg)
    out = collections.OrderedDict()
    tot = collections.Counter()
    for va, _args, body in ir_functions(text):
        if only and va not in only:
            continue
        tot['functions'] += 1
        labels = [int(x, 16) for x in re.findall(r'^dec_label_pc_([0-9a-f]+)[:.]', body, re.M)]
        ent = mach.fns.get(va)
        if ent and labels and max(labels) >= va + ent[1]:
            tot['range_table_shorter_than_ir_labels'] += 1
        if ent and ent[1] <= 2:
            tot['range_table_le_2_bytes'] += 1
        ms = machine_sites(mach, va, labels)
        if ms is None:
            tot['no_machine_range'] += 1
            continue
        lsf, ptr, unk = ms
        tot['mach_fns'] += 1
        tot['lsf_sites'] += len(lsf)
        tot['lsf_unresolved_base_sites'] += unk
        tot['fns_with_unresolved_base'] += 1 if unk else 0
        if not lsf:
            continue
        tot['fns_with_lsf'] += 1
        st, ld, lines = ir_stores(body)
        cnt = collections.Counter((n, w) for (_ad, n, w, _t) in lsf)
        sus = []
        for (n, w), m_lsf in sorted(cnt.items()):
            excess = st[(n, w)] - ptr[(n, w)]
            if excess > 0:
                sus.append(dict(arg=n, width=w, m_lsf=m_lsf, m_ptr=ptr[(n, w)], ir_store=st[(n, w)], excess=excess,
                                ir_loads_of_arg=ld[(n, w)],
                                mach_sites=['%x: %s' % (ad, t) for (ad, nn, ww, t) in lsf if (nn, ww) == (n, w)],
                                ir_lines=lines.get((n, w), [])))
        if sus:
            out['%x' % va] = sus
            tot['suspect_fns'] += 1
            tot['suspect_sites'] += sum(s['excess'] for s in sus)
    summary = dict(tot)
    summary['suspect_vas'] = sorted(out.keys(), key=lambda x: int(x, 16))
    print(json.dumps({k: v for k, v in summary.items() if k != 'suspect_vas'}, ensure_ascii=False))
    print('SUSPECT_VAS ' + ' '.join(summary['suspect_vas']))
    if a.json:
        json.dump(dict(summary=summary, suspects=out), open(a.json, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
