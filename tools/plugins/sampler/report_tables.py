#!/usr/bin/env python3
"""REPORT.md の表 (§1〜§4) を work/sampler/{status.csv,facts.json,engines.csv} から機械的に生成する (転記ミス防止)。
usage: report_tables.py   (sampler_e2e.sh 実行後)
"""
import csv, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, '..', 'work', 'sampler')
sys.path.insert(0, HERE)
import targets

F = json.load(open(os.path.join(W, 'facts.json')))
S = {int(r['block']): r for r in csv.DictReader(open(os.path.join(W, 'status.csv')))}
M = {p['name']: p for p in json.load(open(os.path.join(HERE, '..', 'PLUGIN_MATRIX.json')))['plugins']}
n = lambda x: format(x, ',')

print('## §1 閉包 lift')
print('| プラグイン | block | Tier | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | final.ll define | f80 関数 | 未実装 helper | `emcc -c` | lift 秒 |')
print('|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|')
tot = [0, 0, 0]
for name, blk, _ in targets.SHELLS:
    f, s = F[name], S[blk]
    tot[0] += f['closure_funcs']; tot[1] += f['closure_bytes']; tot[2] += int(s['defines'])
    print('| %s | %d | %s | %s / %s | %s / %s | %d | %d | %d | %s | %s | %s%s | %s | %s |' % (
        name, blk, M[name]['tier'], n(f['closure_funcs']), n(f['closure_bytes']), n(f['frontier_funcs']), n(f['frontier_bytes']),
        f['vcall'], f['ptr_or_vt0'], f['iat_calls'], s['defines'], s['f80_funcs'], s['declares_unimpl'],
        ' (%s)' % s['unimpl_names'] if s['unimpl_names'] else '', s['emcc_c_rc'], s['seconds']))
print('| 計 | | | **%s / %s** | | | | | %s | | | | |' % (n(tot[0]), n(tot[1]), n(tot[2])))

print('\n## §2 host 呼出面')
print('| プラグイン | host call site 計 | slot0 (Dispatcher) 即値 ID (site) | 動的 ID | 他 slot (offset: site) | hs_ids.json に無い ID |')
print('|---|--:|---|--:|---|---|')
for name, blk, _ in targets.SHELLS:
    h = F[name]['host']
    imm = ' / '.join('%s (%d)' % (k, v) for k, v in sorted(h['ids'].items(), key=lambda kv: int(kv[0]) if kv[0] != 'dyn' else 1 << 30) if k != 'dyn') or '—'
    oth = ', '.join('%s: %d' % (k, v) for k, v in h['slot_disps'].items() if k != '0x0') or '—'
    print('| %s | %d | %s | %d | %s | %s |' % (name, h['sites'], imm, h['dyn_id_sites'], oth, h['ids_not_in_hs_ids'] or '無し'))

print('\n## §3 SIMD kernel 依存')
print('| プラグイン | 閉包内 site | 閉包内で呼ぶ kernel (site) | frontier 内 site | DLL 固有関数走査の site / kernel 種 |')
print('|---|--:|---|--:|---|')
for name, blk, _ in targets.SHELLS:
    k = F[name]['kernel']
    if not k.get('init_found'):
        print('| %s | — | kernel 表 init 未検出 | — | — |' % name)
        continue
    kc = ', '.join('%s (%d)' % (a, b) for a, b in k['kernels_in_closure'].items()) or '—'
    print('| %s | %d | %s | %d | %d / %d |' % (name, k['callsites_in_closure'], kc, k['callsites_in_frontier'], k['callsites_dll_unique_scan'], k['n_kernels_dll_scan']))

print('\n## §4 engine / 単体 DLL の外形')
print('| 対象 | block | サイズ B | `.text` B | `.pdata` 関数 / B | export | import DLL (関数数) |')
print('|---|--:|--:|--:|--:|---|---|')
engs = [(nm + ' engine', f['engine']) for nm, f in F.items() if 'engine' in f and not f.get('monolith')] + \
       [(nm + ' (単体 DLL)', f['engine']) for nm, f in F.items() if f.get('monolith')]
for nm, e in engs:
    print('| %s | %d | %s | %s | %s / %s | %s | %s |' % (nm, e['block'], n(e['size']), n(e['text_bytes']), n(e['pdata_funcs']), n(e['pdata_bytes']),
          ', '.join(e['exports']) + (' (計 %d)' % e['n_exports'] if e['n_exports'] > len(e['exports']) else ''), ', '.join('%s (%d)' % kv for kv in e['imports'].items())))
ep = os.path.join(W, 'engines.csv')
if os.path.exists(ep):
    print('\n| block | RetDec rc | final.ll define | `.pdata` で define 無し (B) | f80 関数 | 未実装 helper | `emcc -c` | fixcmp 後 `emcc -c` | lift 秒 |')
    print('|--:|--:|--:|--:|--:|--:|--:|--:|--:|')
    for r in csv.DictReader(open(ep)):
        print('| %s | %s | %s | %s / %s (%s B) | %s | %s | %s | %s | %s |' % (r['block'], r['lift_rc'], r['defines'], r['missing_define'], r['pdata_funcs'], r['missing_bytes'],
              r['f80_funcs'], r['unimpl_helpers'], r['emcc_c_rc'], r['emcc_c_rc_after_fixcmp'], r['lift_s']))
