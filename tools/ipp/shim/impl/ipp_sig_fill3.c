/* CAB-262 (IPP-7 ipp-fill-3): 残 stub 次層 — win 呼出モジュール数降順の静的優先順で 29 関数を実装。
   契約: ../impl/README.md — 宣言は ../gen/ipp_proto.h と一致 (コンパイラが署名検査)。
   引数順序・数式の根拠: 実 win64 dsp_ippv2_x64.dll を pe_load ネイティブ実行した probe (work/fill7/probe_*.c)
   とオラクル (test/fill3_oracle.c) の実測。

   1. ippsRealToCplx_32f / ippsCplxToReal_32fc (61 モジュール)
      — 舞台裏の interleave/deinterleave。RealToCplx は「dst NULL → -8 が最優先、次に
        len<1 → -6」という実 DLL の順序 quirk を持ち、len>=1 では re/im の片方 NULL は
        エラーにならずその成分だけ書込する (書けない側は 0 充填)。両方 NULL のときだけ -8
        (実装先頭の ippsRealToCplx_32f コメントと test/fill3_oracle.c の err_grid_r2c = 32 点で実測)。
      CplxToReal は通常順 (NULL → -8, len → -6)。
      出力は Ipp32fc = {re, im} の 8 バイト値をそのまま (GPR ではなく *pDst 書込)。
   2. ippsCopy_8u (55) / ippsZero_32s (51) / ippsCopy_64s (19) / ippsZero_64s (14)
      — memcpy/memset。NULL → -8, len<1 → -6。
   3. ippsMinMax_32f (50) / ippsMinMax_16s (49) / ippsMin_16s / ippsMax_16s
      — 単純 min/max 走査。pMin/pMax どちらが NULL でも -8 (len 検査より先)。
   4. ippsRound_32f (38) — round-half-away-from-zero。/ -0 は保存 (実測: -0.5 → -1)。
   5. ippsSwapBytes_32u_I / _16u_I — バイト順反転。
   6. ippsFlip_32f_I / _16u_I — 要素順反転 (in-place)。
   7. ippsAbs_32f — 絶対値 (符号ビット mask、-0 → +0)。
   8. ippsSet_64f — 定数充填。
   9. ippsPowerSpectr_32fc — re^2+im^2 (実測: 1.0f 側は float 乗算)。
  10. ippsThreshold_LT_64f_I / _32s_I — x < level → level。
  11. ippsThreshold_LTValGTVal_32f_I — x<levelLT → valueLT、x>levelGT → valueGT、間は不変。
  12. ippsAddProductC_32f — pSrcDst[i] += val * pSrc[i] (dst 事前値 0 なら val*src)。
  13. ippsInterleave_32f / _16s, ippsDeinterleave_32f / _16s (49) — nCh 0..4。
      nCh<1 → -53、pSrc(NULL) → -8、len<1 → -6、pDst NULL → -8。
  14. ippsMulPack_32f (49) — pSrcDst[i] = pSrc[i] * pSrc[i] の「2 乗」ではなく
      実測では dst=101..104 / src=1..4 で出力 1,3,5,7 → これは addProductC と同形?
      → probe 実測: dst=100+i, src=i+1, out=1,3,5,7 = ((i+1)*(i+1)? いや
      probe_o: MulPack(src=i+1, dst=100+i) → 1 3 5 7 = (i+1)*2-1? 
      probe_p: dst=-1 に戻して out=1 3 5 7 (同じ) → src に依存。
      → 決着: MulPack は (src1*2-1) ではなく dst 事前値に依存しない「パック」= 
      IPP の MulPack は「packed 乗算」で pDst = pSrc1[i] * pSrc1[i] ... 
      実測値 1,3,5,7 (src=1,2,3,4) は (2n-1) = 「連番の差分」で、
      実際には AddProductC と同じ pSrcDst += src*src では +1,+3,+5,+7 = 2n-1 で
      dst 事前値が 100 → 101,103,105,107 になるはず。実測は 1,3,5,7 そのもの。
      → MulPack_32f は pSrcDst[i] = pSrc2[i] + pSrc1[i] ではなく
        「差分」= pSrc[i]*2-1 という珍しい意味。安全のため本チケットでは実装しない。 */
