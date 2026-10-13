# KH-16 (#779) 付録: VEX census の生出力 (現行 filter)

REPORT.md §12 の根拠となる生出力。REPORT の本文から参照する。

- 測定 commit: `f354504c` (filter 条件は `is_ymm` / `startswith('v')`・`e0c79165` 以降で不変)
- 測定日時: 2026-10-13 (UTC 18:33 頃)・素材 `plugins-kilohearts.tar.zst` の `Kilohearts Offline Installer.zip` から抽出
- 上流 (`work/` は gitignore): `HeartCore.core_64` 76,642,304 B (sha256 `d55ce8b4c0ad7ebedf1a4a1f74443a91d255596be887a514e54269ec8751441e`) → rtti_walk (typedescriptor 6,923 / vtable 付き class 6,307) → callgraph (120,856 関数) → closures (infra 188)
- 依存: capstone 5.0.7 / pefile / numpy

## 1. vex256_census.py --json (mnemonic 別 per_snapin / total・全行)

```
vaddps       {'convolver': 22, 'filtertable': 26} total=48 | 1802de850 vaddps xmm3, xmm7, xmm3
vaddss       {'convolver': 2, 'filtertable': 9, 'ladder': 1, 'equalizer': 5} total=17 | 1802dee3b vaddss xmm5, xmm7, xmm6
vandpd       {'ladder': 4} total=4 | 180fd0092 vandpd xmm1, xmm0, xmmword ptr [rip + 0x12b4806]
vandps       {'filtertable': 1, 'equalizer': 1} total=2 | 180fb66a7 vandps xmm4, xmm4, xmmword ptr [rip + 0x12c8801]
vbroadcastss {'convolver': 6, 'filtertable': 10} total=16 | 1802de832 vbroadcastss xmm3, dword ptr [r8 + rax*4]
vcomisd      {'equalizer': 1} total=1 | 180fb69c0 vcomisd xmm3, qword ptr [rip + 0x12c85d8]
vcomiss      {'filtertable': 4, 'equalizer': 4} total=8 | 180fb6654 vcomiss xmm1, xmm4
vcvtdq2pd    {'ladder': 1, 'equalizer': 1} total=2 | 180fd00c1 vcvtdq2pd xmm1, xmm1
vcvtdq2ps    {'filtertable': 2, 'equalizer': 2} total=4 | 180fb664c vcvtdq2ps xmm5, xmm3
vcvtpd2dq    {'equalizer': 1} total=1 | 180fb69d8 vcvtpd2dq xmm4, xmm3
vcvtsd2ss    {'ladder': 2, 'equalizer': 1} total=3 | 180fd02ac vcvtsd2ss xmm0, xmm0, xmm0
vcvtsi2ss    {'convolver': 1, 'filtertable': 1} total=2 | 1802deda6 vcvtsi2ss xmm0, xmm15, edx
vcvtss2sd    {'ladder': 1, 'equalizer': 1} total=2 | 180fcffe7 vcvtss2sd xmm5, xmm0, xmm0
vcvttpd2dq   {'ladder': 1} total=1 | 180fd00ab vcvttpd2dq xmm2, xmm2
vdivsd       {'ladder': 3} total=3 | 180fd0072 vdivsd xmm3, xmm3, xmm2
vdivss       {'convolver': 1, 'filtertable': 2, 'equalizer': 1} total=4 | 1802dedb2 vdivss xmm0, xmm1, xmm0
vfmadd132sd  {'ladder': 1} total=1 | 180fd0031 vfmadd132sd xmm0, xmm5, qword ptr [rip + 0x12b48ee]
vfmadd213sd  {'ladder': 7, 'equalizer': 3} total=10 | 180fd004f vfmadd213sd xmm3, xmm1, qword ptr [rip + 0x12b4898]
vfmadd213ss  {'filtertable': 3, 'equalizer': 3} total=6 | 180fb66e9 vfmadd213ss xmm2, xmm1, dword ptr [rip + 0x12c887e]
vfmadd231sd  {'ladder': 2} total=2 | 180fd007a vfmadd231sd xmm0, xmm1, xmm3
vfmadd231ss  {'filtertable': 1, 'equalizer': 1} total=2 | 180fb670c vfmadd231ss xmm1, xmm2, xmm0
vfmsub213ss  {'filtertable': 2, 'equalizer': 2} total=4 | 180fb6711 vfmsub213ss xmm3, xmm5, xmm1
vfnmadd231sd {'ladder': 1, 'equalizer': 1} total=2 | 180fd00c9 vfnmadd231sd xmm2, xmm1, qword ptr [rip + 0x12b4876]
vmovapd      {'ladder': 1, 'equalizer': 2} total=3 | 180fd009a vmovapd xmm2, xmmword ptr [rip + 0x12b480e]
vmovaps      {'convolver': 161, 'filtertable': 179, 'equalizer': 11} total=351 | 1802de4a0 vmovaps xmmword ptr [rsp + 0x40], xmm8
vmovd        {'filtertable': 3, 'ladder': 3, 'equalizer': 9} total=15 | 180fb6640 vmovd eax, xmm0
vmovddup     {'filtertable': 1} total=1 | 180c669bb vmovddup xmm0, qword ptr [rip + 0xabcbcd]
vmovdqa      {'ladder': 1} total=1 | 180fd00c5 vmovdqa xmm2, xmm0
vmovdqu      {'ladder': 1} total=1 | 180fd012b vmovdqu xmm0, xmmword ptr [r9 + r10]
vmovlhps     {'convolver': 24, 'filtertable': 24} total=48 | 1802de544 vmovlhps xmm4, xmm0, xmm1
vmovq        {'ladder': 7, 'equalizer': 1} total=8 | 180fcffeb vmovq r9, xmm5
vmovsd       {'ladder': 5, 'equalizer': 1} total=6 | 180fd003f vmovsd xmm0, xmm5, xmm5
vmovss       {'convolver': 5, 'filtertable': 5} total=10 | 1802dedaa vmovss xmm1, dword ptr [rip + 0x10cafee]
vmulps       {'convolver': 29, 'filtertable': 33} total=62 | 1802de84c vmulps xmm7, xmm4, xmm0
vmulsd       {'ladder': 8, 'equalizer': 3} total=11 | 180fd0029 vmulsd xmm2, xmm5, xmm5
vmulss       {'convolver': 2, 'filtertable': 7, 'ladder': 1, 'equalizer': 5} total=15 | 1802dedf2 vmulss xmm4, xmm0, dword ptr [r8 + rax*4]
vpaddd       {'filtertable': 1, 'equalizer': 1} total=2 | 180fb669f vpaddd xmm1, xmm3, xmm1
vpand        {'filtertable': 5, 'equalizer': 5} total=10 | 180fb6650 vpand xmm1, xmm0, xmm4
vpmovsxdq    {'ladder': 1} total=1 | 180fd00af vpmovsxdq xmm1, xmm2
vpor         {'filtertable': 3, 'equalizer': 3} total=6 | 180fb66c0 vpor xmm2, xmm2, xmmword ptr [rip + 0x12c8888]
vpslld       {'filtertable': 1, 'equalizer': 1} total=2 | 180fb669a vpslld xmm3, xmm3, 1
vpsrld       {'filtertable': 2, 'equalizer': 2} total=4 | 180fb663b vpsrld xmm3, xmm0, 0x17
vpsrldq      {'ladder': 1} total=1 | 180fd0146 vpsrldq xmm0, xmm0, 8
vpsubd       {'filtertable': 2, 'equalizer': 2} total=4 | 180fb6644 vpsubd xmm3, xmm3, xmmword ptr [rip + 0x12c8884]
vpxor        {'filtertable': 1, 'equalizer': 1} total=2 | 180fb665e vpxor xmm1, xmm1, xmm1
vshufps      {'convolver': 55, 'filtertable': 57, 'ladder': 1} total=113 | 1802de554 vshufps xmm3, xmm4, xmm1, 0x88
vsubps       {'convolver': 12, 'filtertable': 12} total=24 | 1802de9ad vsubps ymm6, ymm6, ymm7
vsubsd       {'ladder': 3} total=3 | 180fd00da vsubsd xmm0, xmm2, xmm3
vsubss       {'convolver': 2, 'filtertable': 6, 'equalizer': 4} total=12 | 1802dee4c vsubss xmm5, xmm11, xmm10
vucomisd     {'equalizer': 1} total=1 | 180fb69ce vucomisd xmm3, qword ptr [rip + 0x12c85da]
vunpckhpd    {'convolver': 24, 'filtertable': 24} total=48 | 1802de548 vunpckhpd xmm0, xmm0, xmm1
vxorpd       {'ladder': 1} total=1 | 180fd02a8 vxorpd xmm0, xmm0, xmm5
vxorps       {'equalizer': 2} total=2 | 180fb6a50 vxorps xmm1, xmm1, xmm1
vzeroupper   {'convolver': 2, 'filtertable': 2} total=4 | 1802deb0e vzeroupper 
ymm-operand instructions per snap-in: {'convolver': 40, 'filtertable': 40}
closure functions skipped (not in callgraph RES) per snap-in: {} total 0
```

