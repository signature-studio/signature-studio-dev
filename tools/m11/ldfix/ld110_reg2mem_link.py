#!/usr/bin/env python3
"""ld110_reg2mem_link.py — #2389 (LD-110) cf3790 の spill 宛 3 site (cf3c7a・cf3cbb・cf3d20) の reg2mem 結線。

機械語の `[rbp+disp]` store と IR の `stack_var` の対応を、プロローグから求めた frame 位置で取る。
  F = push 数 * 8 + `sub rsp, imm` ; rbp = entry_rsp - F ; `[rbp+disp]` <-> `stack_var_-(F - disp)`
  (旧表 ld105 の `-(disp+8)` は frame 位置の仮定が誤り。プロローグの 0 初期化 store 8 本で検証する)
site ごとに次を突き合わせ、TRUE_DROP / OK_LOAD を決める:
  機械語   `mov rA,[rip+X]` -> `mov rD,[rA]` -> `mov [rbp+d],rD` の deref 段数 (2) と、slot の以後の読み書き
  IR       セル K = X - base を読む `load` (%Q) の段数、%Q の消費者、`stack_var_-(F-d).*.reg2mem` の store と reload
ネガティブコントロール: NC1 旧式 `-(d+8)` / NC2 IR を 2 段 load に直す / NC3 site と slot の取り違え。
使い方: python3 ld110_reg2mem_link.py [OUT.tsv]      環境変数: M11_WORK (既定 tools/m11/work)
"""
import os
import re
import sys

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '../../..'))
sys.path.insert(0, HERE)
from ldmach_img import ImageMachine  # noqa: E402

FN = 0xcf3790
FN_LEN = 0x1000
SITES = ['cf3c7a', 'cf3cbb', 'cf3d20']
MEM_RBP = re.compile(r'\[rbp \+ (0x[0-9a-f]+)\]')


def frame_size(ins):
    """プロローグ (`mov rbp, rsp` まで) の push と `sub rsp, imm` から F を返す"""
    f = 0
    for x in ins:
        if x.mnemonic == 'push':
            f += 8
        elif x.mnemonic == 'sub' and x.op_str.startswith('rsp, '):
            f += int(x.op_str.split(', ')[1], 16)
        elif x.mnemonic == 'mov' and x.op_str == 'rbp, rsp':
            return f
    raise RuntimeError('`mov rbp, rsp` がプロローグに無い')


def prologue_check(ins, body, name_of):
    """プロローグの `mov qword ptr [rbp+d], 0` と、IR 入口の `store .. 0|null, ptr %stack_var_N` が name_of(d) で対応する数"""
    pro = []
    for x in ins:
        if x.mnemonic == 'call':
            break
        m = re.match(r'qword ptr \[rbp \+ (0x[0-9a-f]+)\], 0$', x.op_str)
        if x.mnemonic == 'mov' and m:
            pro.append(int(m.group(1), 16))
    ok = 0
    for d in pro:
        pat = r'store \S+ (?:0|null), ptr %' + re.escape(name_of(d)) + r'(?:,|$)'
        if any(re.search(pat, l) for l in body[:120]):
            ok += 1
    return ok, len(pro)


def imm_check(ins, body, name_of):
    """関数全体の `mov <幅> ptr [rbp+d], imm` と、IR の同 slot (`.N.reg2mem` 付きも可) への同値 const store の対応数。(一致, 総数, 不一致 site)"""
    ok, tot, miss = 0, 0, []
    for x in ins:
        m = re.match(r'(?:byte|word|dword|qword) ptr \[rbp \+ (0x[0-9a-f]+)\], (-?(?:0x)?[0-9a-f]+)$', x.op_str)
        if x.mnemonic != 'mov' or not m:
            continue
        tot += 1
        d, v = int(m.group(1), 16), int(m.group(2), 0 if m.group(2).lstrip('-').startswith('0x') else 10)
        pat = re.compile(r'store \S+ (-?\d+|null|true|false), ptr %' + re.escape(name_of(d)) + r'(?:\.\d+\.reg2mem)?(?:,|$)')
        got = {(0 if g in ('null', 'false') else 1 if g == 'true' else int(g)) for l in body for g in pat.findall(l)}
        if v in got:
            ok += 1
        else:
            miss.append('%x' % x.address)
    return ok, tot, miss


