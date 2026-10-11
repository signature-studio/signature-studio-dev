#!/usr/bin/env python3
"""IPP-7 (CAB-262) stub 充填の独立再計算 (規則 37)。

数え方の定義 (規則 36):
  - 「関数」= tools/ipp/shim/data/ipp_sigs.json の 420 エントリのうち impl=true のもの
    (= gen_shim.py が nm で検出した ipp* 定義シンボル。shim/impl/*.c と src/ipp_*.c,
     fft/*.c が対象。gen/ipp_shim_tab.c の blk_<name> は生成物なので数えない)
  - 「stub」= 420 - impl
  - 「win 呼出モジュール数」= data/ipp_matrix.csv の win_modules 列
    (win64 全 145〜150 モジュールの IPP 呼出箇所を持ち、そのモジュールのユニーク数)
  - 「使用集合 239」= data/ipp_matrix.csv の used_win/used_mac_x86/used_mac_arm64 の
    いずれかが 1 の distinct 関数 (C5 と同一定義)

usage: python3 count_fill3.py
"""
import csv, glob, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
IPP = os.path.dirname(HERE)
sig = json.load(open(f'{HERE}/data/ipp_sigs.json'))['entries']
matrix = {r['name']: r for r in csv.DictReader(open(f'{IPP}/data/ipp_matrix.csv'))}

NAMES_CAB136 = set("""ippsOrC_32u_I ippiSet_8u_C3R ippiCopy_8u_C3R ippiCopy_8u_C4R ippiCopy_8u_C1C4R
ippiCopy_8u_C3AC4R ippiCopy_8u_AC4C3R ippiCopyManaged_8u_C1R ippiAlphaPremul_8u_AC4IR
ippiFilterBox_8u_C3IR ippiFilterBox_8u_C4IR ippiAddC_8u_C3IRSfs ippiAddC_8u_C4IRSfs
ippiSubC_8u_C3IRSfs ippiSubC_8u_C4IRSfs ippsSet_64s ippsSqrt_32f_A21 ippsThreshold_GT_32f
ippiAlphaCompC_8u_C3R ippiAlphaCompC_8u_C4R ippiMulC_8u_C3IRSfs ippiCopyConstBorder_8u_C3R
ippiCopyConstBorder_8u_C4R ippiCopyReplicateBorder_8u_C3R ippiCopyReplicateBorder_8u_C4R
ippsFIRInitAlloc_32f ippsFIRInitAlloc_64f_32f ippsFIRMRInitAlloc_32f ippsFIRMRInitAlloc_64f_32f
ippsIIRInit64f_BiQuad_32f ippsIIRGetStateSize64f_BiQuad_32f ippiResizeGetBufSize
ippiResizeSqrPixelGetBufSize ippiFilterBoxBorderGetBufferSize
ippiFilterRoundGetBufSize32f_8u_C1R""".split())
NAMES_CAB245 = set("""ippiResizeSqrPixel_8u_C1R ippiResizeSqrPixel_8u_C3R ippiResizeSqrPixel_8u_C4R
ippsThreshold_GT_32s_I ippsSub_32f_I ippsCopy_32s ippsAtan_32f_A11""".split())
NAMES_CAB262 = set("""ippsRealToCplx_32f ippsCplxToReal_32fc ippsCopy_8u ippsZero_32s ippsZero_64s ippsCopy_64s
ippsMinMax_32f ippsMinMax_16s ippsMin_16s ippsMax_16s ippsRound_32f ippsAbs_32f ippsFlip_32f_I
ippsFlip_16u_I ippsSwapBytes_32u_I ippsSwapBytes_16u_I ippsSet_64f ippsPowerSpectr_32fc
ippsAddProductC_32f ippsThreshold_LT_64f_I ippsThreshold_LT_32s_I
ippsThreshold_LTValGTVal_32f_I ippsVectorSlope_64f ippsInterleave_32f ippsInterleave_16s
ippsDeinterleave_32f ippsDeinterleave_16s ippsWinKaiser_32f_I ippsConvert_16s32f""".split())

impl = [r for r in sig if r['impl']]
stub = [r for r in sig if not r['impl']]
used = set(n for n, r in matrix.items()
           if r.get('used_win') == '1' or r.get('used_mac_x86') == '1' or r.get('used_mac_arm64') == '1')

print('== IPP shim 実装/stub (数え方: data/ipp_sigs.json の 420 エントリ, impl フラグ) ==')
print(f'  全名 420 / 型付き thunk (impl=true) {len(impl)} / fail-soft stub {len(stub)}')
print(f'  使用集合 239 中 実装済 {sum(1 for r in impl if r["name"] in used)} / stub {sum(1 for r in stub if r["name"] in used)}')
print()
print('== チケット別の増分 (gen_shim.py の実装検出 = nm on src/ipp_*.c + fft/*.c + impl/*.c) ==')
# 独立検算: nm で直接数える
names = set()
files = sorted(glob.glob(f'{IPP}/src/ipp_*.c')) + sorted(glob.glob(f'{HERE}/fft/*.c')) + \
        sorted(glob.glob(f'{HERE}/fft/pffft/*.c')) + sorted(glob.glob(f'{HERE}/impl/*.c'))
for f in files:
    subprocess.run(['gcc', '-c', '-O0', '-I', f'{IPP}/src', '-o', '/tmp/opencode/_cnt.o', f], check=True, capture_output=True)
    out = subprocess.run(['nm', '-g', '--defined-only', '/tmp/opencode/_cnt.o'], capture_output=True, text=True).stdout
    names |= set(re.findall(r'\sT\s(ipp\w+)', out))
print(f'  nm 実装シンボル {len(names)} (impl=true {len(impl)}, 差 {len(names) - len(impl)})')
assert names == set(r['name'] for r in impl), 'nm と ipp_sigs.json の impl 集合が不一致'
print()
print('== 優先順 (win_modules 降順) の新規 29 関数 ==')
rows = []
for n in sorted(NAMES_CAB262):
    if n not in set(r['name'] for r in impl):
        print(f'  !! {n} は未実装 (impl に無い)')
        continue
    rows.append((int(matrix[n]['win_modules']), n, n in used))
for wm, n, u in sorted(rows, reverse=True):
    print(f'  {wm:4d} modules  {n:34s} used239={u}')
print(f'  合計 {len(rows)} 関数 / win_modules 総和 {sum(r[0] for r in rows)}')
print()
print('== 残 stub の上位 (CAB-262 後) ==')
rem = sorted(((int(matrix[r['name']]['win_modules']), r['name']) for r in stub if r['name'] in matrix), reverse=True)
for wm, n in rem[:8]:
    print(f'  {wm:4d} modules  {n}')
print(f'  使用集合 239 内 stub {sum(1 for r in stub if r["name"] in used)} / 全 stub {len(stub)}')
