# REPORT 付録 (#5664 KH-174): Delay の float の符号判定・符号反転をビット列で読む規則

親 #4687 (KH-110) の受入 1・2 の残件。`(uint)` が float の**ビット再解釈**か**数値変換**かを機械語で 1 件ずつ確認し、ビット再解釈の行を `f2u()`/`u2f()` の規則 (`ghidra_route/ghidra_to_c.py` の `DELAY_RULES`) に入れた。

## 結論

- float 変数・float グローバルの `(uint)` は、符号マスク XOR・符号ビット判定 (`test ... 0x8000`) では **ビット列** (機械語の `movss`/`xorps`/`test` の幅)。値変換 `(uint)` は**誤り**だった (例: `(float)((uint)X ^ 0x80000000)` は X の値を整数化してから XOR するため、符号反転にならない)。
- 規則 12 件 (件数 1 件ずつ assert) を入れた。Gain/Haas/Gate の `.o` は `origin/main` の `.o` と `cmp` 一致 (`delay` 限定の規則のため)。
- 差し戻し (round 1) への対応: 3594・3784 は「変更なし」と書いていたが誤りだったため、`f2u()` の規則を追加した (同じ式の 3653・3909 も同様)。下の「測定」の数値は `51b85e2f1` の時点のもので、この変更後の値ではない (下の「再測定の状態」を参照)。
- emcc の error 件数は変わらない (315 → 315)。これは silent miscompile (値の誤り) で、emcc は検出しないため。数値の正しさは emcc では確認できない (下の限界)。

## 機械語の確認 (1 件ずつ)

HeartCore は `HeartCore.core_64` (sha256 先頭 16 桁 `d55ce8b4c0ad7ebe`、REPORT と一致)。`objdump -d -M intel` で確認。

| 行 (現 emcc・生成 C) | 関数 | 機械語 (VA) | 判定 | 処理 |
|---|---|---|---|---|
| 2684 `(float)((uint)_DAT_182286970 ^ _DAT_1813d1a80)` | `FUN_180fbbfb8` | `movss xmm2,[182286970]` (float) → `xorps xmm0,[1813d1a80]` (180fbc0a0) | 符号反転 (bit XOR) | 規則 `u2f(f2u(X) ^ M)` |
| 2707 `(float)((uint)_DAT_182286958 ^ _DAT_1813d1a80)` | `FUN_180fbbfb8` | `movss xmm1,[182286958]` → `xorps xmm1,[1813d1a80]` (180fbc14f) | 同上 | 同上 |
| 1249・1250 `(uint)fVar26 ^ _DAT_1813d1a80` 等 | `FUN_1802ed7f0` | `movaps xmm2,xmm0` → `xorps xmm2,[1813d1a80]` → `andps xmm2,xmm0` (1802ee03d〜044) | float レジスタの符号マスク XOR と AND | 規則 `f2u(fVar)` (XOR・AND の両辺) |
| 1254・1255 `auVar6._4_4_ = uVar19 & (uint)fVar31` 等 | `FUN_1802ed7f0` | 同上 (AND 側) | 同上 | 規則 `f2u(fVar)` |
| 2766 `((uint)afStackX_8[0] & 0x80000000) != 0` | `FUN_180fbc1f4` | `test WORD PTR [rsp+0x42],0x8000` (180fbc2c1) | 符号ビット判定 (float の上位 16bit) | 規則 `f2u(...)` |
| 3549 `((uint)afStackX_8[0] & 0x80000000) == 0` | `FUN_180fc61e4` | `test WORD PTR [rsp+0x32],ax` (`0x8000`・180fc6223) | 同上 | 規則 `f2u(...)` |
| 3594・3784 `((uint)fVar3 & _DAT_1822822a0) == …` (fVar22 は 3784) | `FUN_180fc6870`・`FUN_180fc6d70` | `movd edx,xmm0` → `and r10d,edx` (mask 0x7f800000) | 入口 float のビット列の指数判定 (C の `(uint)` は値変換なので誤り) | 規則 `f2u(fVar3)`・`f2u(fVar22)` (件数 1 件ずつ assert) |
| 3653・3909 `((uint)fVar3 & 0x7f800000) == 0x7f800000` (fVar22 は 3909) | `FUN_180fc6870`・`FUN_180fc6d70` | 3594・3784 と同じ入力 xmm0 (同関数・同じ `movd`) | 同上 | 規則 `f2u(fVar3)`・`f2u(fVar22)` |
| 3068 (現 3069) `auVar20._0_4_ & 0x3f` | `FUN_180fc4590` | `movd ecx,xmm4` → `and eax,ecx` | ビット列 | #4900 で対応済み |

受入の「残 7 件」は issue 本文の時点の行番号による。上の表で float の `(uint)` を全件確認した (7 件 + 同形の符号判定 2 件の計 8 規則 + 指数判定 4 件 (3594・3653・3784・3909) の計 12 規則)。

