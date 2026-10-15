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
- **測定 commit**: `d7603d630` (コード変更の最後の commit)。以降に積んだ commit は docs のみで、`git diff d7603d630 HEAD -- tools/targets/kilohearts/snapins/lift tools/targets/kilohearts/snapins/harness tools/targets/kilohearts/snapins/scripts` の出力は 0 行 (下の差分節)。
- **RetDec 生 IR (親 session の実測を転記。本環境に `retdec-decompiler` が無く、本 run では再実行していない)**:
  - `vmovaps ymm0, ymm1` (c5 fc 28 c1) / `vmovaps ymm0, ymmword ptr [rdi]` (c5 fc 28 07): `declare i256 @__asm_vmovaps(i256) local_unnamed_addr`
  - `vmovaps ymmword ptr [rdi], ymm0` (c5 fc 29 07・store 形): `declare void @__asm_vmovaps(i256, i256)` (メモリ書込みが IR に現れない)
  - `vfmadd213ss xmm0,xmm1,xmm2` (c4 e2 71 a9 c2): `declare i128 @__asm_vfmadd213ss(i128, i128, i128)`
  - 引数の意味 (Intel 順): 第 1 = op1 (dest)、第 2 = op2、第 3 = op3。
- **変更**:
  - `lift/gen_simd.py` `gen256`: `vmovaps` かつ `ret i256` かつ引数 `[i256]` の時だけ `define i256 @NAME(i256 %a0) { ret i256 %a0 }` を返す (+2 行)。void 2 引数の store 形は None のまま = `abort()` スタブ (既存の `stub256` の挙動)。
  - `harness/ymm_vocab_harness.c` / `scripts/ymm_vocab_check.py`: vmovaps を 4 語彙目に追加。store 形の宣言も入れ、`undefined(abort stub) 1` と定義が無いことを判定に加えた。ネガコン (d) を追加。
  - `harness/fma_vocab_harness.c` / `scripts/fma_vocab_check.py` (新規): 7 語彙の宣言を 1 ファイル (`work/fma_vocab/decl.ll`) にまとめ、`gen_simd.py` で C 化して `clang -O1 -mfma -mavx2 -ffp-contract=off` でホストビルドする。oracle はホスト FMA3 (`_mm_fmadd_ss` 等)。上位 lane は dest (`_mm_move_ss` / `_mm_move_sd`)。vfmadd132sd の oracle だけは同じ命令形の inline asm (検証 C)。
  - 生成 C の `<emscripten.h>` 依存は `work/fma_vocab/inc/emscripten.h` (`#define EMSCRIPTEN_KEEPALIVE` のみ) で解決 (ホスト検証専用・gitignore)。
- **回帰**: i256 を含まない宣言 (本 run の FMA 宣言 = i128 のみ 7 件) を、基準 commit `7a30d228` 版と新版の `gen_simd.py` に通し、C 出力と標準出力を `cmp` で比較 → 両方一致。
- **入力**: 各 op 20,000 call・seed 1。値は 1/4 特殊値 (±0・±Inf・NaN・非正規・1.0 等)、1/4 任意 bit、1/2 指数を 1 付近に寄せた通常域 (単精度・倍精度の丸め差が出やすい)。
- **判定**: 128bit 全 bit (NaN payload を含む)。NaN payload の差を除外・別計上する処理は持たない (旧版の除外は検証 C で撤回した)。

### 検証 A: `python3 snapins/scripts/ymm_vocab_check.py 20000 1`
- 実行 (測定 commit `d7603d630`): rc 0・`real 1.143 s` (user 0.664 s / sys 0.244 s)。実行前後の load は `0.16 0.25 0.12`。
- 結果: vaddps / vsubps / vmulps / vmovaps 各 20,000 call・160,000 lane **mismatch 0**。ネガコン (a) link 失敗・(b) mismatch 19,971・(c) abort rc=-6・(d) mismatch 20,000 → すべて FAIL。store 形の abort スタブ OK → PASS。
- 生出力の全行: [REPORT_APPENDIX_3256.md](REPORT_APPENDIX_3256.md)。

### 検証 B: `python3 snapins/scripts/fma_vocab_check.py 20000 1`
- 実行 (測定 commit `d7603d630`): rc 0・`real 0.842 s` (user 0.655 s / sys 0.186 s)。実行前後の load は `0.18 0.25 0.12`。
- 結果: 7 語彙 (vfmadd213sd・vfmadd213ss・vfmsub213ss・vfmadd231sd・vfmadd231ss・vfnmadd231sd・vfmadd132sd) の各 20,000 call が 128bit 全 bit で **mismatch 0** (NaN payload を含む)。ネガコン (a) link 失敗・(b) mismatch 604・(c) mismatch 15,804 → すべて FAIL。判定 → PASS。
- 別 seed (同じ測定 commit・同じ checker): `fma_vocab_check.py 20000 2` → 判定 PASS (全 bit 不一致 0・wall 0.82 s)。`fma_vocab_check.py 20000 3` → 判定 PASS (全 bit 不一致 0・wall 0.85 s)。
- 生出力の全行: [REPORT_APPENDIX_3256.md](REPORT_APPENDIX_3256.md)。

