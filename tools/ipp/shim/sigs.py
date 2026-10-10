#!/usr/bin/env python3
"""420 名の IPP 関数署名の導出 (IPP ヘッダ現物は手元に無いため: 命名規則 + 公開 API の知識 → 呼出箇所実績で独立に検算)。

derive(name) -> (ret_ctype, "C 仮引数列", family)。仮引数列は C 宣言そのもの (生成ヘッダにそのまま出す)。
ABI 上の分類は gen_shim.classify() が C 型名から行う (MS x64: 8B 以下の struct は GPR 値渡し、16B 構造体は呼出側コピーへのポインタ)。
IPP の enum (IppRoundMode/IppHintAlgorithm/IppiAxis/...) は ABI 同一なので int で書く (実装 ipp_min.h と型衝突させないため)。"""
import re

CT = {'8u': 'Ipp8u', '16s': 'Ipp16s', '16u': 'Ipp16u', '32s': 'Ipp32s', '32u': 'Ipp32u', '64s': 'Ipp64s', '32f': 'Ipp32f', '64f': 'Ipp64f',
      '32fc': 'Ipp32fc', '64fc': 'Ipp64fc', '16sc': 'Ipp16sc', '32sc': 'Ipp32sc', '64sc': 'Ipp64sc', '24s': 'Ipp8u', '24u': 'Ipp8u'}
VM_UNARY = {'Exp', 'Expm1', 'Ln', 'Log10', 'Sqrt', 'Cbrt', 'Inv', 'Sin', 'Cos', 'Tan', 'Atan', 'Tanh'}
VM_BINARY = {'Div', 'Pow', 'Atan2'}


def cp(t, c=True): return ('const ' if c else '') + CT[t] + '*'


