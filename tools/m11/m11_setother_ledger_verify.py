#!/usr/bin/env python3
"""set_other 台帳 (m11_argrecover.py の stats src:*) の独立検算.

別アルゴリズム: 代入元の判定は op_str の文字列だけで行う (capstone の regs_access / operand 型は使わない).
ただし命令列の取得に ldmach.disasm_fn (内部で capstone) を使うため、「capstone 非依存」ではない.
各 set_other 引数について、call 直前を後ろ向きに見て「その引数の 32bit/64bit 名を dest にする最初の命令」の
src (op_str の最後のオペランド) を文字列で分類し、台帳の内訳と突き合わせる.
使い方: python3 m11_setother_ledger_verify.py FIXES.json --pe PE
  FIXES.json: m11_argrecover.py --out の出力。site_detail[].src (台帳: 引数位置 -> 代入元) を照合対象に取る.
  出力: 台帳と検算の一致/不一致件数 (kind 別・引数単位)、不一致行 (ledger_verify_rows.json に全行).
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
ledger_rows = []
ledger = {}
for r in d['site_detail']:
    for pos_s, src in (r.get('src') or {}).items():
        ledger[(r['caller'], r['callee'], r['k'], int(pos_s))] = src
for r in d['site_detail']:
    if r['status'] != 'matched':
        continue
    cva = int(r['caller'].split('_')[1], 16)
    tva = int(r['callee'].split('_')[1], 16)
    tgt = hex(tva)
    ins = m.disasm_fn(cva) or []
    idx = [i for i, x in enumerate(ins) if x.mnemonic == 'call' and x.op_str == tgt]
    if r['k'] >= len(idx):
        cnt['unverified:call_index'] += 1
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
        lg = ledger.get((r['caller'], r['callee'], r['k'], pos), 'MISSING')
        ok = lg == got
        cnt['match' if ok else 'mismatch'] += 1
        cnt['kind:%s:%s' % (kind, 'match' if ok else 'mismatch')] += 1
        ledger_rows.append({'caller': r['caller'], 'callee': r['callee'], 'k': r['k'], 'pos': pos,
                            'kind': kind, 'ledger': lg, 'verify': got, 'match': ok})
print('[ledger-verify] set_other 系 引数 %d (台帳 %d)' % (len(ledger_rows), len(ledger)))
for k, v in sorted(cnt.items()):
    print('  %-40s %d' % (k, v))
mis = collections.Counter((x['kind'], x['ledger'], x['verify']) for x in ledger_rows if not x['match'])
for (kd, lg, vf), v in sorted(mis.items()):
    print('  mismatch %-18s ledger=%-12s verify=%-12s %d' % (kd, lg, vf, v))
json.dump(ledger_rows, open(os.path.join(os.path.dirname(a.fixes), 'ledger_verify_rows.json'), 'w'), indent=1)
sys.exit(1 if cnt['mismatch'] or cnt['unverified:call_index'] else 0)
