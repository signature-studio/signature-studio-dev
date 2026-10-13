#!/usr/bin/env python3
"""work/distortion/{status.csv,shell_audit.csv,facts.json,engines.csv} から REPORT.md の表 (§1〜§4) を Markdown で出力する (転記ミス防止)。
usage: tables.py [DIR]    前提: distortion_e2e.sh 実行済み (DIR 省略時 work/distortion)
"""
import csv, json, os, re, sys
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
D = sys.argv[1] if len(sys.argv) > 1 else os.path.join(P, 'work', 'distortion')
S = {r['block']: r for r in csv.DictReader(open(os.path.join(D, 'status.csv')))}
A = {r['block']: r for r in csv.DictReader(open(os.path.join(D, 'shell_audit.csv')))}
F = json.load(open(os.path.join(D, 'facts.json')))
E = {r['block']: r for r in csv.DictReader(open(os.path.join(D, 'engines.csv')))}
sh = F['shells']
n = lambda x: '{:,}'.format(int(x))

print('### §1 閉包 lift')
print('| DLL | block | Tier | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | final.ll define (うち range 内部の追加) | f80 関数 | 未実装 helper | `emcc -c` | lift 秒 |')
print('|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|')
tf = tb = td = 0
for b, f in sh.items():
    s, a = S[b], A[b]
    tf += f['closure_funcs']; tb += f['closure_bytes']; td += int(s['defines'])
    print('| %s | %s | %s | %s / %s | %s / %s | %d | %d | %d | %s (%s) | %s | %s | %s | %s |' % (
        f['label'], b, f['tier'], n(f['closure_funcs']), n(f['closure_bytes']), n(f['frontier_funcs']), n(f['frontier_bytes']),
        f['vcall'], f['ptr_or_vt0'], f['iat_calls'], s['defines'], a['extra_inside'], s['f80_funcs'], s['declares_unimpl'], s['emcc_c_rc'], s['seconds']))
print('| 計 | | | **%s / %s** | | | | | %s | 0 | %d | 0 | |' % (n(tf), n(tb), n(td), sum(int(S[b]['declares_unimpl']) for b in sh)))
print()
print('### §2 host 呼出面')
print('| DLL | host call site 計 | slot0 (Dispatcher) 即値 ID (site) | 動的 ID | 他 slot (offset: site) | hs_ids.json に無い ID |')
print('|---|--:|---|--:|---|---|')
for b, f in sh.items():
    h = f['host']
    ids = ', '.join('%s (%d)' % (k, v) for k, v in sorted(h['ids'].items(), key=lambda x: (x[0] == 'dyn', x[0])) if k != 'dyn') or '—'
    oth = ', '.join('%s: %d' % (k, v) for k, v in h['slot_disps'].items() if k != '0x0') or '—'
    print('| %s | %d | %s | %d | %s | %s |' % (f['label'], h['sites'], ids, h['dyn_id_sites'], oth, h['ids_not_in_hs_ids'] or '無し'))
print()
print('### §3 SIMD kernel 依存')
print('| DLL | 閉包内 site | 閉包内で呼ぶ kernel (site) | frontier 内 site | DLL 固有関数走査 site / kernel 種 |')
print('|---|--:|---|--:|---|')
for b, f in sh.items():
    k = f['kernel']
    kc = ', '.join('%s (%d)' % (a, c) for a, c in k['kernels_in_closure'].items()) or '—'
    print('| %s | %d | %s | %d | %d / %d |' % (f['label'], k['callsites_in_closure'], kc, k['callsites_in_frontier'], k['callsites_dll_unique_scan'], k['n_kernels_dll_scan']))
print()
print('### §4 C++ DLL')
print('| DLL | block | サイズ B | `.text` B | `.pdata` 関数 / B | import (DLL: 件数) |')
print('|---|--:|--:|--:|--:|---|')
for b, e in F['engines'].items():
    print('| %s | %s | %s | %s | %s / %s | %s |' % (e['name'], b, n(e['size']), n(e['text_bytes']), n(e['pdata_funcs']), n(e['pdata_bytes']),
                                                   ', '.join('%s: %d' % (k.replace('.dll', ''), v) for k, v in e['imports'].items())))
print()
print('| DLL | RetDec rc | final.ll define | `.pdata` で define 無し (関数 / B) | f80 関数 | 未実装 helper | `emcc -c` | f80 lowering 前の f80 関数 / `emcc -c` | lift 秒 |')
print('|---|--:|--:|--:|--:|--:|--:|--:|--:|')
for b, e in F['engines'].items():
    r = E[b]
    names = set(re.findall(r'^   unimplemented: .*?(__asm_\w+)', open(os.path.join(D, 'engine' + b, 'e.simd.log')).read(), re.M))
    vex = sum(1 for x in names if x.startswith('__asm_v'))
    print('| %s | %s | %s | %s / %s | %s | %s (うち VEX %d) | %s | %s | %s |' % (e['name'], r['lift_rc'], n(r['defines']), r['missing_define'], r['missing_bytes'], r['f80_funcs'],
                                                                r['unimpl_helpers'], vex, r['emcc_c_rc'], '%s / %s' % (r['f80_funcs_pre'], r['emcc_c_rc_pre_f80']), r['lift_s']))
