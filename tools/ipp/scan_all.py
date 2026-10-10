#!/usr/bin/env python3
"""143 モジュールの x86_64 / arm64 両スライスで ipp 参照を分類し work/ipp_refs.json に保存。"""
import json, os, sys, collections
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_x64, scan_arm64
HERE = os.path.dirname(os.path.abspath(__file__))
idx = json.load(open(f'{HERE}/work/mac/index.json'))
jobs = [(int(i), rec['path'], rec.get('x86_64'), rec.get('arm64')) for i, rec in idx.items()]
def work(j):
    i, p, xs, as_ = j
    out = {'path': p}
    try: out['x64'] = scan_x64.analyze(xs) if xs else None
    except Exception as e: out['x64'] = {'error': repr(e)}
    try: out['a64'] = scan_arm64.analyze(as_) if as_ else None
    except Exception as e: out['a64'] = {'error': repr(e)}
    return i, out
if __name__ == '__main__':
    with Pool(14) as pl: res = dict(pl.map(work, jobs, chunksize=1))
    json.dump(res, open(f'{HERE}/work/ipp_refs.json', 'w'))
    for arch in ('x64', 'a64'):
        ok = [v for v in res.values() if v[arch] and 'error' not in v[arch]]
        print(arch, 'modules ok', len(ok), 'errors', sum(1 for v in res.values() if v[arch] and 'error' in v[arch]),
              'entries hist', collections.Counter(v[arch]['entries'] for v in ok))
