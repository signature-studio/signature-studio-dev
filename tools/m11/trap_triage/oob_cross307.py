#!/usr/bin/env python3
"""oob_cross307.py (#596): #307 (LD-7, liftdiff batch の関数単位 OOB) と m11 survey (unit 単位 OOB) の最上位 frame を同じ軸で突き合わせる.
  比較軸を揃える: (a) liftdiff = tests/oob_414ad0.py と同じ定義 (関数ごとに「最初の outcome=wasm_trap の case」の wasm_detail が
  `memory access out of bounds @ ...` のもの, 最上位 frame = `@` 直後の先頭 frame), (b) survey = oob_top.mjs の JSON の kind=oob, frames[0].
  出力: 軸ごとの件数 / 最上位 frame 別の件数 / 両者に現れる frame の対応 (survey の oob unit が持つ frame が liftdiff で何関数あるか)
  usage: python3 oob_cross307.py <survey_top.json> [batch.jsonl]   (既定 batch = ../../liftdiff/work/m11/batch_closure.jsonl)
  別アルゴリズム検算: --verify は (a) を正規表現でなく jsonl の raw 文字列検索 (`"memory access out of bounds @ ld_wasm.wasm.function_414ad0`) で数え直して一致を確認する"""
import json, re, sys, os, collections
HERE = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith('--')]
survey = json.load(open(args[0]))
batch = args[1] if len(args) > 1 else os.path.join(HERE, '../../liftdiff/work/m11/batch_closure.jsonl')

ld_top = {}; rows = 0
for l in open(batch):
    try: r = json.loads(l)
    except ValueError: continue
    rows += 1
    cs = [c for c in r.get('cases', []) if c.get('outcome') == 'wasm_trap']
    if not cs: continue
    d = cs[0].get('wasm_detail') or ''
    if d.startswith('memory access out of bounds @ '):
        m = re.search(r'ld_wasm\.wasm\.([A-Za-z0-9_]+)', d)
        ld_top[r['function']['va']] = m.group(1) if m else '?'
ld_cnt = collections.Counter(ld_top.values())

sv = [(r['unit'], r['frames'][0] if r.get('frames') else '-') for r in survey if r['kind'] == 'oob']
sv_cnt = collections.Counter(f for _, f in sv)
print('liftdiff: batch %d 行 / 最初の wasm_trap が OOB の関数 %d / 最上位 frame %d 種' % (rows, len(ld_top), len(ld_cnt)))
print('survey  : oob unit %d / 最上位 frame %d 種' % (len(sv), len(sv_cnt)))
print('| 最上位 frame | survey oob unit | liftdiff OOB 関数 |\n|---|--:|--:|')
for f, n in sorted(sv_cnt.items(), key=lambda x: -x[1]):
    print('| `%s` | %d | %d |' % (f, n, ld_cnt.get(f, 0)))
print('liftdiff 上位 8: ' + ', '.join('`%s` %d' % kv for kv in ld_cnt.most_common(8)))
print('survey の最上位 frame のうち liftdiff にも現れる種類: %d / %d' % (sum(1 for f in sv_cnt if f in ld_cnt), len(sv_cnt)))
if '--verify' in sys.argv:
    n2 = collections.Counter(); seen = set()
    for l in open(batch):
        i = l.find('"outcome": "wasm_trap"')
        if i < 0: continue
        j = l.find('memory access out of bounds @ ld_wasm.wasm.', i)
        va = re.search(r'"va": "(0x[0-9a-f]+)"', l).group(1)
        if j < 0 or va in seen: continue
        # 最初の wasm_trap case の detail が OOB か: 最初の wasm_trap の後ろ 400 字以内に OOB があること
        if j - i > 400: continue
        seen.add(va); n2[re.match(r'[A-Za-z0-9_]+', l[j + len('memory access out of bounds @ ld_wasm.wasm.'):]).group(0)] += 1
    print('verify (raw 文字列走査): 関数 %d / 414ad0 %d' % (len(seen), n2.get('function_414ad0', 0)))
    if len(seen) != len(ld_top) or n2.get('function_414ad0', 0) != ld_cnt.get('function_414ad0', 0):
        print('VERIFY MISMATCH: 正規表現版 %d / %d と一致しない' % (len(ld_top), ld_cnt.get('function_414ad0', 0))); sys.exit(1)
