#!/usr/bin/env python3
"""win64 PE (Delphi) 全モジュールで ipp 変数表と参照を capstone 分類 (work/win_refs.json)。"""
import json, os, sys, collections
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_x64
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'shared')); from paths import FL_WIN64_DIR
EXT = f'{FL_WIN64_DIR}/extracted'
mods = json.load(open(f'{HERE}/work/win_modules.json'))
def work(f):
    try: return f, scan_x64.analyze(f'{EXT}/{f}', 'pe')
    except Exception as e: return f, {'error': repr(e)}
if __name__ == '__main__':
    with Pool(14) as p: res = dict(p.map(work, mods))
    json.dump(res, open(f'{HERE}/work/win_refs.json', 'w'))
    ok = [v for v in res.values() if v and 'error' not in v]
    print('modules', len(res), 'ok', len(ok), 'err', sum(1 for v in res.values() if v and 'error' in v), collections.Counter(v['entries'] for v in ok))
    tot = collections.Counter(); mm = collections.defaultdict(set); oth = collections.Counter()
    for f, v in res.items():
        if not v or 'error' in v: continue
        for e in v['table']:
            tot[e['name']] += e['call']; oth[e['name']] += e['other'] + e['check']
            if e['call']: mm[e['name']].add(f)
    print('distinct called', sum(1 for c in tot.values() if c), {n: (tot[n], len(mm[n])) for n in tot if tot[n]})
    print('other/check refs', {n: c for n, c in oth.items() if c})