def derive(name):
    """(ret, params, family)。未知なら None。"""
    if name in EXPLICIT: r = EXPLICIT[name]; return (r[0], r[1], r[2] if len(r) > 2 else 'explicit')
    if name.startswith('ippi'): return None            # ippi は全て EXPLICIT
    m = re.match(r'^ipps([A-Za-z0-9]+?)_((?:\d+[a-z]+?)(?:\d+[a-z]+)?)((?:_[A-Za-z0-9]+)*)$', name)
    if not m: return None
    stem, ty, suf = m.group(1), m.group(2), m.group(3)
    sfx = [s for s in suf.split('_') if s]
    inpl = 'I' in sfx; acc = next((s for s in sfx if re.fullmatch(r'A\d+', s)), None); sfs = 'Sfs' in sfx
    # 型 2 つ並び (例 32f64f / 32f32fc)
    tys = re.findall(r'\d+[a-z]+?(?=\d|$)', ty) if ty not in CT else [ty]
    if ty in CT: tys = [ty]
    else:
        mm = re.match(r'^(\d+[a-z]+?)(\d+[a-z]+)$', ty)
        tys = [mm.group(1), mm.group(2)] if mm and mm.group(1) in CT and mm.group(2) in CT else [ty]
    if any(t not in CT for t in tys): return None
    T = tys[0]; Tn = CT[T]; V = Tn   # 値渡し型
    if acc:                                            # ippvm (精度等級付き): len は Ipp32s n
        if stem in VM_UNARY: return ('IppStatus', f'{cp(T)} a, {Tn}* r, Ipp32s n', 'vm-unary')
        if stem in VM_BINARY: return ('IppStatus', f'{cp(T)} a, {cp(T)} b, {Tn}* r, Ipp32s n', 'vm-binary')
        if stem == 'Powx': return ('IppStatus', f'{cp(T)} a, const {Tn} b, {Tn}* r, Ipp32s n', 'vm-powx')
        if stem == 'SinCos': return ('IppStatus', f'{cp(T)} a, {Tn}* r1, {Tn}* r2, Ipp32s n', 'vm-sincos')
        return None
    if stem in ('Add', 'Sub', 'Mul'):
        if len(tys) == 2:                              # Mul_32f32fc: (f, fc) -> fc
            T2 = CT[tys[1]]
            return ('IppStatus', f'{cp(T)} pSrc, {T2}* pSrcDst, int len', 'arith-mixed-I') if inpl else ('IppStatus', f'{cp(T)} pSrc1, const {T2}* pSrc2, {T2}* pDst, int len', 'arith-mixed')
        return ('IppStatus', f'{cp(T)} pSrc, {Tn}* pSrcDst, int len', 'arith-I') if inpl else ('IppStatus', f'{cp(T)} pSrc1, {cp(T)} pSrc2, {Tn}* pDst, int len', 'arith')
    if stem in ('AddC', 'SubC', 'MulC', 'DivC', 'SubCRev', 'DivCRev'):
        return ('IppStatus', f'{V} val, {Tn}* pSrcDst, int len', 'const-arith-I') if inpl else ('IppStatus', f'{cp(T)} pSrc, {V} val, {Tn}* pDst, int len', 'const-arith')
    if stem in ('Sqr', 'Abs', 'Sqrt', 'Conj', 'Trunc', 'Round', 'Flip', 'Exp', 'Ln', 'Arctan', 'ConjFlip') and not acc:
        if stem in ('Exp', 'Ln', 'Arctan', 'Sqrt') and not inpl:
            if stem == 'Exp' and len(tys) == 2: return ('IppStatus', f'{cp(T)} pSrc, {CT[tys[1]]}* pDst, int len', 'unary-cvt')
            if stem == 'Ln' and len(tys) == 2: return ('IppStatus', f'{cp(T)} pSrc, {CT[tys[1]]}* pDst, int len', 'unary-cvt')
        return ('IppStatus', f'{Tn}* pSrcDst, int len', 'unary-I') if inpl else ('IppStatus', f'{cp(T)} pSrc, {Tn}* pDst, int len', 'unary')
    if stem in ('ConjCcs', 'ConjPack', 'ConjPerm'):
        return ('IppStatus', f'{Tn}* pSrcDst, int lenDst', 'conj-I') if inpl else ('IppStatus', f'const {CT["32f" if T == "32fc" else "64f"]}* pSrc, {Tn}* pDst, int lenDst', 'conj')
    if stem in ('Real', 'Imag', 'Phase', 'Magnitude', 'PowerSpectr'):
        rt = CT['32f' if T == '32fc' else '64f']; return ('IppStatus', f'{cp(T)} pSrc, {rt}* pDst, int len', 'cplx-unary')
    if stem == 'CplxToReal': rt = CT[{'32fc': '32f', '64fc': '64f', '16sc': '16s'}[T]]; return ('IppStatus', f'{cp(T)} pSrc, {rt}* pDstRe, {rt}* pDstIm, int len', 'cplx-split')
    if stem == 'RealToCplx':
        ct = {'32f': '32fc', '64f': '64fc', '16s': '16sc'}[T]; return ('IppStatus', f'{cp(T)} pSrcRe, {cp(T)} pSrcIm, {CT[ct]}* pDst, int len', 'cplx-join')
    if stem == 'AddProduct': return ('IppStatus', f'{cp(T)} pSrc1, {cp(T)} pSrc2, {Tn}* pSrcDst, int len', 'addproduct')
    if stem == 'AddProductC': return ('IppStatus', f'{cp(T)} pSrc, const {Tn} val, {Tn}* pSrcDst, int len', 'addproduct-c')
    if stem == 'MulPack': return ('IppStatus', f'{cp(T)} pSrc, {Tn}* pSrcDst, int len', 'mulpack-I') if inpl else ('IppStatus', f'{cp(T)} pSrc1, {cp(T)} pSrc2, {Tn}* pDst, int len', 'mulpack')
    if stem in ('Copy', 'Move'): return ('IppStatus', f'{cp(T)} pSrc, {Tn}* pDst, int len', 'mem')
    if stem == 'Zero': return ('IppStatus', f'{Tn}* pDst, int len', 'mem')
    if stem == 'Set': return ('IppStatus', f'{V} val, {Tn}* pDst, int len', 'mem-set')
    if stem == 'Convert':
        d = CT[tys[1]] if len(tys) == 2 else None
        if d is None: return None
        flt_src = T in ('32f', '64f')
        if sfs: return ('IppStatus', f'{cp(T)} pSrc, {d}* pDst, int len, int rndMode, int scaleFactor', 'convert-sfs-rnd') if flt_src else ('IppStatus', f'{cp(T)} pSrc, {d}* pDst, int len, int scaleFactor', 'convert-sfs')
        return ('IppStatus', f'{cp(T)} pSrc, {d}* pDst, int len', 'convert')
    if stem == 'SwapBytes': return ('IppStatus', f'{Tn}* pSrcDst, int len', 'swap-I') if inpl else ('IppStatus', f'{cp(T)} pSrc, {Tn}* pDst, int len', 'swap')
    if stem in ('Max', 'Min', 'MaxAbs', 'MinAbs', 'Sum') and not inpl:
        if stem == 'Sum' and T == '32f': return ('IppStatus', f'{cp(T)} pSrc, int len, {Tn}* pSum, int hint', 'reduce')
        return ('IppStatus', f'{cp(T)} pSrc, int len, {Tn}* pRes', 'reduce')
    if stem == 'MinMax': return ('IppStatus', f'{cp(T)} pSrc, int len, {Tn}* pMin, {Tn}* pMax', 'reduce-minmax')
    if stem in ('XorC', 'OrC', 'AndC') and inpl: return ('IppStatus', f'{V} val, {Tn}* pSrcDst, int len', 'logic-I')
    if stem == 'VectorSlope': return ('IppStatus', f'{Tn}* pDst, int len, Ipp32f offset, Ipp32f slope', 'gen') if T in ('32f', '32s') else ('IppStatus', f'{Tn}* pDst, int len, Ipp64f offset, Ipp64f slope', 'gen')
    return None


