#!/usr/bin/env python3
"""set_other 台帳 (m11_argrecover.py の stats src:*) の独立検算.

別アルゴリズム: capstone の regs_access / operands を使わず、op_str の文字列だけで代入元を判定する.
各 set_other 引数について、call 直前を後ろ向きに見て「その引数の 32bit/64bit 名を dest にする最初の命令」の
src (op_str の最後のオペランド) を文字列で分類し、台帳の内訳と突き合わせる.
使い方: python3 m11_setother_ledger_verify.py SITES.json --pe PE --ledger LEDGER.json
  SITES.json: m11_argrecover.py --out の fixes.json (site_detail を持つ)
  LEDGER.json: 同じ出力 (stats の src:* を照合する) を out 先に別途作ったもの。ここでは per-arg 台帳を再計算する。
"""
import argparse, json, os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'ldfix'))
import ldmach

ap = argparse.ArgumentParser()
ap.add_argument('fixes'); ap.add_argument('--pe', required=True)
a = ap.parse_args()
d = json.load(open(a.fixes))
m = ldmach.Machine(a.pe)
ALIAS = {0: ('ecx', 'rcx', 'cx', 'cl'), 1: ('edx', 'rdx', 'dx', 'dl'), 2: ('r8d', 'r8', 'r8w', 'r8b'), 3: ('r9d', 'r9', 'r9w', 'r9b')}
GPR8 = ('al', 'bl', 'cl', 'dl', 'sil', 'dil', 'ah', 'bh', 'ch', 'dh', 'bpl', 'spl')
GPR16 = ('ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp', 'sp')
BRANCH = ('call', 'ret', 'jmp')


def classify_str(mn, opstr):
    parts = [p.strip() for p in opstr.split(',')]
    src = parts[-1] if len(parts) >= 2 else ''
    if src == '':
        return 'other'
    if '[' in src:
        inner = src[src.index('[') + 1:src.index(']')]
        if 'rip' in inner:
            return 'lea_global' if mn == 'lea' else 'mem_global'
        if 'rsp' in inner or 'rbp' in inner:
            return 'lea_stack' if mn == 'lea' else 'mem_stack'
        return 'lea_ptr' if mn == 'lea' else 'mem_ptr'
    if src.startswith(('0x', '-')) or src.isdigit():
        return 'imm'
    if src in GPR8 or src in GPR16 or src.startswith(('xmm', 'r', 'e')) and src[1:].rstrip('dwb').isalnum() and len(src) <= 5:
        return 'reg'
    return 'other'


cnt = collections.Counter()
mism = 0
ledger_rows = []
for r in d['site_detail']:
    if r['status'] != 'matched':
        continue
    cva = int(r['caller'].split('_')[1], 16)
    tva = int(r['callee'].split('_')[1], 16)
    tgt = hex(tva)
    ins = m.disasm_fn(cva) or []
    idx = [i for i, x in enumerate(ins) if x.mnemonic == 'call' and x.op_str == tgt]
    if r['k'] >= len(idx):
        continue
    ci = idx[r['k']]
    for pos_s, kind in r['args'].items():
        if kind not in ('set_other', 'stack_set_other'):
            continue
        pos = int(pos_s)
        names = ALIAS.get(pos) if pos < 4 else None
        got = 'entry'
        j = ci - 1
        while j >= 0:
            x = ins[j]
            if x.mnemonic.startswith(BRANCH) or x.mnemonic.startswith('j'):
                got = 'boundary'
                break
            dst = x.op_str.split(',')[0].strip()
            if names:
                hit = dst in names
            else:
                hit = ('[rsp' in dst or '[rbp' in dst) and ('+0x%x]' % (0x20 + 8 * (pos - 4)) in dst or '+ 0x%x]' % (0x20 + 8 * (pos - 4)) in dst)
            if hit:
                got = classify_str(x.mnemonic, x.op_str)
                break
            j -= 1
        cnt['%s:%s' % (kind, got)] += 1
        ledger_rows.append((r['caller'], r['callee'], r['k'], pos, kind, got))
print('[ledger-verify] set_other 系 引数 %d' % len(ledger_rows))
for k, v in sorted(cnt.items()):
    print('  %-34s %d' % (k, v))
json.dump(ledger_rows, open(os.path.join(os.path.dirname(a.fixes), 'ledger_verify_rows.json'), 'w'))
