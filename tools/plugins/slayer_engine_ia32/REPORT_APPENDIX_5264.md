# REPORT_APPENDIX_5264 — NaN どうしのビット差の後段の算術への伝播 (#5264 PLG-G2-73)

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない)。 NaN の符号・ペイロードは wasm 仕様で未規定 (§9.1 の V8 tier 切替が源)。

- 親 REPORT: `tools/plugins/slayer_engine_ia32/REPORT.md` §13。 前段の正本: `REPORT_APPENDIX_2989.md` §7・§9・§10。 本付録は §10.3 の残課題のうち「後段の算術」の実測を書く。
- 測定 commit: 本付録の PR の commit (`x87_nan_downstream.c`・`x87_nan_downstream.py` を加えた最後のコード commit)。 前段の突合 (`x87_fn_diff.py --special`) は `main` の `6bc58a66d` 時点のコードを再実行した。
- 起動・GUI に関わらない (製品 KPI は対象外)。

## 1. 結論

- NaN どうしのビット差 (符号・ペイロード) は、後段の四則演算 (add・sub・mul・div)・符号反転・絶対値の結果の NaN ビットにだけ出る。 **非 NaN の結果・比較 (`fucomip` の C3/C2/C0) には 0 件**。 NaN と数値の混在は 0 件。
- 12 値の全組 144 組、連鎖 2 本 (`(a*b)+1.5`・`1.0/(a+b)`) を含めて、native (実 x87 命令) と wasm (emcc・`--liftoff-only`) を突合。 非 NaN・比較・混在の差は **0 件**。 NaN どうしの差は 102 件 (合否に入れない・分類のみ)。
- 負の対照: wasm の数値 1 件の 1 bit 反転で判定が FAIL (非 NaN の差 1 件)。 検出できる。
- 前段の残課題 (§10.2) への答え: 後段の算術は、この入力集合では NaN どうしの差を別の値に増幅しなかった。 ただし NaN の**ビット値そのもの**は一致しない (wasm 規定の未規定)。

## 2. 方法

- 入力 (`x87_nan_downstream.c` の `V`): `1.0`・`-2.5`・`±0`・`±inf`・`qNaN` 3 種 (`7fc00000`・`ffc00000`・`7fc12345`)・`sNaN`・ペイロード違い NaN。 12 値 × 12 値 = 144 組。
- 演算: `a+b`・`a-b`・`a*b`・`a/b` (x87 の `fadds`・`fsubs`・`fmuls`・`fdivs`)、`cmp` (`fucomip` の ZF/PF/CF)、`-a` (`fchs`)、`|a|` (`fabs`)、連鎖 `(a*b)+1.5` と `1.0/(a+b)`。
- native: `gcc -m32` freestanding・`-ffp-contract=off`・inline asm で x87 命令を発行。 wasm: `emcc -O1 -ffp-contract=off`・`node --liftoff-only` (tier 固定)。
- 再現: `cd tools/plugins/slayer_engine_ia32 && python3 x87_nan_downstream.py` (exit 0) と `python3 x87_nan_downstream.py --nega` (exit 0)。

## 3. 実測

| 項目 | 行数 (144 組) | NaN どうしの差 | NaN と数値の混在 | 非 NaN の差 | 比較 (cmp) の差 |
|---|---:|---:|---:|---:|---:|
| add・sub・mul・div | 144 | 9 (各) | 0 | 0 | — |
| 連鎖 c1・c2 | 144 | 9 (各) | 0 | 0 | — |
| abs | 144 | 24 | 0 | 0 | — |
| neg | 144 | 24 | 0 | 0 | — |
| cmp | 144 | — | — | — | 0 |
| 合計 | — | 102 | 0 | 0 | 0 |

- 行単位: 144 組のうち NaN どうしの差を含む行は 30 行。 残り 114 行は native と wasm が全項目一致。
- wasm 出力の再現性: `--liftoff-only` で 3 回実行、md5 は 3/3 で `aa59a2f6…`。 native の md5 は `04d9a0f0…`。 両者の差は NaN ビットだけ。
- 所要: `time python3 x87_nan_downstream.py` の実測 real 0.303 s (user 0.229 s・sys 0.084 s・build は emcc キャッシュ済み)。 load1 0.01 (測定直前)。

## 4. ネガコン

- `--nega`: wasm 出力の数値 (NaN でない) の `add` を 1 bit 反転 → 非 NaN の差 1 件 → FAIL (検出)。 exit 0 = 検出。

## 5. 判断材料 (PM 判断用・本付録は判断を下さない)

- 受入条件 1 (許容するか・実 FL の x87 と一致させるか) は PM が決める。 本 runner は実 FL の x87 (Windows の `Slayer_Engine.dll`) を実行できないので、基準は native の x87 命令 (issue 本文の定義どおり)。
- 本付録の実測が示したこと: (a) 後段の算術の**結果の値** (非 NaN) と**分岐** (比較) には、NaN どうしの差は伝播しなかった。 (b) NaN の**ビット値**は native と一致しない。 これが `eax`・OBJ 窓・ST(0) の NaN どうしの差として前段で見えている。
- 既定案 (許容) を支える点: 非 NaN の値・分岐は全件一致。 NaN の符号・ペイロードは IEEE 754 で規定されない値。
- 許容しない場合に必要な作業: 一致させるには wasm 側で NaN を生成する演算の結果を正規化する必要がある (例: 演算結果が NaN のとき、x87 の default NaN `ffc00000` に揃える)。 本付録ではこれを実装していない。

## 6. 範囲と未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 FL の x87 の値との NaN ビット一致 (本 runner では Windows の DLL を実行できない) | NaN の値そのものは native 基準でしか確認していない | PM 判断 (#5264 の受入 1) |
| 後段の算術の入力は 12 値・144 組 (乱数入力・大きさの違う値の網羅は未確認) | 入力を広げると別の NaN 伝播が出る可能性 | 本 PR の範囲外 (必要なら PM が子 issue を起票) |
| `sqrt`・超越関数・`fistp` の NaN 変換 | 本 harness の対象外 | #2966 (PLG-G2-23) |
