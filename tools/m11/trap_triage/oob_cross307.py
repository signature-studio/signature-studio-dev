#!/usr/bin/env python3
"""oob_cross307.py (#596): #307 (LD-7, liftdiff batch の関数単位 OOB) と m11 survey (unit 単位 OOB) の最上位 frame を同じ軸で突き合わせる.
  比較軸を揃える: (a) liftdiff = tests/oob_414ad0.py と同じ定義 (関数ごとに「最初の outcome=wasm_trap の case」の wasm_detail が
  `memory access out of bounds @ ...` のもの, 最上位 frame = `@` 直後の先頭 frame), (b) survey = oob_top.mjs の JSON の kind=oob, frames[0].
  出力: 軸ごとの件数 / 最上位 frame 別の件数 / 両者に現れる frame の対応 (survey の oob unit が持つ frame が liftdiff で何関数あるか)
  usage: python3 oob_cross307.py <survey_top.json> [batch.jsonl] [--verify]   (既定 batch = ../../liftdiff/work/m11/batch_closure.jsonl)
  TSV 基準 (results/m11_wasm_trap_triage.md = 222 件) も併記する: 定義は verdicts TSV の tags に wasm_trap + 最初の wasm_trap が oob (ldlib.classify.trap_kind)
  別アルゴリズム検算: --verify は (a) を正規表現でなく jsonl の raw 文字列検索 (`"memory access out of bounds @ ld_wasm.wasm.function_414ad0`) で数え直して一致を確認する"""
import json, re, sys, os, collections
HERE = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith('--')]
survey = json.load(open(args[0]))
batch = args[1] if len(args) > 1 else os.path.join(HERE, '../../liftdiff/work/m11/batch_closure.jsonl')

ld_top = {}; ld_first = {}; rows = 0
for l in open(batch):
    try: r = json.loads(l)
    except ValueError: continue
    rows += 1
    cs = [c for c in r.get('cases', []) if c.get('outcome') == 'wasm_trap']
    if not cs: continue
    ld_first[r['function']['va']] = cs[0]
    d = cs[0].get('wasm_detail') or ''
    if d.startswith('memory access out of bounds @ '):
        m = re.search(r'ld_wasm\.wasm\.([A-Za-z0-9_]+)', d)
        ld_top[r['function']['va']] = m.group(1) if m else '?'
ld_cnt = collections.Counter(ld_top.values())
# TSV 基準 (results/m11_wasm_trap_triage.md = triage_wasm_trap.py と同じ定義): verdicts TSV の tags に wasm_trap があり、最初の wasm_trap case の trap_kind が oob
sys.path.insert(0, os.path.join(HERE, '../../liftdiff')); from ldlib.classify import trap_kind
tsv_tags = {}
for l in open(os.path.join(HERE, '../../liftdiff/results/m11_closure_verdicts.tsv')):
    p = l.rstrip('\n').split('\t')
    if not p[0].startswith('#'): tsv_tags[p[0]] = p[4].split(',') if len(p) > 4 else []
tsv_top = {}
for va, tags in tsv_tags.items():
    c = ld_first.get(va)
    if 'wasm_trap' in tags and c and trap_kind(c.get('wasm_detail')) == 'oob':
        m = re.search(r'ld_wasm\.wasm\.([A-Za-z0-9_]+)', c.get('wasm_detail') or '')
        tsv_top[va] = m.group(1) if m else '?'
tsv_cnt = collections.Counter(tsv_top.values())

sv = [(r['unit'], r['frames'][0] if r.get('frames') else '-') for r in survey if r['kind'] == 'oob']
sv_cnt = collections.Counter(f for _, f in sv)
print('liftdiff: batch %d 行 / 最初の wasm_trap が OOB の関数 %d / 最上位 frame %d 種' % (rows, len(ld_top), len(ld_cnt)))
print('survey  : oob unit %d / 最上位 frame %d 種' % (len(sv), len(sv_cnt)))
print('| 最上位 frame | survey oob unit | liftdiff OOB 関数 |\n|---|--:|--:|')
for f, n in sorted(sv_cnt.items(), key=lambda x: -x[1]):
    print('| `%s` | %d | %d |' % (f, n, ld_cnt.get(f, 0)))
print('liftdiff 上位 8: ' + ', '.join('`%s` %d' % kv for kv in ld_cnt.most_common(8)))
print('survey の最上位 frame のうち liftdiff にも現れる種類: %d / %d' % (sum(1 for f in sv_cnt if f in ld_cnt), len(sv_cnt)))
print('TSV 基準 (results/m11_wasm_trap_triage.md の定義): OOB %d 関数 / 最上位 frame %d 種 / `414ad0` %d / `40ff70` %d' % (len(tsv_top), len(tsv_cnt), tsv_cnt.get('function_414ad0', 0), tsv_cnt.get('function_40ff70', 0)))
print('  jsonl 基準との関係: 共通 %d / TSV のみ %d / jsonl のみ %d (jsonl のみのうち TSV の tags に wasm_trap が無い: %d)' % (
    len(set(tsv_top) & set(ld_top)), len(set(tsv_top) - set(ld_top)), len(set(ld_top) - set(tsv_top)),
    sum(1 for va in set(ld_top) - set(tsv_top) if 'wasm_trap' not in tsv_tags.get(va, []))))
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