def ir_depth(defs, val, seen=0):
    """値 %val の deref 段数。`load T, ptr inttoptr(const)` = 1、`load T, ptr %p` (%p = inttoptr %v) = 1 + depth(%v)。不明は None"""
    if seen > 8 or val not in defs:
        return None
    l = defs[val]
    m = re.search(r'= load \S+, ptr inttoptr \(i64 \d+ to ptr\)', l)
    if m:
        return 1
    m = re.search(r'= load \S+, ptr (%[\w.\-]+)', l)
    if m and m.group(1) in defs:
        p = defs[m.group(1)]
        m2 = re.search(r'= inttoptr i64 (%[\w.\-]+) to ptr', p)
        if m2:
            d = ir_depth(defs, m2.group(1), seen + 1)
            return None if d is None else d + 1
    return None


def load_machine(w):
    mach = ImageMachine(os.path.join(w, 'm11_image.bin'), os.path.join(w, 'boot*.drc.config.json'))
    ins = list(mach.cs.disasm(mach.read(FN - mach.base, FN_LEN), FN, FN_LEN))
    return mach, ins


def load_ir(w):
    ll = open(os.path.join(w, 'boot_final3.ll')).read().splitlines()
    start = next(i for i, l in enumerate(ll) if l.startswith('define weak i64 @function_cf3790('))
    end = next(i for i in range(start, len(ll)) if ll[i] == '}')
    return start, ll[start:end]


def machine_side(mach, ins, idx, site, disp_of):
    a = int(site, 16)
    i = idx[a]
    d = disp_of(ins[i])
    deref, cell = ins[i - 1], ins[i - 2]
    m1 = re.match(r'(\w+), qword ptr \[(\w+)\]$', deref.op_str)
    m0 = re.match(r'(\w+), qword ptr \[rip \+ (0x[0-9a-f]+)\]$', cell.op_str)
    if not (deref.mnemonic == 'mov' and m1 and cell.mnemonic == 'mov' and m0 and m1.group(2) == m0.group(1)):
        raise RuntimeError('%s: 2 段 deref の形でない' % site)
    x = cell.address + cell.size + int(m0.group(2), 16)
    k = x - mach.base
    v = int.from_bytes(mach.read(x - mach.base, 8), 'little')
    refs, stores = [], 0
    for y in ins[i + 1:]:
        mm = MEM_RBP.search(y.op_str)
        if not mm or int(mm.group(1), 16) != d:
            continue
        is_store = y.mnemonic == 'mov' and y.op_str.startswith('qword ptr [rbp + ' + hex(d) + ']')
        refs.append('%x %s %s' % (y.address, y.mnemonic, y.op_str))
        stores += is_store
        if stores >= 1 and not is_store:
            break
    return dict(disp=d, cell=cell, deref=deref, x=x, k=k, v=v, depth=2,
                chain='%x %s %s; %x %s %s; %x %s %s' % (cell.address, cell.mnemonic, cell.op_str,
                                                        deref.address, deref.mnemonic, deref.op_str,
                                                        a, ins[i].mnemonic, ins[i].op_str),
                refs=refs)


def dest_slot(body, val):
    """値 val (と、その trunc/zext/sext) を store する `%stack_var_N.k.reg2mem` の stack_var_N 一覧"""
    vals = {val}
    for _ in range(3):
        for l in body:
            mc = re.match(r'\s+(%[\w.\-]+) = (?:trunc|zext|sext) \S+ (%[\w.\-]+) to', l)
            if mc and mc.group(2) in vals:
                vals.add(mc.group(1))
    out = set()
    for l in body:
        ms_ = re.match(r'\s+store \S+ (%[\w.\-]+), ptr %(stack_var_-\d+)\.\d+\.reg2mem\b', l)
        if ms_ and ms_.group(1) in vals:
            out.add(ms_.group(2))
    return out


