#!/usr/bin/env python3
"""LD-27 (#1034): m11 unreachable の型 B (L が leaf) 食い違いを、完全 trace で再確認する。

batch jsonl の trace_head (最大 12 件) は native/wasm の先頭から切られるため、
最後の共通 entry L の求め方が不正確になりうる。本スクリプトは対象 case を
xfill 既定 (1) と xfill=0 の両方で、ランナの完全 trace を取り直して比較する。

  python3 tools/liftdiff/tests/trace_fullcompare_typeb.py TARGET.json [batch.jsonl]

TARGET.json は targets/m11.json を使う (pe は ${FL_WIN64_DIR}/extracted/block00031_PE.bin を指す)。
入力 batch 既定 = tools/liftdiff/work/m11/batch_closure.jsonl。ビルド済み work/ を要する (再ビルドはしない)。
結果は stdout に出す (results/ への書き込みはしない)。
class: X = xmm0 入力の脱落 (呼出元/L の entry で xmm0 を読み、x0 が native≠wasm) / M = L が MXCSR 系 (0x40a380 / 0x40a3b0) / R = 未特定。
"""
import collections
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
    """(L, L の位置) を返す。L は最後の共通 entry (位置は共通接頭辞の末尾)。"""
    i = 0
    while i < len(N) and i < len(W) and N[i] == W[i]:
        i += 1
    if i == len(N) == len(W) or i == 0:
        return None, None
    return N[i - 1], i - 1


WRITE_ONLY = {'movsd', 'movss', 'movaps', 'movapd', 'movups', 'movupd', 'movq', 'movd', 'movdqa', 'movdqu',
              'cvtsi2sd', 'cvtsi2ss', 'cvtss2sd', 'cvtsd2ss', 'cvttsd2si', 'pxor', 'xorps', 'xorpd', 'movlpd', 'movhpd'}


def reads_xmm0(f):
    """f の本体で xmm0 が「書かれる前に読まれる」なら True (xmm0 の入力 = 署名外の引数の読み)。"""
    for ins in md.disasm(sess.pe.read(f - sess.pe.base, 0x400), f):
        if ins.id == X.X86_INS_RET:
            return False
        ops = [o.strip() for o in ins.op_str.split(',')]
        if 'xmm0' not in ins.op_str:
            continue
        if ops[0] == 'xmm0' and ins.mnemonic in WRITE_ONLY:
            return False
        return True
    return False


def call_site(caller, L):
    """caller の本体で L への直接 call 命令の番地 (最初の 1 件) と、その後の最初の jcc と分岐先を返す。"""
    if caller is None:
        return None, None, None
    ins_list = list(md.disasm(sess.pe.read(caller - sess.pe.base, 0x800), caller))
    for k, ins in enumerate(ins_list):
        if ins.id == X.X86_INS_CALL and ins.op_str == '0x%x' % L:
            after = ins_list[k + 1:k + 9]
            text = ' ; '.join('%s %s' % (a.mnemonic, a.op_str) for a in after[:4])
            jcc = next(((a.mnemonic, a.op_str) for a in after if a.mnemonic.startswith('j') and a.mnemonic != 'jmp'), None)
            return ins.address, text, jcc
    return None, None, None


items = []
for line in open(batch):
    r = json.loads(line)
    cs = [c for c in r['cases'] if c['outcome'] == 'wasm_trap']
    if not (cs and (cs[0].get('wasm_detail') or '').startswith('unreachable') and cs[0].get('wasm_status') != 'badjson'):
        continue
    c = cs[0]
    N = [int(t[0], 16) for t in c['raw']['native']['trace_head']]
    W = [int(t[0], 16) for t in c['raw']['wasm']['trace_head']]
    L, _ = first_div_L(N, W)
    if L is None or not leaf(L):
        continue
    items.append((int(r['function']['va'], 16) if isinstance(r['function']['va'], str) else r['function']['va'], c['pattern'], L))

print('# 型 B 候補 %d case (trace_head 基準の L が leaf)' % len(items))
nat, was = sess.make_runners()
rows = []
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
            TN = rn.get('trace', [])
            TW = rw.get('trace', [])
            N = [int(t[0], 16) for t in TN]
            W = [int(t[0], 16) for t in TW]
            Lf, i = first_div_L(N, W)
            nxt = caller = lx = cx = None
            if Lf is not None:
                nxt = (N[i + 1] if i + 1 < len(N) else None, W[i + 1] if i + 1 < len(W) else None)
                lx = (TN[i][10], TW[i][10])
                if i >= 1:
                    caller = N[i - 1]
                    cx = (TN[i - 1][10], TW[i - 1][10])
            typ = ('B' if leaf(Lf) else 'notB') if Lf is not None else '-'
            site, post, jcc = call_site(caller, Lf) if Lf is not None else (None, None, None)
            if Lf is None:
                cls = '-'
            elif Lf in (0x40a380, 0x40a3b0):
                cls = 'M'
            elif (cx and cx[0] != cx[1] and reads_xmm0(caller)) or (lx[0] != lx[1] and reads_xmm0(Lf)):
                cls = 'X'
            else:
                cls = 'R'
            rows.append((xf, cls, Lf, caller))
            print('fn=0x%x pat=%s xfill=%d class=%s L_full=%s typeB_full=%s next(native,wasm)=%s native=%s wasm=%s' % (
                fva, pat, 1 if xf else 0, cls,
                ('0x%x' % Lf) if Lf is not None else '-',
                typ,
                tuple(('0x%x' % v) if v is not None else '-' for v in nxt) if nxt else '-',
                rn.get('status'), rw.get('status')))
            print('   L_x0(native,wasm)=%s caller=%s call@%s caller_x0(native,wasm)=%s post=[%s] jcc=%s' % (
                ('%s,%s' % lx) if lx else '-',
                ('0x%x' % caller) if caller is not None else '-',
                ('0x%x' % site) if site is not None else '-',
                ('%s,%s' % cx) if cx else '-',
                post or '-',
                ('%s %s' % jcc) if jcc else '-'))
    print('## 集計 (xfill, class): %s' % sorted(collections.Counter((int(x), c) for x, c, _, _ in rows).items()))
finally:
    nat.close()
    was.close()
