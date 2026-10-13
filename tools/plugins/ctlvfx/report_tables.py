#!/usr/bin/env python3
"""REPORT.md の §1〜§3 の表と集計値を work/ctlvfx/{status.csv,facts.json} から生成する (転記ミス防止)。 REPORT へは出力をそのまま貼る。
usage: report_tables.py
"""
import csv, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from targets import TARGETS
P = os.path.join(HERE, '..')
F = json.load(open(os.path.join(P, 'work', 'ctlvfx', 'facts.json')))
S = {int(r['block']): r for r in csv.DictReader(open(os.path.join(P, 'work', 'ctlvfx', 'status.csv')))}
ALL = list(csv.DictReader(open(os.path.join(P, 'work', 'batch', 'status.csv'))))   # 追記式。 28 行ずつが 1 回分
RUNS = [ALL[i:i + len(TARGETS)] for i in range(0, len(ALL), len(TARGETS))]
SECS = {}
for r in ALL:
    SECS.setdefault(int(r['block']), []).append(int(r['seconds']))
rng = lambda b: '%d–%d' % (min(SECS[b]), max(SECS[b])) if min(SECS[b]) != max(SECS[b]) else str(SECS[b][0])
fmt = lambda d: ' / '.join('%s (%d)' % (k, v) for k, v in d.items()) or '—'
tot = dict(funcs=0, bytes=0, defines=0, f80=0, unimpl=0, emcc=0, sec=0)

print('### §1 閉包 lift 結果')
print('| プラグイン | block | Tier | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | final.ll define | f80 関数 | 未実装 helper | `emcc -c` | lift 秒 |')
print('|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|')
for name, blk, tier, eng in TARGETS:
    f, s = F[name], S[blk]
    print('| %s%s | %d | %s | %d / %s | %d / %s | %d | %d | %d | %s | %s | %s | %s | %s |' % (
        name, ' (+engine %d)' % eng if eng else '', blk, tier, f['closure_funcs'], format(f['closure_bytes'], ','),
        f['frontier_funcs'], format(f['frontier_bytes'], ','), f['vcall'], f['ptr_or_vt0'], f['iat_calls'],
        s['defines'], s['f80_funcs'], s['declares_unimpl'], s['emcc_c_rc'], rng(blk)))
    tot['funcs'] += f['closure_funcs']; tot['bytes'] += f['closure_bytes']; tot['defines'] += int(s['defines'])
    tot['f80'] += int(s['f80_funcs']); tot['unimpl'] += int(s['declares_unimpl']); tot['emcc'] += int(s['emcc_c_rc']); tot['sec'] += int(s['seconds'])
print('| 計 | | | **%d / %s** | | | | | %d | %d | %d | %d | 各回の計 %s |' % (tot['funcs'], format(tot['bytes'], ','), tot['defines'], tot['f80'], tot['unimpl'], tot['emcc'],
                                                               ' / '.join(str(sum(int(r['seconds']) for r in run)) for run in RUNS)))
print('\nlift 秒の列は status.csv に残る全回 (n=%d 回、`lift_ranges.sh` のみ。 emcc 除く) の min–max' % len(RUNS))
bt = {}
for name, blk, tier, eng in TARGETS:
    b = bt.setdefault(tier, [0, 0, 0, 0])
    b[0] += 1; b[1] += F[name]['closure_funcs']; b[2] += F[name]['closure_bytes']
    b[3] += (int(S[blk]['lift_rc']) == 0 and int(S[blk]['emcc_c_rc']) == 0 and int(S[blk]['f80_funcs']) == 0 and int(S[blk]['declares_unimpl']) == 0)
print('Tier 別 (本数 / 閉包関数 / B / gate 項目全 0 の本数): ' + '、'.join('%s: %d / %d / %s / %d' % (t, *bt[t][:2], format(bt[t][2], ','), bt[t][3]) for t in sorted(bt)))

print('\n### §2 host 呼出面')
print('| プラグイン | host call site 計 | slot0 (Dispatcher) 即値 ID (site) | 動的 ID | 他 slot (offset: site) |')
print('|---|--:|---|--:|---|')
ids, nohost, notin, dynt, imm_t, sites_t = {}, [], {}, 0, 0, 0
for name, blk, tier, eng in TARGETS:
    h = F[name]['host']
    imm = {k: v for k, v in h['ids'].items() if k != 'dyn'}
    oth = {k: v for k, v in h['slot_disps'].items() if k != '0x0'}
    print('| %s | %d | %s | %d | %s |' % (name, h['sites'], fmt(imm), h['dyn_id_sites'], ', '.join('%s: %d' % kv for kv in oth.items()) or '—'))
    for k, v in imm.items():
        ids[k] = ids.get(k, 0) + v
    dynt += h['dyn_id_sites']; imm_t += h['imm_id_sites']; sites_t += h['sites']
    if h['sites'] == 0:
        nohost.append(name)
    if h['ids_not_in_hs_ids']:
        notin[name] = h['ids_not_in_hs_ids']
print('\n即値 ID distinct = %d 種 %s、即値 ID site 計 %d、動的 ID site 計 %d、host call site 総計 %d' % (
    len(ids), sorted(int(k) for k in ids), imm_t, dynt, sites_t))
print('hs_ids.json に無い即値 ID: %s' % (notin or 'なし'))
print('host call site 0 の plugin: %s' % (nohost or 'なし'))

print('\n### §3 SIMD kernel 表への依存')
print('| プラグイン | 閉包内 site | 閉包内で呼ぶ kernel (site) | frontier 内 site | DLL 固有関数走査 site / kernel 種 |')
print('|---|--:|---|--:|---|')
uses = []
for name, blk, tier, eng in TARGETS:
    k = F[name]['kernel']
    if not k.get('init_found'):
        print('| %s | init 未検出 | | | |' % name)
        continue
    print('| %s | %d | %s | %d | %d / %d |' % (name, k['callsites_in_closure'], fmt(k['kernels_in_closure']), k['callsites_in_frontier'],
                                                k['callsites_dll_unique_scan'], k['n_kernels_dll_scan']))
    if k['callsites_in_closure']:
        uses.append(name)
print('\n閉包内に kernel 呼出がある plugin: %s' % (uses or 'なし'))

print('\n### §4 engine')
for name, blk, tier, eng in TARGETS:
    if eng:
        e = F[name]['engine']
        print('%s: block %d size %d text %d pdata %d funcs / %d B exports %s KERNEL32 import %s imports=%s' % (
            name, eng, e['size'], e['text_bytes'], e['pdata_funcs'], e['pdata_bytes'], e['exports'], e['imports'].get('KERNEL32.dll'), dict(e['imports'])))