#include "ipp_min.h"
#include "../gen/ipp_proto.h"
#include <string.h>
#include <math.h>

#define IPP_STS_BADARG (-5)
#define IPP_STS_CH     (-53)   /* 実測: reorder nCh<1 */

/* ---- 共通検査 ---- */
static IppStatus len_chk(int len) { return len < 1 ? ippStsSizeErr : ippStsNoErr; }

/* ============ 1. RealToCplx / CplxToReal ============ */
/* 実測 (probe_q/r2c): エラー格子は「dst NULL → -8 が最優先」、以下 len<1 → -6。
   len>=1 では re/im の片方 NULL はエラーにならず、その成分だけ書込 (書けない側は 0 を充填)
   — 両方 NULL のときだけ -8。 */
IppStatus ippsRealToCplx_32f(const Ipp32f *pSrcRe, const Ipp32f *pSrcIm, Ipp32fc *pDst, int len) {
  if (!pDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  if (!pSrcRe && !pSrcIm) return ippStsNullPtrErr;
  for (int i = 0; i < len; i++) {
    pDst[i].re = pSrcRe ? pSrcRe[i] : 0.0f;
    pDst[i].im = pSrcIm ? pSrcIm[i] : 0.0f;
  }
  return ippStsNoErr;
}
IppStatus ippsCplxToReal_32fc(const Ipp32fc *pSrc, Ipp32f *pDstRe, Ipp32f *pDstIm, int len) {
  if (!pSrc || !pDstRe || !pDstIm) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0; i < len; i++) { pDstRe[i] = pSrc[i].re; pDstIm[i] = pSrc[i].im; }
  return ippStsNoErr;
}

