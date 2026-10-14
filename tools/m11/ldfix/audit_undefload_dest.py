#!/usr/bin/env python3
"""audit_undefload_dest.py — audit_undefload.py の拡張 (#1647 / #564 残件)。

既存監査は「消費者 IR 命令の !insn.addr の機械語命令」のメモリ read だけを見る。消費者が read 命令と別の命令
(`mov eax,[rbp+x]; and eax,...`) だと、消費者側には memop が無く REGLIVE に落ちて偽陰性になる (REPORT_564 §3)。

本監査は、消費者命令が読むレジスタ (capstone regs_read) を、同じ関数の線型 disasm で直前に書いた命令まで遡り、
その命令がメモリを read していれば (dest 追跡) その種別で分類する。遡りは call / ret / 無条件 jmp で止める
(IR ブロック境界の厳密な判定はしない近似)。

分類 (consumer 直接 memop の判定は audit_undefload と同じ。REGLIVE だったものだけ dest 追跡を試す):
  DEST_FRAME_IN_ESCAPED  dest 元が escape 済み stack_var 内部の frame read (= 本件の型の候補)
  DEST_FRAME_PTR_ESCAPED 同上だが、consumer が dest 値をメモリアドレス (base/index) に使う (ポインタ値 read)
  DEST_FRAME_OTHER       dest 元が frame read だが escape 無し / 解決不能
  DEST_MEMREAD           dest 元が非 frame の memory read
  REGLIVE                dest 追跡でも memory read に辿れない (従来どおり脱落ではない扱い)
  NOADDR                 insn.addr 無し

使い方: python3 audit_undefload_dest.py PE.bin OUT.json IN.norm0.ll [IN2 ...]
"""
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach import Machine, memops_of  # noqa: E402
from ldframe import is_write_only, frame_model, escaped_stack_vars  # noqa: E402
from audit_undefload import scan_text, META_RE, DEF_RE, INSN_RE  # noqa: E402

STOP_MN = ('call', 'ret', 'jmp')
BACK_MAX = 16
LOAD_RE = re.compile(r'^  (%[\w.$-]+) = load (i\d+), ptr (%[\w.$-]+)(?![\w.$-])')


def named_stack_reads(body, svars):
    """escape 済み名前付き stack_var の load (直接、または ptrtoint/add/inttoptr 経由 = ldfix F4 の形) を返す。
    戻り値: [(load 名, ty, stack_var 番号, 先頭からの offset, load 行)]。"""
    ptr, num = {}, {}
    for n, e in svars.items():
        if e:
            ptr['%%stack_var_-%d' % n] = (n, 0)
    lines = body.split('\n')
    for _ in range(2):
        for l in lines:
            m = re.match(r'^\s*(%[\w.$-]+) = (.*)$', l)
            if not m:
                continue
            d, rhs = m.groups()
            mm = re.match(r'bitcast ptr (%[\w.$-]+) to ptr$', rhs)
            if mm and mm.group(1) in ptr:
                ptr[d] = ptr[mm.group(1)]
                continue
            mm = re.match(r'ptrtoint ptr (%[\w.$-]+) to i64$', rhs)
            if mm and mm.group(1) in ptr:
                num[d] = ptr[mm.group(1)]
                continue
            mm = re.match(r'add i64 (%[\w.$-]+), (-?\d+)$', rhs)
            if mm and mm.group(1) in num:
                b, o = num[mm.group(1)]
                num[d] = (b, o + int(mm.group(2)))
                continue
            mm = re.match(r'inttoptr i64 (%[\w.$-]+) to ptr$', rhs)
            if mm and mm.group(1) in num:
                ptr[d] = num[mm.group(1)]
    out = []
    for l in lines:
        lm = LOAD_RE.match(l)
        if lm and lm.group(3) in ptr:
            n, off = ptr[lm.group(3)]
            out.append((lm.group(1), lm.group(2), n, off, l))
    return out


