#!/usr/bin/env python3
"""kh52_sse_check.py — license/lift/gen_simd.py の SSE 語彙 6 件 (KH-52 / #3307) の bit-exact 単体検証.

  python3 license/scripts/kh52_sse_check.py [N] [SEED]      (既定 N=200000 SEED=12345)

1. RetDec 形の宣言 (pcmpeqd/pcmpeqw/pmovmskb/pshufd/vpxor/tzcnt) を lift/gen_simd.py に通し C を得る。
2. ホスト SSE2 intrinsics (_mm_cmpeq_epi32/16・_mm_movemask_epi8・_mm_shuffle_epi32・_mm_xor_si128) と
   ctz の結果を、乱数入力 (一致/不一致を混ぜる) で 128bit 全 bit 突合する。
ネガコン: pcmpeqd の比較を反転すると不一致 > 0 (FAIL) になることを確認する。
exit 0 = 全 bit 一致 かつ ネガコンが FAIL。作業は license/work/sse6/ (gitignore 対象)。
"""
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIC = os.path.dirname(HERE)
GEN = os.path.join(LIC, 'lift', 'gen_simd.py')
W = os.path.join(LIC, 'work', 'sse6')

DECLS = ('declare i128 @__asm_pcmpeqd(i128, i128)\n'
         'declare i128 @__asm_pcmpeqw(i128, i128)\n'
         'declare i32 @__asm_pmovmskb(i128)\n'
         'declare i128 @__asm_pshufd(i128, i8)\n'
         'declare i128 @__asm_vpxor(i128, i128)\n'
         'declare i32 @__asm_tzcnt(i32)\n')

HEAD = r'''#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <immintrin.h>
typedef unsigned __int128 u128; typedef uint64_t u64; typedef uint32_t u32; typedef uint8_t u8;
typedef union { u128 q; u32 w[4]; u64 d[2]; float f[4]; double g[2]; } L128;
'''

MAIN = r'''
static u128 rnd(void) { u128 x = 0; for (int i = 0; i < 4; i++) x = (x << 32) | (u32)(rand() * 2654435761u); return x; }
static u128 from(__m128i v) { u128 r; memcpy(&r, &v, 16); return r; }
static __m128i to(u128 q) { __m128i v; memcpy(&v, &q, 16); return v; }
static __m128i shuf_host(__m128i v, int imm) {
  switch (imm) {
SHUF_CASES
  }
  return v;
}
int main(int argc, char **argv) {
  long n = argc > 1 ? atol(argv[1]) : 200000, bad = 0;
  srand(argc > 2 ? (unsigned)atol(argv[2]) : 12345);
  for (long t = 0; t < n; t++) {
    u128 a = rnd(), b = rnd();
    if (t % 5 == 0) b = a;
    if (t % 7 == 0) ((u32 *)&b)[1] = ((u32 *)&a)[1];
    if (t % 3 == 0) ((uint16_t *)&b)[5] = ((uint16_t *)&a)[5];
    u8 imm = (u8)rand();
    u32 x = (u32)rand() * 7u; if (t % 11 == 0) x = 0;
    u128 g1 = __asm_pcmpeqd(a, b), h1 = from(_mm_cmpeq_epi32(to(a), to(b)));
    u128 g2 = __asm_pcmpeqw(a, b), h2 = from(_mm_cmpeq_epi16(to(a), to(b)));
    u32 g3 = __asm_pmovmskb(a), h3 = (u32)_mm_movemask_epi8(to(a));
    u128 g4 = __asm_pshufd(a, imm), h4 = from(shuf_host(to(a), imm));
    u128 g5 = __asm_vpxor(a, b), h5 = from(_mm_xor_si128(to(a), to(b)));
    u32 g6 = __asm_tzcnt(x), h6 = x ? (u32)__builtin_ctz(x) : 32u;
    if (g1 != h1 || g2 != h2 || g3 != h3 || g4 != h4 || g5 != h5 || g6 != h6) bad++;
  }
  printf("sse6 cases=%ld mismatch=%ld\n", n, bad);
  return bad != 0;
}
'''


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def build(tag, gen_c_text):
    os.makedirs(W, exist_ok=True)
    body = os.path.join(W, tag + '.c')
    src = HEAD + gen_c_text + MAIN.replace('SHUF_CASES', ''.join('    case %d: return _mm_shuffle_epi32(v, %d);\n' % (i, i) for i in range(256)))
    open(body, 'w').write(src)
    exe = os.path.join(W, tag)
    r = run(['cc', '-O1', '-msse2', '-Wall', '-o', exe, body])
    if r.returncode:
        print(r.stderr[-2000:])
        raise SystemExit('build failed: ' + tag)
    return exe


def main():
    os.makedirs(W, exist_ok=True)
    ll = os.path.join(W, 'sse6.ll')
    gen_c = os.path.join(W, 'sse6.c')
    open(ll, 'w').write(DECLS)
    r = run([sys.executable, GEN, ll, gen_c])
    print(r.stdout.strip())
    if r.returncode:
        print(r.stderr[-2000:])
        raise SystemExit(1)
    lines = [l for l in open(gen_c).read().splitlines() if l.startswith('EX ')]
    text = '\n'.join(l.replace('EX ', 'static ', 1) for l in lines) + '\n'
    args = sys.argv[1:3]
    exe = build('pos', text)
    rp = run([exe] + args)
    print(rp.stdout.strip())
    pos_ok = rp.returncode == 0
    # ネガコン: pcmpeqd の比較を反転 (== → !=) すると不一致が出ること
    neg_text = text.replace('(x_a0.w[i] == x_a1.w[i])', '(x_a0.w[i] != x_a1.w[i])', 1)
    if neg_text == text:
        raise SystemExit('negctrl pattern not found in generated C')
    rn = run([build('neg', neg_text)] + args)
    print(rn.stdout.strip())
    neg_detected = rn.returncode != 0
    ok = pos_ok and neg_detected
    print('RESULT: %s (positive=%s, negctrl_detected=%s)' % ('PASS' if ok else 'FAIL', pos_ok, neg_detected))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
