#!/usr/bin/env python3
"""ghidra_to_c.py — Ghidra decompile 出力 (DecompEach.java の <va>.c 群) を emcc でビルド可能な 1 本の C に組む (KH-5)。

  ghidra_to_c.py <name> <outdir> <decomp_dir> <core.pe> [--fix F1,F2,..]

機械的書換えだけを行う (手書きの意味補正は --fix で個別に ON/OFF = 「修復の要否」を測るため):
  常時:   Ghidra 型名 shim (ghidra_shim.h)、FUN_<va> の前方宣言、_DAT_/_UNK_ グローバルを PE 実データで定義、
          `undefined1 auVarN[16]` + `<< 0x20` の 128bit 書込を V128 へ、callee stub (memmove/memset/abort)、
          harness 用 function_<va> wrapper (sigs.json 付き)
  --fix 対象 (既定 なし):
    bitcast    Ghidra は float のビット操作 (abs マスク `(float)((uint)(x) & MASK)`) を C キャストで表示するが、C では数値変換になる。
               f2u()/u2f() のビット再解釈に書換える (`(float)(*(uint*)p & uVarN)` も同様)
    concat     `CONCAT44(hi, fVarN)` は float をビット列として連結する意味だが、C の関数引数では float→uint の数値変換になる。f2u() で包む
    intload    Ghidra が float フィールドを int 型 (`(int **)p)[1]`) で読み `(float)` 数値変換で包む型混同。ビット再解釈 (`((float*)*(int**)p)[1]`) に直す
    assoc      Ghidra は浮動小数の積/和の結合括弧を表示で落とす (`a*(b*c)` を `a * b * c` と印字 → C は左結合 `(a*b)*c` で 1 ulp ずれる)。
               実機 x86 の演算順 (逆アセンブルで確認) に合わせ手で括弧を戻す = patches.py の (name, regex, repl) 表。**手作業 1 件 = 1 行**
    stackpair  lStack_e8/lStack_e0 のように「隣接を仮定して &lStack_e8 を配列として渡される」2 変数を long long[2] にする
"""
import json
import re
import sys
import os

import pefile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SNAPINS = {
    'gain': {'proc': 0x1804b0380, 'exports': [0x1804b0380], 'stubs': {}},
    'haas': {'proc': 0x1804d0280, 'exports': [0x1804d0280, 0x1804d0180, 0x1804cff00, 0x1804cff90, 0x1804d0720], 'stubs': {}},
    'gate': {'proc': 0x1804c2f50, 'exports': [0x1804c2f50], 'stubs': {}, 'also': [0x180295f20, 0x180020e70]},
    'resonator': {'proc': 0x180743390, 'exports': [0x180743390], 'stubs': {}, 'also': [0x180fbc1f4, 0x180fbbfb8, 0x180fbdfcc, 0x180fbe018, 0x180fcf904, 0x180fd54cc, 0x180fd62dc, 0x180fd6320, 0x180fb6ce0, 0x180fd648c, 0x180fbdef4, 0x180fe5dfc, 0x180fd6498, 0x180fd662c, 0x180fe5f40, 0x180fd3144]},
    'stereo': {'proc': 0x18080d4d0, 'exports': [0x18080d4d0], 'stubs': {}, 'also': [0x180fcd690, 0x180fce0d0, 0x180fdc470, 0x180fdc660, 0x180fdc700, 0x180fdfdb0, 0x180fdc6d8]},
}
STUB = {  # 未 decompile の callee → C 実装 (RetDec stage-0 + kh_lower ルート (snapins/lift/kh_lower.py) の shims/fail-fast stub と同じ扱い)
    0x181384040: 'void* FUN_181384040(void* d, const void* s, ulonglong n) { return memmove(d, s, (size_t)n); }',
    0x1813846e0: 'void* FUN_1813846e0(void* d, int c, ulonglong n) { return memset(d, c, (size_t)n); }',
    0x18004cf20: 'longlong FUN_18004cf20(void* a, void* b, void* c) { abort(); return 0; }',
}
# IAT thunk (jmp [rip+disp] → KERNEL32 の import) → fail-fast stub。Ghidra は thunk の引数を落として `func_0x000<va>(...)` と呼ぶ。
# 引数無しの定義 (`()`) は呼出の arity を問わない。Win API の意味は実装しない (到達時に abort し、突合で検出する)。
THUNK = {
    0x180fd81e4: 'longlong func_0x000180fd81e4() { abort(); return 0; } /* KERNEL32!FlsGetValue */',
    0x180fd81ec: 'longlong func_0x000180fd81ec() { abort(); return 0; } /* KERNEL32!FlsSetValue */',
}


