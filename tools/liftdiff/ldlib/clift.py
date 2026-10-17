"""clift — C 転写 lift (x64c, tools/flelift) の liftdiff 接続ビルド (CAB-232)。

target JSON に "clift": true を置くと build_wasm.build() から本モジュールに分岐する。
LLVM IR を持たない lift 産物 (fle_lifted.c) を次の方針で liftdiff プロトコルに載せる:

  - 署名 (sigs.json) と np テーブルは m11 RetDec IR (target の "ir" = 署名ソース) から抽出。
    case 生成 (引数パターン) と callee 引数比較を m11 route と同一にし、比較可能性を保つ。
  - lift 産物 C は「関数 entry に ld_fle_trace(0xVA) を 1 行挿入するだけ」のテキスト計装で
    wasm 化 (意味不変)。トレース記録はブリッジ (rt/fle_ldbridge.c) が行う。
  - import は全 IAT 名の強い imp_<名前> を imps.inc として生成し ld_core.ld_stub (native
    ld_native.c と同一応答モデル + 呼出しログ) に流す。fle_lifted.c の weak 既定 / fle_cpu.c
    の既定 import (-Dimp_X=flecpu_X でリネーム) を両方上書きする。imps.inc はブリッジと
    同一翻訳単位に #include する (ld_core の状態 = 呼出しログを共有するため)。
  - lift 定義集合は lift_meta.json (x64c lift 実績) から lifted.json に書き出し、
    Session が非 lift 関数を no_wasm_definition (unexec) として先に分類する。

出力: work/<target>/{sigs.json, stubs.json, lifted.json, fle_lifted_tr.c, imps.inc, nptab.c, ld_wasm.cjs}
"""
import json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
REPO = os.path.abspath(os.path.join(ROOT, '..', '..'))
sys.path.insert(0, ROOT)
from ldlib import irtool


def sh(cmd, **kw):
    print('[clift] $ %s' % (cmd if isinstance(cmd, str) else ' '.join(cmd)), flush=True)
    r = subprocess.run(cmd, shell=isinstance(cmd, str), **kw)
    if r.returncode:
        raise SystemExit('clift build failed (%d): %s' % (r.returncode, str(cmd)[:200]))


def newer(a, b):
    return not os.path.exists(b) or os.path.getmtime(a) > os.path.getmtime(b)


def rp(p):
    return p if os.path.isabs(p) else os.path.join(REPO, p)


def instrument_clift(src, dst, vas):
    """各 `void f_<hex>(void) {` の直後に ld_fle_trace(0x<hex>ULL); を挿入 (lift 集合のみ)。
    冒頭に ld_fle_trace の宣言を足す (暗黙宣言による wasm signature mismatch を防ぐ)。"""
    pat = re.compile(r'^(void f_([0-9a-f]+)\(void\) \{)$')
    n = 0
    with open(src, errors='replace') as fi, open(dst, 'w') as fo:
        fo.write('/* 計装済コピー (ldlib/clift.py): f_ entry に ld_fle_trace を挿入 */\n'
                 'void ld_fle_trace(unsigned long long va);\n')
        for line in fi:
            m = pat.match(line.rstrip('\n'))
            fo.write(line)
            if m and int(m.group(2), 16) in vas:
                fo.write('  ld_fle_trace(0x%sULL);\n' % m.group(2))
                n += 1
    return n


