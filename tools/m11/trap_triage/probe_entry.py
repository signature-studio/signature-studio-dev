#!/usr/bin/env python3
"""probe_entry.py (#596): boot_final3.ll の指定関数の入口に引数 dump の call を挿入した build を作る (動作は IR と同一, 読み取りのみ).
  usage: probe_entry.py <fn_hex,fn_hex,...> [--out work/probe]      (例: 4f9f40,4fad10)
  生成: <out>/boot_probe.ll (IR) と <out>/probe.c (m11_pe: stderr に `[pe] <fn> a1 a2 a3 a4 | q(a1) q(a2)` を出す)
  build: emcc -c <out>/boot_probe.ll -o work/obj/boot.o (+ probe.c を work/obj/probe.o) → m11_build.sh と同じ link
        (probe_entry.sh が一式やる). 引数は IR の arg1..arg4 (arity が足りなければ 0). q(x) は x が image 内ポインタ候補 (0x10000..0x20000000) のときだけ読む
  同じ build で survey_units.mjs を SV_PROG=1 で走らせると stderr に `unit N` と `[pe]` が交互に出る (probe_entry.sh が <tag>.err に残す)"""
import re, sys, os
HERE = os.path.dirname(os.path.abspath(__file__)); W = os.path.join(HERE, '..', 'work')
WATCH = None   # --watch <lva_hex>:<off_hex>:... → 全関数の入口で値が変わったら [chg] <直前に走っていた fn> -> <この fn> を出す (書込元の特定, #596)
if '--watch' in sys.argv: WATCH = sys.argv[sys.argv.index('--watch') + 1]
fns = sys.argv[1].split(',')
out = os.path.join(W, 'probe')
if '--out' in sys.argv: out = sys.argv[sys.argv.index('--out') + 1]
os.makedirs(out, exist_ok=True)
src = open(os.path.join(W, 'boot_final3.ll')).read()
n = 0
if fns == ['all']:
    fns = sorted(set(re.findall(r'^define [^\n@]*@function_([0-9a-f]+)\(', src, re.M)))
for f in fns:
    pat = re.compile(r'(^define [^\n@]*@function_%s(?:__lifted)?\(([^)]*)\)[^\n]*\{\n[^\n]*:[^\n]*\n)' % f, re.M)
    m = pat.search(src)
    if not m: print('no define for', f, file=sys.stderr); continue
    args = re.findall(r'(i64|ptr|i32) (?:nonnull )?(%arg\d+)', m.group(2))
    pre = ''; a = []
    for k, (ty, nm) in enumerate(args[:4]):
        if ty == 'i64': a.append(nm)
        elif ty == 'ptr': pre += '  %%pe_%s_%d = ptrtoint ptr %s to i64\n' % (f, k, nm); a.append('%%pe_%s_%d' % (f, k))
        else: pre += '  %%pe_%s_%d = zext i32 %s to i64\n' % (f, k, nm); a.append('%%pe_%s_%d' % (f, k))
    a = (a + ['0'] * 4)[:4]
    call = ('  call void @m11_pw(i64 %d)\n' % int(f, 16)) if WATCH else pre + '  call void @m11_pe(i64 %d, i64 %s, i64 %s, i64 %s, i64 %s)\n' % (int(f, 16), *a)
    src = src[:m.end()] + call + src[m.end():]; n += 1
src += '\ndeclare void @m11_pe(i64, i64, i64, i64, i64)\ndeclare void @m11_pw(i64)\n'
open(os.path.join(out, 'boot_probe.ll'), 'w').write(src)
open(os.path.join(out, 'probe.c'), 'w').write(r'''#include <stdio.h>
#include <stdint.h>
typedef unsigned long long u64;
static int ok(u64 x) { return x >= 0x10000 && x < 0x20000000; }
static u64 q(u64 x) { return ok(x) ? *(volatile u64*)(uintptr_t)x : 0xdeadULL; }
static int in_img(u64 x) { return x >= 0x10000 && x < 0x20000000; }
static u64 rd64(u64 x) { return in_img(x) ? *(volatile u64*)(uintptr_t)x : 0xdeadULL; }
static u64 rd8(u64 x) { return in_img(x) ? *(volatile unsigned char*)(uintptr_t)x : 0xdeadULL; }
/* a1 / a2 と, a1 をオブジェクトとみた [a1] [a1+8] [[a1+8]+8] [[a1+8]+0x10] (TList: FItems / Count 位置) を出す */
void m11_pe(u64 fn, u64 a1, u64 a2, u64 a3, u64 a4) {
    u64 l = q(a1 + 8);
    fprintf(stderr, "[pe] %llx a=%llx %llx %llx %llx | [a1]=%llx [a1+8]=%llx [[a1+8]+8]=%llx [[a1+8]+0x10]=%llx\n", fn, a1, a2, a3, a4, q(a1), l, q(l + 8), q(l + 0x10));
    if (fn == 0x407a50ULL) { u64 p = a1 - 8; fprintf(stderr, "[raw407] a1=%llx p=%llx v=%llx\n", a1, p, rd64(p));
        if (a1 < 2601) { u64 b = rd8(18770492ULL + (a1 + 7) / 8); u64 rb = 16404744ULL + 16 * b; u64 n = rd64(rb + 8); u64 m = rd64(n + 24); fprintf(stderr, "[chain407] b=%llx rbx=%llx n=%llx m=%llx m-8=%llx\n", b, rb, n, m, m - 8); } }
    if (fn == 0x412e40ULL && a2 <= 16) { for (u64 i = 0; i < a2; i++) { u64 s = a1 + 8 * i; fprintf(stderr, "[arr412] n=%llx i=%llx slot=%llx\n", a2, i, in_img(s) ? *(volatile u64*)(uintptr_t)s : 0xdeadULL); } }
}
''')
if WATCH:   # 各 fn 入口で chain を読み, 前回から値が変わっていたら「直前の fn の入口〜この fn の入口の間」に書込みがあったと出す
    offs = [int(x, 16) for x in WATCH.split(':')]
    open(os.path.join(out, 'probe.c'), 'a').write(r'''
static u64 w_last = 0, w_prev = ~0ULL; static const unsigned long long W[] = {%s};
void m11_pw(u64 fn) {
    u64 a = W[0], v = 0; int ok_ = 1;
    for (unsigned k = 1; k < sizeof W / sizeof W[0] + 1; k++) { if (!ok(a)) { ok_ = 0; break; } v = *(volatile u64*)(uintptr_t)a; a = v + (k < sizeof W / sizeof W[0] ? W[k] : 0); }
    u64 cur = ok_ ? v : 0xdeadULL;
    if (cur != w_prev) { fprintf(stderr, "[chg] %%llx -> %%llx (前の入口 fn=%%llx, 今の入口 fn=%%llx)\n", w_prev, cur, w_last, fn); w_prev = cur; }
    w_last = fn;
}
''' % ', '.join('0x%x' % o for o in offs))
print('probed', n, 'of', len(fns))
