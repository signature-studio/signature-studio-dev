/* CAB-245 (IPP-5 ipp-fill-2): ippiResizeSqrPixel_8u_{C1,C3,C4}R + GetBufSize 2 関数の実装。
   契約: ../impl/README.md — 宣言は ../gen/ipp_proto.h と一致 (コンパイラが署名検査)。

   実装モデルの根拠 (実 win64 dsp_ippv2 DLL を pe_load ネイティブ実行してフィット, 詳細 shim/REPORT §12):
   - 座標パイプライン (実 DLL の逆アセ/実測から Q16 固定小数点と特定):
       inv16   = trunc(65536 / factor)
       u16     = (((x + 0.5) * 65536 - sx16) * inv16) >> 16 - srcRoi.x*65536   (sx16 = round(xShift*65536))
     ここで x は dst の「絶対座標」(dstRoi.x + dx)、u は srcRoi 相対座標。
     実測 (noop_check): srcRoi=(4,0,8,8) fx=0.5 で dst x=2..5 に書込 — u = (x+0.5)/fx − srcRoi.x のみ整合。
     p = u16/65536 - 0.5 (位相), i = floor(p)。
     NN の index は u16 から直接: idx = (u16 - 1) >> 16 (= round-half-down(u-0.5) の Q16 版)。
     実測: fx=0.7 で double 誤差 (u=15.000000000000002) と Q16 (14.99998) を区別するケースが存在。
   - 書込み条件: 0 <= u <= srcRoi.width かつ 0 <= v <= srcRoi.height の dst 画素のみ書込
     (範囲外は dst を触らない — probe5/6 実測)。1 つも書込可能画素が無ければ status 1 で無操作。
   - 補間カーネル (1D, 位相 a = frac(p)):
     LINEAR : 2 tap, w = (1-a, a)
     CUBIC  : 4 tap, f(d)=0.5d^3-d^2-0.5d+1 (d<=1), f(d)=-(1/6)(d-1)(d-2)(d-3) (1<d<=2)
              (全位相で partition of unity — fit13 実測フィット)
     LANCZOS: 8 tap, f(d)=sinc(d)sinc(d/3) (|d|<3)
     SUPER  : 面積平均。footprint [start, start+1/fx), start=(x-sx)/fx (Q16),
              ROI 外の面積はエッジ画素に畳み込み (fold), 総面積 (fold 込み) で正規化
              (spike 重み表と全一致: fx=0.3/0.5/0.75 × sx=0/0.25/0.5/0.75)
   - 出力丸め: round-half-up。実 DLL は重み量子化の独自経路を持ち、255·w が .5 近傍
     (±0.006) の位相で ±1 差が生じうる → 実測率を REPORT §12-5 に記録 (受入条件の許容差)。
   - interp は {1,2,4,5,6,7,8,16} のみ有効 (probe3-E 実測)。本実装は 5/6/7 を 4 (CUBIC) として処理
      (6 の H-pass 重みは cubic と一致, 5/7 は独立カーネル — 実 DLL とは it5 14.5% / it7 13.2% の画素差が残る, REPORT §12-4)。
     それ以外は -22。factor <= 0 → -23、Super で factor > 1 → -23 (実測)。
     srcSize/ROI 寸法 < 1 → -6。NULL (src/dst/pBuffer) → -8。
   - GetBufSize 2 関数:
     ippiResizeSqrPixelGetBufSize は実 DLL が「常時 -8・書込なし」(逆アセ mov eax,-8; ret 実測 +
     全数グリッド probe1-B) のため同一挙動。ippiResizeGetBufSize は実測式
     (密グリッド dw<=96/dh<=48 でフィット — REPORT §12-3)。ch=2 は -53 (実測)。 */
#include "ipp_min.h"
#include "../gen/ipp_proto.h"
#include <math.h>
#include <stdlib.h>

#define IPP_STS_BADARG     (-5)
#define IPP_STS_SIZE       (-6)
#define IPP_STS_NULL       (-8)
#define IPP_STS_NOOP       (1)
#define IPP_STS_FACTOR     (-23)  /* 実測: factor<=0 / Super で factor>1 */
#define IPP_STS_INTERP     (-22)  /* 実測: 未対応 interp */
#define IPP_STS_CH2        (-53)  /* 実測: ResizeGetBufSize ch=2 */

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static int interp_ok(int it) {
  return it == 1 || it == 2 || it == 4 || it == 5 || it == 6 || it == 7 || it == 8 || it == 16;
}
static int interp_base(int it) { return it == 5 ? 35 : ((it == 6 || it == 7) ? 4 : it); }