def instrument_clift_blocks(src, dst, vas):
    """lift 集合の各 `L_<hex>:;` (基本ブロック入口) の直後に volatile store で block 入口を記録する (LD-64 / LD-67 の clift 版)。
    ir 版 (irtool._blk_store) と同じ ld_blk_n / ld_blk_arr を使う。call は戻り値を変えるため使わない。
    記録は f_ の内側だけ (関数 VA ごとに L_ を対応させる)。戻り値: 挿入したブロック数"""
    pat_f = re.compile(r'^void f_([0-9a-f]+)\(void\) \{$')
    pat_l = re.compile(r'^L_([0-9a-f]+):;$')
    n = 0
    cur = None
    with open(src, errors='replace') as fi, open(dst, 'w') as fo:
        fo.write('/* 計装済コピー (ldlib/clift.py): 基本ブロック入口の記録 (block_trace) */\n'
                 'extern volatile unsigned long long ld_blk_n;\n'
                 'extern volatile unsigned long long ld_blk_arr[65536];\n')
        for line in fi:
            s = line.rstrip('\n')
            mf = pat_f.match(s)
            if mf:
                cur = int(mf.group(1), 16) if int(mf.group(1), 16) in vas else None
            fo.write(line)
            ml = pat_l.match(s)
            if ml and cur is not None:
                va = int(ml.group(1), 16)
                fo.write('  { unsigned long long _n = ld_blk_n; ld_blk_arr[_n & 65535] = 0x%xULL; ld_blk_n = _n + 1; }\n' % va)
                n += 1
    return n


def gen_imps(names, dst):
    """全 IAT 名の強い imp_<名前> (ブリッジ TU へ #include される): ld_core 応答モデル + 呼出しログ。
    CAB-233: 第5/6引数を guest stack ([R4+0x28]/[R4+0x30]) からも読む (6引数 API の dst 書込み用)。"""
    out = ['/* 生成ファイル (ldlib/clift.py): flelift import を ld_core.ld_stub 経由に統一 (native と同一応答) */',
           'static u64 fle_imp_stub(const char* n) {',
           '  u64 r = ld_stub(n, R[1], R[2], R[8], R[9], LD64(R[4] + 0x28), LD64(R[4] + 0x30));   /* rcx,rdx,r8,r9 + stack */',
           '  R[0] = r; R[4] += 8;                          /* rax = 応答, callee 側 ret */',
           '  return r;',
           '}', '']
    for nm in names:
        out.append('void imp_%s(void) { fle_imp_stub("%s"); }' % (nm, nm))
    out.append('')
    open(dst, 'w').write('\n'.join(out))
    return len(names)


def gen_nptab(sigs, lifted, dst, prefix):
    """ソート済 {va,np} テーブル (トレースの callee 引数比較数 = m11 IR 署名)。"""
    ents = []
    for k, v in sigs.items():
        if not k.startswith(prefix) or not v['defined']:
            continue
        try:
            va = int(k[len(prefix):], 16)
        except ValueError:
            continue
        if va in lifted:
            ents.append((va, len(v['params'])))
    ents.sort()
    with open(dst, 'w') as f:
        f.write('/* 生成ファイル (ldlib/clift.py): {va,np} — m11 IR sig 由来 */\n')
        f.write('#include <stdint.h>\n')
        f.write('typedef struct { uint64_t va; uint32_t np; } fle_nptab_t;\n')
        f.write('const fle_nptab_t fle_nptab[] = {\n')
        for i, (va, np) in enumerate(ents):
            f.write('  {0x%xULL,%d},' % (va, np))
            if (i + 1) % 8 == 0:
                f.write('\n')
        f.write('\n};\nconst int fle_nptab_n = %d;\n' % len(ents))
    return ents


def decl_widths(ir_path):
    """IR declare から import 名 → 引数幅 [w0..w3] (m11 gen_stubs と同一規則)。cmp_calls の幅比較に使用。"""
    widths = {}
    with open(ir_path, errors='replace') as f:
        for line in f:
            if not line.startswith('declare '):
                continue
            m = irtool.DECL_RE.match(line.rstrip('\n'))
            if not m:
                continue
            ps = [irtool.param_type(p)[0] for p in irtool.split_top(m.group('args'))]
            cps = [irtool.ctype(t) for t in ps[:4]]
            if any(c is None for c in cps):
                continue
            widths[m.group('name')] = [64 if c == 'u64' else 32 for c in cps]
    return widths


