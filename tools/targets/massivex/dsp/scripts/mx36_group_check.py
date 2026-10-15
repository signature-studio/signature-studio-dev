#!/usr/bin/env python3
"""MX-36 (#3487): dsp/e2e.sh step 3/5 の x64c 未対応群分けの検算 (別アルゴリズム)。

e2e.sh = key の mnemonic 部で判定する正規表現・接頭辞規則 (修正後)。
本スクリプト = 明示的な mnemonic 集合の照合 (接頭辞規則を使わない)。
両規則の判定が食い違う key は NOTE として列挙する (将来 aesenc128kl 等が入ったときの検知)。
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


def e2e_rule(k):    # e2e.sh step 3/5 と同じ接頭辞規則 (修正後)
    mn = k.split(':', 1)[0]
    if mn.startswith(('aes', 'vaes', 'sha256')) or mn in ('pclmulqdq', 'pshufb', 'palignr'):
        return 'AES/SHA-NI'
    if mn.startswith('v'):
        return 'AVX(VEX/EVEX)'
    if mn[0] == 'f':
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
diff = [k for k in u if e2e_rule(k) != new_rule(k)]
print('NOTE 接頭辞規則 (e2e.sh) と明示集合で判定が食い違う key: %d 種 %d site' % (len(diff), sum(u[k] for k in diff)))
for k in diff[:20]:
    print('   %s  e2e=%s  set=%s' % (k, e2e_rule(k), new_rule(k)))
