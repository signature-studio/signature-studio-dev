#!/usr/bin/env python3
"""p0c_regress.py — 修正後の p0c/kernel_matrix.py (dispfix 適用) で kernel 表ハッシュ突合が 79/80 → 80/80 に改善するかの実測 (CAB-229 要件4)

kernel_matrix.py の __main__ は p0c/work/kernel_matrix.json を上書きするので、ここでは module を import して
scan_dll を直接回し、結果は icall/disp_size/work/kernel_matrix_fixed.json (gitignore) に書く。p0c の成果物には触れない。
比較対象 = p0c/work/kernel_matrix.json (修正前の実走結果)。 usage: p0c_regress.py [--jobs 12] [--limit N]
"""
import argparse, collections, json, os, sys, time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
P0C = os.path.abspath(os.path.join(HERE, '..', '..', 'plugins', 'p0c'))
sys.path.insert(0, P0C)
import kernel_matrix as K      # import 時に Balance の基準 hash (INIT_HASH / KHASH) を修正版で計算する


def dist(M):
    c = collections.Counter()
    for k, v in M.items():
        if v.get('delphi') and v.get('init_found'):
            c[(v['kernels_hash_ok'], v['kernels_hash_bad'])] += 1
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=12)
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()
    ids = K.dll_ids()
    if a.limit:
        ids = ids[:a.limit]
    t = time.time()
    with Pool(a.jobs) as p:
        R = dict(p.map(K.scan_dll, ids))
    R = {str(i): r for i, r in R.items()}
    os.makedirs(os.path.join(HERE, 'work'), exist_ok=True)
    json.dump(R, open(os.path.join(HERE, 'work', 'kernel_matrix_fixed.json'), 'w'))
    old = json.load(open(os.path.join(P0C, 'work', 'kernel_matrix.json')))
    old = {k: v for k, v in old.items() if k in R}
    do, dn = dist(old), dist(R)
    print('scan %.0fs, DLL %d (delphi+init found: 修正前 %d / 修正後 %d)' % (time.time() - t, len(R), sum(do.values()), sum(dn.values())))
    print('(kernels_hash_ok, bad) 分布  修正前:', dict(do))
    print('(kernels_hash_ok, bad) 分布  修正後:', dict(dn))
    full_o = sum(v for (ok, bad), v in do.items() if ok == 80 and bad == 0)
    full_n = sum(v for (ok, bad), v in dn.items() if ok == 80 and bad == 0)
    print('80/80 一致 DLL: 修正前 %d → 修正後 %d' % (full_o, full_n))
    nnone_o = sum(1 for v in old.values() if v.get('kernel_va_map') and any(x is None for x in v['kernel_va_map'].values()))
    nnone_n = sum(1 for v in R.values() if v.get('kernel_va_map') and any(x is None for x in v['kernel_va_map'].values()))
    print('kernel_va_map に未対応 (None) を含む DLL: 修正前 %d → 修正後 %d' % (nnone_o, nnone_n))
    cs_o = sum(v.get('ncallsites', 0) for v in old.values())
    cs_n = sum(v.get('ncallsites', 0) for v in R.values())
    print('kernel 呼出 site 合計: 修正前 %d → 修正後 %d' % (cs_o, cs_n))
    keys = [k for k in R if k in old and old[k].get('delphi') and old[k].get('init_found')]
    chg = [k for k in keys if (old[k].get('init_va'), old[k].get('nvars'), old[k].get('nimpls')) != (R[k].get('init_va'), R[k].get('nvars'), R[k].get('nimpls'))]
    print('init_va / nvars / nimpls が変わった DLL:', len(chg))
    mism_o = collections.Counter(len(v.get('kernels_mismatch', [])) for v in old.values() if v.get('init_found'))
    mism_n = collections.Counter(len(v.get('kernels_mismatch', [])) for v in R.values() if v.get('init_found'))
    print('mismatch 件数 分布: 修正前', dict(mism_o), '修正後', dict(mism_n))
    out = dict(dlls=len(R), before=dict(zip(map(str, do), do.values())), after=dict(zip(map(str, dn), dn.values())),
               full_80_before=full_o, full_80_after=full_n, dlls_with_unmapped_kernel_before=nnone_o, dlls_with_unmapped_kernel_after=nnone_n,
               callsites_before=cs_o, callsites_after=cs_n, init_changed=len(chg))
    os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, 'results', 'p0c_regress.json'), 'w'), indent=1)
    return 0 if full_n >= full_o and not any(bad for (ok, bad) in dn) else 1


if __name__ == '__main__':
    sys.exit(main())
