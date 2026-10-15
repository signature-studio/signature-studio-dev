# REPORT_APPENDIX_3756 — KH-62 (#3756): phaser/delay/limiter/khbase の globals.c 過大の原因と修正

親 `REPORT.md` の付録。測定 commit は本ファイルを含む PR の `gen_globals.py` 修正 commit (コードを変えた最後の commit)。
環境: GitHub Actions runner (RAM 15,989MB・swap 3,071MB・nproc 4)。素材 `fl-win64` `plugins-kilohearts` (Windows 側 zip のみ展開) `toolchain-retdec` `toolchain-emsdk` を使用。

## 1. 原因 (確定)

`lift/gen_globals.py` の `rd(va, n)` は、VA を PE のセクションに写して `n` バイトを返す。`.data` は `Misc_VirtualSize` (BSS 込み 28MB) に対し `SizeOfRawData` が 1.8MB しかなく、RVA `0x40f7300` 以降はファイルに実体が無い (ゼロ初期化)。
このとき `avail = min(n, raw_end - o)` が負になり、`b'\0' * (n - avail)` が **宣言長 `n` を超える 0 埋め** を返していた。`n - avail` は約 2,400 万 (`[64]` の宣言に 2,400 万要素) になる。

- 修正前の `globals.c` は、RVA が `.data` の実体末尾 (`0x40f7300` 以降) を超える宣言が支配する。件数と名前は次のとおり (修正後の `final.ll` を `gen_globals.py` の判定式で走査した結果。値はすべて 0):
  - **phaser: 19 件** (宣言 64・192・256・940 B。合計 2,412 B)。大きい順に `global_var_184162358` (940 B)・`global_var_18436cc80` (256 B)・`global_var_18436cc00` (192 B)、残り 16 件は 64 B (`18436cd78`・`18436cd18`・`18436cd00`・`18436cbf8`・`18436cbf0`・`18436cbe4`・`18436cbe0`・`184162aa0`・`184162a98`・`184162a70`・`184162364`・`184162120`・`184162118`・`1840f7308`・`1840f7304`・`1840f7300`)。
  - **limiter: 25 件** (宣言 64・192・256・940 B。合計 2,796 B)。phaser の 19 件から `1840f7300`・`1840f7304`・`1840f7308` の 3 件を除き、`184161974`・`184161f80`・`184161fa4`・`184161fa8`・`184161fb0`・`1841620e8`・`184162100`・`184162354`・`184162a88` の 9 件 (いずれも 64 B) を加えた集合。件数は 19 − 3 + 9 = 25。合計は phaser の 2,412 B − 64 × 3 + 64 × 9 = 2,796 B。
  - 修正前の `globals.c` の byte 数 (`REPORT_APPENDIX_3707.md` §4): phaser 960,709,664 B / limiter 1,255,439,321 B / khbase 1,257,571,498 B / delay 1,263,683,900 B。この値のとおり、支配 global の 0 埋めが全量を占める。
  - 残りの global は正常 (phaser の残り 161 件・合計 26KB 程度)。
- `final.ll` 1.46MB・`final.ll` の宣言数 180 は正常。膨張は emcc 入力の `globals.c` だけ。
- **delay: 25 件** (宣言 `[8192]`・各 8,192 B。合計 204,800 B)。`rdata_window` 8192 の経路で、`avail` が負になる VA の集合。名前は `184161974`・`184161f80`・`184161fa4`・`184161fa8`・`184161fb0`・`1841620e8`・`184162100`・`184162118`・`184162120`・`184162354`・`184162358`・`184162364`・`184162a70`・`184162a88`・`184162a98`・`184162aa0`・`18436cbe0`・`18436cbe4`・`18436cbf0`・`18436cbf8`・`18436cc00`・`18436cc80`・`18436cd00`・`18436cd18`・`18436cd78`。
- **khbase: 25 件** (宣言 `[8192]`・各 8,192 B。合計 204,800 B)。delay と同じ 25 件の名前 (上の列挙と同一)。`1840f7300`・`1840f7304`・`1840f7308` は両 snap-in の `final.ll` に宣言が無く、対象外。
- 件数・名前は、本 PR の修正後 `gen_globals.py` が出した `final.ll` (`build.py --path s0 --no-compare` で再生成) を、修正前の判定式 `avail = min(n, raw_end - o)` で走査した結果。`avail < 0` の VA を数えた。素材は `plugins-kilohearts` (Installer zip → payload.dat → windows.zip → HeartCore.core_64、sha256 先頭 `d55ce8b4c0ad7ebe`) を本 run で展開して使用。emcc の再実行は無し (`build.py` の末尾の emcc は走った)。