/* ============ 2. Copy / Zero ============ */
IppStatus ippsCopy_8u(const Ipp8u *pSrc, Ipp8u *pDst, int len) {
  if (!pSrc || !pDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  memcpy(pDst, pSrc, (size_t)len);
  return ippStsNoErr;
}
IppStatus ippsZero_32s(Ipp32s *pDst, int len) {
  if (!pDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  memset(pDst, 0, sizeof(Ipp32s) * (size_t)len);
  return ippStsNoErr;
}
IppStatus ippsZero_64s(Ipp64s *pDst, int len) {
  if (!pDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  memset(pDst, 0, sizeof(Ipp64s) * (size_t)len);
  return ippStsNoErr;
}
IppStatus ippsCopy_64s(const Ipp64s *pSrc, Ipp64s *pDst, int len) {
  if (!pSrc || !pDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  memcpy(pDst, pSrc, sizeof(Ipp64s) * (size_t)len);
  return ippStsNoErr;
}

/* ============ 3. Min / Max / MinMax ============ */
IppStatus ippsMinMax_32f(const Ipp32f *pSrc, int len, Ipp32f *pMin, Ipp32f *pMax) {
  if (!pMin || !pMax) return ippStsNullPtrErr;
  if (!pSrc) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  Ipp32f lo = pSrc[0], hi = pSrc[0];
  for (int i = 1; i < len; i++) { Ipp32f v = pSrc[i]; if (v < lo) lo = v; if (v > hi) hi = v; }
  *pMin = lo; *pMax = hi;
  return ippStsNoErr;
}
IppStatus ippsMinMax_16s(const Ipp16s *pSrc, int len, Ipp16s *pMin, Ipp16s *pMax) {
  if (!pMin || !pMax) return ippStsNullPtrErr;
  if (!pSrc) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  Ipp16s lo = pSrc[0], hi = pSrc[0];
  for (int i = 1; i < len; i++) { Ipp16s v = pSrc[i]; if (v < lo) lo = v; if (v > hi) hi = v; }
  *pMin = lo; *pMax = hi;
  return ippStsNoErr;
}
IppStatus ippsMin_16s(const Ipp16s *pSrc, int len, Ipp16s *pRes) {
  if (!pSrc || !pRes) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  Ipp16s lo = pSrc[0];
  for (int i = 1; i < len; i++) if (pSrc[i] < lo) lo = pSrc[i];
  *pRes = lo;
  return ippStsNoErr;
}
IppStatus ippsMax_16s(const Ipp16s *pSrc, int len, Ipp16s *pRes) {
  if (!pSrc || !pRes) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  Ipp16s hi = pSrc[0];
  for (int i = 1; i < len; i++) if (pSrc[i] > hi) hi = pSrc[i];
  *pRes = hi;
  return ippStsNoErr;
}

/* ============ 4. Round / Abs / Flip / SwapBytes ============ */
/* 実測 (probe_p/rnd*): round-half-away-from-zero。
   x>=0 → floor(x+0.5)、x<0 → ceil(x-0.5)。±0 は符号保存 (-0 → -0)。
   |結果| >= 2^31 では入力をそのまま返す (float はその域で全て整数値のため)。
   例: 0.5→1, 2.5→3, -0.5→-1, -0.463→-0, 3.4e38→3.4e38, inf/NaN→そのまま */
static Ipp32f round_haf(Ipp32f x) {
  if (x == 0.0f) return x;
  if (x > 0.0f) {
    double r = floor((double)x + 0.5);
    return (r >= 2147483648.0) ? x : (Ipp32f)r;
  }
  double r = ceil((double)x - 0.5);
  return (r <= -2147483648.0) ? x : (Ipp32f)r;
}
IppStatus ippsRound_32f(const Ipp32f *pSrc, Ipp32f *pDst, int len) {
  if (len < 1) return ippStsSizeErr;
  if (!pSrc || !pDst) return ippStsNullPtrErr;
  for (int i = 0; i < len; i++) pDst[i] = round_haf(pSrc[i]);
  return ippStsNoErr;
}
IppStatus ippsAbs_32f(const Ipp32f *pSrc, Ipp32f *pDst, int len) {
  if (!pSrc || !pDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0; i < len; i++) pDst[i] = fabsf(pSrc[i]);
  return ippStsNoErr;
}
IppStatus ippsFlip_32f_I(Ipp32f *pSrcDst, int len) {
  if (!pSrcDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0, j = len - 1; i < j; i++, j--) { Ipp32f t = pSrcDst[i]; pSrcDst[i] = pSrcDst[j]; pSrcDst[j] = t; }
  return ippStsNoErr;
}
IppStatus ippsFlip_16u_I(Ipp16u *pSrcDst, int len) {
  if (!pSrcDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0, j = len - 1; i < j; i++, j--) { Ipp16u t = pSrcDst[i]; pSrcDst[i] = pSrcDst[j]; pSrcDst[j] = t; }
  return ippStsNoErr;
}
IppStatus ippsSwapBytes_32u_I(Ipp32u *pSrcDst, int len) {
  if (!pSrcDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0; i < len; i++) {
    Ipp32u v = pSrcDst[i];
    pSrcDst[i] = ((v & 0xFFu) << 24) | ((v & 0xFF00u) << 8) | ((v >> 8) & 0xFF00u) | (v >> 24);
  }
  return ippStsNoErr;
}
IppStatus ippsSwapBytes_16u_I(Ipp16u *pSrcDst, int len) {
  if (!pSrcDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0; i < len; i++) {
    Ipp16u v = pSrcDst[i];
    pSrcDst[i] = (Ipp16u)(((v & 0xFFu) << 8) | (v >> 8));
  }
  return ippStsNoErr;
}

/* ============ 5. Set / PowerSpectr / AddProductC ============ */
IppStatus ippsSet_64f(Ipp64f val, Ipp64f *pDst, int len) {
  if (!pDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0; i < len; i++) pDst[i] = val;
  return ippStsNoErr;
}
/* 実測 (probe_d): re^2 + im^2 (float 演算) */
IppStatus ippsPowerSpectr_32fc(const Ipp32fc *pSrc, Ipp32f *pDst, int len) {
  if (!pSrc || !pDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0; i < len; i++) pDst[i] = pSrc[i].re * pSrc[i].re + pSrc[i].im * pSrc[i].im;
  return ippStsNoErr;
}
/* 実測 (apcz fit): IPP は double で乗算・加算してから float に丸める
   (= fmaf(val, src, dst) と等価)。float のままだと 1 ULP 差が出る。
   dst 事前値 0 のときは val*src (probe_o/p 実測)。 */
IppStatus ippsAddProductC_32f(const Ipp32f *pSrc, Ipp32f val, Ipp32f *pSrcDst, int len) {
  if (!pSrc || !pSrcDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0; i < len; i++)
    pSrcDst[i] = (Ipp32f)((double)pSrcDst[i] + (double)val * (double)pSrc[i]);
  return ippStsNoErr;
}

/* ============ 6. Threshold ============ */
IppStatus ippsThreshold_LT_64f_I(Ipp64f *pSrcDst, int len, Ipp64f level) {
  if (!pSrcDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0; i < len; i++) if (pSrcDst[i] < level) pSrcDst[i] = level;
  return ippStsNoErr;
}
IppStatus ippsThreshold_LT_32s_I(Ipp32s *pSrcDst, int len, Ipp32s level) {
  if (!pSrcDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0; i < len; i++) if (pSrcDst[i] < level) pSrcDst[i] = level;
  return ippStsNoErr;
}
/* 実測 (probe_i): x<levelLT → valueLT; x>levelGT → valueGT; 間は不変 */
IppStatus ippsThreshold_LTValGTVal_32f_I(Ipp32f *pSrcDst, int len, Ipp32f levelLT, Ipp32f valueLT,
                                          Ipp32f levelGT, Ipp32f valueGT) {
  if (!pSrcDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0; i < len; i++) {
    Ipp32f v = pSrcDst[i];
    if (v < levelLT) pSrcDst[i] = valueLT;
    else if (v > levelGT) pSrcDst[i] = valueGT;
  }
  return ippStsNoErr;
}

/* ============ 6b. Convert_16s32f ============ */
/* 実測 (probe_e): (int16) → (float) の単純変換。NULL → -8, len<1 → -6。 */
IppStatus ippsConvert_16s32f(const Ipp16s *pSrc, Ipp32f *pDst, int len) {
  if (!pSrc || !pDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0; i < len; i++) pDst[i] = (Ipp32f)pSrc[i];
  return ippStsNoErr;
}

/* ============ 7. VectorSlope ============ */
/* IPP-9 (#276): 実 DLL の生成算法 (全 ISA 経路で同一出力・ブロック幅 8 の累積)。
   - 8 要素ブロックの 8 レーン k の初期値: o+k*s (k=0..4,6)、レーン5 = o+(3s+2s)、
     レーン7 = o+((3s+2s)+2s) (積の丸めを挟んだ加算経路)。
   - 以降のブロックは各レーンに step=8*s を加算して更新 (len/8 ブロック)。
   - 端数 (len%8) は先頭要素 = 次ブロックのレーン0 累積値、以降は直前要素 + s の直列加算。
   乗算と加算は融合しない (-ffp-contract=off 必須)。 */
IppStatus ippsVectorSlope_64f(Ipp64f *pDst, int len, Ipp64f offset, Ipp64f slope) {
  if (!pDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  const double s = slope, s2 = 2.0 * s, s3 = 3.0 * s, s5 = s3 + s2;
  double lane[8] = {offset,         offset + s,        offset + s2,           offset + s3,
                    offset + 4.0 * s, offset + s5, offset + 6.0 * s, offset + (s5 + s2)};
  const double step = 8.0 * s;
  int i = 0;
  for (; i + 8 <= len; i += 8)
    for (int k = 0; k < 8; k++) { pDst[i + k] = lane[k]; lane[k] += step; }
  if (i < len) {
    pDst[i] = lane[0];
    for (i++; i < len; i++) pDst[i] = pDst[i - 1] + s;
  }
  return ippStsNoErr;
}

/* ============ 8. Interleave / Deinterleave ============ */
/* 実測 (probe_f): nCh<1 → -53 (ptr/len 検査より先)、pSrc(NULL) → -8、
   len<1 → -6、pDst NULL → -8。値は channel インターリーブ。 */
IppStatus ippsInterleave_32f(const Ipp32f *const *pSrc, int nChannels, int len, Ipp32f *pDst) {
  if (nChannels < 1) return IPP_STS_CH;
  if (!pSrc) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  if (!pDst) return ippStsNullPtrErr;
  for (int i = 0; i < len; i++)
    for (int c = 0; c < nChannels; c++) pDst[i * nChannels + c] = pSrc[c][i];
  return ippStsNoErr;
}
IppStatus ippsInterleave_16s(const Ipp16s *const *pSrc, int nChannels, int len, Ipp16s *pDst) {
  if (nChannels < 1) return IPP_STS_CH;
  if (!pSrc) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  if (!pDst) return ippStsNullPtrErr;
  for (int i = 0; i < len; i++)
    for (int c = 0; c < nChannels; c++) pDst[i * nChannels + c] = pSrc[c][i];
  return ippStsNoErr;
}
IppStatus ippsDeinterleave_32f(const Ipp32f *pSrc, int nChannels, int len, Ipp32f *const *pDst) {
  if (nChannels < 1) return IPP_STS_CH;
  if (!pSrc) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  if (!pDst) return ippStsNullPtrErr;
  for (int i = 0; i < len; i++)
    for (int c = 0; c < nChannels; c++) pDst[c][i] = pSrc[i * nChannels + c];
  return ippStsNoErr;
}
IppStatus ippsDeinterleave_16s(const Ipp16s *pSrc, int nChannels, int len, Ipp16s *const *pDst) {
  if (nChannels < 1) return IPP_STS_CH;
  if (!pSrc) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  if (!pDst) return ippStsNullPtrErr;
  for (int i = 0; i < len; i++)
    for (int c = 0; c < nChannels; c++) pDst[c][i] = pSrc[i * nChannels + c];
  return ippStsNoErr;
}

/* ============ 9. WinKaiser ============ */
/* 実測 (work/fill7/probe_u → kaiser_fit.py):
     beta = alpha*(len-1)/2,  r_i = 2i/(len-1) - 1
     w[i] = I0(beta*sqrt(1-r^2)) / I0(beta)
   I0 は級数 60 項が必要 (検証: 24 項だと beta=30 で最大 2.6e-04、beta≈37.5 で 6.5e-03 の
   誤差になり実 DLL と合わない。60 項なら 3e-06 以下)。beta >= 38 では実 DLL が -39
   (ippStsNotSupportedMode) を返し書込なし (境界を実測: beta=37.995 は 0、38.001 は -39)。
   実測精度: float 出力で max abs err 2.4e-06 (I0 級数の打ち切り誤差) — bit-exact ではない。 */
static double bessel_i0(double x) {
  double h = x * x / 4.0, s = 1.0, t = 1.0;
  for (int k = 1; k < 60; k++) { t *= h / ((double)k * (double)k); s += t; }
  return s;
}
IppStatus ippsWinKaiser_32f_I(Ipp32f *pSrcDst, int len, Ipp32f alpha) {
  if (!pSrcDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  double beta = (double)alpha * (double)(len - 1) / 2.0;
  if (beta >= 38.0) return (-39);            /* 実測: beta>=38 は未対応 */
  double i0b = bessel_i0(beta);
  for (int i = 0; i < len; i++) {
    double r = (len == 1) ? 0.0 : (2.0 * (double)i / (double)(len - 1) - 1.0);
    double t = 1.0 - r * r;
    /* t は負になりうる (丸め) — その場合は 0 に切る (I0(0)=1) */
    double w = (t < 0.0) ? 0.0 : bessel_i0(beta * sqrt(t)) / i0b;
    pSrcDst[i] = (Ipp32f)w;
  }
  return ippStsNoErr;
}
