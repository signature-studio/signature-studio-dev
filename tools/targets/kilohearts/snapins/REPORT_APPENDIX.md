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

## 12-2. (#3256 / KH-48) vmovaps (ymm・1 引数) と FMA3 scalar 7 語彙の bit-exact 検証

- **対象**: REPORT §12 の未解決 = vmovaps ymm (census 40 件) と vfmadd 系 xmm scalar。依頼文は「8 mnemonic」だが列挙は 7 件 (census 表の vf 行は 7 mnemonic・計 27 件) のため、7 件を対象とした。store 形の lift は本 run の範囲外 (下記)。
- **測定条件**: 基準 commit `7a30d228` (origin/main) の上に本変更。nproc=4・clang 18.1.3。census の再測定 (plugins 素材の展開を含む) は**本 run では実施していない** (census は §12 の f354504c の値を引く)。
- **RetDec 生 IR (親 session の実測を転記。本環境に `retdec-decompiler` が無く、本 run では再実行していない)**:
  - `vmovaps ymm0, ymm1` (c5 fc 28 c1) / `vmovaps ymm0, ymmword ptr [rdi]` (c5 fc 28 07): `declare i256 @__asm_vmovaps(i256) local_unnamed_addr`
  - `vmovaps ymmword ptr [rdi], ymm0` (c5 fc 29 07・store 形): `declare void @__asm_vmovaps(i256, i256)` (メモリ書込みが IR に現れない)
  - `vfmadd213ss xmm0,xmm1,xmm2` (c4 e2 71 a9 c2): `declare i128 @__asm_vfmadd213ss(i128, i128, i128)`
  - 引数の意味 (Intel 順): 第 1 = op1 (dest)、第 2 = op2、第 3 = op3。
- **変更**:
  - `lift/gen_simd.py` `gen256`: `vmovaps` かつ `ret i256` かつ引数 `[i256]` の時だけ `define i256 @NAME(i256 %a0) { ret i256 %a0 }` を返す (+2 行)。void 2 引数の store 形は None のまま = `abort()` スタブ (既存の `stub256` の挙動)。
  - `harness/ymm_vocab_harness.c` / `scripts/ymm_vocab_check.py`: vmovaps を 4 語彙目に追加。store 形の宣言も入れ、`undefined(abort stub) 1` と定義が無いことを判定に加えた。ネガコン (d) を追加。
  - `harness/fma_vocab_harness.c` / `scripts/fma_vocab_check.py` (新規): 7 語彙の宣言を 1 ファイル (`work/fma_vocab/decl.ll`) にまとめ、`gen_simd.py` で C 化して `clang -O1 -mfma -mavx2 -ffp-contract=off` でホストビルドする。oracle はホスト FMA3 (`_mm_fmadd_ss` 等)。上位 lane は dest (`_mm_move_ss` / `_mm_move_sd`)。
  - 生成 C の `<emscripten.h>` 依存は `work/fma_vocab/inc/emscripten.h` (`#define EMSCRIPTEN_KEEPALIVE` のみ) で解決 (ホスト検証専用・gitignore)。
- **回帰**: i256 を含まない宣言 (本 run の FMA 宣言 = i128 のみ 7 件) を、基準 commit `7a30d228` 版と新版の `gen_simd.py` に通し、C 出力と標準出力を `cmp` で比較 → 両方一致。
- **入力**: 各 op 20,000 call・seed 1。値は 1/4 特殊値 (±0・±Inf・NaN・非正規・1.0 等)、1/4 任意 bit、1/2 指数を 1 付近に寄せた通常域 (単精度・倍精度の丸め差が出やすい)。

### 検証 A: `python3 snapins/scripts/ymm_vocab_check.py 20000 1`
- 生出力の省略: ネガコン区間の `mismatch=0` 行と NANPAYLOAD 行は省略 (全行は再実行で得られる)。
- 実行: `timeout 300 python3 snapins/scripts/ymm_vocab_check.py 20000 1` → rc 0・`real 1.170 s` (user 0.852 s / sys 0.219 s)。実行前後の load は `0.47 0.38 0.28`。