def thr(name):
    m = re.fullmatch(r'ipps(Threshold_(?:LTValGTVal|LTVal|GTVal|LTAbs|GTAbs|LT|GT))_(\w+?)(_I)?', name)
    if not m: return None
    kind, T, inpl = m.group(1), m.group(2), bool(m.group(3)); Tn = CT[T]
    lv = {'Threshold_LTValGTVal': f'{Tn} levelLT, {Tn} valueLT, {Tn} levelGT, {Tn} valueGT', 'Threshold_LTVal': f'{Tn} level, {Tn} value', 'Threshold_GTVal': f'{Tn} level, {Tn} value'}.get(kind, f'{Tn} level')
    return ('IppStatus', (f'{Tn}* pSrcDst, int len, ' if inpl else f'{cp(T)} pSrc, {Tn}* pDst, int len, ') + lv, 'threshold')


# ---- 規則に乗らないもの: 明示 (C 仮引数列; ret は既定 IppStatus) ----
S = 'IppStatus'
E = {}
def e(n, params, ret=S, fam='explicit'): E[n] = (ret, params, fam)

e('ippMalloc', 'int length', 'void*', 'control'); e('ippFree', 'void* ptr', 'void', 'control')
e('ippSetFlushToZero', 'int value, unsigned int* pUMask', fam='control'); e('ippSetDenormAreZeros', 'int value', fam='control')
e('ippSetNumThreads', 'int numThr', fam='control'); e('ippGetNumThreads', 'int* pNumThr', fam='control')
e('ippGetLibVersion', '', 'const void*', 'control')
e('ippsInterleave_16s', 'const Ipp16s* const* pSrc, int nChannels, int len, Ipp16s* pDst', fam='reorder'); e('ippsInterleave_32f', 'const Ipp32f* const* pSrc, int nChannels, int len, Ipp32f* pDst', fam='reorder')
e('ippsDeinterleave_16s', 'const Ipp16s* pSrc, int nChannels, int len, Ipp16s* const* pDst', fam='reorder'); e('ippsDeinterleave_32f', 'const Ipp32f* pSrc, int nChannels, int len, Ipp32f* const* pDst', fam='reorder')
e('ippsCompare_8u', 'const Ipp8u* pSrc1, const Ipp8u* pSrc2, int len, int* pResult'); e('ippsEqual_8u', 'const Ipp8u* pSrc1, const Ipp8u* pSrc2, int len, int* pResult')
e('ippsArctan_32f_I', 'Ipp32f* pSrcDst, int len'); e('ippsFilterMedian_32f_I', 'Ipp32f* pSrcDst, int len, int maskSize, const Ipp32f* pDlySrc, Ipp32f* pDlyDst, Ipp8u* pBuffer')
e('ippsAutoCorr_NormA_32f', 'const Ipp32f* pSrc, int srcLen, Ipp32f* pDst, int dstLen, Ipp8u* pBuffer')
e('ippsConv_32f', 'const Ipp32f* pSrc1, int src1Len, const Ipp32f* pSrc2, int src2Len, Ipp32f* pDst'); e('ippsConv_64f', 'const Ipp64f* pSrc1, int src1Len, const Ipp64f* pSrc2, int src2Len, Ipp64f* pDst')
e('ippsCrossCorr_32f', 'const Ipp32f* pSrc1, int src1Len, const Ipp32f* pSrc2, int src2Len, Ipp32f* pDst, int dstLen, int lowLag')
for t, T in (('32f', 'Ipp32f'), ('64f', 'Ipp64f')):
    e(f'ippsTone_Direct_{t}', f'{T}* pDst, int len, {T} magn, {T} rFreq, {T}* pPhase, int hint', fam='siggen')
    e(f'ippsRandUniform_Direct_{t}', f'{T}* pDst, int len, {T} low, {T} high, unsigned int* pSeed', fam='siggen')
    e(f'ippsRandGauss_Direct_{t}', f'{T}* pDst, int len, {T} mean, {T} stdDev, unsigned int* pSeed', fam='siggen')
    e(f'ippsWinKaiser_{t}_I', f'{T}* pSrcDst, int len, {T} alpha', fam='siggen')
    e(f'ippsFFTGetSize_R_{t}', 'int order, int flag, int hint, int* pSpecSize, int* pSpecBufSize, int* pBufSize', fam='fft')
    e(f'ippsFFTInit_R_{t}', 'void** ppFFTSpec, int order, int flag, int hint, Ipp8u* pSpec, Ipp8u* pSpecBuffer', fam='fft')
    for fw, srcf in (('Fwd_RToPack', 1), ('Fwd_RToPerm', 1), ('Fwd_RToCCS', 1), ('Inv_PackToR', 1), ('Inv_PermToR', 1), ('Inv_CCSToR', 1)):
        e(f'ippsFFT{fw}_{t}', f'const {T}* pSrc, {T}* pDst, const void* pFFTSpec, Ipp8u* pBuffer', fam='fft')
        e(f'ippsFFT{fw}_{t}_I', f'{T}* pSrcDst, const void* pFFTSpec, Ipp8u* pBuffer', fam='fft')
