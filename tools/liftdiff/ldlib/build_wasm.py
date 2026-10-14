#!/usr/bin/env python3
"""liftdiff wasm ビルド: target JSON の IR を entry 計装し、外部スタブ(応答モデル)と共に wasm 化する。

  python3 ldlib/build_wasm.py targets/m11.json [--force]

出力: work/<target>/{sigs.json, ir_instr.ll, stubs.c, ld_wasm.cjs(+.wasm), build.json}
"""
import json, os, re, subprocess, sys, time, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
REPO = os.path.abspath(os.path.join(ROOT, '..', '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(REPO, 'tools', 'shared'))
from ldlib import irtool
import paths as shared_paths


def expand_vars(s):
    # target JSON の ${VAR} を展開 (環境変数優先、未設定は tools/shared/paths.py の既定値)
    return re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1)) or shared_paths.ALL.get(m.group(1)) or m.group(0), s)


def load_target(path):
    t = json.load(open(path))
    for k in ('pe', 'ir', 'image'):
        if isinstance(t.get(k), str):
            t[k] = expand_vars(t[k])
    t['_path'] = os.path.abspath(path)
    for k in ('pe', 'ir', 'image'):
        if t.get(k) and not os.path.isabs(t[k]):
            t[k] = os.path.join(REPO, t[k])
    t['work'] = os.path.join(ROOT, 'work', t['name'])
    return t


def sh(cmd, **kw):
    print('[build] $', cmd if isinstance(cmd, str) else ' '.join(cmd), flush=True)
    r = subprocess.run(cmd, shell=isinstance(cmd, str), **kw)
    if r.returncode:
        raise SystemExit('command failed (%d): %s' % (r.returncode, cmd))


def newer(a, b):
    return not os.path.exists(b) or os.path.getmtime(a) > os.path.getmtime(b)