static Ipp8u clamp_u8(double v) {
  long r = (long)(v + 0.5);  /* round-half-up (可搬: lround のプラットフォーム差を排除) */
  if (r < 0) return 0;
  if (r > 255) return 255;
  return (Ipp8u)r;
}

/* cubic convolution (実測フィット核) */
static double ker_cubic(double d) {
  if (d < 1.0) return 0.5 * d * d * d - d * d - 0.5 * d + 1.0;
  if (d <= 2.0) { double q = d - 1.0; return -(1.0 / 6.0) * q * (q - 1.0) * (q - 2.0); }
  return 0.0;
}
/* interp 5 (CUBIC2P 系) = 3 次 B-スプライン (実測: work/resize/sp57.c + sweep2 の spike で
   位相 64 点の 1D 重みを抽出 → bspl3 が 0/64 mismatch で一致、ゲイン 255*5/6=212.5)。
   分離実装では重みの和が 1 になるよう正規化して使う (clamp_u8 は round-half-up)。 */
static double ker_bspl3(double d) {
  double a = fabs(d);
  if (a < 1.0) return 2.0 / 3.0 - a * a + a * a * a / 2.0;
  if (a < 2.0) { double q = 2.0 - a; return q * q * q / 6.0; }
  return 0.0;
}
/* 可搬 sin(pi*d) (d ∈ [0,3]): native/wasm で同一演算順序 (libm 差異の排除, wasm 突合用)。
   sin(x)/x の テイラー (|x| <= pi/2, x^21/21! ~ 3e-16 まで) を Horner で評価。 */
static double sin_pi(double d) {
  int n = (int)floor(d + 0.5);          /* 最近接整数 */
  double r = d - (double)n;             /* |r| <= 0.5 */
  double x = M_PI * r;
  double x2 = x * x;
  /* sin(x)/x = Σ_{k=0..10} (−1)^k x^{2k}/(2k+1)! */
  static const double FACT[10] = {6.0, 120.0, 5040.0, 362880.0, 39916800.0, 6227020800.0,
                                  1307674368000.0, 355687428096000.0, 121645100408832000.0,
                                  51090942171709440000.0};
  double xx = x2;
  double sign = -1.0;
  double sum = 1.0;
  for (int k = 0; k < 10; k++) {
    sum += sign * xx / FACT[k];
    xx *= x2;
    sign = -sign;
  }
  return (n % 2 == 0 ? 1.0 : -1.0) * x * sum;
}

static double ker_lanczos(double d) {
  if (d < 3.0) {
    if (d < 1e-12) return 1.0;
    double s1 = sin_pi(d) / (M_PI * d);
    double s2 = sin_pi(d / 3.0) / (M_PI * d / 3.0);
    return s1 * s2;
  }
  return 0.0;
}

/* Q16 パイプライン: u16 = (((x+0.5)*65536 - sx16) * inv16) >> 16 */
static void q16_init(double factor, double shift, int *inv16, int *sx16) {
  *inv16 = (int)(65536.0 / factor);  /* trunc (実測: fx=0.7/0.9/2.3 の NN index と一致) */
  *sx16 = (int)floor(shift * 65536.0 + 0.5);
}
static int q16_u(int x, int inv16, int sx16) {
  return (int)(((int64_t)((x * 65536 + 32768) - sx16) * inv16) >> 16);
}
/* ROI 相対 u16: 絶対 dst 座標 x から ROI 原点分を差し引く */
static int q16_ur(int x, int inv16, int sx16, int roi0) {
  return q16_u(x, inv16, sx16) - roi0 * 65536;
}

