#!/usr/bin/env python3
"""kh709_ymm_check.py — license/lift/gen_simd.py の i256 (VEX.256) 整数語彙の bit-exact 単体検証 (#709 / KH-14).

  python3 license/scripts/kh709_ymm_check.py [N] [SEED]      (既定 N=20000 SEED=1)

1. RetDec 形の宣言 (declare i256 @__asm_vpcmpeqb/w/d, i32 @__asm_vpmovmskb, i256 @__asm_vinsertf128) を
   lift/gen_simd.py に通し、.i256.ll (LLVM IR 定義) を得る。
2. それを呼ぶ driver (load / call / store, align 1) を IR で書き、ホスト clang で obj 化する。
3. ホスト AVX2 の _mm256_cmpeq_epi8/16/32・_mm256_movemask_epi8・_mm256_insertf128_si256 と
   harness 内の乱数入力で 32B 全 bit を突合する。
ネガコン: vpcmpeqd の icmp eq → ne に差し替えると不一致 > 0 (FAIL) を確認する。
exit 0 = 本検証が全 bit 一致 かつ ネガコンが FAIL。成果物は license/work/ymm_check/ (gitignore 対象)。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIC = os.path.dirname(HERE)
GEN = os.path.join(LIC, 'lift', 'gen_simd.py')
W = os.path.join(LIC, 'work', 'ymm_check')

DECLS = ('declare i256 @__asm_vpcmpeqb(i256, i256)\n'
         'declare i256 @__asm_vpcmpeqw(i256, i256)\n'
         'declare i256 @__asm_vpcmpeqd(i256, i256)\n'
         'declare i32 @__asm_vpmovmskb(i256)\n'
         'declare i256 @__asm_vinsertf128(i256, i128, i8)\n')

DRIVER = '''
define void @drv_cmpeqb(ptr %pa, ptr %pb, ptr %pr) {
  %a = load i256, ptr %pa, align 1
  %b = load i256, ptr %pb, align 1
  %r = call i256 @__asm_vpcmpeqb(i256 %a, i256 %b)
  store i256 %r, ptr %pr, align 1
  ret void
}
define void @drv_cmpeqw(ptr %pa, ptr %pb, ptr %pr) {
  %a = load i256, ptr %pa, align 1
  %b = load i256, ptr %pb, align 1
  %r = call i256 @__asm_vpcmpeqw(i256 %a, i256 %b)
  store i256 %r, ptr %pr, align 1
  ret void
}
define void @drv_cmpeqd(ptr %pa, ptr %pb, ptr %pr) {
  %a = load i256, ptr %pa, align 1
  %b = load i256, ptr %pb, align 1
  %r = call i256 @__asm_vpcmpeqd(i256 %a, i256 %b)
  store i256 %r, ptr %pr, align 1
  ret void
}
define void @drv_movmskb(ptr %pa, ptr %pb, ptr %pr) {
  %a = load i256, ptr %pa, align 1
  %r = call i32 @__asm_vpmovmskb(i256 %a)
  store i32 %r, ptr %pr, align 1
  ret void
}
define void @drv_insertf128(ptr %pa, ptr %pb, ptr %pr) {
  %a = load i256, ptr %pa, align 1
  %b = load i128, ptr %pb, align 1
  %r0 = call i256 @__asm_vinsertf128(i256 %a, i128 %b, i8 0)
  store i256 %r0, ptr %pr, align 1
  %pr1 = getelementptr i8, ptr %pr, i64 32
  %r1 = call i256 @__asm_vinsertf128(i256 %a, i128 %b, i8 1)
  store i256 %r1, ptr %pr1, align 1
  ret void
}
'''

HARNESS = r'''
#include <immintrin.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
void drv_cmpeqb(const void*, const void*, void*);
void drv_cmpeqw(const void*, const void*, void*);
void drv_cmpeqd(const void*, const void*, void*);
void drv_movmskb(const void*, const void*, void*);
void drv_insertf128(const void*, const void*, void*);
static unsigned long long s;
static unsigned rnd(void) { s ^= s << 13; s ^= s >> 7; s ^= s << 17; return (unsigned)s; }
static void fill(unsigned char *p, int n) {
  for (int i = 0; i < n; i++) p[i] = (unsigned char)rnd();
  if (rnd() % 4 == 0) for (int i = 0; i < n; i++) if (rnd() % 3 == 0) p[i] = 0;
}
int main(int argc, char **argv) {
  int N = argc > 1 ? atoi(argv[1]) : 20000;
  s = argc > 2 ? strtoull(argv[2], 0, 10) * 2654435761ULL + 1 : 1;
  long mism = 0, cases = 0;
  unsigned char a[32] __attribute__((aligned(32))), b[32] __attribute__((aligned(32)));
  unsigned char got[64] __attribute__((aligned(32))), ref[64] __attribute__((aligned(32)));
  unsigned char b128[16];
  for (int t = 0; t < N; t++) {
    fill(a, 32); fill(b, 32);
    __m256i va = _mm256_loadu_si256((const __m256i*)a), vb = _mm256_loadu_si256((const __m256i*)b);
    memset(got, 0xAA, sizeof got); memset(ref, 0xAA, sizeof ref);
    drv_cmpeqb(a, b, got); _mm256_storeu_si256((__m256i*)ref, _mm256_cmpeq_epi8(va, vb));
    cases++; if (memcmp(got, ref, 32)) mism++;
    drv_cmpeqw(a, b, got); _mm256_storeu_si256((__m256i*)ref, _mm256_cmpeq_epi16(va, vb));
    cases++; if (memcmp(got, ref, 32)) mism++;
    drv_cmpeqd(a, b, got); _mm256_storeu_si256((__m256i*)ref, _mm256_cmpeq_epi32(va, vb));
    cases++; if (memcmp(got, ref, 32)) mism++;
    drv_movmskb(a, b, got); int m = _mm256_movemask_epi8(va); memcpy(ref, &m, 4);
    cases++; if (memcmp(got, ref, 4)) mism++;
    fill(b128, 16);
    __m128i xb = _mm_loadu_si128((const __m128i*)b128);
    memset(got, 0xAA, sizeof got); memset(ref, 0xAA, sizeof ref);
    drv_insertf128(a, b128, got);
    _mm256_storeu_si256((__m256i*)ref, _mm256_insertf128_si256(va, xb, 0));
    _mm256_storeu_si256((__m256i*)(ref + 32), _mm256_insertf128_si256(va, xb, 1));
    cases++; if (memcmp(got, ref, 64)) mism++;
  }
  printf("ymm_check cases=%ld mismatch=%ld\n", cases, mism);
  return mism != 0;
}
'''


def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-3000:])
        raise SystemExit('FAILED: ' + cmd[:200])
    return r


def build(tag, decl_text, mutate=None):
    d = os.path.join(W, tag)
    os.makedirs(d, exist_ok=True)
    decl = os.path.join(d, 'decl.ll')
    open(decl, 'w').write(decl_text)
    run('python3 %s %s %s' % (GEN, decl, os.path.join(d, 'simd.c')))
    ll = os.path.join(d, 'simd.c.i256.ll')
    if mutate:
        txt = open(ll).read()
        assert mutate[0] in txt, 'mutation anchor missing'
        open(ll, 'w').write(txt.replace(mutate[0], mutate[1], 1))
    open(os.path.join(d, 'drv.ll'), 'w').write(decl_text + DRIVER)
    open(os.path.join(d, 'h.c'), 'w').write(HARNESS)
    run('clang -O1 -c %s -o %s' % (ll, os.path.join(d, 'gen.o')))
    run('clang -O1 -c %s -o %s' % (os.path.join(d, 'drv.ll'), os.path.join(d, 'drv.o')))
    run('clang -O1 -mavx2 %s %s %s -o %s' % (os.path.join(d, 'h.c'), os.path.join(d, 'gen.o'),
                                          os.path.join(d, 'drv.o'), os.path.join(d, 'chk')))
    r = subprocess.run([os.path.join(d, 'chk'), str(N), str(SEED)], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 1

rc, out = build('pos', DECLS)
print('[pos] ' + out)
ok = rc == 0
# ネガコン: vpcmpeqd の icmp eq → ne に変えると不一致が出て FAIL になること
rc_nc, out_nc = build('nc_cmpeqd_ne', DECLS, mutate=('icmp eq <8 x i32>', 'icmp ne <8 x i32>'))
print('[nc] vpcmpeqd eq→ne: ' + out_nc + ' (rc=%d)' % rc_nc)
nc_fail = rc_nc != 0
print('RESULT: %s (positive=%s, negctrl_detected=%s)' % ('PASS' if ok and nc_fail else 'FAIL', ok, nc_fail))
sys.exit(0 if ok and nc_fail else 1)