def build(t, force=False):
    if t.get('clift'):
        from ldlib import clift
        return clift.build(t, force)
    W = t['work']
    os.makedirs(W + '/obj', exist_ok=True)
    os.makedirs(W + '/tmp', exist_ok=True)
    ir = t['ir']
    sigs_p = W + '/sigs.json'
    if force or newer(ir, sigs_p):
        sigs = irtool.parse_sigs(ir, t.get('fn_prefix', 'function_'))
        json.dump(sigs, open(sigs_p, 'w'))
        print('[build] sigs: %d (defined %d)' % (len(sigs), sum(1 for s in sigs.values() if s['defined'])))
    sigs = json.load(open(sigs_p))
    defined = {k for k, v in sigs.items() if v['defined']}
    ir2 = W + '/ir_instr.ll'
    if force or newer(ir, ir2):
        t0 = time.time()
        n = irtool.instrument(ir, ir2, t.get('fn_prefix', 'function_'), blocks=bool(t.get('block_trace')))
        print('[build] instrumented %d functions (%.1fs)' % (n, time.time() - t0))
    extra_objs = []
    extra_defined = set()
    c_sigs = {}
    env_sh = 'source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; export TMPDIR=%s/tmp; ' % W
    for src in t.get('extra_sources', []):
        srcp = src if os.path.isabs(src) else os.path.join(REPO, src)
        obj = W + '/obj/x_' + os.path.basename(srcp) + '.o'
        flags = ' '.join('-I' + os.path.join(os.path.dirname(srcp), d) for d in ('.', '..', '../..')) + ' ' + ' '.join(t.get('extra_cflags', []))
        if force or newer(srcp, obj):
            sh(env_sh + 'emcc -c %s -o %s -w -Wno-error=int-conversion -Wno-int-conversion -Wno-implicit-function-declaration -O0 -g1 %s' % (srcp, obj, flags), executable='/bin/bash')
        extra_objs.append(obj)
        c_sigs.update(irtool.parse_c_sigs(srcp, t.get('fn_prefix', 'function_')))
        nm = subprocess.run(env_sh + 'llvm-nm --defined-only %s' % obj, shell=True, executable='/bin/bash', capture_output=True, text=True).stdout
        for ln in nm.splitlines():
            f = ln.split()
            if len(f) == 3 and f[1] in 'TtWwDdBbRr':
                extra_defined.add(f[2])
    if c_sigs:
        sigs.update({k: v for k, v in c_sigs.items() if k not in sigs or not sigs[k]['defined']})
        json.dump(sigs, open(sigs_p, 'w'))
        defined = {k for k, v in sigs.items() if v['defined']}
    stubs_c = W + '/stubs.c'
    if force or newer(ir, stubs_c) or newer(os.path.join(ROOT, 'ldlib/irtool.py'), stubs_c):
        # 定義済の全名 (function_* 以外の IR 内 define も含む) を除外
        alldef = set(defined)
        with open(ir, errors='replace') as f:
            for line in f:
                if line.startswith('define '):
                    m = irtool.DEF_RE.match(line.rstrip('\n'))
                    if m:
                        alldef.add(m.group('name'))
        src, names, skipped = irtool.gen_stubs(ir, alldef | extra_defined)
        open(stubs_c, 'w').write(src)
        json.dump({'stubs': names, 'skipped': skipped, 'widths': irtool.gen_stubs.widths}, open(W + '/stubs.json', 'w'))
        print('[build] stubs: %d (skipped %d: %s)' % (len(names), len(skipped), skipped[:5]))
    # simd helper
    objs = []
    simd = t.get('simd')
    simd_c = W + '/simd.c'
    inc = ['-I' + os.path.join(ROOT, 'rt')]
    if simd:
        gen = simd['gen'].replace('{ir}', simd.get('ir', ir) if os.path.isabs(simd.get('ir', ir)) else os.path.join(REPO, simd.get('ir', ir)))
        if force or not os.path.exists(simd_c):
            sh('cd %s && %s > %s 2> %s/simd.log' % (REPO, gen, simd_c, W))
        if os.path.exists(simd_c):
            txt = open(simd_c).read().replace('#include "../', '#include "')
            open(simd_c, 'w').write(txt)
        for d in simd.get('include', []):
            inc.append('-I' + os.path.join(REPO, d))
    env = os.environ.copy()
    CF = '-w -Wno-implicit-function-declaration -O0 -g1 -fno-delete-null-pointer-checks'

    def cc(src, obj, extra=''):
        if force or newer(src, obj) or any(newer(os.path.join(ROOT, 'rt', h), obj) for h in ('ld_core.h',)):
            sh('source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; export TMPDIR=%s/tmp; emcc -c %s -o %s %s %s' % (W, src, obj, CF, ' '.join(inc) + ' ' + extra), executable='/bin/bash')
        objs.append(obj)

    cc(ir2, W + '/obj/ir.o')
    objs.extend(extra_objs)
    cc(stubs_c, W + '/obj/stubs.o')
    cc(os.path.join(ROOT, 'rt/ld_wasm.c'), W + '/obj/ld_wasm.o')
    if simd:
        cc(simd_c, W + '/obj/simd.o')
    out = W + '/ld_wasm.cjs'
    if force or any(newer(o, out) for o in objs):
        exports = '_ld_w_inbuf,_ld_w_layout,_ld_w_init,_ld_w_add_wr,_ld_w_snapshot,_ld_w_blob,_ld_w_fix,_ld_w_case_begin,_ld_w_fn,_ld_w_arg,_ld_w_arg_kind,_ld_w_nargs,_ld_w_case_end,_ld_w_state,_emscripten_stack_get_current,__emscripten_stack_restore,_malloc,_free'
        gb = t.get('global_base', 0x10000000)
        mem = t.get('initial_memory', 0x16000000)
        for e in t.get('init_exports', []):
            exports += ',_' + e
        maxmem = t.get('max_memory', 0x7f000000)
        cmd = ('source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; export TMPDIR=%s/tmp; emcc %s -o %s -O0 --profiling-funcs -sALLOW_MEMORY_GROWTH=1 '
               '-sSTACK_SIZE=8MB -sGLOBAL_BASE=%d -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=ldcreate -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=0 '
               '--no-entry -Wl,--export-all -sEXPORTED_RUNTIME_METHODS=UTF8ToString,HEAPU8,wasmExports -sEXPORTED_FUNCTIONS=%s '
               '-Wl,--no-gc-sections -Wl,--initial-memory=%d -Wl,--max-memory=%d 2> %s/link.log') % (
            W, ' '.join(objs), out, gb, exports, mem, maxmem, W)
        t0 = time.time()
        r = subprocess.run(cmd, shell=True, executable='/bin/bash')
        if r.returncode:
            print(open(W + '/link.log').read()[-3000:])
            raise SystemExit('link failed')
        print('[build] link %.1fs' % (time.time() - t0))
    link = open(W + '/link.log').read() if os.path.exists(W + '/link.log') else ''
    info = {'wasm': out, 'wasm_size': os.path.getsize(out[:-4] + '.wasm') if os.path.exists(out[:-4] + '.wasm') else 0,
            'sig_mismatch': link.count('signature mismatch'), 'undefined': link.count('undefined symbol')}
    json.dump(info, open(W + '/build.json', 'w'))
    print('[build] OK', info)
    return info


if __name__ == '__main__':
    t = load_target(sys.argv[1])
    build(t, '--force' in sys.argv)
