# REPORT 付録 (#4900 KH-132): Delay の vcvtpd2dq 下位 lane を int で読む規則

親 #4687 (KH-110) の残件。Delay の `FUN_180fc4590` (`auVar20._0_4_` 系) は、`GTYPE` (`_DAT_` グローバル専用) の対象外の局所 lane。

## 結論

- `DELAY_RULES` に 2 件 (件数 assert 付き) を足した。`uVar19 = auVar20._0_4_ & 0x3f` と `uVar3 = (int)(auVar20._0_4_ - uVar19) >> 6` を、ビット列を読む `f2u()` で包む形に書いた (レビュー指摘 blocking 1 の修正)。`V128` の型は変えていない。
- 旧式 (`(int)` の値変換) は、`float` の数値を int にするため機械語のビット読みと一致しなかった。下の表の `(int)` 版の測定値 (343 → 342) は旧式の値で、現在の `f2u()` 式には対応しない。
- **現 HEAD (`f2u()` 式) の再測定は未実施**。素材 `plugins-kilohearts` が `$ARTIFACTS_DIR` に無く、emcc も無いため。必要素材は `oc_artifacts: fl-win64 plugins-kilohearts toolchain-emsdk`。
- Gain/Haas/Gate の `.o` の `cmp` 一致は、旧式での結果。現 HEAD では未確認。

## 機械語の確認

`HeartCore.core_64` (sha256 先頭 16 桁 `d55ce8b4c0ad7ebe`、REPORT 記載と一致) の `FUN_180fc4590` 0x180fc48bc〜48db:

```
movd  ecx,xmm4        ; vcvtpd2dq の結果の下位 32bit
and   eax,ecx         ; rax = 0x3f
sub   ecx,eax
sar   ecx,0x6         ; 整数の算術右シフト
```

整数演算なので、読み方は `int`。ただし `movd` はビット列を読む。`auVar20` の `_0_4_` は `V128` 上で `float` なので、`f2u()` (`memcpy` によるビット再解釈) で読み直す。`(int)` の値変換は、小さい整数のビット列 (denormal) を 0 にするため使わない。

## 測定

- 測定 commit (コードを変えた最後の commit): `86abf8a79`。
- 基準: `origin/main` = `ef51996d0` (同じ `gtype_census.sh`・同じ素材)。
- 環境: 素材 `plugins-kilohearts` (Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64`)・`toolchain-emsdk` ([EMSDK])・Ghidra 12.1.4 (zip sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)・JDK 21。作業ディレクトリは CI の一時領域 (repo 外・作業 dir 名 `kh`)。n=1。
- 実行: `bash tools/targets/kilohearts/ghidra_route/gtype_census.sh <作業 dir>` (既定 FX)。decompile 151/151 OK。
- 所要 (real): 基準 56.6 s・PR 46.1 s。load (1 分平均): 基準 1.19・PR 0.61。

| 項目 | 基準 `ef51996d0` | PR `86abf8a79` |
|---|---|---|
| delay emcc error 行 | 343 | **342** |
| 演算・代入・ポインタの型不一致 | 90 | **89** |
| 128bit レーン型 | 167 | 167 |
| 引数数不一致 | 86 | 86 |
| gain / haas / gate `.o` | 1435 / 3217 / 3756 B | 1435 / 3217 / 3756 B (`cmp` 一致) |

## 現 HEAD までの差分

`git diff ef51996d0 86abf8a79 -- tools/targets/kilohearts/ghidra_route` = `ghidra_to_c.py` 7 行 (+7)。

## 基準値の出所 (issue 本文との差)

- issue 本文の基準 (型不一致 95・emcc error 348) は、現 `origin/main` では再現しない。現 HEAD の基準は 90 / 343 (上の表)。issue の値は古い tree の値として扱う。

## 限界・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 行 2683 (`(float)((uint)_DAT_182286970 ^ _DAT_1813d1a80)`) | 1 件。#4687 の残件 | #4687 |
| 1000 trial 突合 (Delay の bit-exact) | 未確認 | #3073 [KH-41] |