RCPPS_HELPER = r'''/* rcpps 2 引数形 rcpps(dest, src): 実機 (AMD Ryzen 9 9950X) の近似表 (snapins/lift/gen_simd.py と同一表・同一指数則)。 */
static const uint32_t kh_at_rcp[4096] = %s;
static inline uint32_t kh_rcp_exact(uint32_t x) {
    uint32_t s = x & 0x80000000u, e = (x >> 23) & 0xff, man = x & 0x7fffffu;
    if (e == 0) return s | 0x7f800000u;
    if (e == 0xff) return man ? (s | 0x7f800000u | (man | 0x400000u)) : s;
    int t = 253 - (int)e;
    return t <= 0 ? s : (s | ((uint32_t)t << 23) | kh_at_rcp[(x >> 11) & 0xfffu]);
}
static inline V128 rcpps(undefined1 dst[16], V128 src) {
    V128 r; (void)dst;
    for (int i = 0; i < 4; i++) {
        uint32_t x, w;
        memcpy(&x, src.b + 4 * i, 4);
        w = kh_rcp_exact(x);
        memcpy(r.b + 4 * i, &w, 4);
    }
    return r;
}
'''


def approx_rcp_table():
    """snapins/scripts/approx_tables.b64 の rcp 表 (4096 entry) を C 配列リテラルで返す。"""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'snapins', 'lift'))
    import gen_simd
    return gen_simd.load_approx_tables()['rcp']


def pe_bytes(pe, va, n):
    rva = va - pe.OPTIONAL_HEADER.ImageBase
    return pe.get_data(rva, n)


def infer_type(lines, sym):
    """グローバル sym ごとの C 型推定。(double) キャスト直前の比較 → double / `& sym`・`uVarN = sym`・`sym = uVarN` → uint / 他 float。
    Ghidra は同一グローバルを float と uint の両方で使うことがある (abs マスク 0x1813d6fc0)。uint が 1 行でもあれば uint。"""
    t = set()
    for l in lines:
        if re.search(r'\(double\)\w+\)?\s*$|<= \(double\)|\(double\)[^;]*[<>]=? ' + re.escape(sym) + r'|' + re.escape(sym) + r' [<>]=? \(double\)', l):
            t.add('double')
        elif re.search(r'& ' + re.escape(sym) + r'\b|\buVar\d+ = ' + re.escape(sym) + r'\b|\b' + re.escape(sym) + r' = uVar\d+', l):
            t.add('uint')
        else:
            t.add('float')
    return t


