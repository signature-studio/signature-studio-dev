#!/usr/bin/env python3
"""#1588: liftdiff run の JSON から native / wasm の trace_head を比べ、最初の分岐点と wasm trap 直前の呼出列を出す。

usage: diverge_1588.py <liftdiff run json>
"""
import json
import sys

d = json.load(open(sys.argv[1]))
for c in d['cases']:
    raw = c.get('raw') or {}
    n = [t[0] for t in raw.get('native', {}).get('trace_head', [])]
    w = [t[0] for t in raw.get('wasm', {}).get('trace_head', [])]
    print('case %s outcome=%s native=%s wasm=%s' % (c.get('pattern'), c.get('outcome'),
          raw.get('native', {}).get('status'), raw.get('wasm', {}).get('status')))
    print('  trace_len native=%s wasm=%s (head %d/%d)' % (raw.get('native', {}).get('trace_len'),
          raw.get('wasm', {}).get('trace_len'), len(n), len(w)))
    i = 0
    while i < min(len(n), len(w)) and n[i] == w[i]:
        i += 1
    print('  first divergence index=%d' % i)
    if i < len(n) or i < len(w):
        print('  native[%d:]=%s' % (i, n[i:i + 6]))
        print('  wasm  [%d:]=%s' % (i, w[i:i + 6]))
    print('  native has 0x414c70=%s 0x4133f0=%s 0x414ad0=%s' % ('0x414c70' in n, '0x4133f0' in n, '0x414ad0' in n))
    print('  wasm   has 0x414c70=%s 0x4133f0=%s 0x414ad0=%s' % ('0x414c70' in w, '0x4133f0' in w, '0x414ad0' in w))
    print('  wasm detail: %s' % (raw.get('wasm', {}).get('detail') or '')[:200])
