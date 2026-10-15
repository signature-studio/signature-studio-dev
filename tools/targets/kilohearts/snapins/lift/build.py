#!/usr/bin/env python3
"""build.py — 1 snap-in の lift → wasm → ctx-fuzz 差分を一括実行する。

  build.py <name> [--skip flags,f7,...] [--tag T] [--trials N] [--seed S] [--no-compare]

  <name> は snapins.json のキー。work/<name>/ に成果物 (RetDec 出力は work/<name>/retdec/ にキャッシュ)。
  --skip は kh_passes の ablation (外した時の不一致数を測る)。--tag で出力サブdirを分ける (既定 'main')。
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
CORE = os.path.abspath(os.path.join(ROOT, '..', 'work', 'winpkg', 'HeartCore.core_64'))
EMSDK = '/opt/emsdk/emsdk_env.sh'


def sh(cmd, log=None, check=True, env=None):
    t = time.time()
    cmd = 'source %s >/dev/null 2>&1; ' % EMSDK + cmd
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, executable='/bin/bash', env=env)
    if log:
        open(log, 'w').write(r.stdout + r.stderr)
    if check and r.returncode:
        print(r.stdout[-2000:], r.stderr[-3000:])
        raise SystemExit('FAILED: ' + cmd[:200])
    return r, time.time() - t


def capture_stage0(rstr, dst, base):
    """RetDec を --print-after-all で走らせ、最初のダンプ (Input binary to LLVM IR decoding = stage-0 IR) だけ保存して打ち切る"""
    p = subprocess.Popen(['/opt/retdec/bin/retdec-decompiler', CORE, '-o', base + '.c', '--select-ranges', rstr, '--select-decode-only',
                          '--print-after-all', '--timeout', '1800'], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors='replace')
    cap, on = [], False
    for line in p.stderr:
        if line.startswith('*** IR Dump After '):
            if on:
                break
            on = 'Input binary to LLVM IR decoding' in line
            continue
        if on:
            cap.append(line)
    p.kill()
    p.wait()
    os.system('rm -f %s.dsm' % base)
    assert cap, 'stage-0 dump not found'
    open(dst, 'w').write(''.join(cap))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('name')
    ap.add_argument('--skip', default='')
    ap.add_argument('--tag', default='main')
    ap.add_argument('--trials', type=int, default=200)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--no-compare', action='store_true')
    ap.add_argument('--opt', default='-O1')
    ap.add_argument('--path', default='a', choices=['a', 's0'], help='a: RetDec 最終IR+kh_passes / s0: RetDec stage-0 IR + kh_lower')
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(ROOT, 'snapins.json')))[a.name]
    W = os.path.join(ROOT, 'work', a.name)
    D = os.path.join(W, a.tag)
    os.makedirs(os.path.join(W, 'retdec'), exist_ok=True)
    os.makedirs(D, exist_ok=True)
    from fnscan import extent
    vas = sorted({int(v, 16) for v in cfg['lift'].values()} | {int(v, 16) for v in cfg.get('extra', [])})
    ranges = []
    for va in vas:
        e = cfg.get('ends', {}).get('%x' % va)
        end = int(e, 16) if e else extent(va)[0]
        ranges.append('0x%x-0x%x' % (va, end))
    rstr = ','.join(ranges)
    key = hashlib.sha1(rstr.encode()).hexdigest()[:10]
    stat = {'name': a.name, 'ranges': ranges, 'skip': a.skip, 'path': a.path}
    P = lambda f: os.path.join(D, f)
    if a.path == 'a':
        drc = os.path.join(W, 'retdec', '%s.%s.drc.ll' % (a.name, key))
        if not os.path.exists(drc):
            base = os.path.join(W, 'retdec', '%s.%s.drc.c' % (a.name, key))
            r, dt = sh('/opt/retdec/bin/retdec-decompiler %s -o %s --select-ranges %s --select-decode-only --timeout 1800' % (CORE, base, rstr),
                       log=os.path.join(W, 'retdec', 'retdec.log'))
            os.system('rm -f %s' % base.replace('.c', '.dsm'))
            stat['retdec_sec'] = round(dt, 1)
            assert os.path.exists(drc), 'retdec produced no .ll'
        else:
            stat['retdec_sec'] = 0
        skip = '--skip ' + a.skip if a.skip else ''
        r, _ = sh('python3 %s/kh_passes.py %s %s --core %s %s --report %s' % (HERE, drc, P('fix.ll'), CORE, skip, P('passes.json')))
        stat['passes'] = r.stdout.strip()
        sh('python3 %s/ir_normalize.py %s %s' % (HERE, P('fix.ll'), P('n0.ll')))
        sh('python3 %s/ir5_patch.py %s %s --report %s' % (HERE, P('n0.ll'), P('n1.ll'), P('ir5.json')), log=P('ir5.log'))
        win = ''
        lines_in = open(P('n1.ll')).read().split('\n')
    else:
        s0 = os.path.join(W, 'retdec0', '%s.stage0.ll' % key)
        os.makedirs(os.path.join(W, 'retdec0'), exist_ok=True)
        if not os.path.exists(s0):
            t = time.time()
            capture_stage0(rstr, s0, os.path.join(W, 'retdec0', 'x'))
            stat['retdec_sec'] = round(time.time() - t, 1)
        else:
            stat['retdec_sec'] = 0
        abi = json.dumps(cfg.get('abi', {}))
        jts = json.dumps(cfg.get('jumptables', {}))
        r, _ = sh("python3 %s/kh_lower.py %s %s --core %s --lift %s --abi '%s' --jt '%s' %s" % (
            HERE, s0, P('lowered.ll'), CORE, ','.join('%x' % v for v in vas), abi, jts, ('--skip ' + a.skip) if a.skip else ''))
        stat['passes'] = r.stdout.strip()
        sh('python3 %s/ir_normalize.py %s %s' % (HERE, P('lowered.ll'), P('n1.ll')))
        # rdata 窓幅: 既定 64B。テーブルを base+offset (可変 index) で読む関数 (k_dfdb0 の 2/π 表は +164B,
        # log10f の 2^(k/256) 表は +1KB) がある snap-in は snapins.json の rdata_window で拡張する (D14 修復)。
        # KH-6: kh_lower [rdataest] の推定 map (rdata_window_map) を snapins.json の "rdata_est": true の
        # エントリのみ使う (per-VA 窓)。明示 rdata_window があれば従来どおり全局共通窓を優先。
        # 未指定エントリ (既存 10 本) は意図的に従来の --window 64 相当に固定する (RESULT baseline 不変のため)。
        ljson = json.load(open(P('lowered.ll.json')))
        if 'rdata_window' in cfg:
            win = '--window %d' % cfg['rdata_window']
        elif cfg.get('rdata_est') and ljson.get('rdata_window_map'):
            mp = P('rdatamap.json')
            json.dump(ljson['rdata_window_map'], open(mp, 'w'))
            win = '--window-map %s' % mp
        else:
            win = ''
        stat['rdata_window_map'] = ljson.get('rdata_window_map', {})
        lines_in = open(P('n1.ll')).read().split('\n')
    # declare 重複除去
    seen, outl = set(), []
    for l in lines_in:
        m = re.match(r'^declare \S+ @([\w.\-]+)\(', l)
        if m:
            if m.group(1) in seen:
                continue
            seen.add(m.group(1))
        outl.append(l)
    txt = '\n'.join(outl)
    for m in re.finditer(r'^declare \S+ @([\w.\-]+)\(.*$', txt, re.M):
        nm = m.group(1)
        if len(re.findall(r'@' + re.escape(nm) + r'(?![\w.\-])', txt)) == 1:
            txt = txt.replace(m.group(0) + '\n', '')
    open(P('final.ll'), 'w').write(txt)
    # 3) helper / globals / stubs / sigs
    r, _ = sh('python3 %s/gen_simd.py %s %s --report %s' % (HERE, P('final.ll'), P('simd.c'), P('simd.json')))
    stat['simd'] = r.stdout.strip()
    r, _ = sh('python3 %s/gen_globals.py %s %s %s %s' % (HERE, P('final.ll'), CORE, P('globals.c'), win))
    stat['globals'] = r.stdout.strip()
    json.dump(cfg.get('shims', {}), open(P('shims.json'), 'w'))
    r, _ = sh('python3 %s/gen_stubs_sigs.py %s %s %s %s' % (HERE, P('final.ll'), P('stubs.c'), P('sigs.json'), P('shims.json')))
    stat['stubs'] = r.stdout.strip()
    extra_c = [P('lowered.ll.icall.c')] if os.path.exists(P('lowered.ll.icall.c')) else []
    extra_ll = [P('simd.c.i256.ll')] if os.path.exists(P('simd.c.i256.ll')) else []
    sig = json.load(open(P('sigs.json')))
    exports = ','.join(['_function_' + k for k in sig] + ['_malloc', '_free'])
    # 4) emcc
    r, dt = sh('source %s >/dev/null 2>&1; emcc -w %s -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=96MB -sENVIRONMENT=node -sMODULARIZE=1 '
               '-sEXPORT_NAME=KhSnap -sERROR_ON_UNDEFINED_SYMBOLS=0 --no-entry -sEXPORTED_FUNCTIONS=%s -sEXPORTED_RUNTIME_METHODS=HEAPU8 '
               '-Wl,--no-gc-sections -I%s %s %s %s %s %s -o %s' % (EMSDK, a.opt, exports, HERE, P('final.ll'), P('simd.c'), P('globals.c'), P('stubs.c'), ' '.join(extra_c + extra_ll), P('mod.cjs')),
               log=P('emcc.log'))
    stat['emcc_sec'] = round(dt, 1)
    stat['wasm_bytes'] = os.path.getsize(P('mod.wasm'))
    # undefined imports
    r, _ = sh('node -e "const m=new WebAssembly.Module(require(\'fs\').readFileSync(\'%s\'));console.log(JSON.stringify(WebAssembly.Module.imports(m).filter(i=>i.kind===\'function\').map(i=>i.module+\'.\'+i.name)))"' % P('mod.wasm'))
    imps = json.loads(r.stdout)
    stat['wasm_imports'] = imps
    stat['undefined_imports'] = [i for i in imps if not re.match(r'^(env\.(_?abort_js|_?emscripten_\w+|emscripten_\w+|__\w+)|wasi_\w+\.\w+)$', i)]
    # 5) compare
    if not a.no_compare:
        vec = os.path.join(W, 'vec_%d_%d.bin' % (a.trials, a.seed))
        nat = os.path.join(ROOT, 'work', 'native_ref')
        if not os.path.exists(vec):
            sh('%s %s %s %d %d %s.tmp && mv %s.tmp %s' % (nat, CORE, cfg['scenario'], a.trials, a.seed, vec, vec, vec))
        # CAB-273: tol gate は撤去済み。compare.mjs は常に全バイト strict 一致で判定する。
        r, _ = sh('timeout 180 node %s/harness/compare.mjs %s %s %s --json %s' % (ROOT, vec, P('mod.cjs'), P('sigs.json'), P('compare.json')), check=False,
                  log=P('compare.log'))
        stat['compare'] = r.stdout.strip().split('\n')[-1]
        cj = json.load(open(P('compare.json'))) if os.path.exists(P('compare.json')) else {}
        stat['trials_ok'], stat['trials'] = cj.get('trialsOk'), cj.get('trials')
        stat['calls_ok'], stat['calls'] = cj.get('callsOk'), cj.get('calls')
        stat['fails'] = cj.get('fails', [])[:3]
    json.dump(stat, open(P('stat.json'), 'w'), indent=1)
    print(json.dumps({k: v for k, v in stat.items() if k not in ('ranges', 'wasm_imports', 'fails')}, ensure_ascii=False))
    for f in stat.get('fails', []):
        print('  FAIL', f)


if __name__ == '__main__':
    main()
