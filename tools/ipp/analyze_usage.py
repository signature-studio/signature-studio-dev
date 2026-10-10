#!/usr/bin/env python3
"""scan 結果 (work/ipp_refs.json = mac x86_64/arm64, work/win_refs.json = win64) を突合し
   data/ipp_usage_summary.json と data/ipp_matrix.csv を生成。
   used = 呼出 (call) もしくは関数ポインタ読出 (品質切替で変数へ代入する形; other。x86/win のみ。arm64 は other に誤検出が多いので call のみ) のある関数。"""
import json, collections, os, re, csv
HERE = os.path.dirname(os.path.abspath(__file__)); W = f'{HERE}/work'
refs = json.load(open(f'{W}/ipp_refs.json')); win = json.load(open(f'{W}/win_refs.json'))
a64 = set(l.strip()[1:] for l in open(f'{W}/a64.syms')); x64 = set(l.strip()[1:] for l in open(f'{W}/x64.syms'))
legacy = {s[8:] for s in x64 if s.startswith('legacy90')}
x_prov = {s for s in x64 if not s.startswith('legacy90')} | legacy
winexp = set(json.load(open(f'{W}/win_exports.json')))
names = json.load(open(f'{W}/flengine_ipp_names.json'))['x86_64']; req = [n for n in names if n.startswith('ipp')]
from common import implemented_names
impl = implemented_names()

def cat(n):
    if n in ('ippMalloc', 'ippFree') or n.startswith(('ippSet', 'ippGet')): return 'control'
    if n.startswith('ippi'): return 'imaging(ippi)'
    if n.startswith('ippsFFT'): return 'FFT'
    if re.match(r'ippsConvert|ippsRound', n): return 'convert'
    if re.match(r'ipps(FIR|IIR|Conv_|CrossCorr|AutoCorr)', n): return 'FIR/IIR/conv/corr'
    if re.match(r'ipps(Copy|Move|Zero|Set)_', n): return 'mem/fill'
    if re.match(r'ippsThreshold', n): return 'threshold'
    if re.search(r'_A\d+$', n) or re.match(r'ipps(Exp|Ln|Log10|Sin|Cos|Atan|Tanh|Powx|Cbrt|Expm1|Sqrt)', n): return 'vector math (accuracy-graded)'
    if re.match(r'ipps(CplxToReal|RealToCplx|Magnitude|Phase|PowerSpectr|MulPack|Mul_32f32fc|Mul_32fc|AddProduct)', n): return 'complex/spectral'
    if re.match(r'ipps(Tone|Rand|VectorSlope|Win|Triangle)', n): return 'signal gen'
    if re.match(r'ipps(Interleave|Deinterleave|SwapBytes|Flip|OrC|AndC|XorC|Equal)', n): return 'reorder/bit'
    if re.match(r'ipps(Sum|Min|Max)', n): return 'reduce'
    return 'vector arith'

def agg_x(arch):
    calls = collections.Counter(); oth = collections.Counter(); mods = collections.defaultdict(set); fe = {}
    for i, v in refs.items():
        t = v.get(arch)
        if not t: continue
        isfe = v['path'].endswith('FLEngine_x64.dylib')
        for e in t['table']:
            calls[e['name']] += e['call']; oth[e['name']] += e.get('other', 0)
            if e['call'] or e.get('other', 0): mods[e['name']].add(int(i))
            if isfe: fe[e['name']] = e['call'] + e.get('other', 0)
    return calls, oth, mods, fe
out = {'meta': {'mac_modules': len(refs), 'mac_modules_arm64': sum(1 for v in refs.values() if v.get('a64')), 'win_modules_with_table': sum(1 for v in win.values() if v and v.get('entries'))}}
S = {}
for arch, label in (('x64', 'mac_x86_64'), ('a64', 'mac_arm64')):
    calls, oth, mods, fe = agg_x(arch)
    S[label] = {'call': {n for n, c in calls.items() if c}, 'used': {n for n in req if calls[n] or (oth[n] and arch == 'x64')}, 'flengine': {n for n, c in fe.items() if c}, 'mods': mods, 'sites': calls}
wc = collections.Counter(); wo = collections.Counter(); wm = collections.defaultdict(set); wfe = {}
for f, v in win.items():
    if not v or 'error' in v or not v.get('entries'): continue
    for e in v['table']:
        wc[e['name']] += e['call']; wo[e['name']] += e['other']
        if e['call'] or e['other']: wm[e['name']].add(f)
        if f == 'block00031_PE.bin': wfe[e['name']] = e['call'] + e['other']