```
[gen_simd] helpers 4, undefined(abort stub) 1 ['void __asm_vmovaps.2(i256,i256)'] approx_tables=none
== 本検証 (生成 IR 定義 vs ホスト AVX2) n=20000 seed=1
  vaddps calls=20000 lanes=160000 mismatch=0
  vsubps calls=20000 lanes=160000 mismatch=0
  vmulps calls=20000 lanes=160000 mismatch=0
  vmovaps calls=20000 lanes=160000 mismatch=0
== ネガコン (a) 語彙定義なし (リンクが通らなければ FAIL)
  link rc=1 -> FAIL (期待どおり)
== ネガコン (b) vaddps の演算を fsub に改変 (不一致 > 0 で FAIL)
    MISMATCH vaddps i=0 a0=0c011441 b0=555d8025 got0=d55d8025 want0=555d8025
    MISMATCH vaddps i=1 a0=00800000 b0=ea4ef7fd got0=6a4ef7fd want0=ea4ef7fd
    MISMATCH vaddps i=2 a0=ff800000 b0=7aa1c0b3 got0=ff800000 want0=ff800000
  vaddps calls=20000 lanes=160000 mismatch=19971
  rc=1 vaddps mismatch=19971 -> FAIL (期待どおり)
== ネガコン (c) 未対応の i256 宣言 vfmadd231ps (abort スタブ化 + 呼出で abort しなければ FAIL)
  [gen_simd] helpers 0, undefined(abort stub) 1 ['i256 __asm_vfmadd231ps(i256,i256,i256)'] approx_tables=none
  stub=あり call rc=-6 -> FAIL (期待どおり)
== ネガコン (d) vmovaps 定義を ret i256 0 に改変 (不一致 > 0 で FAIL)
    MISMATCH vmovaps i=0 a0=df0ce790 b0=c9cfe3ab got0=00000000 want0=df0ce790
    MISMATCH vmovaps i=1 a0=b8a29698 b0=3155261e got0=00000000 want0=b8a29698
    MISMATCH vmovaps i=2 a0=4831b4e3 b0=813b94d4 got0=00000000 want0=4831b4e3
  vmovaps calls=20000 lanes=160000 mismatch=20000
  rc=1 vmovaps mismatch=20000 -> FAIL (期待どおり)
== store 形 void __asm_vmovaps.2(i256,i256) は abort スタブのまま (定義されていれば FAIL)
  stub=あり -> OK
== 判定: 本検証 PASS / ネガコン(a) FAIL / ネガコン(b) FAIL / ネガコン(c) FAIL / ネガコン(d) FAIL / store 形 stub OK -> PASS

real	0m1.170s
user	0m0.852s
sys	0m0.219s
```

### 検証 B: `python3 snapins/scripts/fma_vocab_check.py 20000 1`
- 実行: `timeout 300 python3 snapins/scripts/fma_vocab_check.py 20000 1` → rc 0・`real 1.137 s` (user 0.952 s / sys 0.182 s)。実行後の load は `0.19 0.32 0.26`。
- **NaN の扱い (緩和。件数を明記)**: 本検証の 7 語彙中、非 NaN の bit 不一致は **0 件**。NaN 同士の payload だけの差は **31 件** (`vfmadd132sd` のみ・`nan_only=31`)。差のある lane が両側とも NaN で、NaN か否かは一致している。判定は「非 NaN bit の不一致 = mismatch - nan_only」で行い、payload 差は nan_only に別計上して判定から外した。理由: wasm 仕様は算術結果の NaN payload を決定的に規定しない (nondeterministic NaN) ため、ターゲット側で payload 一致は保証できない。緩めない (全 bit) 場合の判定は **FAIL** (31 件)。
- **原因 (未特定)**: 生成 C の `__asm_vfmadd132sd` は `objdump` で `vfmadd231sd %xmm1,%xmm0,%xmm2` (加数が dest の形) にコンパイルされた。oracle 側の被乗数を入れ替えた probe (作業用コピー・削除済み) でも 31 件のまま不変。したがって被乗数順だけでは説明できず、NaN 選択の機構は未確認 (推定を書かない)。
- NaN 差の実例 (`NANPAYLOAD` 行・lane 0 の 16 進):

```
[gen_simd] helpers 7, undefined(abort stub) 0 [] approx_tables=none
== 本検証 (生成 C 実装 vs ホスト FMA3・128bit 全 bit・NaN 含む) n=20000 seed=1
  vfmadd213sd calls=20000 bits=128 mismatch=0 nan_only=0
  vfmadd213ss calls=20000 bits=128 mismatch=0 nan_only=0
  vfmsub213ss calls=20000 bits=128 mismatch=0 nan_only=0
  vfmadd231sd calls=20000 bits=128 mismatch=0 nan_only=0
  vfmadd231ss calls=20000 bits=128 mismatch=0 nan_only=0
  vfnmadd231sd calls=20000 bits=128 mismatch=0 nan_only=0
    NANPAYLOAD vfmadd132sd i=39 d0=fff8000000000000 s2=cd07710bc8e17cc9 s3=7ff0000000000001 got0=fff8000000000000 want0=7ff8000000000001
    NANPAYLOAD vfmadd132sd i=155 d0=7ff0000000000001 s2=4579a5a633bf62f9 s3=7ff8000000000000 got0=7ff8000000000001 want0=7ff8000000000000
  vfmadd132sd calls=20000 bits=128 mismatch=31 nan_only=31
== ネガコン (a) 語彙定義なし (リンクが通らなければ FAIL)
  link rc=1 -> FAIL (期待どおり)
== ネガコン (b) vfmadd213ss の fmaf を単精度 2 段丸め x*y+z に改変 (不一致 > 0 で FAIL)
    MISMATCH vfmadd213ss i=9 d0=00000000b82cf9b0 s2=00000000475f857a s3=000000003f000000 got0=00000000bfee0f60 want0=00000000bfee0f61
    MISMATCH vfmadd213ss i=79 d0=0000000044a7ec93 s2=00000000c4f7bd14 s3=000000003d4e09cc got0=00000000ca228149 want0=00000000ca228148
    MISMATCH vfmadd213ss i=81 d0=000000004438ed30 s2=00000000423577ac s3=00000000408b0968 got0=0000000047031a7d want0=0000000047031a7e
  vfmadd213ss calls=20000 bits=128 mismatch=604 nan_only=45
  vfmadd132sd calls=20000 bits=128 mismatch=31 nan_only=31
  rc=1 vfmadd213ss mismatch=(604, 45) -> FAIL (期待どおり)
== ネガコン (c) vfmadd213ss の被演算子順を 231 形 fmaf(s2, s3, d) に改変 (不一致 > 0 で FAIL)
    MISMATCH vfmadd213ss i=3 d0=000000003f76d4a2 s2=000000004319b8b7 s3=00000000bd48e9b5 got0=00000000c0d26eb5 want0=0000000043142a9f
    MISMATCH vfmadd213ss i=4 d0=0000000040490fdb s2=00000000a56c27b8 s3=00000000c97e958d got0=0000000040490fdb want0=00000000c97e958d
    MISMATCH vfmadd213ss i=5 d0=000000003d3a58a8 s2=00000000435ca855 s3=00000000e9c1f44d got0=00000000eda72d7b want0=00000000e9c1f44d
  vfmadd213ss calls=20000 bits=128 mismatch=15804 nan_only=38
  vfmadd132sd calls=20000 bits=128 mismatch=31 nan_only=31
  rc=1 vfmadd213ss mismatch=(15804, 38) -> FAIL (期待どおり)
== 判定: 本検証 PASS (非 NaN bit 不一致 0 / NaN payload のみの差 31 件) / ネガコン(a) FAIL / ネガコン(b) FAIL / ネガコン(c) FAIL -> PASS
== wall 1.11 秒 (N=20000 語彙 7 件/各)

real	0m1.137s
user	0m0.952s
sys	0m0.182s
```