def ir_side(body, base_line, ms, name):
    """%Q (セル K を読む load) を site の cell load が属する IR ブロックから探し、消費者と reg2mem 結線を集める"""
    labels = [(int(m.group(1), 16), i) for i, l in enumerate(body) for m in [re.match(r'dec_label_pc_([0-9a-f]+)[.\w]*:', l)] if m]
    ca = ms['cell'].address
    blk = max((a, i) for a, i in labels if a <= ca)
    defs = {}
    for l in body:
        m = re.match(r'\s+(%[\w.\-]+) = (.*)', l)
        if m:
            defs[m.group(1)] = l.strip()
    pat = re.compile(r'\s+(%[\w.\-]+) = load (i\d+), ptr inttoptr \(i64 ' + str(ms['k']) + r' to ptr\)')
    q = None
    for i in range(blk[1], len(body)):
        if i > blk[1] and re.match(r'dec_label_pc_', body[i]):
            break
        m = pat.match(body[i])
        if m:
            q, qline = m.group(1), i
            break
    if q is None:
        return dict(q=None)
    c = q
    while True:
        nxt = None
        for i in range(qline + 1, len(body)):
            if re.match(r'dec_label_pc_', body[i]):
                break
            mi = re.match(r'\s+(%[\w.\-]+) = inttoptr i64 ' + re.escape(c) + ' to ptr', body[i])
            if mi:
                for j in range(i + 1, min(i + 3, len(body))):
                    ml = re.match(r'\s+(%[\w.\-]+) = load i64, ptr ' + re.escape(mi.group(1)) + r'(?:,|$)', body[j])
                    if ml:
                        nxt = (ml.group(1), j)
        if not nxt:
            break
        q, qline = nxt
        c = q
    use = re.compile(re.escape(q) + r'(?![\w.\-])')
    cons = [(i, l.strip()) for i, l in enumerate(body) if i != qline and use.search(l)]
    direct = [(i, l) for i, l in cons if re.search('icmp eq i64 ' + re.escape(q) + ', 0|add i64 ' + re.escape(q) + ', -8', l)]
    # add Q,-8 -> inttoptr -> load(%L) -> store %L, ptr %stack_var_N.*.reg2mem
    chain = []
    for i, l in direct:
        m = re.match(r'(%[\w.\-]+) = add i64 ' + re.escape(q) + ', -8', l)
        if not m:
            continue
        p = m.group(1)
        for j in range(i + 1, min(i + 6, len(body))):
            mi = re.match(r'\s+(%[\w.\-]+) = inttoptr i64 ' + re.escape(p) + ' to ptr', body[j])
            if mi:
                pp = mi.group(1)
                for k2 in range(j + 1, min(j + 4, len(body))):
                    ml = re.match(r'\s+(%[\w.\-]+) = load i64, ptr ' + re.escape(pp) + ',', body[k2])
                    if ml:
                        chain.append((i, j, k2, ml.group(1)))
    stores, reload, reload_use = [], None, None
    sv = re.compile(r'store (\S+) (\S+), ptr (%' + re.escape(name) + r'\.\d+\.reg2mem)\b')
    for i, l in enumerate(body):
        m = sv.search(l)
        if m:
            stores.append((i, l.strip(), m.group(3)))
    st_regs = {s[2] for s in stores}
    for reg in st_regs:
        for i, l in enumerate(body):
            m = re.match(r'\s+(%[\w.\-]+) = load \S+, ptr ' + re.escape(reg) + '$', l)
            if m:
                reload = (i, l.strip())
                u = re.compile(re.escape(m.group(1)) + r'(?![\w.\-])')
                reload_use = next(((j, y.strip()) for j, y in enumerate(body) if j != i and u.search(y)), None)
    depth = ir_depth(defs, q)
    chain_dest = [(c, dest_slot(body, c[3])) for c in chain]
    return dict(q=q, qline=qline, qdef=body[qline].strip(), depth=depth, direct=direct, chain=chain, chain_dest=chain_dest,
                linked=any(name in d for _c, d in chain_dest),
                stores=stores, reload=reload, reload_use=reload_use, defs=defs)


