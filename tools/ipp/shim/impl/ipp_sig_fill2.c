/* CAB-245 (IPP-5 ipp-fill-2): 125 モジュール群 4 関数の実装。
   契約: ../impl/README.md — 宣言は ../gen/ipp_proto.h と一致 (コンパイラが署名検査)。
   引数順序の根拠: sigs.py 規則 (thr / arith-I / mem / vm-unary) + 呼出実績 (data/ipp_sigs.json,
   ippsThreshold_GT_32s_I / ippsSub_32f_I / ippsCopy_32s / ippsAtan_32f_A11 はいずれも win 実績あり)。
   - ippsThreshold_GT_32s_I : in-place (pSrcDst, len, level)。x > level → level (実測オラクル)。
   - ippsSub_32f_I          : pSrcDst[i] -= pSrc[i] (IEEE 演算のままで bit-exact)。
   - ippsCopy_32s           : 32bit 丸ごとコピー (実測: memcpy と等価)。
   - ippsAtan_32f_A11       : A11 等級 (低精度)。実 IPP は固有多項式で bit は一致しない
     (CAB-141 確定方針: A11 系の bit 不一致は許容)。atanf ベースで実装し、
     実測の ulp 分布を REPORT §12 に記録 (qNaN/±0 の符号規約のみ実測に合わせる)。 */
#include "ipp_min.h"
#include "../gen/ipp_proto.h"
#include <math.h>
#include <string.h>

IppStatus ippsThreshold_GT_32s_I(Ipp32s *pSrcDst, int len, Ipp32s level) {
  if (!pSrcDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0; i < len; i++)
    if (pSrcDst[i] > level) pSrcDst[i] = level;
  return ippStsNoErr;
}

IppStatus ippsSub_32f_I(const Ipp32f *pSrc, Ipp32f *pSrcDst, int len) {
  if (!pSrc || !pSrcDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0; i < len; i++) pSrcDst[i] -= pSrc[i];
  return ippStsNoErr;
}

IppStatus ippsCopy_32s(const Ipp32s *pSrc, Ipp32s *pDst, int len) {
  if (!pSrc || !pDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  memcpy(pDst, pSrc, sizeof(Ipp32s) * (size_t)len);
  return ippStsNoErr;
}

IppStatus ippsAtan_32f_A11(const Ipp32f *pSrc, Ipp32f *pDst, Ipp32s len) {
  /* len 検査が先 (A11 実装の実測順 — Sqrt_A21 と同型) */
  if (len < 1) return ippStsSizeErr;
  if (!pSrc || !pDst) return ippStsNullPtrErr;
  for (Ipp32s i = 0; i < len; i++) {
    float x = pSrc[i];
    /* A11: ±0 の符号保存, ±Inf → ±π/2, NaN → NaN (CAB-141 で bit 差は許容) */
    pDst[i] = atanf(x);
  }
  return ippStsNoErr;
}
