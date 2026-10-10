/* IPP FFT (ippsFFT*_R_32f/64f, 28 関数) の宣言 — CAB-139 (pffft 実装) 用。
   シグネチャは shim/data/ipp_sigs.json (gen_shim.py 生成) から機械的に転記したもので,
   gen/ipp_proto.h と同一 (食い違いは fft_e2e.sh の proto 突合 TU で検出する)。編集は署名表由来で行うこと。 */
#pragma once
#include <stdint.h>
#include "pffft/pffft.h"
#include "pffft/pffft_double.h"

typedef int IppStatus; typedef float Ipp32f; typedef double Ipp64f; typedef uint8_t Ipp8u;

/* vendored pffft に加えた CAB-139 パッチ関数 (pffft.c / pffft_double.c 内で定義)。
   IPP の spec メモリモデル (呼出し側バッファ内に spec を構築) のためのもの。詳細は PROVENANCE.md。 */
int pffft_setup_bytes(int N, pffft_transform_t transform);
PFFFT_Setup *pffft_new_setup_into(void *mem, int N, pffft_transform_t transform);
int pffftd_setup_bytes(int N, pffft_transform_t transform);
PFFFTD_Setup *pffftd_new_setup_into(void *mem, int N, pffft_transform_t transform);

IppStatus ippsFFTGetSize_R_32f(int order, int flag, int hint, int* pSpecSize, int* pSpecBufSize, int* pBufSize);
IppStatus ippsFFTGetSize_R_64f(int order, int flag, int hint, int* pSpecSize, int* pSpecBufSize, int* pBufSize);
IppStatus ippsFFTInit_R_32f(void** ppFFTSpec, int order, int flag, int hint, Ipp8u* pSpec, Ipp8u* pSpecBuffer);
IppStatus ippsFFTInit_R_64f(void** ppFFTSpec, int order, int flag, int hint, Ipp8u* pSpec, Ipp8u* pSpecBuffer);
IppStatus ippsFFTFwd_RToCCS_32f(const Ipp32f* pSrc, Ipp32f* pDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTFwd_RToCCS_32f_I(Ipp32f* pSrcDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTFwd_RToCCS_64f(const Ipp64f* pSrc, Ipp64f* pDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTFwd_RToCCS_64f_I(Ipp64f* pSrcDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTFwd_RToPack_32f(const Ipp32f* pSrc, Ipp32f* pDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTFwd_RToPack_32f_I(Ipp32f* pSrcDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTFwd_RToPack_64f(const Ipp64f* pSrc, Ipp64f* pDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTFwd_RToPack_64f_I(Ipp64f* pSrcDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTFwd_RToPerm_32f(const Ipp32f* pSrc, Ipp32f* pDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTFwd_RToPerm_32f_I(Ipp32f* pSrcDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTFwd_RToPerm_64f(const Ipp64f* pSrc, Ipp64f* pDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTFwd_RToPerm_64f_I(Ipp64f* pSrcDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTInv_CCSToR_32f(const Ipp32f* pSrc, Ipp32f* pDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTInv_CCSToR_32f_I(Ipp32f* pSrcDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTInv_CCSToR_64f(const Ipp64f* pSrc, Ipp64f* pDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTInv_CCSToR_64f_I(Ipp64f* pSrcDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTInv_PackToR_32f(const Ipp32f* pSrc, Ipp32f* pDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTInv_PackToR_32f_I(Ipp32f* pSrcDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTInv_PackToR_64f(const Ipp64f* pSrc, Ipp64f* pDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTInv_PackToR_64f_I(Ipp64f* pSrcDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTInv_PermToR_32f(const Ipp32f* pSrc, Ipp32f* pDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTInv_PermToR_32f_I(Ipp32f* pSrcDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTInv_PermToR_64f(const Ipp64f* pSrc, Ipp64f* pDst, const void* pFFTSpec, Ipp8u* pBuffer);
IppStatus ippsFFTInv_PermToR_64f_I(Ipp64f* pSrcDst, const void* pFFTSpec, Ipp8u* pBuffer);