e('ippsTone_Direct_32fc', 'Ipp32fc* pDst, int len, Ipp32f magn, Ipp32f rFreq, Ipp32f* pPhase, int hint', fam='siggen')
e('ippsDivCRev_32f_I', 'Ipp32f val, Ipp32f* pSrcDst, int len')
e('ippsAddC_32fc', 'const Ipp32fc* pSrc, Ipp32fc val, Ipp32fc* pDst, int len', fam='const-arith')
# FIR / IIR (IPP 7.x 以前系 API。引数順は記憶ベース: 個数/型位置は呼出箇所で検算, 順序は未検証)
for p, tp, TT in (('', '32f', 'Ipp32f'), ('64f', '32f', 'Ipp64f')):
    nm = lambda s: f'ipps{s}{p}_32f' if p else f'ipps{s}_32f'
    e(nm('FIRInitAlloc'), f'void** ppState, const {TT}* pTaps, int tapsLen, const Ipp32f* pDlyLine', fam='fir')
    e(nm('FIRMRInitAlloc'), f'void** ppState, const {TT}* pTaps, int tapsLen, int upFactor, int upPhase, int downFactor, int downPhase, const Ipp32f* pDlyLine', fam='fir')
    e(nm('FIRFree'), 'void* pState', fam='fir')
    e(nm('FIR'), 'const Ipp32f* pSrc, Ipp32f* pDst, int numIters, void* pState', fam='fir')
    e(nm('FIR') + '_I', 'Ipp32f* pSrcDst, int numIters, void* pState', fam='fir')
    e(nm('FIRSetDlyLine'), 'void* pState, const Ipp32f* pDlyLine', fam='fir')
    e(nm('FIRSetTaps'), f'const {TT}* pTaps, void* pState', fam='fir')