/* 分離核のタップ重み (p は Q16 由来の double)。戻り: ntap, *base = 先頭 tap の src index */
static int build_taps(int mode, double p, int *base, double w[8]) {
  int i0 = (int)floor(p);
  double a = p - i0;
  int n = 0;
  if (mode == 2) {
    w[0] = 1.0 - a; w[1] = a; *base = i0; return 2;
  }
  if (mode == 4) {
    *base = i0 - 1;
    for (int t = 0; t < 4; t++) { w[n++] = ker_cubic(fabs(p - (i0 - 1 + t))); }
    return 4;
  }
  if (mode == 35) {
    /* interp 5: 3 次 B-スプライン。窓は [i0-1, i0+2] の 4 タップ (実測 sp57/sweep2)。
       和が 1 になるよう正規化 (分離路の clamp_u8 は round-half-up で 0..255 を期待)。 */
    *base = i0 - 1;
    double s = 0.0;
    for (int t = 0; t < 4; t++) { double v = ker_bspl3(p - (i0 - 1 + t)); w[t] = v; s += v; }
    if (s > 0.0) for (int t = 0; t < 4; t++) w[t] /= s;
    return 4;
  }
  *base = i0 - 3;
  for (int t = 0; t < 8; t++) { w[n++] = ker_lanczos(fabs(p - (i0 - 3 + t))); }
  return 8;
}

