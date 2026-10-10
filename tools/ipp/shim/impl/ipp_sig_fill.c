/* CAB-136 (IPP-2 ipp-fill): 優先順上位 stub の実装 — 信号 (ipps) 系 + FIR/IIR/GetSize のエラーコード返却。
   契約: ../impl/README.md — 宣言は ../gen/ipp_proto.h (生成) と一致 = コンパイラが署名検査する。
   引数順序の根拠 (win 呼出実績, tools/ipp/shim/REPORT §10 と work/fill/callsite_dump.py):
   - ippsOrC_32u_I      : val=ecx 即値 0xff000000 / pSrcDst=rdx / len=r8d (block00031 0x6c71b2)
   - ippsSet_64s        : 規則 mem-set (Set_32f/32s と同形, 実績 agree)
   - ippsSqrt_32f_A21   : A11 と同形 (実 DLL でオラクル検証済み, §10)
   - ippsThreshold_GT_32f: pSrc=rcx / pDst=rdx / len=r8d / level=xmm0 (block00031 0x6a41d1)
   - FIR/IIR/GetSize 10 名: 実績なし (B-) は IPP 標準の引数順 (sigs.py 明示表) のまま。
     CAB-134 検収決定どおり「0 (成功) 戻し」ではなくエラーコード返却で fail-fast にする。
     実 IPP の状態コード実測 (work/fill/probe.c + arm64 dsp_ippv2 逆アセンブル):
     NULL 出力 → -8 (ippStsNullPtrErr), 不正サイズ → -5 (ippStsBadArgErr; arm64 ippsFIRInitAlloc_32f
     は taps==NULL / tapsLen<1 で -5, malloc 失敗で -9)。未実装の意味は -22 (実 DLL が Resize 系の
     「未対応モード」で返すコード, work/fill/probe.c 観測) を使用。 */
#include "ipp_min.h"
#include "../gen/ipp_proto.h"
#include <math.h>

#define IPP_STS_BADARG     (-5)  /* ippStsBadArgErr — 実 IPP 観測 (arm64 FIRInit/IIRGetStateSize の不正引数) */
#define IPP_STS_NOTSUPPORT (-22) /* 実 DLL が「未対応モード」で返すコード (Resize 系 interp, probe.c 観測) */

/* ---- ippsOrC_32u_I: 要素ごとに OR (win 実績: FL は alpha 版 0xff000000 を OR する用途) ---- */
IppStatus ippsOrC_32u_I(Ipp32u val, Ipp32u *pSrcDst, int len) {
  if (!pSrcDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0; i < len; i++) pSrcDst[i] |= val;
  return ippStsNoErr;
}

/* ---- ippsSet_64s ---- */
IppStatus ippsSet_64s(Ipp64s val, Ipp64s *pDst, int len) {
  if (!pDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0; i < len; i++) pDst[i] = val;
  return ippStsNoErr;
}

/* ---- ippsSqrt_32f_A21: A11 実装と同方針 (IEEE sqrtf)。負値 → NaN + ippStsSqrtNegArg。
      A21 (高精度等級) は実 IPP と bit 比較済み (shim/REPORT §10: bit-exact)。 ---- */
IppStatus ippsSqrt_32f_A21(const Ipp32f *pSrc, Ipp32f *pDst, Ipp32s len) {
  /* len 検査が NULL 検査より先 (A11 実装と同じ順; 実 IPP 観測) */
  if (len < 1) return ippStsSizeErr;
  if (!pSrc || !pDst) return ippStsNullPtrErr;
  IppStatus st = ippStsNoErr;
  for (Ipp32s i = 0; i < len; i++) {
    if (pSrc[i] < 0.f) st = ippStsSqrtNegArg;
    pDst[i] = sqrtf(pSrc[i]);
  }
  return st;
}

/* ---- ippsThreshold_GT_32f (非 in-place): src > level → level ---- */
IppStatus ippsThreshold_GT_32f(const Ipp32f *pSrc, Ipp32f *pDst, int len, Ipp32f level) {
  if (!pSrc || !pDst) return ippStsNullPtrErr;
  if (len < 1) return ippStsSizeErr;
  for (int i = 0; i < len; i++) pDst[i] = (pSrc[i] > level) ? level : pSrc[i];
  return ippStsNoErr;
}

/* ---- FIR/IIR Init/Alloc と GetSize 系: エラーコード返却 (CAB-134 検収決定)。
      実装方針: 実 IPP が返すはずの検証 (NULL → -8, 不正サイズ → -5) を先に行い、
      正常引数は未実装マーカ (-22) を返す。state/handle は書き換えない (fail-fast)。 ---- */
static IppStatus fill_unsupported(void **ppState, const void *pTaps, int tapsLen) {
  if (!ppState) return ippStsNullPtrErr;
  if (!pTaps || tapsLen < 1) return IPP_STS_BADARG; /* 実 IPP (arm64) と同じ検証順 */
  return IPP_STS_NOTSUPPORT;
}

IppStatus ippsFIRInitAlloc_32f(void **ppState, const Ipp32f *pTaps, int tapsLen, const Ipp32f *pDlyLine) {
  (void)pDlyLine;
  return fill_unsupported(ppState, pTaps, tapsLen);
}

IppStatus ippsFIRInitAlloc64f_32f(void **ppState, const Ipp64f *pTaps, int tapsLen, const Ipp32f *pDlyLine) {
  (void)pDlyLine;
  return fill_unsupported(ppState, pTaps, tapsLen);
}

IppStatus ippsFIRMRInitAlloc_32f(void **ppState, const Ipp32f *pTaps, int tapsLen,
                                 int upFactor, int upPhase, int downFactor, int downPhase, const Ipp32f *pDlyLine) {
  (void)upFactor; (void)upPhase; (void)downFactor; (void)downPhase; (void)pDlyLine;
  return fill_unsupported(ppState, pTaps, tapsLen);
}

IppStatus ippsFIRMRInitAlloc64f_32f(void **ppState, const Ipp64f *pTaps, int tapsLen,
                                    int upFactor, int upPhase, int downFactor, int downPhase, const Ipp32f *pDlyLine) {
  (void)upFactor; (void)upPhase; (void)downFactor; (void)downPhase; (void)pDlyLine;
  return fill_unsupported(ppState, pTaps, tapsLen);
}

IppStatus ippsIIRInit64f_BiQuad_32f(void **ppState, const Ipp64f *pTaps, int numBq, const Ipp64f *pDlyLine, Ipp8u *pBuf) {
  (void)pDlyLine; (void)pBuf;
  if (!ppState) return ippStsNullPtrErr;
  /* 実 IPP (win probe) は pTaps==NULL を -8 で返す。arm64 は numBq<1 を -5。 */
  if (!pTaps) return ippStsNullPtrErr;
  if (numBq < 1) return IPP_STS_BADARG;
  return IPP_STS_NOTSUPPORT;
}

IppStatus ippsIIRGetStateSize64f_BiQuad_32f(int numBq, int *pBufferSize) {
  if (!pBufferSize) return ippStsNullPtrErr;
  if (numBq < 1) return IPP_STS_BADARG; /* arm64 実装と同じ検証 (実値は IPP バージョンで異なるため書き込まない) */
  return IPP_STS_NOTSUPPORT;
}