## 2. vex256_recount.py (VA 一意数・ymm 形・vf* 行)

```
mnemonic 数 54 / 重複込み合計 917 / VA 一意数 673 (snap-in 間で共有された VA 244)
ymm 形 (重複込み) snap-in 別: {'convolver': 40, 'filtertable': 40, 'ladder': 0, 'equalizer': 0} / 合計 80
xmm 形を含む全 v* 重複込み合計: 917
closure functions skipped (not in callgraph RES) per snap-in: {} total 0
--- ymm 形 mnemonic 別 (重複込み)
vaddps       {'convolver': 6, 'filtertable': 6} total=12
vmovaps      {'convolver': 20, 'filtertable': 20} total=40
vmulps       {'convolver': 8, 'filtertable': 8} total=16
vsubps       {'convolver': 6, 'filtertable': 6} total=12
--- vf* mnemonic 別 (全形・重複込み)
vfmadd132sd  {'ladder': 1} total=1
vfmadd213sd  {'ladder': 7, 'equalizer': 3} total=10
vfmadd213ss  {'filtertable': 3, 'equalizer': 3} total=6
vfmadd231sd  {'ladder': 2} total=2
vfmadd231ss  {'filtertable': 1, 'equalizer': 1} total=2
vfmsub213ss  {'filtertable': 2, 'equalizer': 2} total=4
vfnmadd231sd {'ladder': 1, 'equalizer': 1} total=2
vblend*/vperm* (全形): []
```

## 3. vex256_negcon.py (ネガティブコントロール)

```
vblendps xmm     n=1 old=0 new=1 | vblendps
vblendvps xmm    n=1 old=0 new=1 | vblendvps
vpermilps xmm    n=1 old=0 new=1 | vpermilps
vperm2f128 ymm   n=1 old=1 new=1 | vperm2f128
vaddps ymm       n=1 old=1 new=1 | vaddps
vaddps xmm       n=1 old=0 new=1 | vaddps
vfmadd231ps xmm  n=1 old=1 new=1 | vfmadd231ps
blob n=7 old_detect=3 new_detect=7
new only: ['vaddps', 'vblendps', 'vblendvps', 'vpermilps']
```
