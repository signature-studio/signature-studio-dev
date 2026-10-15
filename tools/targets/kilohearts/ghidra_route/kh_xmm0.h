/* kh_xmm0.h — Stereo の callee の戻り xmm0 (縮約後の double) を機械語から確定した式で C 化する helper (KH-74・#3853)。
 * ghidra_to_c.py が stereo の出力 C に丸ごと入れる。呼出元の extraout_XMM0_Qa* は kh_xmm0_<va> を読む。
 * 式の根拠 (capstone 逆アセンブル): FUN_180fdc660 の ret は 180fdc6d6 の 1 本。xmm0 は 180fdc6c5 の vmovapd xmm0,xmm2 で
 * t2 = fma(-k, m2, t1)、t1 = fma(-k, m1, x)、k = fma(x, 2/pi, 1.5*2^52) - 1.5*2^52 (= xmm1)。
 * 数値突合は xmm0_check.c (native 実行と bit 一致)。 */
#include <math.h>
#include <stdint.h>
#include <string.h>
#include <string.h>

static double kh_xmm0_180fdc660;

static inline unsigned kh_fn_180fdc660(double x) {
    const double kM = 0x1.45f306dc9c883p-1, kK2 = 0x1.8000000000000p+52;
    const double kM1 = 0x1.921fb54442d18p+0, kM2 = 0x1.1a62633145c00p-54;
    double k = fma(x, kM, kK2) - kK2;
    double t1 = fma(-k, kM1, x);
    int32_t ki = (k > -2147483649.0 && k < 2147483648.0) ? (int32_t)k : INT32_MIN;
    kh_xmm0_180fdc660 = fma(-k, kM2, t1);
    return (unsigned)(ki & 3);
}


/* FUN_180fdfdb0 (KH-77・#3885): 三角関数の引数縮約。ret は 180fdffb6 の 1 本。戻り rax = 四分象限 (k & 3)、戻り xmm0 = 縮約値。
 * 戻り xmm1 (残差・1e-19 台) は kh_xmm1_180fdfdb0 として式だけ持つ (KH-114・#4705)。呼出元 180fcd9c8・180fce43e への配線は未対応 (子 issue)。
 * 機械語 132 命令の順で写す。table = PE 0x18228ac50 の 168 B。定数 (c1 = 0x18228ab30・c2 = ...ab40・c3 = ...ab50) は bit パターンで置く。
 * 入力は ABS (符号 0)。m = 仮数 + 暗黙の 1。table の 3 語 (A, Bl, Bh) と m の 64×64→128 積を 128bit 整数で足し、正規化して d0 (上 53bit) と rr (下位) を作る。 */
