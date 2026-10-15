#!/usr/bin/env python3
"""MX-36 (#3487): dsp/e2e.sh step 3/5 の x64c 未対応群分けの検算 (別アルゴリズム)。

e2e.sh = key の mnemonic 部で判定する正規表現・接頭辞規則 (修正後)。
本スクリプト = 明示的な mnemonic 集合の照合 (接頭辞規則を使わない)。
負例 = 修正前の判定 (k.startswith('v') が AES より先・完全一致の tuple) を同じ入力に当てる。

usage: mx36_group_check.py <lift_meta.json>   (e2e.sh 実行後の dsp/work/lift_seeds/lift_meta.json)
"""
import json, re, sys
from collections import Counter

AES = {'aesenc', 'aesdec', 'aesenclast', 'aesdeclast', 'aesimc', 'aeskeygenassist',
       'vaesenc', 'vaesdec', 'vaesenclast', 'vaesdeclast',
       'sha256rnds2', 'sha256msg1', 'sha256msg2', 'pclmulqdq', 'pshufb', 'palignr'}


def new_rule(k):
    mn = re.match(r'[a-z0-9]+', k).group(0)
    if mn in AES:
        return 'AES/SHA-NI'
    if re.fullmatch(r'v[a-z0-9]+', mn):
        return 'AVX(VEX/EVEX)'
    if mn.startswith('f'):
        return 'x87'
    return 'other'


def old_rule(k):
    if k.startswith('v') or 'zmm' in k:
        return 'AVX(VEX/EVEX)'
    if k.startswith(('aes', 'vaes', 'sha256')) or k in ('pclmulqdq', 'pshufb', 'palignr'):
        return 'AES/SHA-NI'
    if k[0] == 'f':
        return 'x87'
    return 'other'


def tally(u, rule):
    c = Counter()
    for k, v in u.items():
        c[rule(k)] += v
    return c


u = json.load(open(sys.argv[1]))['unsup']
for name, rule in (('new (mnemonic・明示集合)', new_rule), ('old (修正前の判定・負例)', old_rule)):
    c = tally(u, rule)
    print('%-26s %s sum=%d' % (name, ', '.join('%s %d' % kv for kv in sorted(c.items())), sum(c.values())))