/* 共通本体: ch = 1/3/4 */
static IppStatus resize_sqrpixel(const Ipp8u *pSrc, IppiSize srcSize, int srcStep, IppiRect srcRoi,
                                 Ipp8u *pDst, int dstStep, IppiRect dstRoi,
                                 double xFactor, double yFactor, double xShift, double yShift,
                                 int interpolation, Ipp8u *pBuffer, int ch) {
  (void)pBuffer;
  if (!pSrc || !pDst || !pBuffer) return IPP_STS_NULL;
  if (srcSize.width < 1 || srcSize.height < 1) return IPP_STS_SIZE;
  if (srcRoi.width < 1 || srcRoi.height < 1 || dstRoi.width < 1 || dstRoi.height < 1) return IPP_STS_SIZE;
  if (!interp_ok(interpolation)) return IPP_STS_INTERP;
  if (!(xFactor > 0.0) || !(yFactor > 0.0)) return IPP_STS_FACTOR;
  const int mode = interp_base(interpolation);
  if (mode == 8 && (xFactor > 1.0 || yFactor > 1.0)) return IPP_STS_FACTOR; /* Super は縮小のみ (実測) */

  const int rw = srcRoi.width, rh = srcRoi.height;
  int ix16, iy16, sx16, sy16;
  q16_init(xFactor, xShift, &ix16, &sx16);
  q16_init(yFactor, yShift, &iy16, &sy16);
  const int rw16 = rw * 65536, rh16 = rh * 65536;
  const int rox16 = srcRoi.x * 65536, roy16 = srcRoi.y * 65536;
  long writable = 0;
  double wx[8], wy[8];
  int bx, by, ntx, nty;

  for (int dy = 0; dy < dstRoi.height; dy++) {
    int v16 = q16_ur(dstRoi.y + dy, iy16, sy16, srcRoi.y);
    if (v16 < 0 || v16 > rh16) continue;
    Ipp8u *drow = pDst + (size_t)(dstRoi.y + dy) * (size_t)dstStep + (size_t)dstRoi.x * ch;
    if (mode == 1) {
      int j = (v16 - 1) >> 16; /* round-half-down(u-0.5) の Q16 版 (ROI 相対) */
      int jabs = srcRoi.y + j;
      if (jabs < 0) jabs = 0;
      if (jabs > srcSize.height - 1) jabs = srcSize.height - 1;
      const Ipp8u *srow = pSrc + (size_t)jabs * (size_t)srcStep;
      for (int dx = 0; dx < dstRoi.width; dx++) {
        int u16 = q16_ur(dstRoi.x + dx, ix16, sx16, srcRoi.x);
        if (u16 < 0 || u16 > rw16) continue;
        int i = (u16 - 1) >> 16; /* round-half-down(u-0.5) の Q16 版 (ROI 相対) */
        int iabs = srcRoi.x + i;
        if (iabs < 0) iabs = 0;
        if (iabs > srcSize.width - 1) iabs = srcSize.width - 1;
        writable++;
        for (int c = 0; c < ch; c++) drow[dx * ch + c] = srow[iabs * ch + c];
      }
      continue;
    }
    if (mode == 8) {
      /* Super: 面積重み (Q16)。footprint [start, start+1/fx) を ROI で切り抜き、
         ROI 外の面積は最近接エッジ画素へ fold してから総面積 (1/fx·1/fy) で正規化。
         (実測: fx=0.3 sx=0.25 dst0 = (140,77,38) — 左 fold をエッジ列に加算) */
      for (int dx = 0; dx < dstRoi.width; dx++) {
        int u16 = q16_ur(dstRoi.x + dx, ix16, sx16, srcRoi.x);
        if (u16 < 0 || u16 > rw16) continue;
        writable++;
        int xlo16 = (((int64_t)((dstRoi.x + dx) * 65536 - sx16) * ix16) >> 16) - rox16;
        int ylo16 = (((int64_t)((dstRoi.y + dy) * 65536 - sy16) * iy16) >> 16) - roy16;
        int wx16 = ix16, wy16 = iy16;
        int kx0 = xlo16 >> 16, kx1 = (xlo16 + wx16 + 65535) >> 16;
        int ky0 = ylo16 >> 16, ky1 = (ylo16 + wy16 + 65535) >> 16;
        if (kx0 < 0) kx0 = 0;
        if (ky0 < 0) ky0 = 0;
        if (kx1 > rw) kx1 = rw;
        if (ky1 > rh) ky1 = rh;
        double xlo = (double)xlo16 / 65536.0, xhi = (double)(xlo16 + wx16) / 65536.0;
        double ylo = (double)ylo16 / 65536.0, yhi = (double)(ylo16 + wy16) / 65536.0;
        double sum[4] = {0, 0, 0, 0};
        for (int ky = ky0; ky < ky1; ky++) {
          double oyt = (yhi < ky + 1.0 ? yhi : ky + 1.0);
          double oyb = (ylo > ky ? ylo : (double)ky);
          double oy = oyt - oyb;
          if (oy <= 0) continue;
          const Ipp8u *srow = pSrc + (size_t)(srcRoi.y + ky) * (size_t)srcStep + (size_t)srcRoi.x * ch;
          for (int kx = kx0; kx < kx1; kx++) {
            double oxt = (xhi < kx + 1.0 ? xhi : kx + 1.0);
            double oxb = (xlo > kx ? xlo : (double)kx);
            double ox = oxt - oxb;
            if (ox <= 0) continue;
            for (int c = 0; c < ch; c++) sum[c] += ox * oy * srow[kx * ch + c];
          }
#ifndef RSZ_SUPER_NOFOLD
          if (xlo < 0) for (int c = 0; c < ch; c++) sum[c] += (-xlo) * oy * srow[0 * ch + c];
          if (xhi > rw) for (int c = 0; c < ch; c++) sum[c] += (xhi - rw) * oy * srow[(rw - 1) * ch + c];
#endif
        }
#ifndef RSZ_SUPER_NOFOLD
        /* 列の上/下 fold (各行の横幅で重み) */
        if (ylo < 0) {
          double oyf = -ylo;
          for (int kx = kx0; kx < kx1; kx++) {
            double oxt = (xhi < kx + 1.0 ? xhi : kx + 1.0);
            double oxb = (xlo > kx ? xlo : (double)kx);
            double ox = oxt - oxb;
            const Ipp8u *srow = pSrc + (size_t)srcRoi.y * (size_t)srcStep + (size_t)srcRoi.x * ch;
            for (int c = 0; c < ch; c++) sum[c] += ox * oyf * srow[kx * ch + c];
          }
        }
        if (yhi > rh) {
          double oyf = yhi - rh;
          const Ipp8u *srow = pSrc + (size_t)(srcRoi.y + rh - 1) * (size_t)srcStep + (size_t)srcRoi.x * ch;
          for (int kx = kx0; kx < kx1; kx++) {
            double oxt = (xhi < kx + 1.0 ? xhi : kx + 1.0);
            double oxb = (xlo > kx ? xlo : (double)kx);
            double ox = oxt - oxb;
            for (int c = 0; c < ch; c++) sum[c] += ox * oyf * srow[kx * ch + c];
          }
        }
#endif
#ifndef RSZ_SUPER_NOFOLD
        double areaFull = (double)wx16 * wy16 / (65536.0 * 65536.0);
#else
        double xhic = (xhi > rw ? (double)rw : xhi);
        double yhic = (yhi > rh ? (double)rh : yhi);
        double xlol = (xlo < 0 ? 0.0 : xlo);
        double ylol = (ylo < 0 ? 0.0 : ylo);
        double areaFull = (xhic - xlol) * (yhic - ylol);
#endif
        for (int c = 0; c < ch; c++) drow[dx * ch + c] = clamp_u8(sum[c] / areaFull);
      }
      continue;
    }
    /* 分離モード (2/4/16): 位相は double で直接計算 (重みの量子化境界を実 DLL に合わせる) */
#ifdef RSZ_Q16_PHASE
    double py = (double)(v16 - 32768) / 65536.0;
#else
    double py = (double)(dstRoi.y + dy + 0.5 - yShift) / yFactor - (double)srcRoi.y - 0.5;
#endif
    nty = build_taps(mode, py, &by, wy);
    for (int dx = 0; dx < dstRoi.width; dx++) {
      int u16 = q16_ur(dstRoi.x + dx, ix16, sx16, srcRoi.x);
      if (u16 < 0 || u16 > rw16) continue;
      writable++;
#ifdef RSZ_Q16_PHASE
      double px = (double)(u16 - 32768) / 65536.0;
#else
      double px = (double)(dstRoi.x + dx + 0.5 - xShift) / xFactor - (double)srcRoi.x - 0.5;
#endif
      ntx = build_taps(mode, px, &bx, wx);
      /* 実測: タップindexは ROI 相対だが、フェッチは絶対座標 (srcRoi.x/y 加算) し
         画像範囲でクランプ (ROI 外の隣接画素も読む — CAB-136 FilterBox 同様, it=2 fx=0.3 x=9 の実測) */
      double sum[4] = {0, 0, 0, 0};
      for (int ty = 0; ty < nty; ty++) {
        if (wy[ty] == 0.0) continue;
        int jj = srcRoi.y + by + ty;
        if (jj < 0) jj = 0;
        if (jj > srcSize.height - 1) jj = srcSize.height - 1;
        const Ipp8u *srow = pSrc + (size_t)jj * (size_t)srcStep;
        for (int tx = 0; tx < ntx; tx++) {
          if (wx[tx] == 0.0) continue;
          int ii = srcRoi.x + bx + tx;
          if (ii < 0) ii = 0;
          if (ii > srcSize.width - 1) ii = srcSize.width - 1;
          double w = wy[ty] * wx[tx];
          for (int c = 0; c < ch; c++) sum[c] += w * srow[ii * ch + c];
        }
      }
      for (int c = 0; c < ch; c++) drow[dx * ch + c] = clamp_u8(sum[c]);
    }
  }
  if (writable == 0) return IPP_STS_NOOP;
  return ippStsNoErr;
}