def scan_named_text(text, meta):
    """escape 済み名前付き stack_var の load 1 件ごとに consumer (!insn.addr) を集める (F4 相当の site 抽出)。"""
    for m in DEF_RE.finditer(text):
        end = text.index('\n}', m.end()) + 2
        body = text[m.start():end]
        if '%stack_var_-' not in body:
            continue
        svars = escaped_stack_vars(body)
        lines = body.split('\n')
        for (v, ty, n, off, _l) in named_stack_reads(body, svars):
            cons = []
            for j, l2 in enumerate(lines):
                if not re.search(re.escape(v) + r'(?![\w.$-])', l2) or re.match(r'^  %s = ' % re.escape(v), l2):
                    continue
                im = INSN_RE.search(l2)
                cons.append((l2.strip()[:120], meta.get(int(im.group(1))) if im else None))
            yield dict(fn=m.group(1), va=int(m.group(2), 16), load=v, ty=ty, sv=n, off=off, cons=cons)


def run_named(pe, out, paths):
    mach = Machine(pe)
    sites = []
    for path in paths:
        text = open(path, errors='replace').read()
        meta = {int(a): int(b) for a, b in META_RE.findall(text)}
        for rec in scan_named_text(text, meta):
            mins = mach.disasm_fn(rec['va']) or []
            cons = []
            for (txt, addr) in rec['cons']:
                ins = next((i for i in mins if i.address == addr), None) if addr is not None else None
                cons.append(dict(ir=txt, addr=('%x' % addr) if addr is not None else None,
                                 mn=('%s %s' % (ins.mnemonic, ins.op_str)) if ins is not None else None))
            if not cons:
                continue
            sites.append(dict(fn='%x' % rec['va'], load=rec['load'], ty=rec['ty'], sv='stack_var_-%d' % rec['sv'],
                              off=rec['off'], cons=cons[:3], file=os.path.basename(path)))
    fns = sorted(set(s['fn'] for s in sites))
    res = dict(sites_total=len(sites), functions=fns, sites=sorted(sites, key=lambda s: s['fn']))
    json.dump(res, open(out, 'w'), indent=1)
    print('named sites', len(sites), 'functions', len(fns), ' '.join(fns))


def regs_of(cs, ids):
    out = set()
    for r in ids:
        n = cs.reg_name(r)
        if n:
            out.add(n.lower())
    return out


def reads_of(cs, ins):
    """命令が値を読むレジスタ (memory オペランドの base/index を含む。dest のみの mov 先は除く)。"""
    import capstone
    out = set(regs_of(cs, ins.regs_read))
    ops = ins.operands
    for i, op in enumerate(ops):
        if op.type == capstone.CS_OP_REG and i > 0 or (op.type == capstone.CS_OP_REG and i == 0 and ins.mnemonic not in ('mov', 'movzx', 'movsx', 'movsxd', 'lea')):
            n = cs.reg_name(op.reg)
            if n:
                out.add(n.lower())
        if op.type == capstone.CS_OP_MEM:
            for r in (op.mem.base, op.mem.index):
                if r:
                    n = cs.reg_name(r)
                    if n:
                        out.add(n.lower())
    return out


def norm_reg64(name):
    from ldmach import _REG_ALIAS
    return _REG_ALIAS.get(name)


def mem_read_of(cs, ins):
    reads = [mo for mo in memops_of(cs, ins) if mo['kind'] in ('load', 'rmw', 'other')]
    if is_write_only(ins):
        return None
    return reads[0] if reads else None


def trace_dest(mach, va, addr, cs_ins):
    """consumer (addr) が読むレジスタを直前に書いた命令を辿り、その memory read を返す。(mo, writer_ins) or (None, None)"""
    cs = mach.cs
    seq = mach.disasm_fn(va) or []
    idx = next((i for i, x in enumerate(seq) if x.address == addr), None)
    if idx is None:
        return None, None
    want = {norm_reg64(r) for r in reads_of(cs, cs_ins)} - {None, 'rsp', 'rbp', 'rip'}
    if not want:
        return None, None
    for j in range(idx - 1, max(-1, idx - 1 - BACK_MAX), -1):
        w = seq[j]
        if w.mnemonic.startswith(STOP_MN):
            break
        wr = set()
        if w.operands and w.operands[0].type == 1 and w.mnemonic not in ('cmp', 'test'):
            wr.add(norm_reg64(cs.reg_name(w.operands[0].reg)))
        if want & wr:
            mo = mem_read_of(cs, w)
            return mo, w
    return None, None


def used_as_ptr(mach, cs_ins, w):
    """consumer が dest 元 (w のレジスタ) をメモリオペランドの base/index に使うなら True (ポインタ値 read)。"""
    import capstone
    cs = mach.cs
    wr = {norm_reg64(cs.reg_name(w.operands[0].reg))} if w.operands and w.operands[0].type == 1 else set()
    for op in cs_ins.operands:
        if op.type == capstone.CS_OP_MEM:
            for r in (op.mem.base, op.mem.index):
                if r and norm_reg64(cs.reg_name(r)) in wr:
                    return True
    return False