def verdict(ms, ir):
    if ir.get('q') is None or ir['depth'] is None or not ir['linked']:
        return 'UNDETERMINED'
    return 'TRUE_DROP' if ir['depth'] < ms['depth'] else 'OK_LOAD'


def ln(base_line, i):
    return base_line + i + 1


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'results/ld110_reg2mem_link.tsv')
    w = os.environ.get('M11_WORK', os.path.join(REPO, 'tools/m11/work'))
    mach, ins = load_machine(w)
    idx = {x.address: i for i, x in enumerate(ins)}
    start, body = load_ir(w)
    f = frame_size(ins)
    new = lambda d: 'stack_var_-%d' % (f - d)  # noqa: E731
    old = lambda d: 'stack_var_-%d' % (d + 8)  # noqa: E731

    def disp_of(x):
        return int(MEM_RBP.search(x.op_str).group(1), 16)

    ok_new, n = prologue_check(ins, body, new)
    ok_old, _ = prologue_check(ins, body, old)
    print('[ld110] frame F=%d (push 4 * 8 + sub rsp 0x%x)' % (f, f - 32))
    print('[ld110] プロローグ 0 初期化 store の IR 対応: 新式 -(F-d) %d/%d, 旧式 -(d+8) %d/%d' % (ok_new, n, ok_old, n))
    im_new, im_n, im_miss = imm_check(ins, body, new)
    im_old, _n2, _m = imm_check(ins, body, old)
    print('[ld110] 関数全体の即値 store の IR 対応 (同 slot・同値): 新式 %d/%d (不一致 %s), 旧式 %d/%d' % (im_new, im_n, ' '.join(im_miss), im_old, im_n))
    fail = []
    if ok_new != n:
        fail.append('frame model')

    rows = ['site\tdisp\tir_slot\tprologue_check\tmachine_chain\tmachine_slot_refs\tcell_K\tcell_content\tir_q_def\tir_depth\tmachine_depth'
            '\tir_consumers\tir_reg2mem_stores\tir_reload_use\told_formula_slot\told_formula_store_value\tverdict']
    res = {}
    for s in SITES:
        ms = machine_side(mach, ins, idx, s, disp_of)
        name = new(ms['disp'])
        ir = ir_side(body, start, ms, name)
        v = verdict(ms, ir)
        res[s] = (ms, ir, v)
        on = old(ms['disp'])
        ost = [l.strip() for l in body if re.search(r'store \S+ %[\w.\-]+, ptr %' + re.escape(on) + r'\.\d+\.reg2mem', l)]
        oval = '-'
        if ost:
            mv = re.search(r'store \S+ (%[\w.\-]+),', ost[-1])
            oval = '%s => %s' % (ost[-1], ir['defs'].get(mv.group(1), '-')) if mv else ost[-1]
        cons = ' | '.join('%d: %s' % (ln(start, i), l) for i, l in ir['direct'] if 'icmp' in l)
        for (c, dst) in ir['chain_dest']:
            i, j, k2, _lv = c
            tag = '自 slot %s' % name if name in dst else '他 slot %s' % ','.join(sorted(dst))
            cons += ' | %d: %s -> %d -> %d: %s => store 先 %s (%s)' % (
                ln(start, i), body[i].strip(), ln(start, j), ln(start, k2), body[k2].strip(), ','.join(sorted(dst)), tag)
        sts = ' | '.join('%d: %s' % (ln(start, i), l) for i, l, _r in ir['stores'])
        rl = '%d: %s' % (ln(start, ir['reload'][0]), ir['reload'][1]) if ir['reload'] else '-'
        ru = '%d: %s' % (ln(start, ir['reload_use'][0]), ir['reload_use'][1]) if ir['reload_use'] else '-'
        rows.append('\t'.join([s, hex(ms['disp']), name, '%d/%d' % (ok_new, n), ms['chain'], '; '.join(ms['refs']),
                               hex(ms['k']), hex(ms['v']), '%d: %s' % (ln(start, ir['qline']), ir['qdef']),
                               str(ir['depth']), str(ms['depth']), cons, sts, '%s => %s' % (rl, ru), on, oval, v]))
        print('[ld110] %s [rbp+%s] -> %s: IR %s (行 %d) 段数 IR %s / 機械語 %d, reg2mem store %d 本 => %s'
              % (s, hex(ms['disp']), name, ir['q'], ln(start, ir['qline']), ir['depth'], ms['depth'], len(ir['stores']), v))
        if v != 'TRUE_DROP' or len(ir['stores']) != 2 or not ir['reload']:
            fail.append(s)
    with open(out, 'w') as fh:
        fh.write('\n'.join(rows) + '\n')
    print('[ld110] %d site -> %s' % (len(SITES), out))

    print('[ld110] ネガティブコントロール')
    # NC1: 旧式の slot 名だと、frame の取り違えで別 site の slot (cf3c7a -> -328 = [rbp+0x90]) を指し、プロローグ照合が落ちる
    nc1 = ok_old < n and im_old < im_new
    print('  NC1 旧式 -(d+8): プロローグ照合 %d/%d・関数全体 %d/%d (新式 %d/%d より低く FAIL 想定) -> %s' % (
        ok_old, n, im_old, im_n, im_new, im_n, 'FAIL を検出' if nc1 else '検出できず'))
    # NC2: IR を壊さず直す。%Q の load を「セル -> 変数」の 2 段 load にした IR で、3 site とも OK_LOAD に動く
    flips = 0
    for s in SITES:
        ms, ir, _v = res[s]
        q = ir['q']
        mut = [re.sub(re.escape(q) + r'(?![\w.\-])', q + '.v', l) if i != ir['qline'] else l for i, l in enumerate(body)]
        qd = mut[ir['qline']]
        m = re.match(r'(\s+)(%[\w.\-]+) = load (i\d+), ptr inttoptr \(i64 (\d+) to ptr\)(.*)', qd)
        mut[ir['qline']] = '%s%s = load i64, ptr inttoptr (i64 %s to ptr), align 8\n%s%s.p = inttoptr i64 %s to ptr\n%s%s.v = load i64, ptr %s.p%s' % (
            m.group(1), q, m.group(4), m.group(1), q, q, m.group(1), q, q, m.group(5))
        mut = '\n'.join(mut).split('\n')
        sh = len(mut) - len(body)
        ms2 = machine_side(mach, ins, idx, s, disp_of)
        ir2 = ir_side(mut, start, ms2, new(ms2['disp']))
        v2 = verdict(ms2, ir2)
        flips += v2 == 'OK_LOAD'
        print('  NC2 %s IR を 2 段 load に直す: 段数 %s -> %s, 判定 %s (行ずれ %d)' % (s, res[s][1]['depth'], ir2['depth'], v2, sh))
    nc2 = flips == len(SITES)
    # NC3: site の取り違え。site a の %Q の消費者連鎖の値は a 自身の slot に store され、b の slot には入らない
    nc3 = True
    for a, b_ in [(SITES[0], SITES[1]), (SITES[1], SITES[2]), (SITES[2], SITES[0])]:
        own = new(res[a][0]['disp'])
        other = new(res[b_][0]['disp'])
        dsts = set().union(*[d for _c, d in res[a][1]['chain_dest'] if own in d] or [set()])
        good = own in dsts and other not in dsts
        nc3 &= good
        print('  NC3 %s の %%Q 連鎖の store 先 %s: 自 slot %s=%s / 取り違え先 %s=%s -> %s' % (
            a, sorted(dsts), own, 'あり' if own in dsts else 'なし', other, 'あり' if other in dsts else 'なし',
            '取り違えを区別' if good else '区別できず'))
    if not (nc1 and nc2 and nc3):
        fail.append('negctl')
    if fail:
        print('[ld110] FAIL: %s' % ', '.join(fail))
        return 1
    print('[ld110] OK: 3 site とも TRUE_DROP (確定)、NC1〜NC3 は期待どおり')
    return 0


if __name__ == '__main__':
    sys.exit(main())
