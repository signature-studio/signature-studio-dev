#!/usr/bin/env python3
"""kh656_census.py — module F の未 lift callee (kh_lower の unlifted callees) を分類して表示する (#656).

  python3 scripts/kh656_census.py            (前提: lic_build.py --module F を実行済み = work/licF/ が存在)

分類 (排他・上から順):
  shim      : modules.F.shims に登録 (C 実装で置換・lift しない)
  i256/AVX2 : 呼び出し先の本体 (n1.ll) が i256 (ymm) を使う = gen_simd.py 未対応で lift 不可
  fail-fast : 上記以外の未 lift (呼ばれると unlifted callee 例外で停止)
出力は表 (VA / class / 入口経路での先頭か) と件数。
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
LIC = os.path.dirname(HERE)
CFG = json.load(open(os.path.join(LIC, 'lic_config.json'), encoding='utf-8'))['modules']['F']
W = os.path.join(LIC, 'work', 'licF')
st = json.load(open(os.path.join(W, 'stat.json'), encoding='utf-8'))
unl = json.loads(re.search(r"unlifted callees (\[[^\]]*\])", st['passes']).group(1).replace("'", '"'))
L = open(os.path.join(W, 'n1.ll'), encoding='utf-8').read().split('\n')
wide = set()
for s, l in enumerate(L):
    m = re.match(r'^define \S+ @(?:function_|kh_)([0-9a-f]+)\(', l)
    if m:
        e = s + 1
        while e < len(L) and not L[e].startswith('}'):
            e += 1
        if any('i256' in x for x in L[s:e]):
            wide.add(m.group(1))
# 証跡: 閉包展開の試行 (lift 36 件追加時の n1.ll) で i256 を含むと検出された関数 (現行 lift 集合には含まれないため再検出できない)
EVIDENCE_I256 = {'180f89cf0', '180fb6124'}
wide |= EVIDENCE_I256
shims = CFG.get('shims', {})
cnt = {'shim': 0, 'i256/AVX2': 0, 'fail-fast': 0}
for va in unl:
    if va in shims:
        cls = 'shim:' + shims[va]
        cnt['shim'] += 1
    elif va in wide:
        cls = 'i256/AVX2'
        cnt['i256/AVX2'] += 1
    else:
        cls = 'fail-fast'
        cnt['fail-fast'] += 1
    first = ' <- 入口経路の先頭' if va == '180112a30' else ''
    print('0x%s  %s%s' % (va, cls, first))
print('unlifted=%d lifted(F)=%d shim=%d i256/AVX2=%d fail-fast=%d wasm=%dB' % (
    len(unl), len(CFG['lift']), cnt['shim'], cnt['i256/AVX2'], cnt['fail-fast'], st['wasm_bytes']))
