#!/usr/bin/env python3
"""set_other 台帳の imm 61 件 (#1524 / M11-N98) の健全性分類.

台帳 (m11_argrecover.py の site_detail[].src == 'imm') の各引数について、直前の書込命令を機械語から取り、
「その命令だけで引数値 (IR 側の型幅) が定まるか」で 4 区分に分ける。IR は変更しない (分類のみ)。

  full_const    : 書込が IR 引数の型幅を全て定める定数 (mov byte/dword [rsp+N], imm で型が i8/i32)
  partial_write : 書込が型幅より狭い (mov r8b/r9b/r8w, imm 等)。上位ビットは旧値依存
  stack_partial : スタック引数を型幅より狭く書込 (mov dword [rsp+N], imm で型が i64)。上位 32bit は旧値依存
  arith         : 定数代入ではなく旧値への加減算 (add/sub edx|r8d, imm)。台帳の imm 分類が誤り

使い方: python3 m11_setother_imm_class.py FIXES.json IR.ll --pe PE
  FIXES.json: m11_argrecover.py --out の出力。IR.ll: 0 詰め前の IR (sigfix の型を得る元; m11_post.py の入力)。
出力: 区分別件数 (stdout)、全行 (imm_class_rows.json を FIXES.json と同じ dir に書く)。
"""
import argparse, collections, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'ldfix'))
sys.path.insert(0, HERE)
import capstone
import ldmach
import m11_argrecover as AR

ap = argparse.ArgumentParser()
ap.add_argument('fixes'); ap.add_argument('ir'); ap.add_argument('--pe', required=True)
a = ap.parse_args()
d = json.load(open(a.fixes))
ir = open(a.ir).read()
sigs = {}
for m in re.finditer(r'^(?:define|declare)(?: weak)? (\S+) @(function_[0-9a-f]+)\(([^)]*)\)', ir, re.M):
    sigs[m.group(2)] = [x.strip().split()[0] for x in m.group(3).split(',') if x.strip()]
mach = ldmach.Machine(a.pe)
fc = {}


def F(va):
    if va not in fc:
        fc[va] = AR.Fn(mach, va)
    return fc[va]


def width(ty):
    return int(ty[1:]) if ty.startswith('i') and ty[1:].isdigit() else None


def classify(pos, ptype, ins):
    mn, op = ins.mnemonic, ins.op_str
    dst = op.split(',')[0].strip()
    if mn in ('add', 'sub'):
        return 'arith'
    w = width(ptype) if ptype else None
    if '[' in dst:
        size = {'byte': 8, 'word': 16, 'dword': 32, 'qword': 64}.get(dst.split()[0], None)
        if size is None or w is None:
            return 'partial_write'
        return 'full_const' if size == w else 'stack_partial'
    # x86-64: 32bit レジスタへの書込は上位 32bit をゼロ拡張するため全幅を定める。8/16bit は上位が旧値依存。
    if dst in ('al', 'bl', 'cl', 'dl', 'r8b', 'r9b', 'r8w', 'r9w', 'cx', 'dx'):
        return 'partial_write'
    return 'full_const'


rows = []
cnt = collections.Counter()
for r in d['site_detail']:
    if r['status'] != 'matched':
        continue
    cva = int(r['caller'].split('_')[1], 16)
    tva = int(r['callee'].split('_')[1], 16)
    cf = F(cva)
    calls = [i for i, x in enumerate(cf.ins) if x.mnemonic == 'call' and x.operands and x.operands[0].type == capstone.CS_OP_IMM and x.operands[0].imm == tva]
    if r['k'] >= len(calls):
        continue
    ci = calls[r['k']]
    for pos_s, src in (r.get('src') or {}).items():
        if src != 'imm':
            continue
        pos = int(pos_s)
        reg = AR.REGS[pos] if pos < 4 else None
        w = None
        j = ci - 1
        while j >= 0:
            x = cf.ins[j]
            if x.mnemonic in ('call', 'ret', 'jmp') or x.mnemonic.startswith('j'):
                break
            if reg:
                hit = reg in cf.rw(x)[1]
            else:
                hit = any(m['write'] and m['base'] == 'rsp' and m['disp'] == 0x20 + 8 * (pos - 4) for m in ldmach.memops_of(cf.cs, x))
            if hit:
                w = x
                break
            j -= 1
        ptype = sigs[r['callee']][pos] if r['callee'] in sigs and pos < len(sigs[r['callee']]) else None
        cls = classify(pos, ptype, w) if w is not None else 'no_write'
        cnt[cls] += 1
        rows.append({'caller': r['caller'], 'callee': r['callee'], 'k': r['k'], 'pos': pos, 'ptype': ptype,
                     'insn': ('%s %s' % (w.mnemonic, w.op_str)) if w is not None else None, 'class': cls})
print('[imm-class] imm 台帳 %d 件' % len(rows))
for k in ('full_const', 'partial_write', 'stack_partial', 'arith', 'no_write'):
    print('  %-14s %d' % (k, cnt[k]))
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(a.fixes)), 'imm_class_rows.json'), 'w'), indent=1)