IppStatus ippiResizeSqrPixel_8u_C1R(const Ipp8u *pSrc, IppiSize srcSize, int srcStep, IppiRect srcRoi,
                                    Ipp8u *pDst, int dstStep, IppiRect dstRoi,
                                    double xFactor, double yFactor, double xShift, double yShift,
                                    int interpolation, Ipp8u *pBuffer) {
  return resize_sqrpixel(pSrc, srcSize, srcStep, srcRoi, pDst, dstStep, dstRoi,
                         xFactor, yFactor, xShift, yShift, interpolation, pBuffer, 1);
}
IppStatus ippiResizeSqrPixel_8u_C3R(const Ipp8u *pSrc, IppiSize srcSize, int srcStep, IppiRect srcRoi,
                                    Ipp8u *pDst, int dstStep, IppiRect dstRoi,
                                    double xFactor, double yFactor, double xShift, double yShift,
                                    int interpolation, Ipp8u *pBuffer) {
  return resize_sqrpixel(pSrc, srcSize, srcStep, srcRoi, pDst, dstStep, dstRoi,
                         xFactor, yFactor, xShift, yShift, interpolation, pBuffer, 3);
}
IppStatus ippiResizeSqrPixel_8u_C4R(const Ipp8u *pSrc, IppiSize srcSize, int srcStep, IppiRect srcRoi,
                                    Ipp8u *pDst, int dstStep, IppiRect dstRoi,
                                    double xFactor, double yFactor, double xShift, double yShift,
                                    int interpolation, Ipp8u *pBuffer) {
  return resize_sqrpixel(pSrc, srcSize, srcStep, srcRoi, pDst, dstStep, dstRoi,
                         xFactor, yFactor, xShift, yShift, interpolation, pBuffer, 4);
}

/* ---- GetBufSize ---- */
/* 実 DLL (win64) の ippiResizeSqrPixelGetBufSize は「常時 -8, *pSize 不変」のスタブ
   (逆アセ mov eax,0xfffffff8; ret — 実測 dis_export.py + probe1-B 全数グリッド)。同一挙動。 */