### 検証 C: vfmadd132sd の NaN payload 差 (旧 31 件) の原因と修正
- **旧 oracle**: `ref_132sd` は `_mm_fmadd_sd(D, s3, s2)` だった。clang -O1 -mfma はこれを `vfmadd213sd` にコンパイルした (旧 harness の `objdump -d` で `vfmadd213sd` が 2 箇所: `ref_213sd` と `ref_132sd`)。RetDec が宣言した `vfmadd132sd` と命令の被演算子の役割が違うため、両方 NaN の時の結果の NaN 選択が変わり、旧 harness では seed 1 で NaN payload だけの差 **31 件** (`mismatch=31 nan_only=31`) になった。修正前 HEAD `86126ccc` で同コマンドを再実行し、この 31 件を再現した。
- **生成 C 側は変更していない**: `__asm_vfmadd132sd` の生成 C は clang で `vfmadd231sd` にコンパイルされる (`objdump -d work/fma_vocab/simd.o`)。命令形が違っても、新 oracle と 128bit 全 bit で一致した (検証 B)。
- **修正** (commit `d7603d630`): oracle を `__asm__("vfmadd132sd %2, %1, %0" : "+x"(d) : "x"(s2), "x"(s3))` に置き換えた。判定から `nan_only` の除外を外した。
- **結果** (測定 commit `d7603d630`・seed 1・20,000 call): `vfmadd132sd` mismatch **31 → 0**。7 語彙すべて mismatch 0。seed 2・3 も全 bit 一致 (検証 B)。

### ネガコン一覧 (実行出力は上記の各ブロック・生出力は REPORT_APPENDIX_3256.md)

| 対象 | 改変 / 除去 | 結果 | 判定 |
|---|---|---|---|
| ymm (a) | 語彙定義 (`.i256.ll`) を外す | link rc=1 | FAIL (期待どおり) |
| ymm (b) | vaddps の fadd → fsub | vaddps mismatch **19,971 / 20,000** | FAIL |
| ymm (c) | 未対応 `vfmadd231ps` 宣言 (abort スタブ) | 呼出で `rc=-6` (abort) | FAIL |
| ymm (d) | vmovaps 定義を `ret i256 0` に改変 | vmovaps mismatch **20,000 / 20,000** | FAIL |
| ymm store | `void __asm_vmovaps.2(i256,i256)` | 定義されず `call void @abort()` のスタブのまま | OK (期待どおり) |
| fma (a) | 語彙定義 (simd.c) を外す | link rc=1 | FAIL (期待どおり) |
| fma (b) | vfmadd213ss の `fmaf(s2,d,s3)` → `(s2*d)+s3` (単精度 2 段丸め) | vfmadd213ss mismatch **604** | FAIL |
| fma (c) | vfmadd213ss の被演算子順を 231 形 `fmaf(s2,s3,d)` に | vfmadd213ss mismatch **15,804** | FAIL |

- ネガコン (b)(c) の判定は全 bit の不一致件数 (604 / 15,804) で行う。

### 未解決 (本 run の範囲外)
- **store 形 `void __asm_vmovaps(i256, i256)`**: 定義しない (abort スタブ)。メモリ書込みが IR に現れず、定義すると store が黙って消える。`kh_passes.py` の store 欠陥類型と同じ形で、lift 対応は子 issue (#3358 KH-54) で行う。
- census の再測定 (plugins 素材の展開を含む) は未実施。
- 14 snap-in のハッシュ不変 (`run_all.sh`) は未実施 (#3259)。

### 差分 (基準 commit `7a30d228` → 測定 commit `d7603d630`・測定対象のコード)
- `git diff --stat 7a30d228 d7603d630 -- tools/targets/kilohearts/snapins/lift tools/targets/kilohearts/snapins/harness tools/targets/kilohearts/snapins/scripts`:

```
 .../kilohearts/snapins/harness/fma_vocab_harness.c | 119 +++++++++++++++++
 .../kilohearts/snapins/harness/ymm_vocab_harness.c |  13 +-
 tools/targets/kilohearts/snapins/lift/gen_simd.py  |   2 +
 .../kilohearts/snapins/scripts/fma_vocab_check.py  | 143 +++++++++++++++++++++
 .../kilohearts/snapins/scripts/ymm_vocab_check.py  |  50 ++++---
 5 files changed, 307 insertions(+), 20 deletions(-)
```

- `git diff d7603d630 HEAD -- tools/targets/kilohearts/snapins/lift tools/targets/kilohearts/snapins/harness tools/targets/kilohearts/snapins/scripts` (測定 commit → HEAD): 出力 0 行。
- `git diff 7a30d228 -- tools/targets/kilohearts/snapins/lift/gen_simd.py` の全文 (他 4 ファイルは新規・変更の本文を commit で確認): `+` 2 行 = vmovaps の 1 引数分岐 (`if b == 'vmovaps' and ret == 'i256' and ptys == ['i256']:` と `return 'define i256 @%s(i256 %%a0) {\n  ret i256 %%a0\n}' % name`)。
