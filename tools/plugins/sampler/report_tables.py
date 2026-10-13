#!/usr/bin/env python3
"""REPORT.md の表 (§1〜§4) を work/sampler/{status.csv,facts.json,engines.csv} から機械的に生成する (転記ミス防止)。
usage: report_tables.py [1|2|3|4|5]   (sampler_e2e.sh 実行後。 引数なしは全節、番号は表だけを見出し無しで出力。 2 は unreached_unique.py の出力から)
"""
import csv, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, '..', 'work', 'sampler')
sys.path.insert(0, HERE)
import targets

F = json.load(open(os.path.join(W, 'facts.json')))
S = {int(r['block']): r for r in csv.DictReader(open(os.path.join(W, 'status.csv')))}
M = {p['name']: p for p in json.load(open(os.path.join(HERE, '..', 'PLUGIN_MATRIX.json')))['plugins']}
n = lambda x: format(x, ',')
SECS = {}
for r in csv.DictReader(open(os.path.join(HERE, '..', 'work', 'batch', 'status.csv'))):
    if r['lift_rc'] == '0':   # 失敗 run の秒 (前提欠け等で即落ちた行) を lift 秒に混ぜない
        SECS.setdefault(int(r['block']), []).append(int(r['seconds']))
rng = lambda b: ('%d–%d' % (min(SECS[b]), max(SECS[b])) if min(SECS[b]) != max(SECS[b]) else str(SECS[b][0])) + ' (n=%d)' % len(SECS[b])
SEC = sys.argv[1] if len(sys.argv) > 1 else ''
import io, contextlib
_buf = io.StringIO()
_stdout = sys.stdout
sys.stdout = _buf

print('@@S1')
print('| プラグイン | block | Tier | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | final.ll define | f80 関数 | 未実装 helper | `emcc -c` | lift 秒 |')
print('|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|')
tot = [0, 0, 0]
for name, blk, _ in targets.SHELLS:
    f, s = F[name], S[blk]
    tot[0] += f['closure_funcs']; tot[1] += f['closure_bytes']; tot[2] += int(s['defines'])
    print('| %s | %d | %s | %s / %s | %s / %s | %d | %d | %d | %s | %s | %s%s | %s | %s |' % (
        name, blk, M[name]['tier'], n(f['closure_funcs']), n(f['closure_bytes']), n(f['frontier_funcs']), n(f['frontier_bytes']),
        f['vcall'], f['ptr_or_vt0'], f['iat_calls'], s['defines'], s['f80_funcs'], s['declares_unimpl'],
        ' (%s)' % s['unimpl_names'] if s['unimpl_names'] else '', s['emcc_c_rc'], rng(blk)))
print('| 計 | | | **%s / %s** | | | | | %s | | | | |' % (n(tot[0]), n(tot[1]), n(tot[2])))

if not SEC or SEC == '2':
    up = os.path.join(W, 'unreached.json')
    if not os.path.exists(up):
        sys.exit('unreached.json が無い: 先に unreached_unique.py を実行する')
    U = json.load(open(up))
    print('@@S2')
    print('| プラグイン | 非共通 関数 / B | 閉包 関数 / B | 閉包外 関数 / B | うちデータ参照あり 関数 / B | データ参照なし 関数 / B | 正の対照 (entry のデータ参照検出) |')
    print('|---|--:|--:|--:|--:|--:|--:|')
    for name, _, _ in targets.SHELLS:
        o = U[name]
        g = lambda k: '%s / %s' % (n(o[k + '_funcs']), n(o[k + '_bytes']))
        ok = o['entries_found'] == o['entries'] and o['entries'] > 0
        print('| %s | %s | %s | %s | %s | %s | %d/%d%s |' % (name, g('nonfw'), g('closure'), g('outside'), g('dataref'), g('nodataref'),
              o['entries_found'], o['entries'], '' if ok else ' **NG**'))

print('@@S3')
print('| プラグイン | host call site 計 | slot0 (Dispatcher) 即値 ID (site) | 動的 ID | 他 slot (offset: site) | hs_ids.json に無い ID |')
print('|---|--:|---|--:|---|---|')
for name, blk, _ in targets.SHELLS:
    h = F[name]['host']
    imm = ' / '.join('%s (%d)' % (k, v) for k, v in sorted(h['ids'].items(), key=lambda kv: int(kv[0]) if kv[0] != 'dyn' else 1 << 30) if k != 'dyn') or '—'
    oth = ', '.join('%s: %d' % (k, v) for k, v in h['slot_disps'].items() if k != '0x0') or '—'
    print('| %s | %d | %s | %d | %s | %s |' % (name, h['sites'], imm, h['dyn_id_sites'], oth, h['ids_not_in_hs_ids'] or '無し'))

print('@@S4')
print('| プラグイン | 閉包内 site | 閉包内で呼ぶ kernel (site) | frontier 内 site | DLL 固有関数走査の site / kernel 種 |')
print('|---|--:|---|--:|---|')
for name, blk, _ in targets.SHELLS:
    k = F[name]['kernel']
    if not k.get('init_found'):
        print('| %s | — | kernel 表 init 未検出 | — | — |' % name)
        continue
    kc = ', '.join('%s (%d)' % (a, b) for a, b in k['kernels_in_closure'].items()) or '—'
    print('| %s | %d | %s | %d | %d / %d |' % (name, k['callsites_in_closure'], kc, k['callsites_in_frontier'], k['callsites_dll_unique_scan'], k['n_kernels_dll_scan']))

print('@@S5')
print('| 対象 | block | サイズ B | `.text` B | `.pdata` 関数 / B | export | import DLL (関数数) |')
print('|---|--:|--:|--:|--:|---|---|')
engs = [(nm + ' engine', f['engine']) for nm, f in F.items() if 'engine' in f and not f.get('monolith')] + \
       [(nm + ' (単体 DLL)', f['engine']) for nm, f in F.items() if f.get('monolith')]
for nm, e in engs:
    print('| %s | %d | %s | %s | %s / %s | %s | %s |' % (nm, e['block'], n(e['size']), n(e['text_bytes']), n(e['pdata_funcs']), n(e['pdata_bytes']),
          ', '.join(e['exports']) + (' (計 %d)' % e['n_exports'] if e['n_exports'] > len(e['exports']) else ''), ', '.join('%s (%d)' % kv for kv in e['imports'].items())))
ep = os.path.join(W, 'engines.csv')
if os.path.exists(ep):
    print('\n| block | lift rc | final.ll define | `.pdata` で define 無し (B) | f80 関数 | 未実装 helper | `emcc -c` | fixcmp 後 `emcc -c` | **f80_lower 後 `emcc -c` (最終)** | lift 秒 |')
    print('|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|')
    for r in csv.DictReader(open(ep)):
        print('| %s | %s | %s | %s / %s (%s B) | %s | %s | %s | %s | **%s** | %s |' % (r['block'], r['lift_rc'], r['defines'], r['missing_define'], r['pdata_funcs'], r['missing_bytes'],
              r['f80_funcs'], r['unimpl_helpers'], r['emcc_c_rc'], r['emcc_c_rc_after_fixcmp'], r['emcc_c_rc_after_f80'], r['lift_s']))

sys.stdout = _stdout
out = _buf.getvalue()
parts = dict(re.findall(r'@@S(\d)\n(.*?)(?=@@S\d\n|\Z)', out, re.S))
if SEC:
    print(parts[SEC].strip('\n'))
else:
    for k in sorted(parts):
        print('## §%s\n%s' % (k, parts[k].strip('\n')))
