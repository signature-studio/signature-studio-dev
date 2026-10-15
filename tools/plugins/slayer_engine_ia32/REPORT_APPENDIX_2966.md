# REPORT_APPENDIX_2966 — x87 の整数・比較・状態・定数・丸め命令の ia32 lowering (#2966 PLG-G2-23 の部分達成)

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない)。 f80→f64 の精度差は付録 1099 §6 の行案 (D24 案) に記録済みで、本付録の定数の差も同じ類型として §3 に書く (`DEFECTS.md` は未編集)。

- 親 REPORT: `REPORT_APPENDIX_1099.md` §8 (残り x87 unsup 87 件の内訳) と §9 (未解決)。 方式: `docs/DECISIONS.md` D28 (f80→f64)。 本付録が本 issue の測定値の正本。
- 測定 commit: `f29c59648` (lowering・runtime・op 表・RC 試行の対象を含む)。 直前の `f1cb2193b` は同じ lowering で、RC 試行の対象 (`RC_NAMES`) に frndint を加える前。
  `git diff f29c59648 HEAD -- tools/ott/lift tools/ott/rt tools/plugins/slayer_engine_ia32/x87_diff.py tools/plugins/slayer_engine_ia32/x64_regress_1099.py tools/plugins/slayer_engine_ia32/lift_text.py` の出力は 0 行 (本付録の commit は docs のみ)。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` (`$FL_WIN64_DIR/extracted/`) と生成した試行のみ。

## 1. 結論

- x87 unsup (`lift_text.py` pass1 の `lift_meta.json` の `unsup`) を **87 → 36 件** に減らした。 lower した 51 件: 整数 `fiadd` 4・`fimul` 1、比較・状態 `ftst` 3・`fxam` 3・`fnclex` 2、平方根 `fsqrt` 2、定数 `fldl2e` 8・`fldlg2` 1・`fldpi` 1、丸め・スケール `frndint` 11・`fscale` 15。
- 残り 36 件は子 issue に送った: 超越・剰余 32 件 (`fsin` 15・`fcos` 2・`f2xm1` 8・`fyl2x` 2・`fprem` 5) を [PLG-G2-29] (#3687)、状態の保存・復元 4 件 (`fnsave`・`frstor`・`fnstenv`・`fldenv`) を [PLG-G2-30] (#3688)。 番号は issue 本文と最終回答に書く。
- x64 の生成 C は不変: `x64_regress_1099.py` 8/8 一致 (§5)。 lift の被覆 (pass2 後) は 85.37% で before/after 同じ (§4)。
- 差分試験 (native と lowered、10 万試行、seed 1): bit 一致 97,857 (97.86%)。 付録 1099 の 99.38% から下がった。 主因は定数 3 種 (`fldpi`・`fldlg2`・`fldl2e`) で、これを op 表から外すと 99,329 (99.33%) になる (§3)。
- RC 試行 (`fldcw` + `fist`/`fistp`/`frndint` 等): 値の不一致は 0 件。 `frndint` の RC 経路も native と一致する。 slot 不一致 1,339 件は全て `fst m32` を含む (ADR D28 制限 2)。
- ネガティブコントロール (既存: `fsub`/`fsubr` の取り違え 1 種): 97,857 → 97,504 (−353) で検出する。 新しい op 群の専用ネガコンは [PLG-G2-29] (#3687) に入れる。

## 2. 対象と方法

- op 表 (`x87_diff.py` の `templates()`): 13 個を追加 (機械語の形: reg/none 9 種・mem 4 種)。 計 76 template・**244 instance** (付録 1099 の 231 から増えた)。
- lowering (`tools/ott/lift/x64c.py` の ia32 経路。 runtime は `tools/ott/rt/ott_x87.h`):

  | 命令 | lowering | 注 |
  |---|---|---|
  | `fiadd`・`fimul` m16/m32 | `x87_arith(op, 0, (double)(intN)LDN(ea), 0)` | 整数を double に変換してから算術 |
  | `ftst` | `x87_fcom(st0, 0.0)` | 比較の C 値 (未順序は 111) |
  | `fxam` | `x87_fxam()`: NaN→C0、有限→C2、inf→C2\|C0、0→C3 | C1 (符号) は未モデル化。 double の非正規は f80 では正規なので有限扱い |
  | `fnclex` | no-op | 例外フラグは未モデル化 (ADR 制限 4) |
  | `fsqrt` | `sqrt(st0)` | |
  | `frndint` | `x87_rc(st0)` | native と同じく FCW.RC に従う。 ADR D28 制限 5 (RC は fist/fistp の丸めだけ) を frndint に広げる (§3 の RC 試行で検証) |
  | `fscale` | `x87_fscale()`: st0·2^trunc(st1)。 指数は ±65536 に丸める | double の指数域外は inf/0 になる (f80 では有限)。 差分試験の入力域での出現は未確認 |
  | `fldl2e`・`fldlg2`・`fldpi` | 定数 (double) を push | f80 の定数 (64 bit 仮数) は double に乗らない (§3) |

- 比較の定義 (`x87_diff.py` の `compare` と同じ): 試行が bit 一致 = F (各 op 後の FSW の C0/C2/C3/TOP)・V (ST(0..d-1))・S (slot 8 個) が全て一致。 `fnstsw m16` の格納値は CMASK (C3/C2/C0) だけを比べる (ADR 制限 4)。
- 方法は付録 1099 §2 と同じ (native は機械語を `.byte` で実行、lowered は x64c が出す C を実行)。

## 3. 実測 (測定 commit `f29c59648`・HEAD で再現)

| 試験 (コマンド) | n | bit 一致 | 試行の最大 ulp (0 / 1 / 2 / ≥3) | 値の ulp (0 / 1 / 2 / ≥3, 値数) | C0/C2/C3 一致 | FSW 不一致 試行 | slot 不一致 試行 |
|---|---:|---:|---|---|---:|---:|---:|
| 主 (`--n 100000 --seed 1`) | 100,000 | 97,857 (97.86%) | 97,918 / 1,981 / 30 / 71 | 123,928 / 2,035 / 30 / 75 (126,068) | 28,575 / 28,576 | 1 | 89 |
| ネガコン (`--nega`) | 100,000 | 97,504 (97.50%) | 97,572 / 1,945 / 30 / 453 | 123,552 / 2,005 / 30 / 481 (126,068) | 28,565 / 28,576 | 11 | 95 |
| 定数除外 (`--skip fldpi,fldlg2,fldl2e`) | 100,000 | 99,329 (99.33%) | 99,346 / 616 / 10 / 28 | 116,679 / 629 / 10 / 28 (117,346) | 27,564 / 27,565 | 1 | 26 |
| RC (`--rc`) | 100,000 | 98,661 (98.66%) | 100,000 / 0 / 0 / 0 | 150,615 値すべて 0 ulp | 対象なし | 0 | 1,339 |

- 所要 (1 driver 実行の native・lowered の wall。 5 実行の範囲): native 0.31〜0.32 s、lowered 0.31〜0.32 s (1 プロセスで 1e5 試行)。 load1 は実行開始時で 0.45〜0.74 (cpu 4、並列 1)。 driver 全体 (Python の試行生成を含む) は約 17 s (実測 17.1 s、1 回)。
- ulp cross-check (nextafter の歩進との独立算法の検算) は全て一致 (`ulp cross-check bad 0`)。
- 定数の寄与: 主の一致率 97.86% に対し、定数 3 種を外すと 99.33%。 定数の f80 値 (64 bit 仮数) は double に丸めると f64 の値と一致せず、後続の算術で 1 ulp 級の差になる。 これは ADR D28 の帰結 (f80 を持たない) で、方式は変えない。
- 付録 1099 の表 (99.38%) との差 (0.05 点) は、op 表の追加で試行の分布が変わったため。 同じ seed の比較はしていない。
- RC 試行の slot 不一致 1,339 件は、`fst`/`fstp` m32 を含む試行と一致する (含まない試行は 0 件。同じ判定で数えた)。 `fst m32` の丸めは C の cast (nearest) 固定 (ADR 制限 2) による。 ネガコン (`--nega`) の数字は算術の取り違え 1 種が出す差で、検出力の確認にだけ使う。

## 4. lift の被覆 (before / after)

before = `origin/main` (`e99fe343c`) を detached worktree で展開して `lift_text.py` を実行。 after = 測定 commit `f29c59648`。 `lift_text.py` の pass1 は roots 254 本の lift、pass2 は gap の (b) 5 区間を roots に加えた再 lift。

| 版 | pass | x87 unsup (件) | 非 x87 unsup | 関数 / 命令 | 被覆 (命令の起点 / バイト) |
|---|---|---:|---:|---:|---|
| origin/main (`e99fe343c`) | pass1 | 87 | 0 | 465 / 20,632 | 未計測 |
| origin/main | pass2 | 89 | 0 | 472 / 21,354 | 20,431 / 62,320 of 73,002 B (85.37%) |
| `f29c59648` | pass1 | 36 | 0 | 465 / 20,632 | 未計測 |
| `f29c59648` | pass2 | 36 | 0 | 472 / 21,354 | 20,431 / 62,320 of 73,002 B (85.37%) |

- pass1 の before (87 件) は付録 1099 §8 の 87 件と一致する。
- pass2 の before が 89 件なのは、(b) の roots 追加で `fscale` が 2 件多く現れるため (pass2 の関数数が 465 → 472 に増える)。
- 被覆は before/after で同じ (lift の起点は増えず、unsup だった x87 が lift されただけ)。

## 5. x64 回帰 (x64 出力が変わらないこと)

- `x64_regress_1099.py <origin/main の tools/ott を展開した dir> 8` (測定 commit `f29c59648`): `[x64-regress] same 8/8`。 x64c は `ia32_only` の handler だけを追加し、x64 の経路は `Unsup` のまま。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 超越・剰余 `fsin` 15・`fcos` 2・`f2xm1` 8・`fyl2x` 2・`fprem` 5 (32 件) の lowering と差分試験・ネガコン | lift の unsup が 32 件残る | [PLG-G2-29] (#3687) (子 issue) |
| 状態の保存・復元 `fnsave`・`frstor`・`fnstenv`・`fldenv` (4 件) | lift の unsup が 4 件残る | [PLG-G2-30] (#3688) (子 issue) |
| 定数の f80 精度 (`fldpi`・`fldlg2`・`fldl2e`) による 1 ulp 級の差 (混合試験の不一致の主因) | 比較・桁落ちの差の源 (D28 の帰結) | 起票なし: 付録 1099 §6 の行案 (D24 案) に含む。 `DEFECTS.md` は PM 判断 |
| `frndint` の RC 適用が ADR D28 制限 5 (RC は fist/fistp だけ) の文言を広げる | ADR の文言と実装の範囲が 1 命令ずれる | PM 判断 (D28 の追記要否)。 本 PR は ADR を変えない |
| `fxam` の C1 (符号) と `fnclex` の例外フラグ (ADR 制限 4) | `fxam` の C1 は比較外 | #1223 (PLG-G2-11) |
| `fscale` の指数域外 (double 外は inf/0) | f80 の有限値と差が出る入力があり得る。 差分試験の入力域での出現は未確認 | 未確認。 [PLG-G2-29] (#3687) の差分試験で入力域を広げて確認する |
| x87 を含む関数の native と wasm の差分 | lowered の実 wasm での一致は未確認 | #2989 (PLG-G2-25) |

## 7. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PATH=$RUNNER_TEMP/bin:$PATH   # emcc 名の gcc ラッパ (lift_text.py 用)
cd tools/plugins/slayer_engine_ia32
python3 x87_diff.py --n 100000 --seed 1                      # 主
python3 x87_diff.py --n 100000 --seed 1 --nega               # ネガコン
python3 x87_diff.py --n 100000 --seed 1 --rc                 # RC
python3 x87_diff.py --n 100000 --seed 1 --skip fldpi,fldlg2,fldl2e   # 定数の寄与
python3 lift_text.py                                         # §4 の after (before は origin/main を worktree で展開して同じ手順)
mkdir -p $RUNNER_TEMP/before && git archive origin/main tools/ott | tar -x -C $RUNNER_TEMP/before
python3 x64_regress_1099.py $RUNNER_TEMP/before 8            # §5
```
