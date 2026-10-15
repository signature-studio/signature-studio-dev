#!/usr/bin/env python3
"""f3d_crosscheck_3528.py: F3d (LD-127 #2745) で変えた関数を機械語と突合する (LD-160 #3528)。

F3d は入口の `xor i64 0,0` を `load i16` に戻す。戻し先の argK が正しいかを、fix_f3d の guard とは
独立に確かめる。
  (1) 機械語: 入口ブロックの `movzx r16, word ptr [B]` (B は rsp/rbp 以外・disp 0) を列挙する。
  (2) B の由来: Win64 引数レジスタ (rcx=arg1, rdx=arg2, r8=arg3, r9=arg4) から、reg→reg の mov と
      rbp/rsp の spill slot (mov [slot],reg / mov reg,[slot]) を経由して追跡する。他の命令で書かれた
      reg と call 後の揮発 reg は由来を失う。
  (3) IR: 変更行の `%ldfxtN = load i16, ptr %argK` (または `inttoptr ... %argK`) の K を取る。
  判定 OK: 機械語の該当 movzx がちょうど 1 本で、その由来 = IR の K。

使い方: python3 f3d_crosscheck_3528.py HEAD.ll F3D.ll --pe PE.bin [--report f3d.json]
出力: 関数ごとに 1 行 (TSV)。末尾に集計。
"""
import argparse
import difflib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ldfix as L  # noqa: E402
from ldmach import Machine, FnMach, memops_of  # noqa: E402

FRAME = ('rbp', 'rsp')
VOLATILE = ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11')
INTTOPTR_ARG = re.compile(r'= inttoptr i\d+ (%arg\d+) to ptr')


def bodies(text):
    out = {}
    for m in L.DEF_RE.finditer(text):
        end = text.index('\n}', m.end()) + 2
        out[m.group('name')] = text[m.start():end]
    return out


def ir_argk(old_body, new_body):
    """変更行から F3d の挿入 load の argK を取る。(argK | None, 挿入 load 数, 削除 xor 数)"""
    ol, nl = old_body.split('\n'), new_body.split('\n')
    ins = []
    dele = 0
    for op, a0, a1, b0, b1 in difflib.SequenceMatcher(None, ol, nl, autojunk=False).get_opcodes():
        if op in ('replace', 'delete'):
            dele += sum(1 for l in ol[a0:a1] if L.XOR0_RE.match(l))
        if op in ('replace', 'insert'):
            ins.extend(nl[b0:b1])
    loads = [l for l in ins if re.search(r'load i16, ptr ', l) and 'ldfxt' in l]
    ks = set()
    for l in loads:
        m = re.search(r'load i16, ptr (%arg\d+)(?![\w.$-])', l)
        if m:
            ks.add(int(m.group(1)[4:]))
            continue
        m = re.search(r'load i16, ptr (%ldfxt\d+_p)', l)
        if m:
            for p in ins:
                mm = INTTOPTR_ARG.search(p)
                if mm and p.lstrip().startswith(m.group(1) + ' '):
                    ks.add(int(mm.group(1)[4:]))
    return (ks.pop() if len(ks) == 1 else None), len(loads), dele


def mach_entry_loads(mach, va, body):
    """入口ブロックの機械語を追跡し、movzx word の zero-disp load ごとに (addr, 基底 reg, 由来 argN) を返す。"""
    fn = L.Fn('', va, body)
    blk_vas = [b for (b, _ls) in fn.blocks() if b is not None]
    fv = FnMach(mach, va, blk_vas)
    ent = fv.blocks.get(va, [])
    cs = mach.cs
    origin = {r: n for r, n in L.ARGREG_ARG.items()}
    slots = {}
    res = []
    n_all = 0
    for ins in ent:
        ops = ins.operands
        mn = ins.mnemonic
        if mn == 'movzx' and len(ops) == 2 and ops[0].type == 1 and ops[1].type == 3 and ops[1].size == 2:
            n_all += 1
            mem = ops[1].mem
            b = L.gprnorm(cs, mem.base) if mem.base else None
            if not mem.index and not mem.disp and b and b not in FRAME:
                res.append((ins.address, '%s %s' % (mn, ins.op_str), b, origin.get(b)))
        if mn == 'mov' and len(ops) == 2:
            o0, o1 = ops
            if o0.type == 1 and o0.size == 8:
                dst = L.gprnorm(cs, o0.reg)
                if o1.type == 1:
                    origin[dst] = origin.get(L.gprnorm(cs, o1.reg))
                elif o1.type == 3 and o1.mem.base and not o1.mem.index and L.gprnorm(cs, o1.mem.base) in FRAME:
                    origin[dst] = slots.get((L.gprnorm(cs, o1.mem.base), o1.mem.disp))
                else:
                    origin[dst] = None
                continue
        for m in memops_of(cs, ins):
            if not m['write'] or m['base'] not in FRAME or m['index']:
                continue
            n = (m['size_bits'] or 0) // 8
            for k in [k for k in slots if k[0] == m['base'] and k[1] < m['disp'] + n and m['disp'] < k[1] + 8]:
                del slots[k]
            if mn == 'mov' and len(ops) == 2 and n == 8 and ops[1].type == 1 and ops[1].size == 8:
                slots[(m['base'], m['disp'])] = origin.get(L.gprnorm(cs, ops[1].reg))
        if mn.startswith('call'):
            for r in VOLATILE:
                origin[r] = None
            continue
        try:
            written = ins.regs_access()[1]
        except Exception:
            written = []
        for rid in written:
            r = L.gprnorm(cs, rid)
            if r:
                origin[r] = None
    return res, n_all


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('head')
    ap.add_argument('f3d')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--report', help='F3d の report JSON (f3d_vas の照合用)')
    a = ap.parse_args()
    old = bodies(open(a.head, errors='replace').read())
    new = bodies(open(a.f3d, errors='replace').read())
    changed = sorted((n for n in new if new[n] != old.get(n)), key=lambda n: int(n[len('function_'):], 16))
    mach = Machine(a.pe)
    print('va\tir_argk\tir_loads\tir_xor_removed\tmach_movzx_word_entry\tmach_base\tmach_argn\tverdict')
    ok = 0
    rows = []
    for n in changed:
        va = int(n[len('function_'):], 16)
        k, nl, dele = ir_argk(old[n], new[n])
        res, n_all = mach_entry_loads(mach, va, old[n])
        if len(res) == 1 and res[0][3] is not None and k is not None and res[0][3] == k and nl == 1 and dele == 1:
            v = 'OK'
            ok += 1
        else:
            v = 'NG'
        mb = res[0][2] if len(res) == 1 else '-'
        ma = res[0][3] if len(res) == 1 else '-'
        rows.append((va, k, nl, dele, n_all, len(res), mb, ma, v))
        print('%x\t%s\t%d\t%d\t%d(%d)\t%s\t%s\t%s' % (va, k, nl, dele, n_all, len(res), mb, ma, v))
    print('# changed=%d OK=%d NG=%d' % (len(changed), ok, len(changed) - ok))
    if a.report:
        rep = json.load(open(a.report))
        want = set(rep.get('f3d_vas', []))
        got = set('%x' % r[0] for r in rows)
        print('# report f3d_vas=%d  diff-changed=%d  same=%s' % (len(want), len(got), want == got))
        print('# only-in-report=%s only-in-diff=%s' % (sorted(want - got), sorted(got - want)))


if __name__ == '__main__':
    main()