e('ippsIIR64f_32f_I', 'Ipp32f* pSrcDst, int len, void* pState', fam='iir')
e('ippsIIRInit64f_BiQuad_32f', 'void** ppState, const Ipp64f* pTaps, int numBq, const Ipp64f* pDlyLine, Ipp8u* pBuf', fam='iir')
e('ippsIIRGetStateSize64f_BiQuad_32f', 'int numBq, int* pBufferSize', fam='iir')

# ---- ippi (imaging)。IppiSize/IppiPoint=8B 値渡し(GPR)、IppiRect=16B(呼出側コピーへのポインタ) ----
P = 'const Ipp8u* pSrc, int srcStep, Ipp8u* pDst, int dstStep, IppiSize roiSize'
for n in ('ippiCopy_8u_C3R', 'ippiCopy_8u_C4R', 'ippiCopy_8u_C1C4R', 'ippiCopy_8u_C3AC4R', 'ippiCopy_8u_AC4C3R', 'ippiRGBToGray_8u_AC4C1R', 'ippiAlphaPremul_8u_AC4R'): e(n, P, fam='ippi')
e('ippiCopy_8u_P3C3R', 'const Ipp8u* const* pSrc, int srcStep, Ipp8u* pDst, int dstStep, IppiSize roiSize', fam='ippi')
e('ippiCopyManaged_8u_C1R', P + ', int flags', fam='ippi')
e('ippiColorToGray_8u_C3C1R', P + ', const Ipp32f* coeffs', fam='ippi'); e('ippiColorToGray_8u_AC4C1R', P + ', const Ipp32f* coeffs', fam='ippi')
e('ippiSet_8u_C3R', 'const Ipp8u* value, Ipp8u* pDst, int dstStep, IppiSize roiSize', fam='ippi'); e('ippiSet_8u_C4R', 'const Ipp8u* value, Ipp8u* pDst, int dstStep, IppiSize roiSize', fam='ippi')
e('ippiAlphaPremul_8u_AC4IR', 'Ipp8u* pSrcDst, int srcDstStep, IppiSize roiSize', fam='ippi')
e('ippiAlphaComp_8u_AC4R', 'const Ipp8u* pSrc1, int src1Step, const Ipp8u* pSrc2, int src2Step, Ipp8u* pDst, int dstStep, IppiSize roiSize, int alphaType', fam='ippi')
for n in ('ippiAlphaCompC_8u_C3R', 'ippiAlphaCompC_8u_C4R', 'ippiAlphaCompC_8u_AC4R'):
    e(n, 'const Ipp8u* pSrc1, int src1Step, Ipp8u alpha1, const Ipp8u* pSrc2, int src2Step, Ipp8u alpha2, Ipp8u* pDst, int dstStep, IppiSize roiSize, int alphaType', fam='ippi')
for n in ('ippiFilterBox_8u_C1IR', 'ippiFilterBox_8u_C3IR', 'ippiFilterBox_8u_C4IR'): e(n, 'Ipp8u* pSrcDst, int srcDstStep, IppiSize dstRoiSize, IppiSize maskSize, IppiPoint anchor', fam='ippi')
for n in ('ippiFilterBox_8u_C4R', 'ippiFilterBox_8u_C3R'): e(n, P.replace('roiSize', 'dstRoiSize') + ', IppiSize maskSize, IppiPoint anchor', fam='ippi')
e('ippiFilterBoxBorderGetBufferSize', 'IppiSize dstRoiSize, IppiSize maskSize, int dataType, int numChannels, int* pBufferSize', fam='ippi')
for n in ('ippiFilterBoxBorder_8u_C1R', 'ippiFilterBoxBorder_8u_C3R', 'ippiFilterBoxBorder_8u_C4R'):
    e(n, 'const Ipp8u* pSrc, int srcStep, Ipp8u* pDst, int dstStep, IppiSize dstRoiSize, IppiSize maskSize, int border, const Ipp8u* borderValue, Ipp8u* pBuffer', fam='ippi')