### ネガコン一覧 (実行出力は上記の各ブロック)

| 対象 | 改変 / 除去 | 結果 | 判定 |
|---|---|---|---|
| ymm (a) | 語彙定義 (`.i256.ll`) を外す | link rc=1 | FAIL (期待どおり) |
| ymm (b) | vaddps の fadd → fsub | vaddps mismatch **19,971 / 20,000** | FAIL |
| ymm (c) | 未対応 `vfmadd231ps` 宣言 (abort スタブ) | 呼出で `rc=-6` (abort) | FAIL |
| ymm (d) | vmovaps 定義を `ret i256 0` に改変 | vmovaps mismatch **20,000 / 20,000** | FAIL |
| ymm store | `void __asm_vmovaps.2(i256,i256)` | 定義されず `call void @abort()` のスタブのまま | OK (期待どおり) |
| fma (a) | 語彙定義 (simd.c) を外す | link rc=1 | FAIL (期待どおり) |
| fma (b) | vfmadd213ss の `fmaf(s2,d,s3)` → `(s2*d)+s3` (単精度 2 段丸め) | vfmadd213ss mismatch **604** (うち NaN payload 45・非 NaN **559**) | FAIL |
| fma (c) | vfmadd213ss の被演算子順を 231 形 `fmaf(s2,s3,d)` に | vfmadd213ss mismatch **15,804** (うち NaN payload 38・非 NaN **15,766**) | FAIL |

- ネガコン (b) (c) の判定は非 NaN 件数 (559 / 15,766) で行う。

### 未解決 (本 run の範囲外)
- **store 形 `void __asm_vmovaps(i256, i256)`**: 定義しない (abort スタブ)。メモリ書込みが IR に現れず、定義すると store が黙って消える。`kh_passes.py` の store 欠陥類型と同じ形で、lift 対応は子 issue (親 #3256 から起票予定)。
- census の再測定 (plugins 素材の展開を含む) は未実施。
- 14 snap-in のハッシュ不変 (`run_all.sh`) は未実施 (#3259)。

### 差分 (基準 commit `7a30d228` → 本変更・測定対象のコード)
- `git diff --stat 7a30d228 -- tools/targets/kilohearts/snapins/lift tools/targets/kilohearts/snapins/harness tools/targets/kilohearts/snapins/scripts`:

```
 .../kilohearts/snapins/harness/fma_vocab_harness.c | 136 +++++++++++++++++++
 .../kilohearts/snapins/harness/ymm_vocab_harness.c |  13 +-
 tools/targets/kilohearts/snapins/lift/gen_simd.py  |   2 +
 .../kilohearts/snapins/scripts/fma_vocab_check.py  | 149 +++++++++++++++++++++
 .../kilohearts/snapins/scripts/ymm_vocab_check.py  |  50 ++++---
 5 files changed, 330 insertions(+), 20 deletions(-)
```

- `git diff 7a30d228 -- tools/targets/kilohearts/snapins/lift/gen_simd.py` の全文 (他 4 ファイルは新規・変更の本文を commit で確認): `+` 2 行 = vmovaps の 1 引数分岐 (`if b == 'vmovaps' and ret == 'i256' and ptys == ['i256']:` と `return 'define i256 @%s(i256 %%a0) {\n  ret i256 %%a0\n}' % name`)。
