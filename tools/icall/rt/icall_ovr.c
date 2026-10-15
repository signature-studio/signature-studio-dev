/* icall_ovr.c — CRT エラー報告経路の override (tools/ott/rt/ott_ovr.c の BLK memory-ABI 移植)。
 * 対象: 1801c8c00 _handle_error(double) / 1801c8cb8 _handle_errorf(float) / 1801a9a6c sqrt wrapper / 1801a9b38 sqrtf wrapper。
 *       (1801c8cb8 は F の外 (呼出し元 1801c8c98 も F 外) のため ott_route.sh が ICALL_EXTRA_ROOTS で root に足す)
 * 理由: DLL の CRT は DllMain 未実行 (= 暗号化 fn ptr 未初期化) だと、これらが未登録の間接 call target へ落ちて fail-fast する。
 *       native 参照も同経路で SIGSEGV するため、UCRT の観測可能な意味 (戻り値) だけを実装する (導出根拠は ott_ovr.c 冒頭)。
 * BLK: +0x28 xmm0 low64 / +0x30 xmm1 low64 / +0x88 戻り xmm0 low64。 */
#include <stdint.h>
#include <math.h>
#include <string.h>
#ifdef ICALL_BLK_GLOBAL   /* #2865: IR の @__icall_blk (icall_rt.c が定義) と同じ global を使う */
extern unsigned char __icall_blk[0x200];
#define BLK_ADDR ((uintptr_t)__icall_blk)
#else
#ifndef ICALL_BLK
#define ICALL_BLK 0x34308000u
#endif
#define BLK_ADDR ((uintptr_t)ICALL_BLK)
#endif
#define BLKQ(off) (*(volatile uint64_t*)(BLK_ADDR + (off)))

/* _handle_error(double): 返り値 xmm0 = 呼出側が渡した retval (xmm1) */
long long function_1801c8c00(long long arg1) { (void)arg1; BLKQ(0x88) = BLKQ(0x30); return 0; }

/* _handle_errorf(float): native も movaps xmm0, xmm6 (= 入力 xmm1 全体) を返す。上位 lane も xmm1 のまま */
long long function_1801c8cb8(long long arg1) { (void)arg1; BLKQ(0x88) = BLKQ(0x30); return 0; }

/* sqrt(double): x<0 → -nan(ind), NaN → quiet 化して伝播, それ以外 sqrt */
long long function_1801a9a6c(void) {
    uint64_t in = BLKQ(0x28); double x; memcpy(&x, &in, 8);
    uint64_t out;
    if (x != x) out = in | 0x0008000000000000ull;
    else if (x < 0) out = 0xfff8000000000000ull;
    else { double r = sqrt(x); memcpy(&out, &r, 8); }
    BLKQ(0x88) = out;
    return 0;
}

/* sqrtf wrapper: 上位 32bit は xmm0 の入力値を保持 */
long long function_1801a9b38(void) {
    uint64_t in = BLKQ(0x28); uint32_t lo = (uint32_t)in; float x; memcpy(&x, &lo, 4);
    uint32_t o;
    if (x != x) o = lo | 0x00400000u;
    else if (x < 0) o = 0xffc00000u;
    else { float r = sqrtf(x); memcpy(&o, &r, 4); }
    BLKQ(0x88) = (in & ~0xffffffffull) | o;
    return 0;
}
