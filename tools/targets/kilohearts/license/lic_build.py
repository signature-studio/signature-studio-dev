#!/usr/bin/env python3
"""lic_build.py — KH-9 ライセンス stub の build driver (snapins/lift/build.py の Path B 系を license/ 用に調整)。

  lic_build.py --module A|B              ライセンス stub モジュール (A: stub 本体 / B: 対照) を lift→stub pass→emcc
  lic_build.py --dsp <name> [--tag T] [--no-stub]
                                         snapin (<name>: matrix/gain/haas/clipper/gate/quickeq) を既定パイプライン
                                         (RetDec stage-0 + kh_lower) で lift し、--no-stub 無しなら lic_stub.py を
                                         挟んだ上で emcc。ctx-fuzz (実機機械語との bit 突合) も実施する。

出力は license/work/<module|name>/<tag>/ (gitignore)。snapins/ 側には一切書き込まない (参照実行のみ許可)。
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
ROOT = HERE                                   # license/
KILO = os.path.dirname(ROOT)                  # tools/targets/kilohearts
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
CORE = os.path.join(KILO, 'work', 'winpkg', 'HeartCore.core_64')
EMSDK = '/opt/emsdk/emsdk_env.sh'
CFG = json.load(open(os.path.join(ROOT, 'lic_config.json')))
RSS_CAP = os.path.abspath(os.path.join(ROOT, '..', '..', '..', 'flelift', 'boot', 'rss_cap.py'))


def sh(cmd, log=None, check=True):
    t = time.time()
    # KH_EM_CACHE: 読取専用な emscripten cache の差替え用 ([EMSDK] の cache が読めない Actions runner 向け)。
    # emsdk_env.sh が EM_CACHE を消すため source 後に再設定する。値は shell に埋め込まず環境変数として展開させる
    cmd = 'source %s >/dev/null 2>&1; ' % EMSDK + ('export EM_CACHE="$KH_EM_CACHE"; ' if os.environ.get('KH_EM_CACHE') else '') + cmd
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, executable='/bin/bash')
    if log:
        open(log, 'w').write(r.stdout + r.stderr)
    if check and r.returncode:
        print(r.stdout[-2000:], r.stderr[-3000:])
        raise SystemExit('FAILED: ' + cmd[:200])
    return r, time.time() - t


def emcc_capped(name, cmd, log, rss_log):
    """emcc を rss_cap.py 経由で走らせ、ピーク RSS (MB) を返す。上限は KH_EMCC_RSS_CAP_MB (既定 11000)。
    超過時は emcc の子孫 PID だけ kill され、非 0 で終わる"""
    cap = int(os.environ.get('KH_EMCC_RSS_CAP_MB', '11000'))
    r, dt = sh('python3 %s --cap-mb %d --interval 0.5 --log %s -- %s' % (RSS_CAP, cap, rss_log, cmd), log=log, check=False)
    m = re.search(r'peak_rss=(\d+)MB', r.stderr)
    peak = int(m.group(1)) if m else -1
    if 'KILLED(cap)' in r.stderr:
        print('[build] emcc RSS cap 超過: %s peak=%dMB (cap=%dMB)' % (name, peak, cap))
        raise SystemExit(1)
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-3000:])
        raise SystemExit('FAILED: emcc ' + name)
    return r, dt, peak


def capture_stage0(rstr, dst, base):
    """RetDec --print-after-all の最初のダンプ (stage-0 IR) のみ保存して打ち切る (snapins build.py と同一)"""
    p = subprocess.Popen(['/opt/retdec/bin/retdec-decompiler', CORE, '-o', base + '.c', '--select-ranges', rstr,
                          '--select-decode-only', '--print-after-all', '--timeout', '1800'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors='replace')
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


def fill_missing_stage0(s0, ranges, base):
    """RetDec は範囲の終端が次の関数の先頭と一致する (隣接する) と、後ろの関数を定義しないことがある
    (KH-86: 0x180f88468-0x180f88488 の直後の 0x180f88488 が欠落)。欠落した関数だけを単独範囲で再取得し、
    stage-0 に定義と未宣言の declare を追記する。戻り値: 追記した関数の VA (hex) リスト"""
    txt = open(s0).read()
    have = set(re.findall(r'^define \S+ @function_([0-9a-f]+)\(', txt, re.M))
    miss = [r for r in ranges if r.split('-')[0][2:] not in have]
    added = []
    for r in miss:
        va = r.split('-')[0][2:]
        cap = base + '.%s.solo.ll' % va
        capture_stage0(r, cap, base + '.%s' % va)
        body, grab, decls = [], False, []
        for l in open(cap).read().split('\n'):
            if l.startswith('define ') and ('@function_%s(' % va) in l:
                grab = True
            if grab:
                body.append(l)
                if l == '}':
                    break
            m = re.match(r'^declare \S+ @([\w.\-]+)\(', l)
            if m:
                decls.append(l)
        assert body, 'solo capture に関数 %s が無い' % va
        txt = txt.rstrip('\n') + '\n' + '\n'.join(body) + '\n'
        for d in decls:
            name = re.match(r'^declare \S+ @([\w.\-]+)\(', d).group(1)
            if not re.search(r'^declare \S+ @%s\(' % re.escape(name), txt, re.M) and not re.search(r'^define \S+ @%s\(' % re.escape(name), txt, re.M):
                txt += d + '\n'
        added.append(va)
    if added:
        open(s0, 'w').write(txt)
    return added


def decl_named_imports(txt):
    """呼ばれているが宣言の無い Win32/CRT named import (`call i64 @Name()`) に declare を補う (#710)。
    定義は gen_stubs_sigs.py の IMP_SHIM / fail-fast 節が stubs.c 側に出す。宣言が無いと emcc が未定義参照で落ちる。"""
    defined = set(re.findall(r'^(?:define|declare)\b[^@\n]*@([\w.\-]+)\(', txt, re.M))
    skip = ('function_', 'kh_', 'llvm', '__asm', 'global_var')
    add = set()
    for m in re.finditer(r'\bcall\b([^@\n]*)@([A-Za-z]\w*)\(([^\n]*?)\)', txt):
        ty, name, args = m.group(1).strip(), m.group(2), m.group(3).strip()
        if name in defined or name.startswith(skip):
            continue
        if ty != 'i64' or args:
            sys.exit('decl_named_imports: 未対応の named import 呼出 @%s (戻り %r / 引数 %r)。declare i64 @%s() の補完は引数なし・戻り i64 のみ' % (name, ty, args, name))
        add.add(name)
    add = ['declare i64 @%s()' % n for n in sorted(add)]
    if not add:
        return txt
    if not re.search(r'(?m)^declare void @llvm\.trap\(\)$', txt):
        sys.exit('decl_named_imports: 挿入位置 `declare void @llvm.trap()` が無い (補完対象: %s)' % ', '.join(add))
    return re.sub(r'(?m)^declare void @llvm\.trap\(\)$', lambda m: '\n'.join(add) + '\n' + m.group(0), txt, count=1)


def make_flag_setters(globals_c, flags):
    """flags: {"182989344": "kh_set_flag_a"}。global_var_<va> を書換可能にし、u32 setter を追記する (経路フラグの切替用・KH-98)"""
    txt = open(globals_c).read()
    names = []
    for va, fn in flags.items():
        pat = 'const unsigned char global_var_%s[' % va
        assert pat in txt, 'flag global not found: ' + va
        txt = txt.replace(pat, 'unsigned char global_var_%s[' % va)
        txt += '\nvoid %s(unsigned v) { *(volatile unsigned*)global_var_%s = v; }\n' % (fn, va)
        names.append(fn)
    open(globals_c, 'w').write(txt)
    return names


def build(vas, tag_dir, tag, apply_stub, module=None, abi=None, jt=None, shims=None, emcc_extra_exports=None, raw_va=False, volatile_ret=False, emcc_opt='-O1', rdata_str=False, rdata_raw_allow='', flag_setters=None):
    """lift → (stub pass) → normalize → helper 生成 → emcc。stat dict を返す"""
    W = tag_dir
    os.makedirs(W, exist_ok=True)
    R = os.path.join(os.path.dirname(W), 'retdec0')
    os.makedirs(R, exist_ok=True)
    ranges = []
    from fnscan import extent
    for va in sorted(vas):
        end = extent(va)[0]
        ranges.append('0x%x-0x%x' % (va, end))
    rstr = ','.join(ranges)
    key = hashlib.sha1(rstr.encode()).hexdigest()[:10]
    s0 = os.path.join(R, '%s.%s.stage0.ll' % (tag, key))
    stat = {'ranges': ranges, 'tag': tag}
    P = lambda f: os.path.join(W, f)
    if not os.path.exists(s0):
        t = time.time()
        capture_stage0(rstr, s0, os.path.join(R, 'x'))
        stat['retdec_sec'] = round(time.time() - t, 1)
    else:
        stat['retdec_sec'] = 0
    stat['stage0_filled'] = fill_missing_stage0(s0, ranges, os.path.join(R, 'fill.' + key))
    abi = json.dumps(abi or {})
    jts = json.dumps(jt or {})
    r, _ = sh("python3 %s/lift/kh_lower.py %s %s --core %s --lift %s --abi '%s' --jt '%s'%s%s" % (
        ROOT, s0, P('lowered.ll'), CORE, ','.join('%x' % v for v in sorted(vas)), abi, jts,
        ' --raw-va' if raw_va else '', ' --volatile-ret' if volatile_ret else '') + (' --rdata-str' if rdata_str else '') + (" --rdata-raw-allow '%s'" % rdata_raw_allow if rdata_raw_allow else ''))
    stat['passes'] = r.stdout.strip()
    sh('python3 %s/lift/ir_normalize.py %s %s' % (ROOT, P('lowered.ll'), P('n1.ll')))
    if apply_stub:
        r, _ = sh('python3 %s/lic_stub.py %s %s --config %s/lic_config.json %s --report %s' % (
            ROOT, P('n1.ll'), P('n1s.ll'), ROOT, ('--module ' + module) if module else '', P('licstub.json')))
        stat['lic_stub'] = r.stdout.strip()
        src = P('n1s.ll')
    else:
        src = P('n1.ll')
    # declare 重複除去 (snapins build.py と同一)
    lines_in = open(src).read().split('\n')
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
    txt = decl_named_imports(txt)
    open(P('final.ll'), 'w').write(txt)
    r, _ = sh('python3 %s/lift/gen_simd.py %s %s --report %s' % (ROOT, P('final.ll'), P('simd.c'), P('simd.json')))
    stat['simd'] = r.stdout.strip()
    r, _ = sh('python3 %s/lift/gen_globals.py %s %s %s --window 64' % (ROOT, P('final.ll'), CORE, P('globals.c')))
    stat['globals'] = r.stdout.strip()
    setters = make_flag_setters(P('globals.c'), flag_setters) if flag_setters else []
    json.dump(shims or {}, open(P('shims.json'), 'w'))
    r, _ = sh('python3 %s/lift/gen_stubs_sigs.py %s %s %s %s' % (ROOT, P('final.ll'), P('stubs.c'), P('sigs.json'), P('shims.json')))
    stat['stubs'] = r.stdout.strip()
    sig = json.load(open(P('sigs.json')))
    exports = ['_function_' + k for k in sig] + ['_malloc', '_free', '_kh_stack_ptr'] + ['_' + s for s in setters]
    if emcc_extra_exports:
        exports += emcc_extra_exports
    extra_ll = (' ' + P('simd.c.i256.ll')) if os.path.exists(P('simd.c.i256.ll')) else ''
    r, dt, peak = emcc_capped(tag, 'emcc -w %s -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=96MB -sENVIRONMENT=node -sMODULARIZE=1 '
                              '-sEXPORT_NAME=KhLic -sERROR_ON_UNDEFINED_SYMBOLS=0 --no-entry -sEXPORTED_FUNCTIONS=%s '
                              '-sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAP32,HEAP64 -Wl,--no-gc-sections -I%s/lift %s %s %s %s%s%s -o %s' % (
                                  emcc_opt, ','.join(exports), ROOT, P('final.ll'), P('simd.c'), P('globals.c'), P('stubs.c'),
                                  (' ' + P('lowered.ll.icall.c')) if os.path.exists(P('lowered.ll.icall.c')) else '', extra_ll, P('mod.cjs')),
                              P('emcc.log'), P('emcc_rss.log'))
    stat['icall'] = os.path.exists(P('lowered.ll.icall.c'))
    stat['emcc_sec'] = round(dt, 1)
    stat['emcc_peak_rss_mb'] = peak
    stat['wasm_bytes'] = os.path.getsize(P('mod.wasm'))
    stat['wasm_sha256'] = hashlib.sha256(open(P('mod.wasm'), 'rb').read()).hexdigest()
    r, _ = sh('node -e "const m=new WebAssembly.Module(require(\'fs\').readFileSync(\'%s\'));console.log(JSON.stringify(WebAssembly.Module.imports(m).filter(i=>i.kind===\'function\').map(i=>i.module+\'.\'+i.name)))"' % P('mod.wasm'))
    imps = json.loads(r.stdout)
    stat['undefined_imports'] = [i for i in imps if not re.match(r'^(env\.(_?abort_js|_?emscripten_\w+|emscripten_\w+|__\w+)|wasi_\w+\.\w+)$', i)]
    json.dump(stat, open(P('stat.json'), 'w'), indent=1)
    return stat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--module', choices=['A', 'B', 'E', 'F', 'K'])
    ap.add_argument('--dsp', default=None, help='snapin name (matrix/gain/haas/clipper/gate/quickeq)')
    ap.add_argument('--tag', default='lic')
    ap.add_argument('--no-stub', action='store_true')
    ap.add_argument('--no-compare', action='store_true')
    ap.add_argument('--trials', type=int, default=200)
    ap.add_argument('--seed', type=int, default=1)
    a = ap.parse_args()

    if a.module:
        mod = CFG['modules'][a.module]
        vas = {int(v, 16) for v in mod['lift']}
        stat = build(vas, os.path.join(ROOT, 'work', 'lic' + a.module), 'lic' + a.module,
                     apply_stub=True, module=a.module, abi=mod.get('abi'),
                     shims=mod.get('shims'), raw_va=mod.get('raw_va', False),
                     volatile_ret=mod.get('volatile_ret', False),
                     emcc_opt=mod.get('emcc_opt', '-O1'),
                     rdata_str=mod.get('rdata_str', False),
                     rdata_raw_allow=mod.get('rdata_raw_allow', ''),
                     flag_setters=mod.get('flag_setters'))
        print(json.dumps({k: v for k, v in stat.items() if k != 'ranges'}, ensure_ascii=False))
        return

    # --dsp <name>: snapins 既定パイプライン + (既定では) lic_stub pass
    cfg = json.load(open(os.path.join(ROOT, 'snapins_head.json')))[a.dsp]
    vas = {int(v, 16) for v in cfg['lift'].values()} | {int(v, 16) for v in cfg.get('extra', [])}
    stat = build(vas, os.path.join(ROOT, 'work', a.dsp, a.tag), a.tag, apply_stub=not a.no_stub,
                 abi=cfg.get('abi'), jt=cfg.get('jumptables'), shims=cfg.get('shims'))
    # ctx-fuzz: 実機機械語との bit 突合 (harness は license/harness の HEAD コピー)
    if not a.no_compare:
        vecdir = os.path.join(ROOT, 'work', a.dsp)
        vec = os.path.join(vecdir, 'vec_%d_%d_v3.bin' % (a.trials, a.seed))
        nat = os.path.join(ROOT, 'work', 'native_ref')
        if not os.path.exists(nat):
            sh('cc -O1 -Wall -o %s %s/harness/native_ref.c %s/harness/scenarios.c -I%s/harness' % (nat, ROOT, ROOT, ROOT))
        if not os.path.exists(vec):
            sh('%s %s %s %d %d %s.tmp && mv %s.tmp %s' % (nat, CORE, cfg['scenario'], a.trials, a.seed, vec, vec, vec))
        r, _ = sh('timeout 120 node %s/harness/compare.mjs %s %s %s --json %s' % (
            ROOT, vec, os.path.join(ROOT, 'work', a.dsp, a.tag, 'mod.cjs'),
            os.path.join(ROOT, 'work', a.dsp, a.tag, 'sigs.json'),
            os.path.join(ROOT, 'work', a.dsp, a.tag, 'compare.json')), check=False,
            log=os.path.join(ROOT, 'work', a.dsp, a.tag, 'compare.log'))
        stat['compare'] = r.stdout.strip().split('\n')[-1]
        cj = json.load(open(os.path.join(ROOT, 'work', a.dsp, a.tag, 'compare.json'))) if os.path.exists(os.path.join(ROOT, 'work', a.dsp, a.tag, 'compare.json')) else {}
        stat['trials_ok'], stat['trials'] = cj.get('trialsOk'), cj.get('trials')
        stat['calls_ok'], stat['calls'] = cj.get('callsOk'), cj.get('calls')
        stat['fails'] = cj.get('fails', [])[:3]
    # ライセンス関数の存在数 (DSP closure がライセンス層を通らないことの lift IR 上の証拠)
    ll = open(os.path.join(ROOT, 'work', a.dsp, a.tag, 'final.ll')).read()
    lic_vas = [s['va'] for s in CFG['stubs']] + [k['va'] for k in CFG['keep_real']]
    stat['lic_va_in_ir'] = {v: len(re.findall(r'@function_%s\b|@kh_%s\b' % (v, v), ll)) for v in lic_vas}
    stat['lic_va_hits_total'] = sum(stat['lic_va_in_ir'].values())
    json.dump(stat, open(os.path.join(ROOT, 'work', a.dsp, a.tag, 'stat.json'), 'w'), indent=1)
    print(json.dumps({k: v for k, v in stat.items() if k not in ('ranges', 'fails')}, ensure_ascii=False))
    for f in stat.get('fails', []):
        print('  FAIL', f)


if __name__ == '__main__':
    main()
