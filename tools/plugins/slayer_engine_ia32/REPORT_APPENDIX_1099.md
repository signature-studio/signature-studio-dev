# REPORT_APPENDIX_1099 — x87 subset の ia32 lowering と実 x87 との差分試験 (#1099 PLG-G2-9)

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない)。 f80→f64 の精度差は新規類型の候補で、行案を §6 に書く (`DEFECTS.md` は未編集)。

- 親 REPORT: `tools/plugins/slayer_engine_ia32/REPORT.md` §11 (#1098 の結論)。 方式は `docs/DECISIONS.md` D28 (f80→f64)。 本付録が測定値の正本。
- 測定 commit: `ce0f0872` (`feat(ott): lower x87 subset for ia32 (PLG-G2-9)`。 lowering・runtime・差分試験を含む)。 本付録の commit は docs のみ。
  `git diff ce0f0872 HEAD -- tools/ott/lift tools/ott/rt tools/plugins/slayer_engine_ia32/x87_diff.py tools/plugins/slayer_engine_ia32/x87_diff_main.h tools/plugins/slayer_engine_ia32/x87_diff_native.c tools/plugins/slayer_engine_ia32/x87_diff_lowered.c tools/plugins/slayer_engine_ia32/x87_crosscheck.py tools/plugins/slayer_engine_ia32/x64_regress_1099.py` の出力は 88 行で、全行が `x87_crosscheck.py` (新規追加・commit `1adb69c3`) である。 この検算スクリプトを除く code (lift・rt・driver・C 参照) の差分は 0 行。 §4 の検算は HEAD で再実行し、同じ値を得た (2026-10-14)。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` (`$FL_WIN64_DIR/extracted/`) と生成した試行のみ。

## 1. 結論

- x87 subset (下の §2 の表) を x64c の ia32 経路で lower し、ott_x87.h (f80 を持たず double) で実行する。 **x64 の出力は不変** (§7 で 8/8 一致)。
- 実 x87 (native) との差分試験 (10 万試行): **99.38% が bit 一致**。 差分は主に 1 ulp で、桁落ちの試行だけ ulp が大きい。 C0/C2/C3 は 24,151 / 24,152 一致 (不一致 1 件は f80 と f64 の丸めで比較結果が変わる例で、有理数の検算で確認。 §4)。
- ネガティブコントロール (fsub/fsubr の取り違え 1 種を lowered に入れる) で bit 一致試行が 282 件減る (FAIL 検出)。
- ia32 の x87 unsup は **4,134 件 → 87 件** (lift 出力の `unsup`)。 残りは超越関数ほか (§8・§9 未解決)。

## 2. 対象と方法

- op 表 (`x87_diff.py` の `templates()`): 機械語 1 命令ごとに 1 id。 reg 形は i=0..7 に展開し、計 **231 件**。
  - 算術: `fadd/fmul/fsub/fsubr/fdiv/fdivr` の D8 (ST0 op= ST(i)) / DC (ST(i) op= ST0) / DE (同 + pop) と、m32 (D8)・m64 (DC)。
  - 比較: `fcom`/`fcomp` (reg・m32・m64)、`fcompp`。 スタック: `fld` (m32/m64/st(i))・`fst`/`fstp` (m32/m64/st(i))・`fild` (m16/m32/m64)・`fist`/`fistp` (m16/m32/m64)・`fxch`・`fchs`・`fabs`・`fld1`・`fldz`。
  - 状態: `fnstsw` (AX と m16)・`fnstcw` m16・`fldcw` m16 (RC 試行のみ)。
- native (参照): 機械語を `.byte` で直接実行 (中間値は実 FPU の 80bit)。 終了時は `fnsave` の ST(0..d-1) を `fldt`→`fstpl` で double に丸める (RN)。
- lowered: 同じ機械語を capstone で decode し、`x64c.FnLift.one()` が出す C 文を実行する (`x87_lowered_ops.inc` を生成)。 つまり lowering 本体を試験する。
- 試行: 入力 slot 6 個 (型 d/f/i/q)、操作列 2〜7 op、終了時の深さ d。 出力は (F) 各 op 後の FSW & 0x7d00 (C0/C2/C3/TOP)、(V) ST(0..d-1) の bit、(S) slot 8 個の bit。 S の `fnstsw m16` の格納値は PE/C1 等の未モデル化フラグを含むため、同じマスクで比べる。
- 比較の定義: 試行が bit 一致 = F・V・S が全て一致。 ulp 距離 = 順序付けした int64 の差 (`x87_diff.py` の `ulp_bits`)。 別算法の検算 `ulp_step` (nextafter の歩進) と全件一致 (`ulp cross-check bad 0`)。
- 開発中に差分試験が検出した不具合: `fxch st(i)` が capstone で 2 operand (`st(0), st(i)`) として返るのを `ops[0]` で読み、swap が no-op になっていた。 `ops[-1]` に修正 (同じ commit に含む)。

## 3. 実測 (測定 commit `ce0f0872`・HEAD で再現)

| 試験 | n | bit 一致 試行 | 試行の最大 ulp (0 / 1 / 2 / ≥3) | 値の ulp (0 / 1 / 2 / ≥3, 値数) | C0/C2/C3 一致 | FSW 不一致 試行 | slot 不一致 試行 |
|---|---:|---:|---|---|---:|---:|---:|
| 主 (seed 1) | 100,000 | 99,379 (99.38%) | 99,396 / 557 / 20 / 27 | 119,367 / 568 / 21 / 30 (119,986) | 24,151 / 24,152 | 1 | 25 |
| 再現 (seed 1, 再実行 2 回) | 100,000 | 99,379 (同じ) | 同じ | 同じ | 同じ | 1 | 25 |
| 別 seed (seed 2) | 100,000 | 99,384 (99.38%) | 99,399 / 565 / 10 / 26 | 119,068 / 594 / 10 / 26 (119,698) | 24,001 / 24,001 | 0 | 24 |
| ネガコン (`--nega`) | 100,000 | 99,097 (99.10%) | 99,127 / 552 / 20 / 301 | 119,079 / 564 / 21 / 322 (119,986) | 24,144 / 24,152 | 8 | 29 |
| RC (`--rc`、fldcw + fist/fistp/fst/fstp、算術なし) | 100,000 | 98,554 (98.55%) | 100,000 / 0 / 0 / 0 | 152,187 値すべて 0 ulp | 対象なし | 0 | 1,446 |

- 所要 (主 seed 1、1 driver 実行): native 0.30〜0.36 s、lowered 0.27〜0.34 s (3 回の min–max。 1 プロセスで 1e5 試行)。 driver 全体 (Python の試行生成を含む) は 13.0〜13.4 s。 load 1 分は 0.32〜0.55 (cpu 4、並列 1)。
- 主 seed 1 の ulp ≥3 の 30 値は、すべて桁落ちの結果 (例: trial 25547 は native 0.0・lowered 2.84e-14、trial 3847 は ulp 61)。 ulp 距離は桁落ち後の小さい値で大きくなる。 検算は §4。
- slot 不一致 25 件 (seed 1) の内訳 (`x87_crosscheck.py` (b)): `fst/fstp m32` を含まない 24 件は、m64 格納 (`fst/fstp/fist/fistp` の m64) の値が 1 ulp 違う (算術の差が格納値に出る)。 含む 1 件は `fst m32` の float 丸めの差。
- RC 試行: slot 不一致 1,446 件は **すべて `fst/fstp m32` を含む** (934 件は fist/fistp なし、512 件は fist/fistp あり)。 fst m32 を含まない試行の RC 由来の不一致は 0。 つまり `fist`/`fistp` の RC 丸めは一致し、`fst m32` は ADR 制限 (2) の C cast (nearest) 固定に起因する。

## 4. 差分が 0 にならない原因 (検算)

- `x87_crosscheck.py` (a) の trial 13317 (seed 1): 操作は `fld m64`・`fsubr m64`・`fist`・`fsubr m64`・`fnstsw`・`fcomp m64`。 有理数で丸め幅を変えて再計算すると、
  - f80 (64bit 有効数字): ST0 = 0.0897503210931822 → m64 と **equal (C3)**。 native の FSW C-bits 4000 と一致。
  - f64 (53bit): ST0 = 0.08975032109316317 → **less (C0)**。 lowered の FSW C-bits 0100 と一致。
  - よって 1 件の C 不一致は semantics の誤りではなく、f80 と f64 の丸めの違いによる比較結果の変化 (ADR 制限 4 の延長)。 「必ず全件一致」は f80→f64 の方式では成り立たない (期待値の修正は本付録で行う)。
- ulp ≥3 の例 (桁落ち): trial 25547 は native 0.0 / lowered 2.84e-14 (差は演算順の丸め由来の残差)、trial 3847 は -1986.1923940838758 と -1986.1923940838897 (ulp 61)。

## 5. ネガティブコントロール

- 方法: `--nega` は lowered 側で `fsub st(i), st(0)` (DC E8+i) を `fsubr st(i), st(0)` (DC E0+i) として lower する (1 種の取り違え)。
- 結果 (seed 1、n=100,000): bit 一致 99,379 → **99,097** (**−282**)。 ulp ≥3 の試行 27 → 301、C0/C2/C3 一致 24,151 → 24,144 (−7)、FSW 不一致 1 → 8。 取り違えが FAIL として数値で出る (検出力あり)。
- 注: 取り違えの影響が 282 件と小さいのは、DC E8+i が試行の約 1/8 にしか出ないため。 試行の分布を変えるとこの数は変わる。

## 6. 行案 (DEFECTS.md 未編集・PM 判断)

| ID (案) | 層 | 新旧 | 症状 (silent) | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|---|---|---|
| D24 (案) | fe | 新規 (候補) | x87 の中間値が native (80bit) と 1 ulp 以上ずれ、比較の C 値が変わる・桁落ちで結果が大きくずれる | f80 を持たず、スタック要素と中間値を double で持つ (D28)。 精度差が比較と格納に伝わる | §3 の表 (bit 一致 99.38%、C 不一致 1/24,152、§4 で検算) | x87 の算術の後に C0/C2/C3 を読む・`fst m64`/`fist` の格納 | 方式の再検討 (soft-float80 等)。 当面は ADR D28 の制限として記録 |

## 7. x64 回帰 (x64 出力が変わらないこと)

- `x64_regress_1099.py <before>`: 素材 x64 PE (`machine 0x8664`) のうち、サイズ順の先頭 8 本を EntryPoint root・closure 2 で、before (`git archive origin/main` の x64c) と after (本 branch) で lift し、`ott_lifted.c` と `lift_meta.json` を `cmp`。
- 結果: **8/8 一致** (`[x64-regress] same 8/8`)。 内訳は 7 本が 23 関数・593 命令、1 本が 1 関数・0 命令。

## 8. lift の被覆 (`lift_text.py` の roots 254 → closure 後 465 関数、命令 20,632)

| 項目 | before (`origin/main`) | after (`ce0f0872`) |
|---|---:|---:|
| unsup 合計 (`lift_meta.json`) | 4,136 | 89 |
| うち x87 (`f*`) | 4,134 | 87 |
| うち非 x87 (`std` 1・`shld` 1) | 2 | 2 |
| 被覆 (命令の起点 / バイト) | 20,212 / 61,654 B (84.46%) | 同じ |
| `emcc -c` 代替 (gcc -O1 -w、rc) | rc 0・object 880,904 B | rc 0・object 1,245,952 B |

- after の残り x87 87 件: `fsin` 15・`fscale` 15・`frndint` 11・`f2xm1` 8・`fldl2e` 8・`fprem` 5・`fiadd` 4・`ftst` 3・`fxam` 3・`fyl2x` 2・`fcos` 2・`fsqrt` 2・`fnclex` 2・`fldlg2` 1・`fimul` 1・`fnsave` 1・`frstor` 1・`fldpi` 1・`fnstenv` 1・`fldenv` 1。
- 被覆の 84.46% は変わらない (命令の起点は同じ。 unsup だった x87 が lift されただけ)。 未被覆 11,348 B の判定は #2814 (PLG-G2-22)。
- 注: `emcc` は本 runner に無く、`emcc` 名の gcc ラッパ (`$RUNNER_TEMP/bin/emcc`) を使った。 object サイズは emcc と比較できない。

## 9. 範囲と未解決

- 範囲内: §2 の op (lowering・差分試験)、fnstsw AX/m16、fldcw/fnstcw、RC の fist/fistp。
- 範囲外 (未検証): `fld`/`fstp` m80 の差分 (乱択の試行に入れていない。 変換は `x87_f80_to_f64` / `x87_f64_to_f80` の実装のみ)、超越関数・`frndint`・`fscale`・`fprem` 等 (未 lower)、x87 例外・stack fault (模型化しない)、PC の変更 (`fldcw` の PC ビット)、関数単位の native vs wasm 差分 (`emcc` と 32bit 実機 harness が要る)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残り x87 87 件 (超越関数 fsin/fcos/fyl2x/f2xm1/fldl2e 等、frndint/fscale/fprem/fsqrt、ftst/fxam、fiadd/fimul、fnsave/frstor/fnstenv/fldenv、fnclex) | lift の unsup が残る | #1099 の残り (子 issue は PM が起票) |
| 関数単位の native vs wasm 差分試験 (emcc と 32bit 実機 harness) | lowered の実 wasm での一致は未確認 | #1099 の残り (子 issue は PM が起票) |
| fld/fstp m80 の差分試験 (乱択に入れていない) | 80bit メモリ経路の丸めは未試験 | #1099 の残り |
| RC の算術への適用・`fst m32` の RC (ADR D28 制限 2・5) | RC≠nearest の算術・fst m32 は native と一致しない (RC 試行で 1,446 件) | PM 判断 (ADR D28 の改訂) |
| f80→f64 の精度差 (§6 の行案 D24) | 比較・桁落ちの差分の既知の源 | PM 判断 (`docs/DEFECTS.md` 編集) |
| 例外フラグ・C1・stack fault の未モデル化 (ADR D28 制限 4) | `fnstsw` の PE/C1 が native と違う | #1223 (PLG-G2-11) |
| Slayer `.text` の未被覆 11,348 B と非 x87 2 件 (`std`・`shld`) | `.text` 全体の lift は未達 | #2814 (PLG-G2-22) |

## 10. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PATH=$RUNNER_TEMP/bin:$PATH   # emcc 名の gcc ラッパ (lift_text.py 用)
cd tools/plugins/slayer_engine_ia32
python3 x87_diff.py --n 100000 --seed 1          # 主 (native/lowered のビルドを含む)
python3 x87_diff.py --n 100000 --seed 1 --nega   # ネガコン
python3 x87_diff.py --n 100000 --seed 1 --rc     # RC
python3 x87_crosscheck.py main                   # §4 (a)(b)。 直前の seed 1 の結果が work/x87/main にある必要がある
python3 lift_text.py                             # §8 の after。 before は origin/main を git archive で展開し同じ手順
python3 x64_regress_1099.py $RUNNER_TEMP/before 8   # §7 (before = origin/main を git archive で展開した dir)
```