S['win64'] = {'call': {n for n, c in wc.items() if c}, 'used': {n for n in req if wc[n] or wo[n]}, 'flengine': {n for n, c in wfe.items() if c}, 'mods': wm, 'sites': wc}
for k, v in S.items():
    out[k] = {'n_call': len(v['call']), 'n_used(call|ptr-load)': len(v['used']), 'n_in_FLEngine_main_binary': len(v['flengine']),
              'used_functions': sorted(v['used']), 'FLEngine_functions': sorted(v['flengine'])}
cats = collections.defaultdict(lambda: collections.Counter())
for n in sorted(S['win64']['used'] | S['mac_x86_64']['used'] | S['mac_arm64']['used']):
    cats[cat(n)]['union'] += 1
    for k in ('win64', 'mac_x86_64', 'mac_arm64'):
        if n in S[k]['used']: cats[cat(n)][k] += 1
    if n in a64: cats[cat(n)]['in_arm64_dylib'] += 1
    if n in impl: cats[cat(n)]['implemented_PoC'] += 1
out['categories(union of used)'] = {c: dict(v) for c, v in sorted(cats.items())}
u_all = S['win64']['used'] | S['mac_x86_64']['used'] | S['mac_arm64']['used']
cov = {}
for k in ('win64', 'mac_x86_64', 'mac_arm64'):
    u = S[k]['used']; fe = S[k]['flengine']
    cov[k] = {'used': len(u), 'implemented_of_used': len(u & impl), 'FLEngine_main_binary': len(fe), 'implemented_of_FLEngine': len(fe & impl)}
out['poc_coverage'] = cov
out['sets'] = {
  'FL_requested_names': len(req), 'union_used_all_platforms': len(u_all),
  'arm64_dylib_exports': len(a64), 'arm64_dylib_provides_of_requested': len(set(req) & a64),
  'x86_64_dylib_provides_of_requested(plain|legacy90)': len(set(req) & x_prov), 'win_dll_provides_of_requested': len(set(req) & winexp),
  'used_by_win_not_in_arm64_dylib': sorted(S['win64']['used'] - a64),
  'used_by_mac_x86_not_in_arm64_dylib': sorted(S['mac_x86_64']['used'] - a64),
  'used_by_mac_arm64_not_in_arm64_dylib': sorted(S['mac_arm64']['used'] - a64),
  'used_by_union_not_in_arm64_dylib': sorted(u_all - a64),
  'win_used_minus_mac_x86_used': sorted(S['win64']['used'] - S['mac_x86_64']['used']), 'mac_x86_used_minus_win_used': sorted(S['mac_x86_64']['used'] - S['win64']['used']),
  'arm64_dylib_exports_unused_by_any': sorted((a64 & set(req)) - u_all), 'arm64_dylib_not_requested_by_FL': sorted(a64 - set(req)),
  'requested_unused_by_any_platform': len(set(req) - u_all),
}
os.makedirs(f'{HERE}/data', exist_ok=True)
json.dump(out, open(f'{HERE}/data/ipp_usage_summary.json', 'w'), indent=1)
with open(f'{HERE}/data/ipp_matrix.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['name', 'category', 'win_dll', 'mac_x86_dylib', 'mac_arm64_dylib', 'used_win', 'used_mac_x86', 'used_mac_arm64', 'win_FLEngine', 'win_modules', 'win_call_sites', 'mac_x86_modules', 'implemented_poc'])
    for n in req:
        w.writerow([n, cat(n), int(n in winexp), int(n in x_prov), int(n in a64), int(n in S['win64']['used']), int(n in S['mac_x86_64']['used']), int(n in S['mac_arm64']['used']),
                    int(n in S['win64']['flengine']), len(S['win64']['mods'].get(n, ())), S['win64']['sites'][n], len(S['mac_x86_64']['mods'].get(n, ())), int(n in impl)])
for k in ('win64', 'mac_x86_64', 'mac_arm64'): print(k, {kk: vv for kk, vv in out[k].items() if kk.startswith('n_')})
for c, v in out['categories(union of used)'].items(): print(f'  {c:34s}', dict(v))
for k, v in out['sets'].items(): print(' ', k, v if not isinstance(v, list) else (len(v), v[:6]))