e('ippiFilter_8u_C4R', P.replace('roiSize', 'dstRoiSize') + ', const Ipp32s* pKernel, IppiSize kernelSize, IppiPoint anchor, int divisor', fam='ippi')
e('ippiFilterGauss_8u_C4R', P.replace('roiSize', 'dstRoiSize') + ', int maskSize', fam='ippi')
e('ippiFilter_Round32f_8u_C1R', P.replace('roiSize', 'dstRoiSize') + ', const Ipp32f* pKernel, IppiSize kernelSize, IppiPoint anchor, Ipp8u* pBuffer', fam='ippi')
e('ippiFilterRoundGetBufSize32f_8u_C1R', 'IppiSize roiSize, IppiSize kernelSize, int* pBufferSize', fam='ippi')
for n in ('ippiAddC_8u_C3IRSfs', 'ippiAddC_8u_C4IRSfs', 'ippiSubC_8u_C3IRSfs', 'ippiSubC_8u_C4IRSfs', 'ippiMulC_8u_C3IRSfs', 'ippiMulC_8u_C4IRSfs'):
    e(n, 'const Ipp8u* value, Ipp8u* pSrcDst, int srcDstStep, IppiSize roiSize, int scaleFactor', fam='ippi')
for n in ('ippiAddC_8u_C3RSfs', 'ippiAddC_8u_AC4RSfs', 'ippiMulC_8u_C3RSfs', 'ippiMulC_8u_C4RSfs', 'ippiMulC_8u_AC4RSfs'):
    e(n, 'const Ipp8u* pSrc, int srcStep, const Ipp8u* value, Ipp8u* pDst, int dstStep, IppiSize roiSize, int scaleFactor', fam='ippi')
e('ippiMulC_8u_C1RSfs', 'const Ipp8u* pSrc, int srcStep, Ipp8u value, Ipp8u* pDst, int dstStep, IppiSize roiSize, int scaleFactor', fam='ippi')
e('ippiMul_8u_C4IRSfs', 'const Ipp8u* pSrc, int srcStep, Ipp8u* pSrcDst, int srcDstStep, IppiSize roiSize, int scaleFactor', fam='ippi')
for c in ('C3R', 'C4R'):
    e(f'ippiResize_8u_{c}', 'const Ipp8u* pSrc, IppiSize srcSize, int srcStep, IppiRect srcRoi, Ipp8u* pDst, int dstStep, IppiSize dstRoiSize, double xFactor, double yFactor, int interpolation', fam='ippi')
    e(f'ippiResizeCenter_8u_{c}', 'const Ipp8u* pSrc, IppiSize srcSize, int srcStep, IppiRect srcRoi, Ipp8u* pDst, int dstStep, IppiSize dstRoiSize, double xFactor, double yFactor, double xCenter, double yCenter, int interpolation', fam='ippi')
for c in ('C1R', 'C3R', 'C4R'):
    e(f'ippiResizeSqrPixel_8u_{c}', 'const Ipp8u* pSrc, IppiSize srcSize, int srcStep, IppiRect srcRoi, Ipp8u* pDst, int dstStep, IppiRect dstRoi, double xFactor, double yFactor, double xShift, double yShift, int interpolation, Ipp8u* pBuffer', fam='ippi')