def main():
    a = sys.argv[1:]
    name, outdir, ddir, core = a[:4]
    fixes = set((a[a.index('--fix') + 1] if '--fix' in a else '').split(','))
    cfg = SNAPINS[name]
    os.makedirs(outdir, exist_ok=True)
    pe = pefile.PE(core, fast_load=True)
    vas = list(dict.fromkeys(cfg['exports'] + cfg.get('also', [])))
    src = {va: open(os.path.join(ddir, '%x.c' % va)).read() for va in vas}
    alltxt = '\n'.join(src.values())
    # --- グローバル
    gl = {}
    for m in re.finditer(r'\b(_DAT|_UNK)_([0-9a-f]{8,9})\b', alltxt):
        gl.setdefault(int(m.group(2), 16), m.group(1))
    gtypes = {}
    for va, kind in gl.items():
        ls = [l for l in alltxt.split('\n') if ('%s_%x' % (kind, va)) in l]
        ts = infer_type(ls, '%s_%x' % (kind, va))
        gtypes[va] = ('uint' if kind == '_UNK' or 'uint' in ts else ('double' if 'double' in ts else 'float'), kind, sorted(ts))
    out = ['#include "ghidra_shim.h"', '/* 自動生成: ghidra_to_c.py %s (fix=%s) */' % (name, ','.join(sorted(f for f in fixes if f)) or 'none')]
    if 'rcpps(' in alltxt:
        out.append(RCPPS_HELPER % approx_rcp_table())
    for va, (ty, kind, _) in sorted(gtypes.items()):
        d = pe_bytes(pe, va, 16)
        out.append('static unsigned char gd_%x[16] __attribute__((aligned(16))) = {%s};' % (va, ','.join(str(x) for x in d)))
        out.append('#define %s_%x (*(%s*)gd_%x)' % (kind, va, ty, va))
    # --- 配列参照 (&UNK_x + 添字 = テーブル先頭からのバイト位置): 参照された範囲を 1 本の byte 配列にする
    tabs = sorted(set(int(x, 16) for x in re.findall(r'&UNK_([0-9a-f]{8,9})\b', alltxt)))
    tbase = tend = None
    if tabs:
        tbase = tabs[0] & ~0xf
        tend = max(tabs) + 0x40
        tb = pe_bytes(pe, tbase, tend - tbase)
        out.append('static unsigned char gt_%x[%d] __attribute__((aligned(16))) = {%s};' % (
            tbase, tend - tbase, ','.join(str(x) for x in tb)))
    # --- 前方宣言 (Ghidra の定義シグネチャから)
    protos = []
    bodies = []
    abi_hits = {}
    for va in vas:
        t = src[va]
        t = re.sub(r'/\*.*?\*/', '', t, flags=re.S)
        t = re.sub(r'undefined1 (auVar\d+) \[16\];', r'V128 \1;', t)
        if tbase is not None:
            t = re.sub(r'&UNK_([0-9a-f]{8,9})\b', lambda m: '((unsigned char*)gt_%x + 0x%x)' % (tbase, int(m.group(1), 16) - tbase), t)
        t = re.sub(r'\*\(undefined1 \(\*\) \[16\]\)\((.*?)\) = (auVar\d+) << 0x20;', r'v128_store_shl32((void*)(\1), \2);', t)
        if 'bitcast' in fixes:
            t = re.sub(r'\(float\)\(\(uint\)(\(.*?\)) & (_DAT_[0-9a-f]+|uVar\d+)\)', r'u2f(f2u\1 & \2)', t)
            t = re.sub(r'\(float\)\((\*\(uint \*\)\(.*?\)) & (uVar\d+)\)', r'u2f(\1 & \2)', t)
        if 'concat' in fixes:
            t = re.sub(r'CONCAT44\((\w+),(fVar\d+)\)', r'CONCAT44(\1,f2u(\2))', t)
        if 'intload' in fixes:
            t = re.sub(r'\(float\)(\(\*\(int \*\*\)\(.*?\)\))\[(\d+)\]', r'((float *)\1)[\2]', t)
        if 'assoc' in fixes:
            from patches import ASSOC
            for nm, rx, rp in ASSOC.get(name, []):
                t, k = re.subn(rx, rp, t)
                if k == 0 and ('FUN_%x' % va) in nm:
                    pass
        if 'stackpair' in fixes:
            t = re.sub(r'\blonglong lStack_e8;\n\s*longlong lStack_e0;', 'longlong lStk[2];', t)
            t = t.replace('&lStack_e8', 'lStk').replace('lStack_e8', 'lStk[0]').replace('lStack_e0', 'lStk[1]')
        from patches import ABI
        for nm, rx, rp in ABI.get(name, []):
            t, k = re.subn(rx, rp, t)
            abi_hits[nm] = abi_hits.get(nm, 0) + k
        m = re.search(r'^([\w \*]+?)\s*\n?\s*FUN_%x\((.*?)\)\s*\n\s*\{' % va, t, re.S | re.M)
        if not m:
            m = re.search(r'^([\w \*]+?)\s+FUN_%x\((.*?)\)\s*\{?' % va, t, re.S | re.M)
        assert m, 'signature not found %x' % va
        protos.append('%s FUN_%x(%s);' % (m.group(1).strip(), va, ' '.join(m.group(2).split())))
        bodies.append(t)
    for nm, _, _ in ABI.get(name, []):
        assert abi_hits.get(nm) == 1, 'ABI rule hit %s: %s' % (abi_hits.get(nm), nm)
    for va, s in STUB.items():
        if ('FUN_%x' % va) in alltxt:
            protos.append(s.split('{')[0].strip() + ';')
    out += protos
    out += [STUB[v] for v in STUB if ('FUN_%x' % v) in alltxt]
    out += [THUNK[v] for v in THUNK if ('func_0x000%x' % v) in alltxt]
    # --- 呼出名の統一: Ghidra は未命名 callee を func_0x<va> で呼ぶが、定義側は同一 va を FUN_<va> で出す (also 追加分)
    defined = set(vas)
    bodies = [re.sub(r'\bfunc_0x000(180f[0-9a-f]{5})\b', lambda m: 'FUN_' + m.group(1)
                     if int(m.group(1), 16) in defined else m.group(0), b) for b in bodies]
    out += bodies
    # --- export wrapper (harness は i64×4 + 戻り値 kind で呼ぶ)
    sigs = {}
    for va in cfg['exports']:
        sg = [p for p in protos if ' FUN_%x(' % va in p or p.split('(')[0].endswith('FUN_%x' % va)][0]
        params = [p.strip() for p in re.search(r'\((.*)\)', sg).group(1).split(',')]
        ret = sg.split('FUN_')[0].strip()
        args = []
        for k, p in enumerate(params):
            ty = re.sub(r'\s*\b\w+$', '', p).strip()
            args.append('(%s)a%d' % (ty, k))
        call = 'FUN_%x(%s)' % (va, ','.join(args))
        out.append('EMSCRIPTEN_KEEPALIVE longlong function_%x(longlong a0, longlong a1, longlong a2, longlong a3) { %s; }' % (
            va, ('return (longlong)%s' % call) if ret != 'void' else '%s; return 0' % call))
        sigs['%x' % va] = {'params': ['i64'] * 4, 'ret': 'i64'}
    open(os.path.join(outdir, name + '.c'), 'w').write('\n'.join(out) + '\n')
    json.dump(sigs, open(os.path.join(outdir, 'sigs.json'), 'w'))
    json.dump({'%x' % k: {'type': v[0], 'kind': v[1], 'candidates': v[2]} for k, v in gtypes.items()}, open(os.path.join(outdir, 'globals.json'), 'w'), indent=1)
    print(json.dumps({'name': name, 'functions': [hex(v) for v in vas], 'globals': {('%x' % k): v[0] for k, v in gtypes.items()}, 'fix': sorted(f for f in fixes if f)}))


if __name__ == '__main__':
    main()
