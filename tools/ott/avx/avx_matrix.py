#!/usr/bin/env python3
"""avx_matrix.py — CAB-135: AVX/FMA 強制 matrix の実行オーケストレーション (crtinit/run_matrix.py 同型)。

  avx_matrix.py MOD.cjs OUT_DIR --scen SCEN.json [--force fma,isa] [--cov COV.json] [--only NAME]...

各 scenario 毎に node avx/avx_wasm.mjs (instance 分離, AVX_FORCE を guest .data に書く) →
native replay は avx/avx_nat.py (同一 flag 書き込み) 。--cov で native insn coverage も取得。
"""
import sys
import os
import json
import subprocess
import argparse
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
NODE = os.environ.get('NODE') or '/opt/emsdk/node/24.19.0_64bit/bin/node'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mod')
    ap.add_argument('outdir')
    ap.add_argument('--scen', required=True)
    ap.add_argument('--force', default='fma,isa')
    ap.add_argument('--cov', default=None)
    ap.add_argument('--only', action='append', default=[])
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='avxm_', dir='/tmp/opencode' if os.path.isdir('/tmp/opencode') else None)
    scens = json.load(open(a.scen))
    if a.only:
        scens = [s for s in scens if s['name'] in a.only]
        a.scen = os.path.join(tmp, 'scen_sub.json')
        json.dump(scens, open(a.scen, 'w'))
    wasm_results, alog_map, vexcov = {}, {}, {}
    for s in scens:
        outj = os.path.join(tmp, 'w_%s.json' % s['name'])
        env = dict(os.environ, MOD=os.path.abspath(a.mod), SCEN=os.path.abspath(a.scen), NAME=s['name'],
                   OUT=outj, AVX_FORCE=a.force)
        if a.cov:
            env['OTT_VEXCOV'] = '1'
        r = subprocess.run([NODE, os.path.join(HERE, 'avx_wasm.mjs')], env=env, capture_output=True, text=True)
        if r.returncode != 0:
            err = (r.stderr.strip().splitlines() or ['?'])
            meaningful = [l for l in err if '[ott]' in l or 'Error' in l or 'abort' in l.lower()]
            wasm_results[s['name']] = {'ok': False, 'err': (meaningful or err)[-1][:200] if err else '?'}
            print('[avx_matrix] %-16s wasm FAIL %s' % (s['name'], wasm_results[s['name']]['err'][:90]))
            continue
        d = json.load(open(outj))
        d['result']['ok'] = True
        wasm_results[s['name']] = d['result']
        alog_map[s['name']] = d['alog']
        if a.cov and 'vexcov' in d['result']:
            vexcov[s['name']] = d['result']['vexcov']
        print('[avx_matrix] %-16s wasm ok calls=%d alog=%d' % (s['name'], len(d['result']['calls']), len(d['alog'])))
    json.dump(wasm_results, open(os.path.join(a.outdir, 'wasm_result.json'), 'w'))
    json.dump(alog_map, open(os.path.join(a.outdir, 'alog_map.json'), 'w'))
    if a.cov:
        json.dump(vexcov, open(os.path.join(a.outdir, 'wasm_vexcov.json'), 'w'))

    natj = os.path.join(a.outdir, 'nat_result.json')
    cmd = [sys.executable, '-u', os.path.join(HERE, 'avx_nat.py'), '--out', natj,
           '--scen', os.path.abspath(a.scen), '--replay', os.path.join(a.outdir, 'alog_map.json')]
    if a.cov:
        cmd += ['--cov', a.cov]
    env = dict(os.environ, AVX_FORCE=a.force)
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else '[avx_matrix] native run (no output)')
    if r.returncode != 0:
        print(r.stderr[-500:])
    print('[avx_matrix] wrote %s' % a.outdir)


if __name__ == '__main__':
    main()