## 規則 (`DELAY_RULES`・件数 assert)

- `2684 _DAT_182286970 ^ sign` → `u2f(f2u(_DAT_182286970) ^ _DAT_1813d1a80)`
- `2707 _DAT_182286958 ^ sign` → `u2f(f2u(_DAT_182286958) ^ _DAT_1813d1a80)`
- `1249`・`1250`・`1254`・`1255` (FUN_1802ed7f0) → `f2u(fVar26)`・`f2u(fVar31)` のビット列
- `2766` (FUN_180fbc1f4)・`3549` (FUN_180fc61e4) → `f2u(afStackX_8[0]) & 0x80000000`
- `3594`・`3653` (FUN_180fc6870)・`3784`・`3909` (FUN_180fc6d70) → `f2u(fVar3)`・`f2u(fVar22)` (指数マスク判定の左辺)。直後の呼出し引数 (`FUN_180fdc6ec`・`FUN_180fdc844`) は `patches.py` の既存 ABI 規則が `f2u()` で渡す。ABI 規則の正規表現も新しい左辺に合わせて直した。

`#3836` (`dbitcast`) との関係: `dbitcast` は double (`ulonglong`) の規則で、本件の float の行 (2684・2707・1249 系・2766・3549) には当たらない。#3836 の規則では解消されない (issue 本文の「#3836 と重なる行」は、この 12 件には当たらない)。

## 測定

- 測定 commit (コードを変えた最後の commit): `51b85e2f1` (`fix(kilohearts): 符号判定 2 件もビット列で読む`)。その前の commit `9fef6d84b` は 6 規則。
- 基準: `origin/main` = `679661428` (`git archive` で `tools/targets/kilohearts` を展開したツリー・同じ `gtype_census.sh`・同じ素材)。
- 環境: 素材 `plugins-kilohearts` (`Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64`、76,642,304 B、sha256 先頭 16 桁 `d55ce8b4c0ad7ebe`)・`toolchain-emsdk` (`emsdk/emsdk_env.sh`)・Ghidra 12.1.4 (zip sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)・JDK 21。作業は repo 外 (`$RUNNER_TEMP/kh`・`$RUNNER_TEMP/kh2`)。n=1。
- 実行: `bash tools/targets/kilohearts/ghidra_route/gtype_census.sh <work>`。decompile 151/151 OK。
- 所要 (real): 基準 `origin/main` 48.7 s / `51b85e2f1` 47.0 s。load (1 分平均): 06:22 時点 0.98 (4 vCPU)。

| 項目 | 基準 `origin/main` `679661428` | PR `51b85e2f1` |
|---|---|---|
| delay emcc error 行 | 315 | **315** |
| 演算・代入・ポインタの型不一致 | 84 | **84** |
| 128bit レーン型 | 166 | 166 |
| 引数数不一致 | 65 | 65 |
| 合計 | 315 | 315 |
| gain / haas / gate `.o` | 1435 / 3217 / 3756 B | 1435 / 3217 / 3756 B (`cmp` 一致) |
| `delay.c` の差分行 (基準との diff) | — | 旧 `51b85e2f1` は **8 行**。HEAD の値は未実測 (上の「再測定の状態」) |

## 再測定の状態 (差し戻し対応)

- 差し戻し対応で `ghidra_route` を変えた (規則 4 件追加・ABI 規則 4 件の左辺を変更)。このため、上の表の `51b85e2f1` の数値は、この commit (以下 HEAD) の数値ではない。
- 本 run では素材 `plugins-kilohearts` が `$ARTIFACTS_DIR` に無く (`fl-win64` のみ)、HeartCore の decompile・emcc の再測定を行えなかった。HEAD の delay emcc error 件数・`delay.c` の差分行数は未実測。
- 代わりに、新規則の正規表現と ABI 規則を、機械語の判定と同じ形の合成テキストに当てて確認した (各規則 1 件ずつ hit、ABI 4 件 hit)。これは規則の文字列の確認であり、emcc 結果の代わりにはならない。
- 再測定が要る (`plugins-kilohearts` を `oc_artifacts:` で取得して `gtype_census.sh` を実行する) ことを、PR 本文の未解決に書く。

## 測定 commit から HEAD までの差分

`git diff 51b85e2f1 HEAD -- tools/targets/kilohearts/ghidra_route` は、差し戻し対応の commit で差分が出る (下の HEAD 行を参照)。

## 限界・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 数値の正しさ (1000 trial の bit-exact 突合) は未確認。emcc の error 件数は silent miscompile を数えないため、変化ゼロは「正しい」の証拠にならない | 8 行の値が機械語どおりかは機械語の読みに依存 | #3073 [KH-41] |
| `stereo` 側に同形の float 符号判定があるかは未確認 (本 PR は `delay` の `DELAY_RULES` のみ) | stereo の float 符号判定 | #4687 (KH-110) の残件として扱う |