e('ippiResizeSqrPixelGetBufSize', 'IppiSize dstSize, int nChannel, int interpolation, int* pSize', fam='ippi')
e('ippiResizeGetBufSize', 'IppiRect srcRoi, IppiRect dstRoi, int nChannel, int interpolation, int* pSize', fam='ippi')
e('ippiMirror_8u_C3IR', 'Ipp8u* pSrcDst, int srcDstStep, IppiSize roiSize, int flip', fam='ippi'); e('ippiMirror_8u_C4IR', 'Ipp8u* pSrcDst, int srcDstStep, IppiSize roiSize, int flip', fam='ippi')
e('ippiMirror_8u_C4R', P + ', int flip', fam='ippi')
for c in ('C3R', 'C4R'):
    e(f'ippiWarpAffine_8u_{c}', 'const Ipp8u* pSrc, IppiSize srcSize, int srcStep, IppiRect srcRoi, Ipp8u* pDst, int dstStep, IppiRect dstRoi, const double* coeffs, int interpolation', fam='ippi')
    for q in ('WarpAffineQuad', 'WarpPerspectiveQuad', 'WarpBilinearQuad'):
        e(f'ippi{q}_8u_{c}', 'const Ipp8u* pSrc, IppiSize srcSize, int srcStep, IppiRect srcRoi, const double* srcQuad, Ipp8u* pDst, int dstStep, IppiRect dstRoi, const double* dstQuad, int interpolation', fam='ippi')
    e(f'ippiRemap_8u_{c}', 'const Ipp8u* pSrc, IppiSize srcSize, int srcStep, IppiRect srcRoi, const Ipp32f* pxMap, int xMapStep, const Ipp32f* pyMap, int yMapStep, Ipp8u* pDst, int dstStep, IppiSize dstRoiSize, int interpolation', fam='ippi')
    e(f'ippiCopyConstBorder_8u_{c}', 'const Ipp8u* pSrc, int srcStep, IppiSize srcRoiSize, Ipp8u* pDst, int dstStep, IppiSize dstRoiSize, int topBorderHeight, int leftBorderWidth, const Ipp8u* value', fam='ippi')
    e(f'ippiCopyReplicateBorder_8u_{c}', 'const Ipp8u* pSrc, int srcStep, IppiSize srcRoiSize, Ipp8u* pDst, int dstStep, IppiSize dstRoiSize, int topBorderHeight, int leftBorderWidth', fam='ippi')
e('ippiRotateCenter_8u_C4R', 'const Ipp8u* pSrc, IppiSize srcSize, int srcStep, IppiRect srcRoi, Ipp8u* pDst, int dstStep, IppiRect dstRoi, double angle, double xCenter, double yCenter, int interpolation', fam='ippi')
# complex Set (値渡し複素数)
for t in ('16sc', '32sc', '32fc', '64sc', '64fc'): e(f'ippsSet_{t}', f'{CT[t]} val, {CT[t]}* pDst, int len', fam='mem-set')
EXPLICIT = E
_derive_rules = derive
def derive(name):  # noqa: F811  (明示表 → threshold → 規則)
    if name in E: r = E[name]; return (r[0], r[1], r[2])
    r = thr(name)
    if r: return r
    return _derive_rules(name)

# ---- thunk デコーダの ABI 検証用プローブ (実 IPP には無い署名。MS x64 の特殊ケース: スタック上の float/double、値渡し struct 8B/16B/4B、狭い整数、13 引数) ----
PROBES = [
    ('probe_narrow', 'IppStatus', 'Ipp8u a, Ipp16s b, unsigned int c, Ipp64s d, double e, float f'),
    ('probe_float', 'IppStatus', 'float a, double b, float c, double d, double e, float f'),
    ('probe_struct', 'IppStatus', 'IppiSize s, Ipp32fc c, IppiRect r, Ipp64fc z, IppiPoint p, Ipp16sc q'),
    ('probe_mixed', 'IppStatus', 'double a, int b, double c, int d, int e, double f'),
    ('probe_many', 'IppStatus', 'const Ipp8u* pSrc, IppiSize srcSize, int srcStep, IppiRect srcRoi, Ipp8u* pDst, int dstStep, IppiRect dstRoi, double xFactor, double yFactor, double xShift, double yShift, int interpolation, Ipp8u* pBuffer'),
    ('probe_ptr', 'void*', 'int n'),
]