## 2. 修正

`snapins/lift/gen_globals.py` の 1 行: `avail = max(0, min(n, ...))`。`avail` を 0 未満にしない。0 埋めは `n - avail` で `n` バイトに収まる。BSS の実体はゼロなので、値は従来どおり 0 (ファイル上に実体が無い領域の値は 0 で不変)。
`license/` 側の `gen_globals` 呼び出しは変更していない (`license/lic_build.py` も同じ `snapins/lift/gen_globals.py` を使う経路の確認は §5 の未解決表)。

## 3. 実測 (修正後・`--path s0 --trials 200 --seed 1`・同一 runner)

| 入力 | rc | globals.c (B) | 宣言と要素数の不一致 | emcc peak (MB) | cap 11000MB 超過 | wasm (B) | compare |
|---|---|---|---|---|---|---|---|
| phaser (修正前) | 1 | 960,709,664 | 19 件 | 11,235 (kill) | Y | — | 未実行 |
| phaser (修正後) | 0 | 85,336 | 0 | 93 | N | 345,242 | **bit-exact 200/200**・calls 1100/1100 |
| limiter (修正後) | 0 | 180,161 | 0 | 129 | N | 438,192 | **bit-exact 200/200**・calls 1100/1100 |
| khbase (修正後) | 0 | 2,312,338 | 0 | 116 | N | 1,314,232 | **bit-exact 200/200**・calls 10500/10500 |
| delay (修正後) | 0 | 8,424,740 | 0 | 273 | N | 3,602,885 | **155/200 (FAIL)**・calls 1188/1299 |

delay の `globals.c` は修正前 1,263,683,900 B (`--window 8192` で生成・宣言 `[8192]` が 25 件で要素過大) → 修正後 8,424,740 B。
修正前後の有効部分を比べると、**366 global すべてで宣言長 n バイトの内容が一致** (差分 0)。変わったのは宣言長を超えていた余分な 0 埋めだけ。
delay の FAIL は fn `1802ed7f0` の exact-region diff (trial 5/19/25/27/31 の 5 件、`@self+0x148`・`@tap+0x228`・`@tap+0x230`)。globals の有効内容が同じなので、FAIL の原因は「要素過大の宣言 (25 件) を emcc が受けた振る舞い」の差か、別経路かは未確定。修正前の wasm を emcc で作ると 10 分超のため、本 run では確定できなかった (未解決 §5)。

## 4. 受入条件の判定

- [x] 4 本の `globals.c` が大きい原因を確定し、byte 数と支配する global を書いた (§1・§3)。
- [x] 4 本が cap 内 (11000MB) で emcc を完了する (4 本とも peak 93〜273MB)。
- [ ] 同じ入力の compare が bit-exact 200/200 のまま: phaser・limiter・khbase は 200/200。**delay は 155/200 で未達** (§3・§5)。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| delay の compare FAIL 155/200 (fn `1802ed7f0` exact-region diff)。修正前の wasm の compare は emcc 10 分超のため未取得 | delay の wasm は bit-exact 不成立。修正前の基準との比較は未確定 | [KH-90] = #4096 |
| `license/lic_build.py` 経路 (module F 等) の再測定 | 同じ `gen_globals.py` を使うため出力は変わる。本 PR では未測定 | [KH-90] = #4096 に含める |
