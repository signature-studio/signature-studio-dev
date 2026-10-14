#!/usr/bin/env python3
"""apiset_readback.py — ICALL-76 (REPORT §10): api-set 表 (34 entry) の読み戻し。

各 scenario を crt_wasm.mjs (APISET_READBACK=1) で 1 本ずつ実行し、表の値を
  apiset_init  = ott_crt_init_tables 直後 (34 entry 全てが enc(NULL)=cookie か)
  apiset_after = scenario 実行後
で読む。init から変わった index は、その scenario の中で解決時の書き戻しが起きた entry。
書き戻しが無い entry について言えるのは「解決時の書き戻しが無かった」まで (解決が NULL を返すと値は変わらない)。

使い方 (crt_e2e.sh の [2/6] までを済ませた tree で実行。tools/ott/work/crtlift/ottl_crt.cjs・
scen_crt.json と tools/ott/work/entrylift/scen.json が要る):
  python3 tools/ott/crtinit/apiset_readback.py [--out tools/ott/work/crtlift/apiset_readback.json]
"""
import argparse
import json
import os
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OTT = os.path.dirname(HERE)
WORK = os.path.join(OTT, 'work')
NODE = os.environ.get('NODE', '/opt/emsdk/node/24.19.0_64bit/bin/node')
MOD = os.path.join(WORK, 'crtlift', 'ottl_crt.cjs')
SCEN_FILES = [os.path.join(WORK, 'crtlift', 'scen_crt.json'),
              os.path.join(WORK, 'entrylift', 'scen.json')]
APISET_N = 34
COOKIE_HEX = '%016x' % 0x2b992ddfa232   # __security_cookie 静的既定 (REPORT §2.1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(WORK, 'crtlift', 'apiset_readback.json'))
    args = ap.parse_args()
    entries = []
    for f in SCEN_FILES:
        with open(f) as fh:
            entries += [(os.path.relpath(f, OTT), e) for e in json.load(fh)]
    runs, fails = [], []
    with tempfile.TemporaryDirectory() as tmp:
        one, out = os.path.join(tmp, 'one.json'), os.path.join(tmp, 'out.json')
        for k, (src, entry) in enumerate(entries):
            name = entry.get('name')
            with open(one, 'w') as fh:
                json.dump([entry], fh)     # NAME 未指定 = all[0] (同名 scenario の重複も 1 本ずつ実行)
            env = {key: v for key, v in os.environ.items() if key != 'NAME'}
            env.update(MOD=MOD, SCEN=one, OUT=out, APISET_READBACK='1')
            r = subprocess.run([NODE, os.path.join(HERE, 'crt_wasm.mjs')], env=env,
                               capture_output=True, text=True, timeout=300)
            if r.returncode != 0 or not os.path.exists(out):
                fails.append({'k': k, 'src': src, 'name': name, 'rc': r.returncode, 'err': r.stderr[-300:]})
                continue
            with open(out) as fh:
                res = json.load(fh)['result']
            init, after = res['apiset_init'], res['apiset_after']
            runs.append({'k': k, 'src': src, 'name': name,
                         'init_cookie': all(v == COOKIE_HEX for v in init) and len(init) == APISET_N,
                         'changed': [i for i in range(APISET_N) if init[i] != after[i]]})
    count = {}
    for run in runs:
        for i in run['changed']:
            count[i] = count.get(i, 0) + 1
    summary = {
        'scenario_runs': len(entries), 'ok_runs': len(runs), 'fail_runs': fails,
        'init_all_cookie_runs': sum(1 for run in runs if run['init_cookie']),
        'changed_index_union': sorted(count),
        'changed_index_run_count': {str(i): count[i] for i in sorted(count)},
        'never_changed_index': [i for i in range(APISET_N) if i not in count],
        'runs': runs,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w') as fh:
        json.dump(summary, fh, indent=1)
    print('scenario run: %d (ok %d / fail %d)' % (len(entries), len(runs), len(fails)))
    print('init 直後に 34 entry 全てが enc(NULL)=cookie (%s): %d / %d run' %
          (COOKIE_HEX, summary['init_all_cookie_runs'], len(runs)))
    print('実行後に値が変わった index: %s' % summary['changed_index_union'])
    print('  index ごとの変化 run 数: %s' % summary['changed_index_run_count'])
    print('一度も変わらなかった index: %s' % summary['never_changed_index'])
    ok = not fails and summary['init_all_cookie_runs'] == len(runs) == len(entries)
    print('readback: %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