def classify_dest(mach, va, addr, cs_ins, fm, svars):
    mo, w = trace_dest(mach, va, addr, cs_ins)
    if mo is None:
        return 'REGLIVE', None
    if mo.get('rip_rva') is not None:
        return 'DEST_RIPREAD', w
    if mo['base'] in ('rbp', 'rsp') and not mo['index'] and fm is not None:
        rs, rb = fm.get(w.address, (None, None))
        basev = rs if mo['base'] == 'rsp' else rb
        if basev is None:
            return 'DEST_FRAME_OTHER', w
        o = basev + mo['disp']
        cover = [n for n in svars if -n <= o]
        n = min(cover, key=lambda n: o + n) if cover else None
        if n is not None and svars[n] and o - (-n) < 4096:
            if used_as_ptr(mach, cs_ins, w):
                return 'DEST_FRAME_PTR_ESCAPED', w
            return 'DEST_FRAME_IN_ESCAPED', w
        return 'DEST_FRAME_OTHER', w
    if mo['base'] in ('rbp', 'rsp'):
        return 'DEST_FRAME_OTHER', w
    return 'DEST_MEMREAD', w


def main():
    if sys.argv[1] == '--named':
        return run_named(sys.argv[2], sys.argv[3], sys.argv[4:])
    pe, out = sys.argv[1], sys.argv[2]
    mach = Machine(pe)
    sites = []
    fcache = {}
    for path in sys.argv[3:]:
        text = open(path, errors='replace').read()
        meta = {int(a): int(b) for a, b in META_RE.findall(text)}
        for rec in scan_text(text, meta):
            if rec['fn'] not in fcache:
                mm = re.search(r'^define [^\n]*@%s\(.*?^\}' % rec['fn'], text, re.S | re.M)
                fcache[rec['fn']] = (frame_model(mach.cs, mach.disasm_fn(rec['va']) or []),
                                     escaped_stack_vars(mm.group(0)) if mm else {})
            fm, svars = fcache[rec['fn']]
            cls = collections.Counter()
            detail = []
            for (txt, addr) in rec['cons']:
                if addr is None:
                    cls['NOADDR'] += 1
                    continue
                ins = next((i for i in (mach.disasm_fn(rec['va']) or []) if i.address == addr), None)
                if ins is None:
                    cls['NOADDR'] += 1
                    continue
                if any(mo['kind'] in ('load', 'rmw', 'other') for mo in memops_of(mach.cs, ins)) and not is_write_only(ins):
                    continue
                k, w = classify_dest(mach, rec['va'], addr, ins, fm, svars)
                cls[k] += 1
                if k.startswith('DEST_') and w is not None:
                    detail.append('%x %s %s <- %x %s %s' % (addr, ins.mnemonic, ins.op_str, w.address, w.mnemonic, w.op_str))
            if not cls:
                continue
            top = next((k for k in ('DEST_FRAME_IN_ESCAPED', 'DEST_FRAME_PTR_ESCAPED', 'DEST_FRAME_OTHER', 'DEST_RIPREAD', 'DEST_MEMREAD', 'REGLIVE', 'NOADDR') if cls[k]), 'NOADDR')
            sites.append(dict(fn='%x' % rec['va'], ty=rec['ty'], cls=top, detail=detail[:3], file=os.path.basename(path)))
    tally = collections.Counter(s['cls'] for s in sites)
    fns = collections.defaultdict(set)
    for s in sites:
        fns[s['cls']].add(s['fn'])
    res = dict(sites_total=len(sites), by_class=dict(tally), fns_by_class={k: len(v) for k, v in fns.items()},
               dest_frame_in_escaped=sorted([s for s in sites if s['cls'] == 'DEST_FRAME_IN_ESCAPED'], key=lambda s: s['fn']),
               dest_frame_ptr_escaped=sorted([s for s in sites if s['cls'] == 'DEST_FRAME_PTR_ESCAPED'], key=lambda s: s['fn']))
    json.dump(res, open(out, 'w'), indent=1)
    print('sites', len(sites), dict(tally), {k: len(v) for k, v in fns.items()})


if __name__ == '__main__':
    main()