def build(t, force=False):
    W = t['work']
    os.makedirs(W + '/obj', exist_ok=True)
    os.makedirs(W + '/tmp', exist_ok=True)
    prefix = t.get('fn_prefix', 'function_')
    # ---- 1) 署名 (m11 RetDec IR を「署名ソース」としてのみ使用 — コンパイルはしない) ----
    sigs_p = W + '/sigs.json'
    if force or newer(t['ir'], sigs_p):
        sigs = irtool.parse_sigs(t['ir'], prefix)
        json.dump(sigs, open(sigs_p, 'w'))
        print('[clift] sigs: %d (defined %d)' % (len(sigs), sum(1 for s in sigs.values() if s['defined'])))
    sigs = json.load(open(sigs_p))
    closure_vas = set()
    for k, v in sigs.items():
        if k.startswith(prefix) and v['defined']:
            try:
                closure_vas.add(int(k[len(prefix):], 16))
            except ValueError:
                pass   # function_<hex>__lifted 等の派生名は closure 集合外
    # ---- 2) lift 定義集合 (lift_meta.json = x64c lift 実績) ----
    meta_p = rp(t['clift_meta'])
    meta = json.load(open(meta_p))
    lifted = {int(v, 16) for v in meta['functions']}
    json.dump({'vas': ['%x' % v for v in sorted(lifted)]}, open(W + '/lifted.json', 'w'))
    print('[clift] lifted: %d / closure %d (non-lifted %d → unexec no_wasm_definition)' % (
        len(lifted), len(closure_vas), len(closure_vas - lifted)))
    # ---- 3) lift 産物 C の計装 + import/np 生成 ----
    src = rp(t['clift_sources'][0])
    tr_c = W + '/fle_lifted_tr.c'
    if force or newer(src, tr_c):
        t0 = time.time()
        n = instrument_clift(src, tr_c, lifted)
        print('[clift] instrumented %d f_ entries (%.1fs)' % (n, time.time() - t0))
        if t.get('block_trace'):
            tmp_c = W + '/fle_lifted_f.c'
            nb = instrument_clift_blocks(tr_c, tmp_c, lifted)
            os.replace(tmp_c, tr_c)
            print('[clift] block_trace: %d basic-block entries' % nb)
    imp_names = list(meta['imports_used'])
    imps_inc = W + '/imps.inc'
    if force or newer(src, imps_inc):
        gen_imps(imp_names, imps_inc)
        print('[clift] imps: %d' % len(imp_names))
    nptab_c = W + '/nptab.c'
    if force or newer(sigs_p, nptab_c):
        ents = gen_nptab(sigs, lifted, nptab_c, prefix)
        print('[clift] nptab: %d entries' % len(ents))
    # stubs.json = import 名と引数幅 (IR declare 由来。実 stub C は imps.inc が担う)
    widths = decl_widths(t['ir'])
    json.dump({'stubs': imp_names, 'skipped': [], 'widths': {n: widths.get(n, [32] * 4) for n in imp_names}},
              open(W + '/stubs.json', 'w'))
    # ---- 4) CPU 実装 (既定 fle_cpu.c / OTT は ott_cpu.c) の既定 import を -D でリネーム (imps.inc と衝突しないように) ----
    cpu_c = rp(t['clift_rt'] + '/' + t.get('clift_cpu', 'fle_cpu.c'))
    cpu_imps = []
    with open(cpu_c, errors='replace') as f:
        for line in f:
            m = re.match(r'^void (imp_[A-Za-z0-9_]+)\(void\) \{', line)
            if m:
                cpu_imps.append(m.group(1))
    rename = ' '.join('-D%s=flecpu_%s' % (n, n) for n in cpu_imps + ['ott_unlifted'])
    if t.get('clift_cpu'):   # OTT 系: 同名の ott_unlifted は bridge 側が持つ (ott_cpu.c 側は退避)
        rename = ' '.join('-D%s=ottcpu_%s' % (n, n) for n in cpu_imps + ['ott_unlifted'])
    # lift 産物側: ott_dispatch をラッパ経由に差し替え (guest stack 範囲外 push の検出)。既定 flelift_dispatch_impl
    lifted_extra = '-Dott_dispatch=%s' % t.get('clift_dispatch', 'flelift_dispatch_impl')
    # ---- data: clift_data_gen (例 OTT = tools/ott/lift/data_gen.py) があれば DLL から生成 ----
    data_c = rp(t['clift_data']) if t.get('clift_data') else W + '/data.c'
    if t.get('clift_data_gen') and (force or newer(rp(t['pe']), data_c)):
        sh([sys.executable, rp(t['clift_data_gen']), rp(t['pe']), data_c, meta_p])
    # ---- 5) コンパイル + リンク (bridge が imps.inc を #include → ld_core 状態を共有) ----
    env_sh = 'source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; export TMPDIR=%s/tmp; ' % W
    objs = []
    CF = '-w -Wno-implicit-function-declaration -O0 -g1 -fno-delete-null-pointer-checks'
    INC = '-I"%s" -I"%s" -I"%s"' % (os.path.join(ROOT, 'rt'), rp(t['clift_rt']), W)
    for tag, path_, extra in (
        ('lifted', tr_c, lifted_extra),
        ('data', data_c, ''),
        ('cpu', cpu_c, rename),
        ('nptab', nptab_c, ''),
        ('bridge', os.path.join(ROOT, t.get('clift_bridge', 'rt/fle_ldbridge.c')), ''),
    ) + tuple(('extra%d' % k, rp(p), '') for k, p in enumerate(t.get('clift_extra_c', []))):
        obj = W + '/obj/%s.o' % tag
        if force or newer(path_, obj):
            sh(env_sh + 'emcc -c %s -o %s %s %s %s' % (path_, obj, CF, INC, extra), executable='/bin/bash')
        objs.append(obj)
    out = W + '/ld_wasm.cjs'
    mem = t.get('initial_memory', 0x36000000)
    maxmem = t.get('max_memory', 0x36000000)
    gb = t.get('global_base', 0x10000000)
    exports = ('_ld_w_inbuf,_ld_w_layout,_ld_w_init,_ld_w_add_wr,_ld_w_snapshot,_ld_w_blob,_ld_w_fix,'
               '_ld_w_case_begin,_fle_ld_run,_fle_ld_xmm0,_ld_w_case_end,_ld_w_state,'
               '_malloc,_free,_emscripten_stack_get_current,__emscripten_stack_restore')
    for e in t.get('init_exports', []):
        exports += ',_' + e
    cmd = (env_sh + 'emcc %s -o %s -O0 --profiling-funcs -sALLOW_MEMORY_GROWTH=1 --no-entry '
           '-sSTACK_SIZE=32MB -sGLOBAL_BASE=%d -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=ldcreate -sEXIT_RUNTIME=0 '
           '-sEXPORTED_FUNCTIONS=%s -Wl,--export-all -sEXPORTED_RUNTIME_METHODS=UTF8ToString,HEAPU8,wasmExports '
           '-Wl,--no-gc-sections -Wl,--initial-memory=%d -Wl,--max-memory=%d 2> %s/link.log') % (
        ' '.join(objs), out, gb, exports, mem, maxmem, W)
    t0 = time.time()
    r = subprocess.run(cmd, shell=True, executable='/bin/bash')
    if r.returncode:
        print(open(W + '/link.log').read()[-3000:])
        raise SystemExit('clift link failed')
    link = open(W + '/link.log').read()
    info = {'wasm': out, 'wasm_size': os.path.getsize(out[:-4] + '.wasm') if os.path.exists(out[:-4] + '.wasm') else 0,
            'sig_mismatch': link.count('signature mismatch'), 'undefined': link.count('undefined symbol'),
            'imps': len(imp_names), 'clift': True}
    json.dump(info, open(W + '/build.json', 'w'))
    print('[clift] link %.1fs OK %s' % (time.time() - t0, info))
    return info
