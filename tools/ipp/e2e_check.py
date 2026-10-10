#!/usr/bin/env python3
"""e2e の各段の出力 (work/*.json) を集約して data/diff_results.json を書き、合否 (exit code) を決める。"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); W = f'{HERE}/work'
def jl(p):
    t = open(p).read(); return json.loads(t[t.index('[\n'):])
res = {}; checks = []
def chk(name, ok, detail=''): checks.append((name, bool(ok), detail)); print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''))
ev = json.load(open(f'{W}/loader_evidence.json')); use = json.load(open(f'{HERE}/data/ipp_usage_summary.json')); nm = json.load(open(f'{W}/flengine_ipp_names.json'))
x, a = [n for n in nm['x86_64'] if n.startswith('ipp')], [n for n in nm['arm64'] if n.startswith('ipp')]
chk('C1 FLEngine x86_64/arm64 が同一の 420 名・同順で ipp 表を持つ', x == a and len(x) == 420, f'{len(x)} vs {len(a)}')
chk('C2 ロードは dlopen/dlsym (ipp 未定義シンボル 0)', ev['mac_x86_64']['imports_dlopen_dlsym'] and ev['mac_arm64']['imports_dlopen_dlsym'] and ev['mac_x86_64']['undefined_ipp_symbols'] == 0 and ev['mac_arm64']['undefined_ipp_symbols'] == 0)
chk('C3 arm64 FLEngine は "IPP function not found" 経路を持たない / x86_64・win64 は持つ', (not ev['mac_arm64']['has_"IPP function not found: "_literal']) and ev['mac_x86_64']['has_"IPP function not found: "_literal'] and ev['win64']['has_"IPP function not found: "_literal'])
s = use['sets']
chk('C4 win DLL / mac x86_64 dylib(plain|legacy90) は要求 420 名を全て提供', s['win_dll_provides_of_requested'] == 420 and s['x86_64_dylib_provides_of_requested(plain|legacy90)'] == 420)
u = use['sets']['union_used_all_platforms']; miss = len(s['used_by_union_not_in_arm64_dylib'])
chk('C5 arm64 スライス export は使用関数集合(全プラットフォーム和集合)をほぼ被覆 (欠落 ≤ 8)', miss <= 8, f'used union={u}, arm64 欠落={miss}: {s["used_by_union_not_in_arm64_dylib"]}')
def load(p): return {r['fn']: r for r in jl(p)}
cmp1, cmp2 = load(f'{W}/cmp_avx512.json'), load(f'{W}/cmp_avx512_spec.json')
TOL = {'ippsSqrt_32f_A11', 'ippsExp_32f_A11', 'ippsVectorSlope_32f'}
exact = [f for f in cmp1 if f not in TOL]
chk('C6 native: 21 関数が実 IPP(AVX512 経路)と bit-exact (通常入力)', all(cmp1[f]['differ'] == 0 and cmp1[f]['status_mismatch'] == 0 for f in exact), f'{len(exact)} 関数')
chk('C7 native: 同 21 関数が特殊値(±0/denormal/inf/NaN)のみの入力でも bit-exact', all(cmp2[f]['differ'] == 0 and cmp2[f]['status_mismatch'] == 0 for f in exact))
chk('C8 エラー経路格子 (NULL×len) の戻り値が実 IPP と一致', json.loads(open(f'{W}/err_grid.json').read().strip().splitlines()[-1])['err_grid_mismatch'] == 0)
isa = json.load(open(f'{W}/isa_diff.json'))
res['isa_path_dependence(real IPP vs real IPP)'] = isa
acc = json.load(open(f'{W}/acc.json'))['acc']; res['accuracy'] = acc
wc = json.load(open(f'{W}/wasm_cmp.json')); ws = json.load(open(f'{W}/wasm_cmp_simd.json'))
chk('C9 wasm(scalar): golden 突合で fail=0, bit-exact 21 関数', all(r['verdict'] == 'PASS' for r in wc['rows']) and sum(1 for r in wc['rows'] if r['bit_exact_all']) >= 21, f"bitExact={sum(1 for r in wc['rows'] if r['bit_exact_all'])}/{len(wc['rows'])}")
chk('C10 wasm(simd128): 同上 (SIMD 化で bit が変わらない)', all(r['verdict'] == 'PASS' for r in ws['rows']) and sum(1 for r in ws['rows'] if r['bit_exact_all']) >= 21)
fw = json.load(open(f'{W}/wasm_fft.json')); chk('C11 wasm FFT(Pack, 32f/64f, 全 flag) が実 IPP と NRMS 一致 (32f<5e-6, 64f<1e-12)', fw['bad'] == 0, f"worst32={fw['worst32']:.2e} worst64={fw['worst64']:.2e}")
chk('C12 ipp_lookup が 420 名を引き、未実装 stub は fail-fast で名前を報告', wc['table']['count'] == 420 and wc['table']['lookup_ok'] and wc['table']['stub_failfast_ok'], f"implemented={wc['table']['implemented']} stubs={wc['table']['stubs']}")
res['wasm_vs_real_ipp'] = {'scalar': wc['rows'], 'simd128': ws['rows'], 'table': wc['table']}
res['fft'] = {'worst_nrms_32f': fw['worst32'], 'worst_nrms_64f': fw['worst64']}
res['native_cmp_avx512'] = list(cmp1.values()); res['native_cmp_avx512_special_values'] = list(cmp2.values())
json.dump(res, open(f'{HERE}/data/diff_results.json', 'w'), indent=1)
fails = [c for c in checks if not c[1]]
print(f'\n== ipp e2e: checks {len(checks)}, failed {len(fails)}')
sys.exit(1 if fails else 0)
