#!/usr/bin/env python3
"""fa_residual.py WORKDIR : 復元後に残る非 IAT 間接 call の落ち (ir != kept_indirect/resolved_direct) を一覧する (#1026).
WORKDIR = roundtrip.sh の出力先 (例: tools/icall/work/rt_freshair-core)。sites_after.json と audit_after.json を読むだけ。"""
import json, os, sys
from collections import Counter

d = sys.argv[1]
sites = json.load(open(os.path.join(d, 'sites_after.json')))
audit = json.load(open(os.path.join(d, 'audit_after.json')))
lost = [s for s in sites if s['kind'] != 'iat' and s['mn'] == 'call' and s['ir'] not in ('kept_indirect', 'resolved_direct')]
print('non-IAT call sites %d / lost %d (audit call_lost_non_iat=%d)' % (
    sum(1 for s in sites if s['mn'] == 'call' and s['kind'] != 'iat'), len(lost), audit['call_lost_non_iat']))
print('by IR status:', dict(Counter(s['ir'] for s in lost)))
print('by kind/disp:', dict(Counter('%s[%s+%#x]' % (s['kind'], s['base'], s['disp']) for s in lost)))
for s in lost:
    print('  va=%#x fn=%#x %-28s ir=%s' % (s['va'], s['fn'], s['text'], s['ir']))
