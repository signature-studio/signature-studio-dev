#!/usr/bin/env python3
"""run_matrix.py — entry 比較 matrix の実行オーケストレーション。

  run_matrix.py MOD.cjs OUT_DIR [--quick]

1) scenario 毎に node entry_wasm.mjs を起動 (module instance / heap を scenario 間で共有しない)
2) 各 scenario の alog (HeapAlloc 記録) を native 側へ replay させ同一アドレスで再現
3) entry_nat.py --replay で native 実機械語側を実行 → cmp_entries.py で判定
出力: OUT_DIR/wasm_result.json, OUT_DIR/nat_result.json, OUT_DIR/alog_map.json
"""
import sys, os, json, subprocess, argparse, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
NODE = os.environ.get('NODE') or '/opt/emsdk/node/24.19.0_64bit/bin/node'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mod')
    ap.add_argument('outdir')
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--scen', default=os.path.join(HERE, '..', 'work', 'entrylift', 'scen.json'))
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='entrym_', dir='/tmp/opencode' if os.path.isdir('/tmp/opencode') else None)
    scens = json.load(open(a.scen))
    if a.quick:
        keep = {'op0', 'op12', 'op45', 'op58', 'getp3', 'getp_range', 'chunk_rt', 'full_cycle', 'virt_sr', 'close'}
        scens = [s for s in scens if s['name'] in keep]
        a.scen = os.path.join(tmp, 'scen_quick.json')
        json.dump(scens, open(a.scen, 'w'))
    wasm_results, alog_map = {}, {}
    for s in scens:
        outj = os.path.join(tmp, 'w_%s.json' % s['name'])
        env = dict(os.environ, MOD=os.path.abspath(a.mod), SCEN=os.path.abspath(a.scen), NAME=s['name'], OUT=outj)
        r = subprocess.run([NODE, os.path.join(HERE, 'entry_wasm.mjs')], env=env, capture_output=True, text=True)
        if r.returncode != 0:
            err = (r.stderr.strip().splitlines() or ['?'])
            # fail-fast (ott_unsup / ott_unlifted) の最後の意味行を拾う
            meaningful = [l for l in err if '[ott]' in l or 'Error' in l or 'abort' in l.lower()]
            wasm_results[s['name']] = {'ok': False, 'err': (meaningful or err)[-1][:200] if err else '?'}
            print('[run_matrix] %-16s wasm FAIL %s' % (s['name'], wasm_results[s['name']]['err'][:90]))
            continue
        d = json.load(open(outj))
        d['result']['ok'] = True
        wasm_results[s['name']] = d['result']
        alog_map[s['name']] = d['alog']
        print('[run_matrix] %-16s wasm ok calls=%d alog=%d' % (s['name'], len(d['result']['calls']), len(d['alog'])))
    json.dump(wasm_results, open(os.path.join(a.outdir, 'wasm_result.json'), 'w'))
    json.dump(alog_map, open(os.path.join(a.outdir, 'alog_map.json'), 'w'))

    natj = os.path.join(a.outdir, 'nat_result.json')
    cmd = [sys.executable, '-u', os.path.join(HERE, 'entry_nat.py'), '--out', natj,
           '--scen', os.path.abspath(a.scen), '--replay', os.path.join(a.outdir, 'alog_map.json')]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else '[run_matrix] native run (no output)')
    if r.returncode != 0:
        print(r.stderr[-500:])
    print('[run_matrix] wrote %s' % a.outdir)


if __name__ == '__main__':
    main()
