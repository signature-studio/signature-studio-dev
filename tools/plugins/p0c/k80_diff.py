#!/usr/bin/env python3
"""k80_diff.py — kernel lift IR (f80 lowering + ARG fix 適用後) vs native 機械語の差分試験ドライバ (P0c-2 検証)。

  python3 k80_diff.py [--ir work/diff/k80.final.lower.argfix.ll] [--cases 100000]
                      [--only VA,...] [--skip VA,...] [--list-groupb]

構成:
  [1] work/k80abi.json (機械語 win64 slot) + work/f80_classes.json (分類) + IR define
      突合 → kernel 毎の引数モデル (win64 規約: int=rcx,rdx,r8,r9 序数 / float=xmm0-3
      序数 / stack=[entry_rsp+8+8k]) を構成
  [2] work/diff/ に C を生成: shims.c (ms_abi native thunk + IR wrapper + helper 再実装
      + __frontend_reg_*.fpr C 実装) / driver.c (kernel 毎差分ループ, NaN 分離, ulp 計測)
  [3] m11_simd2.py で __asm_* helper C を再生成 (lowering 後の double 署名)
  [4] clang -O2 -shared で IR+driver を 1 本の .so へ (native 側は PE を 0x400000 敷設)
  [5] 実行 → per-kernel CSV (ret差分/buf差分/NaN分離/maxulp)

Group B (数値差分対象外, 静的検証のみ): Delphi RTL / x87 helper を外部呼出する kernel
  (--list-groupb で一覧)。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR, REPO_ROOT  # noqa: E402
LIFTP = os.path.join(REPO_ROOT, 'tools', 'plugins', 'lift', 'passes')
PE = os.path.join(FL_WIN64_DIR, 'extracted', 'block18983_PE.bin')

HELPER_CIMPL = {
    'function_409d00': 'u64 function_409d00(u128 a) { return (u64)(i64)llrint(lane0_d(a)); }   /* cvtsd2si RC=nearest */',
    'function_409df0': 'u64 function_409df0(u128 a) { return (u64)(i64)lane0_d(a); }           /* cvttsd2si trunc */',
}
GROUP_B_HELPERS = ('function_5de330', 'function_40d840', 'function_43c5e0', 'function_5d10b0', 'function_408810')
CT = {'i64': 'u64', 'i32': 'u32', 'i16': 'u16', 'i128': 'u128', 'float': 'float', 'double': 'double', 'ptr': 'u64'}
GORD = ['rcx', 'rdx', 'r8', 'r9']


def canon_gprs(glist):
    return [g for g in GORD if g in glist]


def parse_ir_module(path):
    text = open(path, errors='replace').read()
    starts = [m.start() for m in re.finditer(r'(?m)^define [^\n]*\{', text)]
    funcs = {}
    for k, s in enumerate(starts):
        e_next = starts[k + 1] if k + 1 < len(starts) else len(text)
        seg = text[s:e_next]
        nl = seg.index('\n') + 1
        header = seg[:nl].rstrip()
        body = seg[nl:]
        m = re.match(r'define (i\d+|float|double) @([\w.$-]+)\(([^)]*)\)', header)
        if not m:
            continue
        ret, name, params_s = m.group(1), m.group(2), m.group(3)
        params = []
        for p in params_s.split(','):
            p = p.strip()
            if not p:
                continue
            t, n = p.split()
            params.append((n, t))
        funcs[name] = {'ret': ret, 'params': params, 'body': body}
    return funcs


def ptr_args_of(func):
    """inttoptr へ (2 level 以内で) 流れる引数 → ptr<T> 判定。"""
    body = func['body']
    intop = set(re.findall(r'inttoptr i64 ([%\w.$-]+) to (i\d+|float|double)\*', body))
    derived = {}
    for ln in body.split('\n'):
        m = re.match(r'\s*(%[\w.$-]+) = (?:add|mul|sub) i64 ([%\w.$-]+), ([%\w.$-]+|-\d+|\d+)', ln)
        if m:
            derived[m.group(1)] = (m.group(2), m.group(3))
    ptrparams = {}
    for tgt, ty in intop:
        cands = [tgt]
        if tgt in derived:
            cands += [x for x in derived[tgt] if x.startswith('%')]
        for c in cands:
            ptrparams[c] = ty
    return ptrparams


def param_kinds(func):
    """IR 引数ごとの使用形態: ('ptr', elemty) | ('scalar',) | ('unused',)。

    ptr 判定: inttoptr (opaque ptr 含む) へ 2 level 以内で流れる引数。
    要素型はその ptr への load/store 型から復元 (不明は i64)。"""
    body = func['body']
    intop = {}                                         # src定義名 -> elemty|None
    for m in re.finditer(r'inttoptr i64 ([%\w.$-]+) to (i\d+|float|double)\*', body):
        intop[m.group(1)] = m.group(2)
    for m in re.finditer(r'inttoptr i64 ([%\w.$-]+) to ptr\b', body):
        intop.setdefault(m.group(1), None)
    derived = {}
    for ln in body.split('\n'):
        m = re.match(r'\s*(%[\w.$-]+) = (?:add|mul|sub) i64 ([%\w.$-]+), ([%\w.$-]+|-\d+|\d+)', ln)
        if m:
            derived[m.group(1)] = (m.group(2), m.group(3))
    # elem 復元: ptr 値 (inttoptr 結果 or src) への load/store 型
    def elem_of(ptrval):
        for ln in body.split('\n'):
            m = re.match(r'\s*%[\w.$-]+ = load (i\d+|float|double), ptr ' + re.escape(ptrval) + r'\b', ln)
            if m:
                return m.group(1)
            m = re.match(r'\s*store (i\d+|float|double) [^,]+, ptr ' + re.escape(ptrval) + r'\b', ln)
            if m:
                return m.group(1)
        return None
    feeds = {}
    for tgt, ty0 in intop.items():
        cands = [tgt] + [x for x in derived.get(tgt, ()) if x.startswith('%')]
        ty = ty0
        for c in cands:
            if ty is None:
                ty = elem_of(c)
            feeds[c] = ty or 'i64'
        if ty is None:
            feeds[tgt] = 'i64'
    kinds = []
    for pn, pt in func['params']:
        if pn in feeds:
            kinds.append(('ptr', feeds[pn]))
        elif re.search(r'(?<![\w.%-])' + re.escape(pn) + r'(?![\w.-])', body):
            kinds.append(('scalar',))
        else:
            kinds.append(('unused',))
    return kinds


def build_argmodel(func, abi):
    """RetDec 位置引数 → win64 slot 対応 (slot-ordinal 規約)。

    - 非浮動小数 param は gpr slot (rcx,rdx,r8,r9) を序数順に消費し, 満ちたら stack
      (offset 順) へ。
    - float/double param は機械語の使用 xmm slot (canonical 順) に対応 (fp 序数は
      nat thunk 側で xmm位置に敷設する)。xmm 無し kernel の float param は stack fp。
    - 機械語が mem.base として deref する gpr slot はポインタ引数 (バッファ割当)。
      機械語を ground truth とする (IR 側 inttoptr 解析は補助に留める)。

    mslots: [('gpr', reg, used, isbase) x4, ('xmm', (reg,w), used, True).., ('stack', st, True, False)..]
    irmap:  param index -> ('slot', idx) | ('extra', name, ty) | ('none', None)

    **CAB-253 修正**: leftover は「機械語が使用する未割当 slot」のみ数える (旧実装は
    未使用 gpr slot を引き算に含めていたため、機械語が rcx を読まない kernel
    (0x5de3e0: gpr=[rdx,r8] のみ) で leftover が負になり abi-mismatch 除外されていた)。
    """
    gused = set(canon_gprs(abi.get('gpr_slots', [])))
    gbase = set(abi.get('gpr_base', []))
    xmms = abi.get('xmm_slots', [])
    xw = abi.get('xmm_width', {})
    stacks = abi.get('stack', [])
    mslots = []
    for g in GORD:
        mslots.append(('gpr', g, g in gused, g in gbase))
    for x in xmms:
        mslots.append(('xmm', (x, xw.get(x, 32)), True, True))
    for st in stacks:
        mslots.append(('stack', st, True, False))
    irmap = []
    named = set()
    for pn, pt in func['params']:
        m = re.match(r'%in\.(\w+?)\.bits$|%in\.(\w+)$', pn)
        if m:
            sname = m.group(1) or m.group(2)
            j = next((k for k, (kind, d, u, dr) in enumerate(mslots)
                      if (kind == 'xmm' and d[0] == sname) or (kind == 'gpr' and d == sname)), None)
            if j is None:
                irmap.append(('extra', sname, pt))
                continue
            irmap.append(('slot', j))
            named.add(j)
        else:
            # RetDec の %argN は win64 gpr 序数 (rcx,rdx,r8,r9) そのもの。機械語が rcx を読まない
            # kernel (0x5e1280: rdx,r8 のみ) でも arg1=rcx のため、使用 slot を詰めて割り当てると
            # 1 つずれて IR 側が NULL へ store する (#277)
            # 末尾の未使用 gpr (0x5de710 の r9) は RetDec が詰めるため序数固定しない:
            # その slot か、より後ろの gpr slot を機械語が使う (= 手前に穴がある) ときだけ固定する
            ma = re.match(r'%arg(\d+)$', pn)
            if (ma and 1 <= int(ma.group(1)) <= 4 and pt not in ('float', 'double')
                    and os.environ.get('K80_NO_ARGORD') != '1'):
                n = int(ma.group(1)) - 1
                if any(g in gused for g in GORD[n:]):
                    j = next(k for k, s in enumerate(mslots) if s[0] == 'gpr' and s[1] == GORD[n])
                    irmap.append(('slot', j))
                    named.add(j)
                    continue
            irmap.append(('pos', pt))
    pool_gpr = [k for k, (kind, d, u, dr) in enumerate(mslots) if kind == 'gpr' and u and k not in named]
    pool_xmm = [k for k, (kind, d, u, dr) in enumerate(mslots) if kind == 'xmm' and k not in named]
    pool_st = [k for k, (kind, d, u, dr) in enumerate(mslots) if kind == 'stack' and k not in named]
    pool_stf = [k for k in pool_st if not mslots[k][1]['fp']]
    pool_stf = [k for k in pool_st if mslots[k][1]['fp']]
    pool_sti = [k for k in pool_st if not mslots[k][1]['fp']]
    for i, (pn, pt) in enumerate(func['params']):
        if irmap[i][0] != 'pos':
            continue
        if pt in ('float', 'double') and pool_xmm:
            j = pool_xmm.pop(0)
        elif pool_gpr:
            j = pool_gpr.pop(0)
        elif pool_sti:
            j = pool_sti.pop(0)
        elif pool_stf:
            j = pool_stf.pop(0)
        else:
            irmap[i] = ('none', None)
            continue
        irmap[i] = ('slot', j)
    # leftover (CAB-253): 機械語が使い, かつどの IR 引数にも割り当てられなかった slot 数。
    # 未使用 gpr slot は「機械語が読まない」ので数えない (旧実装はこれを引いていた)。
    unclaimed_used = [k for k, (kind, d, u, dr) in enumerate(mslots)
                      if u and k not in named
                      and not any(e[0] == 'slot' and e[1] == k for e in irmap)]
    leftover = len(unclaimed_used)
    status = 'ok' if leftover == 0 else 'abi-mismatch'
    return mslots, irmap, status


def gen_shims(kernels, funcs):
    out = ['/* k80_diff shims.c — auto-generated by k80_diff.py (手編集禁止) */',
           '#include <stdint.h>', '#include <stdio.h>', '#include <stdlib.h>', '#include <string.h>',
           '#include <math.h>', '#include <sys/mman.h>', '#include <fcntl.h>', '#include <unistd.h>',
           '#include "msimd11_core.h"',
           '#define REBASE 0x400000UL',
           'typedef unsigned __int128 u128;',
           'void map_image(const char* path) {',
           '    int fd = open(path, O_RDONLY); if (fd < 0) { perror("open PE"); exit(2); }',
           '    off_t sz = lseek(fd, 0, SEEK_END);',
           '    uint8_t* f = mmap(NULL, sz, PROT_READ, MAP_PRIVATE, fd, 0);',
           '    uint32_t pe; memcpy(&pe, f + 0x3c, 4);',
           '    uint16_t nsec, optsz; memcpy(&nsec, f + pe + 6, 2); memcpy(&optsz, f + pe + 20, 2);',
           '    uint32_t imgsz; memcpy(&imgsz, f + pe + 24 + 56, 4);',
           '    void* b = mmap((void*)REBASE, imgsz, PROT_READ|PROT_WRITE|PROT_EXEC, MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED|MAP_NORESERVE, -1, 0);',
           '    if (b != (void*)REBASE) { fprintf(stderr, "MAP_FIXED fail\\n"); exit(3); }',
           '    uint32_t so = pe + 24 + optsz;',
           '    for (int i = 0; i < nsec; i++) { uint32_t vs, va, rs, rp; uint8_t* e = f + so + 40 * i;',
           '        memcpy(&vs, e + 8, 4); memcpy(&va, e + 12, 4); memcpy(&rs, e + 16, 4); memcpy(&rp, e + 20, 4);',
           '        uint32_t n = rs < vs ? rs : vs; if (n) memcpy((void*)(REBASE + va), f + rp, n); }',
           '}',
           '/* ---- x87 レジスタスタック模型 (RetDec frontend_reg; index は &7 正規化) ---- */',
           'static double g_fpr[8];',
           'double frontend_reg_load_impl(unsigned i) __asm__("__frontend_reg_load.fpr");',
           'double frontend_reg_load_impl(unsigned i) { return g_fpr[i & 7]; }',
           'void frontend_reg_store_impl(unsigned i, double v) __asm__("__frontend_reg_store.fpr");',
           'void frontend_reg_store_impl(unsigned i, double v) { g_fpr[i & 7] = v; }',
           '/* ---- 外部 helper の C 再実装 (機械語 1 命令系のみ) ---- */']
    for h, c in HELPER_CIMPL.items():
        out.append(c)
    out.append('/* Group B helper (未試験 kernel から参照される) — 呼ばれたら fail-fast */')
    out.append('static void gb_fail(const char* n) { fprintf(stderr, "[groupb-helper-called] %s\\n", n); exit(9); }')
    out.append('u64 function_5de330(void) { gb_fail("5de330"); return 0; }')
    out.append('u64 function_40d840(u64 a) { (void)a; gb_fail("40d840"); return 0; }')
    out.append('u64 function_43c5e0(void* a, u64 b, void* c) { (void)a; (void)b; (void)c; gb_fail("43c5e0"); return 0; }')
    out.append('u64 function_5d10b0(u128 a) { (void)a; gb_fail("5d10b0"); return 0; }')
    out.append('u64 function_408810(u64 a, u64 b, u64 c) { (void)a; (void)b; (void)c; gb_fail("408810"); return 0; }')
    out.append('/* ---- kernel thunk ---- */')
    for va, K in sorted(kernels.items()):
        fn = K['name']
        f = funcs[fn]
        reads = K['reads']                                   # [(kind, key, fp, width)]
        ptypes = K['ptypes']
        nparams = K['nparams']
        ntypes = list(ptypes)
        nparams_c = ', '.join('%s a%d' % (t, i) for i, t in enumerate(ntypes)) or 'void'
        callargs = ['a%d' % i for i in range(nparams)]
        isf128 = f['ret'] == 'i128'
        fret = 'float' if isf128 else 'u64'
        out.append('typedef %s (__attribute__((ms_abi)) *natf_%s)(%s);' % (fret, va, nparams_c))
        # xmm レジスタを引数として読む kernel: call 直前に movss/movsd でロードする
        # (ms_abi 間接呼出では FP 引数は xmm に入らず stack home に載る — CAB-253 実測)
        xloads = []
        for kind, key, fp, w in reads:
            if kind != 'xmm':
                continue
            xn = int(key[3:])
            if 4 + xn in K['conflict_pid']:
                continue                                       # stack home と競合 → そちらを優先
            xloads.append('    __asm__ volatile("%s %%0, %%%%xmm%d" :: "m"(a%d) : "xmm%d");'
                          % ('movsd' if w == 64 else 'movss', xn, 4 + xn, xn))
        body = ''.join(x + '\n' for x in xloads)
        if isf128:
            out.append('u64 nat_%s(%s) { %sfloat r = ((natf_%s)(REBASE + ((u64)%s - REBASE)))(%s); u64 b; memcpy(&b, &r, 4); return b; }'
                       % (va, nparams_c, body, va, va, ', '.join(callargs) or '0'))
        else:
            out.append('u64 nat_%s(%s) { %sreturn ((natf_%s)(REBASE + ((u64)%s - REBASE)))(%s); }'
                       % (va, nparams_c, body, va, va, ', '.join(callargs) or '0'))
        itypes = [CT.get(t, 'u64') for _, t in f['params']]
        iparams = ', '.join('%s b%d' % (t, i) for i, t in enumerate(itypes))
        icast = ', '.join('b%d' % i for i in range(len(itypes)))
        out.append('u64 ir_%s(%s) { extern %s %s(%s); return (u64)%s(%s); }'
                   % (va, iparams or 'void', CT.get(f['ret'], 'u64'), fn, iparams or 'void', fn,
                      icast or ''))
    return '\n'.join(out)


def machine_reads(abi):
    """機械語が読む slot → [(kind, key, fp, width)]。
       kind: 'gpr'(key=reg) | 'xmm'(key=xmmN) | 'stack'(key=offset)"""
    out = []
    xw = abi.get('xmm_width', {})
    for g in canon_gprs(abi.get('gpr_slots', [])):
        out.append(('gpr', g, False, 64))
    for x in sorted(abi.get('xmm_slots', []), key=lambda s: int(s[3:])):
        if int(x[3:]) >= 4:
            continue
        out.append(('xmm', x, True, xw.get(x, 32)))
    for st in abi.get('stack', []):
        out.append(('stack', st['off'], st['fp'], st['width']))
    return out


def pid_of(read):
    """machine read → nat thunk の param index (CAB-253 実測配置)。

    a0..a3 = rcx,rdx,r8,r9 (home offset 8..32) / b0..b3 = home offset 40..64 /
    a8.. = stack args (offset 72+)。⇒ offset O の param index は O/8-1。
    """
    kind, key = read[0], read[1]
    if kind == 'gpr':
        return GORD.index(key)
    if kind == 'xmm':
        return 4 + int(key[3:])
    return key // 8 - 1


def build_param_layout(abi):
    """nat thunk の param 型・個数・xmm ロード競合を決める (CAB-253)。"""
    reads = machine_reads(abi)
    pids = [pid_of(r) for r in reads]
    nparams = max([3] + pids) + 1
    # param 型 = その param に対応する機械語 read の型。4..7 は home slot (offset 40..64)
    # だが型は read に応じ u64/float/double どちらでもよい (実測: stack param は型混合でも
    # パラメータ順に offset 40 から詰められる — probe t11)。
    ptypes = []
    for i in range(nparams):
        if i < 4:
            ptypes.append('u64')
            continue
        w64 = any(pid == i and r[3] == 64 for r, pid in zip(reads, pids))
        fp = any(pid == i and r[2] for r, pid in zip(reads, pids))
        if not fp:
            ptypes.append('u64')
        else:
            ptypes.append('double' if w64 else 'float')
    # xmm レジスタロードと stack home の競合: 同じ param を両方が使う場合 stack home 優先
    home_stack = set(r[1] for r in reads if r[0] == 'stack' and r[1] < 72)
    conflict = set()
    for r in reads:
        if r[0] == 'xmm':
            off = 40 + 8 * int(r[1][3:])
            if off in home_stack:
                conflict.add(4 + int(r[1][3:]))
    return {'reads': reads, 'pids': pids, 'ptypes': ptypes, 'nparams': nparams,
            'conflict_pid': conflict, 'clip_index': bool(abi.get('clip_index')),
            'ptr_struct': abi.get('ptr_struct', [])}


def gen_driver(kernels, funcs, cases, proto=None):
    if proto is None:
        proto = os.environ.get('K80_NO_PROTO') != '1'
    bufpad = 0 if os.environ.get('K80_NO_BUFPAD') == '1' else 64
    out = ['/* k80_diff driver.c — auto-generated (手編集禁止) */',
           '#include <stdint.h>', '#include <stdio.h>', '#include <stdlib.h>', '#include <string.h>',
           '#include <math.h>', '#include <sys/wait.h>', '#include <unistd.h>', '#include <sys/types.h>', '#include "msimd11_core.h"',
           'static uint64_t RS0 = 0x9e3779b97f4a7c15ull, RS1 = 0xbf58476d1ce4e5b9ull;',
           'static uint64_t rnd(void) { uint64_t x = RS0, y = RS1; RS0 = y; x ^= x << 23; RS1 = x ^ y ^ (x >> 17) ^ (y >> 26); return RS1 + y; }',
           'static float bits2f(uint32_t u) { float f; memcpy(&f, &u, 4); return f; }',
           'static float nnegf(float v) { return v < 0 ? -v : v; }',
           'static uint32_t fbits(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }',
           'static double ulp32f(float x, float y) { float lo = fabsf(x) < fabsf(y) ? x : y; if (!isfinite(lo)) return 0;',
           '    float nx = nextafterf(lo, INFINITY); double u = (double)nx - (double)lo; return fabs((double)x - (double)y) / (u > 0 ? u : 1e-45); }',
           'static double ulp64d(double x, double y) { double lo = fabs(x) < fabs(y) ? x : y; if (!isfinite(lo)) return 0;',
           '    double u = nextafter(lo, INFINITY) - lo; return fabs(x - y) / (u > 0 ? u : 4.9e-324); }',
           '#define NBUF 8192', '#define NBUF_B (NBUF * 8 + 256)',
           'typedef struct { const char* va; const char* cls; long ncases; long retdiff; long bufdiff; long nandiff; double maxulp; const char* status; } result_t;',
           'static result_t RES[128]; static int NRES = 0;']
    # thunk の prototype (CAB-253): 宣言なしで呼ぶと float 引数が default argument promotion で
    # double に昇格し (call サイトが movsd), thunk 側の movss は double の下 4 byte を読むため
    # 意図した値と不一致になっていた (両側に同じ値が行くため diff 比較自体は成立するが、
    # 添字アクセス kernel では昇値の符号で OOB read → SIGSEGV になる)。
    for va, K in (sorted(kernels.items()) if proto else []):
        out.append('u64 nat_%s(%s);'
                   % (va, ', '.join('%s a%d' % (t, i) for i, t in enumerate(K['ptypes'])) or 'void'))
        f = funcs[K['name']]
        itypes = [CT.get(t, 'u64') for _, t in f['params']]
        out.append('u64 ir_%s(%s);'
                   % (va, ', '.join('%s b%d' % (t, i) for i, t in enumerate(itypes)) or 'void'))
    for va, K in sorted(kernels.items()):
        fn = K['name']
        f = funcs[fn]
        cls = K['cls']
        if K['status'] != 'ok':
            continue
        mslots = K['mslots']
        reads = K['reads']
        ptypes = K['ptypes']
        nparams = K['nparams']
        pids = K['pids']
        nV = nparams
        pid_of_read = {id(r): p for r, p in zip(reads, pids)}
        rpid = {}
        for r, p in zip(reads, pids):
            rpid[(r[0], r[1])] = p
        # read ごとの param id (kind,key) → pid
        bykey = {}
        for r, p in zip(reads, pids):
            bykey[(r[0], r[1])] = (p, r[2])     # (param id, is-fp)
        # gpr ptr 判定: 機械語が mem.base として deref する slot (機械語 ground truth)。
        # 要素型は IR inttoptr 解析 (kinds) で判れば使用, 無ければ分類に応じ既定。
        bufs = {}
        ET = {'i8': 'i8', 'i16': 'i16', 'i32': 'i32', 'i64': 'i64', 'float': 'f32', 'double': 'f64'}
        idelem = {}
        for i, (pn, pt) in enumerate(f['params']):
            if i < len(K['irmap']) and K['irmap'][i][0] == 'slot' and K['kinds'][i][0] == 'ptr':
                idelem[K['irmap'][i][1]] = ET.get(K['kinds'][i][1], None)
        for k, (kind, d, u, isbase) in enumerate(mslots):
            if kind == 'gpr' and u and isbase:
                bufs[k] = idelem.get(k) or ('f32' if cls == 'f32chain' else 'i64')
        # 二重 deref される gpr slot (ptr_struct): buffer 先頭 16B を有効ポインタにし、
        # その指す 2 バッファを比較対象にする (0x5e05b0/0x5e02b0 の record{ptr,ptr})
        struct_slots = [GORD.index(s) for s in K.get('ptr_struct', []) if s in GORD]
        extra = {}                                          # 比較対象の追加 buffer id -> 'f32'
        for k, ps in enumerate(struct_slots):
            extra[200 + 10 * k] = 'f32'
            extra[200 + 10 * k + 1] = 'f32'
        out.append('/* ---- kernel %s (%s) ---- */' % (va, cls))
        out.append('static void test_%s(long NC, result_t* r) {' % va)
        out.append('  union V { u64 u; double f; } vA[%d], vI[%d];' % (nV, nV))
        for si in sorted(bufs):
            if si in struct_slots:
                continue
            out.append('  static unsigned char bA%d[NBUF_B], bI%d[NBUF_B], bK%d[NBUF_B];' % (si, si, si))
        for ei in sorted(extra):
            out.append('  static unsigned char bA%d[NBUF_B], bI%d[NBUF_B], bK%d[NBUF_B];' % (ei, ei, ei))
        for k, ps in enumerate(struct_slots):
            out.append('  static unsigned char bS%d[NBUF_B], bI%d_0[NBUF_B];' % (ps, ps))
        extras = sorted(set(e[1] for e in K['irmap'] if e[0] == 'extra'))
        for e in extras:
            out.append('  u64 vX_%s = 0;' % e.replace('.', '_'))
        out.append('  memset(r, 0, sizeof(*r)); r->va = "%s"; r->cls = "%s"; r->ncases = NC; r->status = "ok";' % (va, cls))
        if K.get('ret_slot') == 'xmm0':
            out.append('  r->retdiff = -1; /* 戻り値は xmm0 (#3513): 比較対象外 */')
        retmask = ' & 0xffffffffu' if f['ret'] == 'i128' else ''
        out.append('  for (long cs = 0; cs < NC; cs++) {')
        for si in sorted(bufs):
            if si in struct_slots:
                continue
            ety = bufs[si]
            if ety == 'f32':
                out.append('    { for (unsigned j = 0; j < NBUF_B / 4; j++) { uint32_t rr = (uint32_t)rnd(); rr = (rr & 0x807fffffu) | ((((rnd() >> 40) & 0xffu) %% 25u + 118u) << 23); float fv; memcpy(&fv, &rr, 4); memcpy(bK%d + j * 4, &fv, 4); } }' % si)
            elif ety == 'f64':
                out.append('    { for (unsigned j = 0; j < NBUF_B / 8; j++) { double dv = (double)(int64_t)(rnd() %% 4000001) / 1000.0; memcpy(bK%d + j * 8, &dv, 8); } }' % si)
            else:
                out.append('    { for (unsigned j = 0; j < NBUF_B / 4; j++) { uint32_t rr = (uint32_t)rnd(); rr = (rr & 0x807fffffu) | ((((rnd() >> 40) & 0xffu) %% 25u + 118u) << 23); memcpy(bK%d + j * 4, &rr, 4); } }' % si)
        # value slot 初期化: 機械語が読む slot (param id) に値を敷設。読まない param は 0。
        clip = K.get('clip_index')
        for pid in range(nparams):
            hit = [(r, p) for r, p in zip(reads, pids) if p == pid]
            if not hit:
                out.append('    vA[%d].u = vI[%d].u = 0;' % (pid, pid))
                continue
            kind, key, fp, w = hit[0][0]
            if kind == 'gpr':
                if pid in bufs:
                    continue                                   # 後で buffer address を設定
                out.append('    vA[%d].u = vI[%d].u = 512 + (rnd() %% 1536);' % (pid, pid))
            elif not fp:
                out.append('    vA[%d].u = vI[%d].u = 512 + (rnd() %% 1536);' % (pid, pid))
            else:
                # clip_index kernel (添字アクセス) は fp scalar を有限・非負に制限する
                # (負または inf/NaN の gain → trunc が 0x8000.. → 負添字 → OOB read → SIGSEGV)
                gate = '' if (clip and os.environ.get('K80_NO_NNEGF') != '1') else 'if ((rnd() >> 40) > 5) '
                # clip_index kernel: gain が大きいと cvttsd2si が 0x80000000 を返し、neg でも INT_MIN の
                # まま clamp を素通りして負添字 OOB (0x5e0c00; 2000 case 中に発生。仮説は
                # K80_NO_CLIPRANGE=1 で sig11 再現を確認)。gain 指数を 2^-9..2^-1 に絞る (#277)
                nexp = 9 if (clip and os.environ.get('K80_NO_CLIPRANGE') != '1') else 25
                gen = ('{ double v = (double)(int64_t)(rnd() %% 4000001) / 1000.0; vA[%d].f = vI[%d].f = v; }'
                       % (pid, pid)) if w == 64 else (
                    '{ uint32_t rr = (uint32_t)rnd(); %srr = (rr & 0x807fffffu) | ((((rnd() >> 40) & 0xffu) %% %du + 118u) << 23); vA[%d].f = vI[%d].f = %s; }'
                    % (gate, nexp, pid, pid, ('nnegf((double)bits2f(rr))'
                                       if (clip and os.environ.get('K80_NO_NNEGF') != '1')
                                       else '(double)bits2f(rr)')))
                out.append('    ' + gen)
        for ei in sorted(extra):
            out.append('    { for (unsigned j = 0; j < NBUF_B / 4; j++) { uint32_t rr = (uint32_t)rnd(); rr = (rr & 0x807fffffu) | ((((rnd() >> 40) & 0xffu) %% 25u + 118u) << 23); float fv; memcpy(&fv, &rr, 4); memcpy(bK%d + j * 4, &fv, 4); } }' % ei)
        for si in sorted(bufs):
            if si in struct_slots:
                continue
            out.append('    memcpy(bA%d, bK%d, NBUF_B); memcpy(bI%d, bK%d, NBUF_B);' % (si, si, si, si))
            # 先頭 BUFPAD byte 内側を渡す: 0x5dfdb0 は添字を [-1, bound] にクランプして
            # tbl[-1] を読むため、先頭を渡すと nat/IR で別 static 配列の直前 byte を読み差分になる
            out.append('    vA[%d].u = (u64)(uintptr_t)bA%d + %d; vI[%d].u = (u64)(uintptr_t)bI%d + %d;'
                       % (si, si, bufpad, si, si, bufpad))
        for k, ps in enumerate(struct_slots):
            # struct buffer 先頭 16B = {extra buf, extra buf} (nat/IR で別領域を指す)
            t0, t1 = 200 + 10 * k, 200 + 10 * k + 1
            out.append('    memcpy(bS%d, bK%d, NBUF_B); memcpy(bI%d_0, bK%d, NBUF_B);' % (ps, t0, ps, t0))
            out.append('    *(uint64_t*)(bS%d + 0) = (uint64_t)(uintptr_t)bA%d; *(uint64_t*)(bS%d + 8) = (uint64_t)(uintptr_t)bA%d;'
                       % (ps, t0, ps, t1))
            out.append('    *(uint64_t*)(bI%d_0 + 0) = (uint64_t)(uintptr_t)bI%d; *(uint64_t*)(bI%d_0 + 8) = (uint64_t)(uintptr_t)bI%d;'
                       % (ps, t0, ps, t1))
            out.append('    vA[%d].u = (u64)(uintptr_t)bS%d; vI[%d].u = (u64)(uintptr_t)bI%d_0;' % (ps, ps, ps, ps))
            # 参照先 extra buffer を nat/IR 同じ内容で埋める
            out.append('    memcpy(bA%d, bK%d, NBUF_B); memcpy(bI%d, bK%d, NBUF_B);' % (t0, t0, t0, t0))
            out.append('    memcpy(bA%d, bK%d, NBUF_B); memcpy(bI%d, bK%d, NBUF_B);' % (t1, t1, t1, t1))
        # nat 引数式: param 型に応じた式
        nat_expr = []
        for pid in range(nparams):
            t = ptypes[pid]
            if t == 'u64':
                nat_expr.append('vA[%d].u' % pid)
            elif t == 'double':
                nat_expr.append('vA[%d].f' % pid)
            else:
                nat_expr.append('(float)vA[%d].f' % pid)
        # ir 引数式 (value slot 番号は nat 側と共通: pid で指定)
        ir_expr = []
        for i, (pn, pt) in enumerate(f['params']):
            entry = K['irmap'][i] if i < len(K['irmap']) else ('none', None)
            if entry[0] == 'slot':
                si2 = entry[1]
                kind2, d2, u2, dr2 = mslots[si2]
                if kind2 == 'xmm':
                    key = ('xmm', d2[0])
                elif kind2 == 'stack':
                    key = ('stack', d2['off'])
                else:
                    key = ('gpr', d2)
                ent = bykey.get(key, (si2, None))
                si2, isfp = ent[0], ent[1]
                if pt in ('float', 'double'):
                    ir_expr.append('(%s)vI[%d].f' % (pt, si2))
                elif isfp:
                    # fp slot の値を整数型引数 (i32 = f32 bits) に渡す: float の bit 表現
                    ir_expr.append('fbits((float)vI[%d].f)' % si2 if pt in ('i32', 'i16', 'i8')
                                   else '(u64)fbits((float)vI[%d].f)' % si2)
                else:
                    ir_expr.append('vI[%d].u' % si2)
            elif entry[0] == 'extra':
                ir_expr.append('vX_%s' % entry[1].replace('.', '_'))
            else:
                ir_expr.append('0')
        out.append('    u64 rn = nat_%s(%s);' % (va, ', '.join(nat_expr) or '0'))
        out.append('    u64 ri = ir_%s(%s);' % (va, ', '.join(ir_expr) or '0'))
        # #3513: 戻り値が xmm0 の kernel は rax (rn) を戻り値として比べない (ret_diff=-1)。
        # IR の ret は xmm0 を表さないため、その戻り値は ucomi_ret_check.py 等で個別に判定する
        if K.get('ret_slot') != 'xmm0':
            out.append('    if ((rn %s) != (ri %s)) { r->retdiff++; if (r->retdiff == 1) fprintf(stderr, "[%s] ret case %%ld nat=%%llx ir=%%llx\\n", cs, (unsigned long long)rn, (unsigned long long)ri); }'
                       % (retmask, retmask, va))
        cmp_bufs = dict((si, bufs[si]) for si in bufs if si not in struct_slots)
        cmp_bufs.update(extra)
        for si in sorted(cmp_bufs):
            ety = cmp_bufs[si]
            esz = {'f32': 4, 'f64': 8, 'i16': 2, 'i32': 4, 'i64': 8}.get(ety, 4)
            isf = ety in ('f32', 'f64')
            ulpfn = 'ulp32f' if ety == 'f32' else 'ulp64d'
            out.append('    for (unsigned j = 0; j < NBUF_B; j += %d) {' % esz)
            if isf:
                ct = 'float' if ety == 'f32' else 'double'
                out.append('      %s x, y; memcpy(&x, bA%d + j, sizeof x); memcpy(&y, bI%d + j, sizeof y);' % (ct, si, si))
                out.append('      if (isnan(x) && isnan(y)) { r->nandiff++; continue; }')
                out.append('      if (memcmp(&x, &y, sizeof x)) { r->bufdiff++; double u = %s(x, y); if (u > r->maxulp) r->maxulp = u; }' % ulpfn)
            else:
                out.append('      if (memcmp(bA%d + j, bI%d + j, %d)) r->bufdiff++;' % (si, si, esz))
            out.append('    }')
        out.append('  }')
        out.append('}')
    out.append('int main(void) {')
    out.append('  map_image("%s");' % PE)
    out.append('  printf("kernel,class,ncases,ret_diff,buf_diff,nan_cells,maxulp,status\\n");')
    out.append('  fflush(stdout);')
    for va, K in sorted(kernels.items()):
        if K['status'] != 'ok':
            continue
        out.append('  {')
        out.append('    pid_t p = fork();')
        out.append('    if (p == 0) { result_t r; test_%s(%d, &r); printf("%%s,%%s,%%ld,%%ld,%%ld,%%ld,%%.4f,%%s\\n", r.va, r.cls, r.ncases, r.retdiff, r.bufdiff, r.nandiff, r.maxulp, r.status); fflush(stdout); _exit(0); }' % (va, cases))
        out.append('    int st = 0; waitpid(p, &st, 0);')
        out.append('    if (WIFSIGNALED(st)) printf("%s,%s,0,0,0,0,0.0000,sig%%d\\n", WTERMSIG(st));' % (va, K['cls']))
        out.append('  }')
    out.append('  fprintf(stderr, "PARENT DONE\\n");')
    out.append('  return 0;')
    out.append('}')
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ir', required=True)
    ap.add_argument('--cases', type=int, default=100000)
    ap.add_argument('--only')
    ap.add_argument('--skip')
    ap.add_argument('--list-groupb', action='store_true')
    ap.add_argument('--nogen', action='store_true', help='生成済み driver を再ビルドのみ')
    a = ap.parse_args()
    abi = json.load(open(os.path.join(HERE, 'work', 'k80abi.json')))
    classes = json.load(open(os.path.join(HERE, 'work', 'f80_classes.json')))
    clsva = {}
    for r in classes['kernels']:
        lab = set(r['labels'])
        if 'int64x87' in lab:
            c = 'int64x87'
        elif 'transc' in lab:
            c = 'transc'
        elif 'rc_chop' in lab:
            c = 'rc_chop'
        elif 'f64mem' in lab:
            c = 'f64mem'
        elif 'f32chain' in lab:
            c = 'f32chain'
        elif 'int32x87' in lab:
            c = 'int32x87'
        else:
            c = 'sse'
        clsva[r['va']] = c
    funcs = parse_ir_module(a.ir)
    only = set(a.only.split(',')) if a.only else None
    skip = set(a.skip.split(',')) if a.skip else set()
    kernels = {}
    groupb = []
    for va, ab in abi.items():
        fn = 'function_' + va[2:]
        if fn not in funcs or (only and va not in only) or va in skip:
            continue
        F = funcs[fn]
        calls = set(re.findall(r'call [^@]*@([\w.$-]+)\(', F['body']))
        extcalls = sorted(c for c in calls if c in GROUP_B_HELPERS)
        if extcalls:
            groupb.append((va, clsva.get(va, 'sse'), ','.join(x[9:] for x in extcalls)))
            continue
        mslots, irmap, status = build_argmodel(F, ab)
        kinds = param_kinds(F)
        ptrargs = {}
        pp = ptr_args_of(F)
        gorder = canon_gprs(ab.get('gpr_slots', []))
        gname = {}
        pi = 0
        for pn, pt in F['params']:
            if re.match(r'%in\.', pn):
                continue
            if pi < len(gorder):
                gname[pn] = gorder[pi]
            pi += 1
        for pname, ty in pp.items():
            g = gname.get(pname)
            if g:
                ptrargs['gpr:%s' % g] = {'i8': 'i8', 'i16': 'i16', 'i32': 'i32', 'i64': 'i64',
                                         'float': 'f32', 'double': 'f64'}.get(ty, 'i64')
        lay = build_param_layout(ab)
        kernels[va] = {'name': fn, 'cls': clsva.get(va, 'sse'), 'mslots': mslots, 'irmap': irmap,
                       'status': status, 'kinds': kinds, 'gprs': canon_gprs(ab.get('gpr_slots', [])),
                       'xmms': ab.get('xmm_slots', []), 'xw': ab.get('xmm_width', {}),
                       'stacks': ab.get('stack', []),
                       'reads': lay['reads'], 'pids': lay['pids'], 'ptypes': lay['ptypes'],
                       'nparams': lay['nparams'], 'conflict_pid': lay['conflict_pid'],
                       'clip_index': lay['clip_index'], 'ptr_struct': lay['ptr_struct'],
                       'ret_slot': ab.get('ret_slot', 'unknown')}
    if a.list_groupb:
        print('GroupB (数値差分対象外 — 外部 helper 呼出):')
        for va, c, h in groupb:
            print('  %-10s %-10s %s' % (va, c, h))
        print('total', len(groupb))
        return
    d = os.path.join(HERE, 'work', 'diff')
    os.makedirs(d, exist_ok=True)
    simd_c = os.path.join(d, 'k80_simd_argfix.c')
    if not a.nogen:
        with open(simd_c, 'w') as w, open(os.devnull, 'w') as dn:
            rc = subprocess.call(['python3', os.path.join(LIFTP, 'm11_simd2.py'), a.ir], stdout=w, stderr=dn)
        assert rc == 0
        txt = open(simd_c).read().replace('#include "../msimd11_core.h"', '#include "msimd11_core.h"')
        open(simd_c, 'w').write(txt)
        shutil.copy(os.path.join(LIFTP, 'msimd11_core.h'), os.path.join(d, 'msimd11_core.h'))
        open(os.path.join(d, 'shims.c'), 'w').write(gen_shims(kernels, funcs))
        open(os.path.join(d, 'driver.c'), 'w').write(gen_driver(kernels, funcs, a.cases))
    so = os.path.join(d, 'k80diff')
    cmd = ['clang', '-O2', '-fPIC', '-Wno-implicit-function-declaration', '-Wno-override-module',
           '-I%s' % LIFTP, '-I%s' % d, a.ir, os.path.join(d, 'shims.c'),
           os.path.join(d, 'driver.c'), simd_c, '-o', so, '-lm']
    print('[build]', ' '.join(os.path.basename(x) for x in cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-6000:])
        raise SystemExit('[build] FAIL')
    r = subprocess.run([so], capture_output=True, text=True)
    if r.stderr:
        print('[stderr tail]', r.stderr[-1200:])
    print(r.stdout)


if __name__ == '__main__':
    main()
