#!/usr/bin/env python3
"""LD-27 (#1034): m11 unreachable の型 B (L が leaf) 食い違いを、完全 trace で再確認する。

batch jsonl の trace_head (最大 12 件) は native/wasm の先頭から切られるため、
最後の共通 entry L の求め方が不正確になりうる。本スクリプトは対象 case を
xfill 既定 (1) と xfill=0 の両方で、ランナの完全 trace を取り直して比較する。

  python3 tools/liftdiff/tests/trace_fullcompare_typeb.py TARGET.json [batch.jsonl]

TARGET.json は pe を展開済みの block00031_PE.bin に向けた targets/m11.json の複製。
入力 batch 既定 = tools/liftdiff/work/m11/batch_closure.jsonl。ビルド済み work/ を要する (再ビルドはしない)。
結果は stdout に出す (results/ への書き込みはしない)。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from liftdiff import Session  # noqa: E402
from ldlib import cases  # noqa: E402
import capstone  # noqa: E402
from capstone import x86_const as X  # noqa: E402

target = sys.argv[1]
batch = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'work/m11/batch_closure.jsonl')
sess = Session(target, shards=1, build=False, trace=True)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)


def leaf(va):
    """ret/int3 まで call 無しなら True (型 B の判定。trace_diverge_unreachable.py と同一)。"""
    for ins in md.disasm(sess.pe.read(va - sess.pe.base, 0x600), va):
        if ins.id == X.X86_INS_CALL:
            return False
        if ins.id in (X.X86_INS_RET, X.X86_INS_INT3):
            break
    return True


def first_div_L(N, W):
    i = 0
    while i < len(N) and i < len(W) and N[i] == W[i]:
        i += 1
    if i == len(N) == len(W) or i == 0:
        return None
    return N[i - 1]


items = []
for line in open(batch):
    r = json.loads(line)
    cs = [c for c in r['cases'] if c['outcome'] == 'wasm_trap']
    if not (cs and (cs[0].get('wasm_detail') or '').startswith('unreachable') and cs[0].get('wasm_status') != 'badjson'):
        continue
    c = cs[0]
    N = [int(t[0], 16) for t in c['raw']['native']['trace_head']]
    W = [int(t[0], 16) for t in c['raw']['wasm']['trace_head']]
    L = first_div_L(N, W)
    if L is None or not leaf(L):
        continue
    items.append((int(r['function']['va'], 16) if isinstance(r['function']['va'], str) else r['function']['va'], c['pattern'], L))

print('# 型 B 候補 %d case (trace_head 基準の L が leaf)' % len(items))
nat, was = sess.make_runners()
try:
    for fva, pat, L in items:
        name = sess.fn_name(fva)
        sig = sess.sigs.get(name)
        if not sig or not sig['defined']:
            print('fn=0x%x pat=%s skipped (no sig)' % (fva, pat))
            continue
        for xf in (True, False):
            line = cases.case_line(fva, name, pat, sig, trace=True, xfill=xf)
            rn = nat.run_cases([line], ['n'])[0]
            rw = was.run_cases([line], ['w'])[0]
            N = [int(t[0], 16) for t in rn.get('trace', [])]
            W = [int(t[0], 16) for t in rw.get('trace', [])]
            Lf = first_div_L(N, W)
            nxt = None
            if Lf is not None:
                i = N.index(Lf) if Lf in N else 0
                ni = N[i + 1] if i + 1 < len(N) else None
                wi = W[i + 1] if i + 1 < len(W) else None
                nxt = (ni, wi)
            print('fn=0x%x pat=%s xfill=%d L_full=%s next(native,wasm)=%s native=%s wasm=%s' % (
                fva, pat, 1 if xf else 0,
                ('0x%x' % Lf) if Lf is not None else '-',
                tuple(('0x%x' % v) if v is not None else '-' for v in nxt) if nxt else '-',
                rn.get('status'), rw.get('status')))
finally:
    nat.close()
    was.close()
