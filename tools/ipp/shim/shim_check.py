#!/usr/bin/env python3
"""shim e2e の各段の出力 (../work/shim/*) を集約して合否を決め、data/shim_results.json を書く。"""
import json, os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__)); IPP = os.path.dirname(HERE); W = f'{IPP}/work/shim'
def jl(p):
    t = open(p).read(); return json.loads(t[t.index('[\n'):])
checks = []; res = {}
def chk(name, ok, detail=''): checks.append((name, bool(ok), detail)); print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''))
summ = json.load(open(f'{HERE}/data/sigs_summary.json')); sigs = json.load(open(f'{HERE}/data/ipp_sigs.json'))['entries']
chk('S1 420 名すべてに署名 (不明 0) + thunk 件数', summ['names'] == 420 and summ['unknown_sig'] == 0, f"typed thunk(実装済)={summ['thunks_typed(impl)']} fail-soft stub={summ['stubs(fail-soft)']}")
chk('S2 署名の呼出実績検算: 型/個数の矛盾 0', summ['evidence_check'].get('conflict', 0) == 0, f"確度 {summ['confidence']} / 実績 {summ['evidence_check']}")
st = open(f'{W}/selftest.log').read().strip().splitlines()[-1]
chk('S3 native 自己検査 (ABI プローブ 6 + 420 名解決 + LoadLibraryW + stub 377 fail-soft)', st.endswith('failed=0'), st)
base1 = {r['fn']: r for r in jl(f'{IPP}/work/cmp_avx512.json')}; base2 = {r['fn']: r for r in jl(f'{IPP}/work/cmp_avx512_spec.json')}
def cmp_set(path, base):
    th = {r['fn']: r for r in jl(path)}; bad = []
    for f, r in th.items():
        d = {k: v for k, v in r.items() if k not in ('thunk', 'thunk_vs_direct_word_diff', 'thunk_vs_direct_status_diff')}
        t = r['thunk']
        if d != base[f] or {k: d[k] for k in t} != t or r['thunk_vs_direct_word_diff'] or r['thunk_vs_direct_status_diff']: bad.append(f)
    exact = [f for f, r in th.items() if r['thunk']['differ'] == 0 and r['thunk']['status_mismatch'] == 0]
    return th, bad, exact
th1, bad1, ex1 = cmp_set(f'{W}/cmp_thunk.json', base1); th2, bad2, ex2 = cmp_set(f'{W}/cmp_thunk_spec.json', base2)
n = sum(r['thunk']['cases'] for r in th1.values())
chk('S4 native: thunk 経路 = 直呼び = 既存 baseline (cmp_avx512.json) の全統計一致 (24 関数, 通常入力)', len(th1) == 24 and not bad1, f'{n} ケース, 不一致関数 {bad1}')
chk('S5 native: 同 (特殊値入力 ±0/denormal/inf/NaN)', len(th2) == 24 and not bad2, f'不一致関数 {bad2}')
chk('S6 native: 実 IPP に対し thunk 経由でも 21 関数 bit-exact (通常/特殊値)', len(ex1) == 21 and len(ex2) == 21, f'{len(ex1)} / {len(ex2)}')
eg = json.loads(open(f'{W}/err_thunk.json').read().strip().splitlines()[-1])
chk('S7 native: エラー経路格子 (NULL×len) 222 点が thunk 経由でも実 IPP と一致', eg['err_grid_total'] == 222 and eg['err_grid_mismatch'] == 0 and eg['err_grid_mismatch_thunk'] == 0, str(eg))
for tag, p in (('scalar', 'wasm_thunk.json'), ('simd128', 'wasm_thunk_simd.json')):
    w = json.load(open(f'{W}/{p}')); rows = w['rows']
    ok = all(r['verdict'] == 'PASS' for r in rows) and sum(1 for r in rows if r['bit_exact_all']) == 21 and w['fft']['bad'] == 0 and w['table']['count'] == 420 and w['table']['stub_failsoft_ok']
    chk(f'S8 wasm({tag}): golden 突合 21 bit-exact + FFT 48 ケース + 420 名表 + stub fail-soft (thunk 経由)', ok, f"bitExact={sum(1 for r in rows if r['bit_exact_all'])}/{len(rows)} fft32={w['fft']['worst32']:.2e} fft64={w['fft']['worst64']:.2e}")
    res[f'wasm_{tag}'] = w
gl = open(f'{W}/shimx_glue.log').read().strip().splitlines()[-1]
chk('S9 shimx 結合: LoadLibraryW(dsp_ippv2_x64.dll) -> GetProcAddress 420/420 -> dispatch (MulC 実行, stub fail-soft)', gl.startswith('shimx_glue_test: PASS'), gl)
sz = {p: os.path.getsize(f'{W}/{p}') for p in ('ipp_shim.wasm', 'ipp_shim_simd.wasm')}
res.update({'sigs_summary': summ, 'native_thunk_cmp': list(th1.values()), 'native_thunk_cmp_special': list(th2.values()), 'native_err_grid': eg, 'wasm_bytes': sz, 'selftest': st, 'shimx_glue': gl})
res.pop('wasm_scalar', None); res.pop('wasm_simd128', None)
json.dump(res, open(f'{HERE}/data/shim_results.json', 'w'), indent=1, ensure_ascii=False)
fails = [c for c in checks if not c[1]]
print(f'\n== ipp shim e2e: checks {len(checks)}, failed {len(fails)}  (wasm bytes: {sz})')
sys.exit(1 if fails else 0)
