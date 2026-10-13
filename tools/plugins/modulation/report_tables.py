#!/usr/bin/env python3
"""REPORT.md §1〜§4 の表を work/modulation/{facts.json,status8.csv,engines.csv} から生成する (REPORT の数値の再現元)。
usage: report_tables.py   (modulation_e2e.sh 実行後)
"""
import csv, json, os, re

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
W = os.path.join(P, 'work', 'modulation')
F = json.load(open(os.path.join(W, 'facts.json')))
S = {r['block']: r for r in csv.DictReader(open(os.path.join(W, 'status8.csv')))}
M = {p['name']: p for p in json.load(open(os.path.join(P, 'PLUGIN_MATRIX.json')))['plugins']}
E = {r['block']: r for r in csv.DictReader(open(os.path.join(W, 'engines.csv')))}
n = lambda x: '{:,}'.format(x)

print('### §1 閉包 lift 結果')
print('| プラグイン | block | Tier | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | define | f80 関数 | 未実装 helper | `emcc -c` | lift 秒 |')
print('|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|')
tot = [0, 0, 0]
for nm, f in F.items():
    s = S[str(f['block'])]
    tot[0] += f['closure_funcs']; tot[1] += f['closure_bytes']; tot[2] += int(s['defines'])
    print('| %s | %d | %s | %d / %s | %d / %s | %d | %d | %d | %s | %s | %s | %s | %s |' % (
        nm, f['block'], M[nm]['tier'], f['closure_funcs'], n(f['closure_bytes']), f['frontier_funcs'], n(f['frontier_bytes']),
        f['vcall'], f['ptr_or_vt0'], f['iat_calls'], s['defines'], s['f80_funcs'], s['declares_unimpl'], s['emcc_c_rc'], s['seconds']))
print('| 計 | | | **%d / %s** | | | | | %d | | | | |' % (tot[0], n(tot[1]), tot[2]))

print('\n### §2 host 呼出面')
print('| プラグイン | host call site 計 | slot0 (Dispatcher) 即値 ID (site 数) | 動的 ID | 他 slot (offset: site) | `hs_ids.json` に無い ID |')
print('|---|--:|---|--:|---|---|')
for nm, f in F.items():
    h = f['host']
    ids = ' / '.join('%s (%d)' % (k, v) for k, v in sorted(((k, v) for k, v in h['ids'].items() if k != 'dyn'), key=lambda x: int(x[0])))
    oth = ', '.join('%s: %d' % (k, v) for k, v in h['slot_disps'].items() if k != '0x0')
    print('| %s | %d | %s | %d | %s | %s |' % (nm, h['sites'], ids or '—', h['dyn_id_sites'], oth or '—', h['ids_not_in_hs_ids'] or 'なし'))

print('\n### §3 SIMD kernel 表')
print('| プラグイン | 閉包内 site | 閉包内で呼ぶ kernel (site) | frontier 内 site | DLL 固有関数走査の site / kernel 種 |')
print('|---|--:|---|--:|---|')
for nm, f in F.items():
    k = f['kernel']
    print('| %s | %d | %s | %d | %d / %d |' % (nm, k['callsites_in_closure'], ', '.join('%s (%d)' % x for x in k['kernels_in_closure'].items()) or '—',
                                              k['callsites_in_frontier'], k['callsites_dll_unique_scan'], k['n_kernels_dll_scan']))

print('\n### §4 engine 外形')
print('| プラグイン | engine block | サイズ B | `.text` B | `.pdata` 関数 / B | export | KERNEL32 import |')
print('|---|--:|--:|--:|--:|---|--:|')
for nm, f in F.items():
    if 'engine' in f:
        e = f['engine']
        print('| %s | %d | %s | %s | %d / %s | %s | %d |' % (nm, e['block'], n(e['size']), n(e['text_bytes']), e['pdata_funcs'], n(e['pdata_bytes']),
                                                            ', '.join(e['exports']), e['imports'].get('KERNEL32.dll', 0)))

print('\n### §4 engine lift')
print('| engine | RetDec rc | final.ll define | `.pdata` で define 無し (B) | 内部に増えた define | f80 関数 | 未実装 helper (うち VEX) | `emcc -c` | 局所修復 (4 operand) 後 | lift 秒 |')
print('|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|')
for nm, f in F.items():
    if 'engine' in f:
        b = str(f['engine']['block'])
        e = E[b]
        simd = open(os.path.join(W, 'engine' + b, 'e.simd.log')).read()
        vex = len([x for x in re.findall(r'unimplemented: .*?(__asm_\w+)', simd) if x.startswith('__asm_v')])
        print('| %s (%s) | %s | %s | %s / %s (%s) | %s | %s | %s (%d) | %s | %s | %s |' % (
            b, nm, e['lift_rc'], e['defines'], e['missing_define'], e['pdata_funcs'], n(int(e['missing_bytes'])), e['extra_inside'], e['f80_funcs'],
            e['unimpl_helpers'], vex, e['emcc_c_rc'], e['emcc_c_rc_after_fixcmp'], e['lift_s']))