IppStatus ippiResizeSqrPixelGetBufSize(IppiSize dstSize, int nChannel, int interpolation, int *pSize) {
  (void)dstSize; (void)nChannel; (void)interpolation; (void)pSize;
  return IPP_STS_NULL; /* 実 DLL 実測: 常時 -8 */
}

/* ippiResizeGetBufSize の実測式 (密グリッド dw<=96, dh<=48, ch∈{1,3,4}, interp∈{1,2,4,8,16})。
   共通: ch=2 → -53, pSize NULL → -8。寸法依存は dstRoi (Super のみ srcRoi.width)。 */
static int c16(int x) { return (x + 15) / 16; }
static int c8(int x) { return (x + 7) / 8; }

IppStatus ippiResizeGetBufSize(IppiRect srcRoi, IppiRect dstRoi, int nChannel, int interpolation, int *pSize) {
  if (!pSize) return IPP_STS_NULL;
  if (srcRoi.width < 1 || srcRoi.height < 1 || dstRoi.width < 1 || dstRoi.height < 1) return IPP_STS_SIZE; /* 実測: w0 → -6 */
  if (nChannel == 2) return IPP_STS_CH2;
  if (nChannel < 1 || nChannel > 4) return IPP_STS_BADARG;
  if (!interp_ok(interpolation)) return IPP_STS_INTERP;
  const int mode = interp_base(interpolation);
  const int dw = dstRoi.width, dh = dstRoi.height, sw = srcRoi.width;
  long sz;
  if (mode == 1) {
    sz = 144 + 64 * (c16(dw) - 1) + 64 * (c16(dh) - 1);
  } else if (mode == 2) {
    /* 実測 (dense2, dw<=600/dh<=400): 16px ブロック b について
       addw = 64·(16·⌊(b−1)/4⌋ + [0,1,6,7][(b−1)%4]), addh = 64·(8·⌊(b−1)/4⌋ + (b−1)%4) */
    int bw = c16(dw), bh = c16(dh);
    static const int AW[4] = {0, 1, 6, 7};
    long addw = 64L * (16 * ((bw - 1) / 4) + AW[(bw - 1) % 4]);
    long addh = 64L * (8 * ((bh - 1) / 4) + (bh - 1) % 4);
    long chterm = (long)(nChannel - 1) * 256 * (2 + (dw - 1) / 32);
    sz = 1168 + addw + addh + chterm;
  } else if (mode == 4) {
    int bw = c8(dw), bh = c8(dh);
    static const int AW[4] = {0, 2, 9, 11}, AH[4] = {0, 2, 5, 7};
    long addw = 64 * (20L * ((bw - 1) / 4) + AW[(bw - 1) % 4]);
    long addh = 64 * (12L * ((bh - 1) / 4) + AH[(bh - 1) % 4]);
    long chterm = (long)(nChannel - 1) * 256 * (4 + (dw - 1) / 16);
    sz = 2448 + addw + addh + chterm;
  } else if (mode == 8) {
    int bw = c16(sw);
    sz = 16 + 128L * nChannel * bw;
  } else { /* 16 (Lanczos) — 5/5/6px ブロック b: addw = 64·(28·⌊(b−1)/6⌋ + [0,4,8,13,17,21][(b−1)%6]),
       addh = 64·(16·⌊(b−1)/6⌋ + [0,2,4,7,9,11][(b−1)%6]) (実測 dense2, b<=113) */
    int gw = (dw - 1) / 16, rwd = (dw - 1) % 16;
    int r = rwd < 5 ? 1 : (rwd < 10 ? 2 : 3);
    int bw = 3 * gw + r;
    static const int LW[6] = {0, 4, 8, 13, 17, 21}, LH[6] = {0, 2, 4, 7, 9, 11};
    long addw = 64L * (28 * ((bw - 1) / 6) + LW[(bw - 1) % 6]);
    int gh = (dh - 1) / 16, rht = (dh - 1) % 16;
    int r2 = rht < 5 ? 1 : (rht < 10 ? 2 : 3);
    int bh = 3 * gh + r2;
    long addh = 64L * (16 * ((bh - 1) / 6) + LH[(bh - 1) % 6]);
    long chterm = (long)(nChannel - 1) * 128 * (bw + 5);
    sz = 2704 + addw + addh + chterm;
  }
  *pSize = (int)sz;
  return ippStsNoErr;
}
