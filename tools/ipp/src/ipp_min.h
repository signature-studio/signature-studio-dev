/* 最小 IPP 互換実装 (案C PoC)。関数名・引数・戻り値は Intel IPP ips*.h に一致。 */
#pragma once
#include <stdint.h>
#include <stddef.h>
typedef int IppStatus;
typedef float Ipp32f; typedef uint8_t Ipp8u; typedef int32_t Ipp32s;
enum { ippStsNoErr = 0, ippStsSizeErr = -6, ippStsNullPtrErr = -8, ippStsOverflow = 12, ippStsUnderflow = 17, ippStsSqrtNegArg = 19 };
enum { ippRndZero = 0, ippRndNear = 1, ippRndFinancial = 2 };

/* tier0: win64 FL (FLEngine + 145 modules) が静的参照する 6 関数 */
IppStatus ippsMove_8u(const Ipp8u *pSrc, Ipp8u *pDst, int len);
IppStatus ippsMove_32f(const Ipp32f *pSrc, Ipp32f *pDst, int len);
IppStatus ippsZero_8u(Ipp8u *pDst, int len);
IppStatus ippsZero_32f(Ipp32f *pDst, int len);
IppStatus ippsAdd_32f_I(const Ipp32f *pSrc, Ipp32f *pSrcDst, int len);
IppStatus ippsMulC_32f_I(Ipp32f val, Ipp32f *pSrcDst, int len);
/* tier1: mac 版 (FPC) の高頻度関数 */
IppStatus ippsAddC_32f(const Ipp32f *pSrc, Ipp32f val, Ipp32f *pDst, int len);
IppStatus ippsAddC_32f_I(Ipp32f val, Ipp32f *pSrcDst, int len);
IppStatus ippsMulC_32f(const Ipp32f *pSrc, Ipp32f val, Ipp32f *pDst, int len);
IppStatus ippsSubCRev_32f(const Ipp32f *pSrc, Ipp32f val, Ipp32f *pDst, int len);
IppStatus ippsSubCRev_32f_I(Ipp32f val, Ipp32f *pSrcDst, int len);
IppStatus ippsMul_32f(const Ipp32f *pSrc1, const Ipp32f *pSrc2, Ipp32f *pDst, int len);
IppStatus ippsMul_32f_I(const Ipp32f *pSrc, Ipp32f *pSrcDst, int len);
IppStatus ippsSqr_32f(const Ipp32f *pSrc, Ipp32f *pDst, int len);
IppStatus ippsSqr_32f_I(Ipp32f *pSrcDst, int len);
IppStatus ippsSqrt_32f_A11(const Ipp32f *pSrc, Ipp32f *pDst, int len);
IppStatus ippsExp_32f_A11(const Ipp32f *pSrc, Ipp32f *pDst, int len);
IppStatus ippsThreshold_GT_32f_I(Ipp32f *pSrcDst, int len, Ipp32f level);
IppStatus ippsThreshold_LT_32f_I(Ipp32f *pSrcDst, int len, Ipp32f level);
IppStatus ippsVectorSlope_32f(Ipp32f *pDst, int len, Ipp32f offset, Ipp32f slope);
IppStatus ippsConvert_32f32s_Sfs(const Ipp32f *pSrc, Ipp32s *pDst, int len, int rndMode, int scaleFactor);
IppStatus ippsCopy_32f(const Ipp32f *pSrc, Ipp32f *pDst, int len);
IppStatus ippsSet_32f(Ipp32f val, Ipp32f *pDst, int len);
IppStatus ippsSet_32s(Ipp32s val, Ipp32s *pDst, int len);
/* 制御系 (win ローダが 420 名の GetProcAddress を要求するため必要) */
void *ippMalloc(int len);
void  ippFree(void *ptr);
IppStatus ippSetFlushToZero(int value, unsigned int *pUMask);
IppStatus ippSetDenormAreZeros(int value);
IppStatus ippSetNumThreads(int n);
/* 実数 FFT (Pack/CCS 形式)。実装は ipp_fft.c */
#define IPP_FFT_FAMILY_DECL(SFX, T) \
IppStatus ippsFFTGetSize_R_##SFX(int order, int flag, int hint, int *pSpecSize, int *pSpecBufSize, int *pBufSize); \
IppStatus ippsFFTInit_R_##SFX(void **ppSpec, int order, int flag, int hint, uint8_t *pSpec, uint8_t *pSpecBuf); \
IppStatus ippsFFTFwd_RToPack_##SFX(const T *s, T *d, const void *spec, uint8_t *b); \
IppStatus ippsFFTInv_PackToR_##SFX(const T *s, T *d, const void *spec, uint8_t *b); \
IppStatus ippsFFTFwd_RToPack_##SFX##_I(T *sd, const void *spec, uint8_t *b); \
IppStatus ippsFFTInv_PackToR_##SFX##_I(T *sd, const void *spec, uint8_t *b);
IPP_FFT_FAMILY_DECL(32f, float)
IPP_FFT_FAMILY_DECL(64f, double)
IppStatus ippsFFTFwd_RToCCS_32f_I(float *sd, const void *spec, uint8_t *b);
IppStatus ippsFFTInv_CCSToR_32f_I(float *sd, const void *spec, uint8_t *b);