static const unsigned char kh_tab_180fdfdb0[168] = {
    0xe0, 0xf1, 0x1b, 0xc1, 0x0c, 0x58, 0x21, 0x74, 0x35, 0x7e, 0xc4, 0x7e,
    0xed, 0xaf, 0xa9, 0x4b, 0x4a, 0x29, 0xde, 0xe7, 0x1c, 0xf4, 0xec, 0xc5,
    0x97, 0xaf, 0x1f, 0xeb, 0x9e, 0xd4, 0xb5, 0xa8, 0x7f, 0x79, 0x9a, 0xfd,
    0x18, 0x3d, 0xdd, 0x26, 0x2c, 0x9f, 0x3c, 0xfb, 0xd9, 0xb4, 0x7d, 0xb4,
    0x29, 0x68, 0x2d, 0x46, 0xbc, 0xbc, 0x3f, 0x60, 0x16, 0x78, 0xff, 0x5f,
    0xe2, 0x7f, 0xec, 0xa0, 0xe4, 0xf7, 0x2e, 0x7e, 0x11, 0x72, 0xd2, 0xe7,
    0x4c, 0x0d, 0xe6, 0x58, 0x47, 0xe6, 0x04, 0xf9, 0x7d, 0xd1, 0x9a, 0xc0,
    0x71, 0xa6, 0x13, 0x12, 0xed, 0xba, 0xd4, 0xd7, 0x08, 0xa2, 0xfb, 0x9c,
    0xa6, 0xc4, 0x72, 0xac, 0x77, 0xf8, 0x73, 0x48, 0x46, 0x27, 0xa8, 0xbb,
    0x24, 0x19, 0x80, 0x4b, 0x37, 0x09, 0xe9, 0xb8, 0x91, 0xdc, 0x86, 0x15,
    0xef, 0x7a, 0xaf, 0x8e, 0x45, 0xf9, 0x07, 0x41, 0x0e, 0xf1, 0x64, 0x56,
    0x8a, 0x6d, 0x03, 0x77, 0xd3, 0xd4, 0x47, 0x5f, 0x9d, 0xf0, 0xa7, 0x54,
    0x10, 0x39, 0xb9, 0x0d, 0xe6, 0x8b, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x55, 0x55, 0x55, 0x55, 0x55, 0x55, 0xa5, 0x3f,
};
static double kh_xmm0_180fdfdb0, kh_xmm1_180fdfdb0;
static inline uint64_t kh_bits(double d) { uint64_t u; memcpy(&u, &d, 8); return u; }
static inline double kh_dbl(uint64_t u) { double d; memcpy(&d, &u, 8); return d; }
static inline uint64_t kh_bsr64(uint64_t v) { return v ? 63 - (uint64_t)__builtin_clzll(v) : 0; }
static inline unsigned kh_fn_180fdfdb0(double x) {
    const double kPiH = kh_dbl(0x3ff921fb54442d18ull), kPiT = kh_dbl(0x3c91a62633145c06ull);
    const double kPiA = kh_dbl(0x3ff921fb50000000ull), kPiB = kh_dbl(0x3e5110b460000000ull);
    uint64_t bits = kh_bits(x), e, p, A, Bl, Bh, m, r8, r9, r10, rdx, rax, quad, j, c, idx, hb, L, b9;
    unsigned __int128 pa, pb, pc, sb;
    int cf;
    double d0, rr, hh, ll, x0, x0t, t, v;
    e = (bits >> 52) - 0x3ff;
    p = 0x86 - (e >> 3);
    memcpy(&A, kh_tab_180fdfdb0 + p, 8);
    memcpy(&Bl, kh_tab_180fdfdb0 + p + 8, 8);
    memcpy(&Bh, kh_tab_180fdfdb0 + p + 16, 8);
    m = ((bits << 12) >> 12) | (1ull << 52);
    pa = (unsigned __int128)A * m;
    r8 = (uint64_t)pa;
    r10 = (uint64_t)(pa >> 64);
    pb = (unsigned __int128)Bl * m;
    j = e & 7;
    sb = pb + (r10);
    r9 = (uint64_t)sb;
    r10 = (uint64_t)(sb >> 64);
    pc = (unsigned __int128)Bh * m;
    r10 += (uint64_t)pc;
    c = 0x36 - j;
    cf = (int)((r10 >> (c - 1)) & 1);
    rax = r10 >> c;
    rdx = 0;
    if (cf) { r10 = ~r10; r9 = ~r9; r8 = ~r8; rdx = 0x8000000000000000ull; }
    rax += (uint64_t)cf;
    quad = rax & 3;
    c = j + 10;
    r10 = (r10 << c) >> c;
    e = c - 0x40;
    if (r10 == 0) { r10 = r9; r9 = r8; r8 = 0; e -= 0x40; }
    idx = kh_bsr64(r10);
    e += idx;
    int64_t s = (int64_t)idx - 52;
    if (s > 0) { r8 = r10; r10 >>= s; r9 >>= s; r8 <<= (64 - s); r9 |= r8; }
    else if (s < 0) { L = (uint64_t)(-s); rax = r9; r10 <<= L; r9 <<= L; rax >>= (64 - L); r10 |= rax; r8 >>= (64 - L); r9 |= r8; }
    e += 0x3ff;
    r10 &= ~(1ull << 52);
    r10 |= rdx;
    r10 |= e << 52;
    d0 = kh_dbl(r10);
    b9 = kh_bsr64(r9);
    r9 = (r9 << ((64 - b9) & 63)) >> 12;
    e -= (64 - b9) + 0x34;
    r9 = (r9 | rdx) | (e << 52);
    rr = kh_dbl(r9);
    hb = kh_bits(d0) & ~((1ull << 27) - 1);
    hh = kh_dbl(hb);
    ll = d0 - hh;
    x0 = d0 * kPiH;
    x0t = d0 * kPiT;
    t = (kPiA * hh - x0) + kPiA * ll;
    t = t + kPiB * hh;
    v = x0t + rr * kPiH;
    t = t + kPiB * ll;
    t = t + v;
    kh_xmm0_180fdfdb0 = x0 + t;
    kh_xmm1_180fdfdb0 = t + (x0 - kh_xmm0_180fdfdb0);
    return (unsigned)quad;
}
