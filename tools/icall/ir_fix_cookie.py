#!/usr/bin/env python3
"""ir_fix_cookie.py IN.ll OUT.ll — cookie global (0x18125eaa8, 8byte) の load 幅を i32 から i64 に戻す (ICALL-70 / #2280)。

   欠陥の段: RetDec の `converting global variables` 段が @global_var_18125eaa8 を `i32` と型付けする
   (RetDec 生出力 lift/fa.drc.c の `int32_t g26 = ...; // 0x18125eaa8` と一致)。以後の段は型を引き継ぐ。
   native は `mov rbx, qword ptr [cookie]` (64bit) で読むため、上位 32bit が落ちると decode
   (`ror(cookie ^ slot, n)`) の結果が native と一致しない (#2262 付録 §3)。

   修復 (関数単位): `%v = load i32, i32* @cookie` を
       %v.q = load i64, i64* @cookie
       %v   = trunc i64 %v.q to i32        ; 既存の i32 利用 (下位 bit: urem 64 等) は従来どおり
   に置換し、`%w = sext i32 %v to i64` は `%w = add i64 %v.q, 0` (64bit 値そのもの) に置換する。
   global の宣言型は i64 とし、初期値は SlateCore.core_64 の .data 実値 0x2b992ddfa232 とする (VA 0x18125eaa8 の 8byte を #2302 で PE から読み取って確認。REPORT_APPENDIX_2302 §2)。
   出力: JSON 1 行 {"cookie_global": N, "loads_fixed": M, "sext_fixed": K}。
"""
import json, re, sys

GLOBAL = '@global_var_18125eaa8'
COOKIE_INIT = 0x2b992ddfa232
DECL = re.compile(r'^(' + re.escape(GLOBAL) + r' = (?:local_unnamed_addr )?global )i32 \d+')
USELIST = re.compile(r'^\s*uselistorder i32\* ' + re.escape(GLOBAL) + r',')
LOAD = re.compile(r'^(\s*)(%[\w.]+) = load i32, i32\* ' + re.escape(GLOBAL) + r'(, align \d+)?(, !insn\.addr !\d+)?[ \t]*$')


def fix_function(lines):
    out, names, nload = [], {}, 0
    for ln in lines:
        if USELIST.match(ln):
            continue
        m = LOAD.match(ln)
        if m:
            ind, v, al, md = m.group(1), m.group(2), m.group(3) or '', m.group(4) or ''
            vq = '%%ck.%s' % v[1:]
            out.append('%s%s = load i64, i64* %s%s%s' % (ind, vq, GLOBAL, al, md))
            out.append('%s%s = trunc i64 %s to i32%s' % (ind, v, vq, md))
            names[v] = vq
            nload += 1
            continue
        out.append(ln)
    nsext = 0
    if names:
        for i, ln in enumerate(out):
            for v, vq in names.items():
                pat = re.compile(r'^(\s*)(%[\w.]+) = sext i32 ' + re.escape(v) + r' to i64(?![\w.])')
                m = pat.match(ln)
                if m:
                    out[i] = '%s%s = add i64 %s, 0%s' % (m.group(1), m.group(2), vq, ln[m.end():])
                    nsext += 1
                    break
    return out, nload, nsext


def main(src, dst):
    lines = open(src).read().split('\n')
    res, nd, nl, ns = [], 0, 0, 0
    body = []
    for ln in lines:
        if ln.startswith('define '):
            if body:
                o, a, b = fix_function(body)
                res += o
                nl += a
                ns += b
                body = []
        if ln.startswith('define ') or body or ln.startswith('}'):
            body.append(ln)
            if ln.startswith('}'):
                o, a, b = fix_function(body)
                res += o
                nl += a
                ns += b
                body = []
            continue
        m = DECL.match(ln)
        if m:
            ln = '%si64 %d' % (m.group(1), COOKIE_INIT)
            nd += 1
        res.append(ln)
    if body:
        o, a, b = fix_function(body)
        res += o
        nl += a
        ns += b
    open(dst, 'w').write('\n'.join(res))
    print(json.dumps({'cookie_global': nd, 'loads_fixed': nl, 'sext_fixed': ns}))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
