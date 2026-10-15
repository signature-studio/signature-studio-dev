# REPORT_APPENDIX_2966 — x87 の整数・比較・状態・定数・丸め命令の ia32 lowering (#2966 PLG-G2-23 の部分達成)

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない)。 f80→f64 の精度差は付録 1099 §6 の行案 (D24 案) に記録済みで、本付録の定数の差も同じ類型として §3 に書く (`DEFECTS.md` は未編集)。

- 親 REPORT: `REPORT_APPENDIX_1099.md` §8 (残り x87 unsup 87 件の内訳) と §9 (未解決)。 方式: `docs/DECISIONS.md` D28 (f80→f64)。 本付録が本 issue の測定値の正本。
- 測定 commit: `c508291cf` (`Merge remote-tracking branch 'origin/main' into 2966-x87-int-state-round`)。 main の x87 差分試験 (#2967: 16 byte slot・m80 入力・`--nega80`・`--rc-arith`) を取り込んだ commit で、x87 差分試験の数値はこの commit で測り直した。 取り込み前の数値 (`139c2c9b5` の 97,857 など) は試行列が違うので使わない。
  `git diff c508291cf HEAD -- tools/ott tools/plugins/slayer_engine_ia32/x87_diff.py tools/plugins/slayer_engine_ia32/x87_diff_main.h tools/plugins/slayer_engine_ia32/x87_crosscheck.py` の出力は 0 行 (本付録の commit は docs のみ)。
- lift (`tools/plugins/slayer_engine_ia32/lift_text.py`・`tools/ott/lift`) と x64 回帰 (`x64_regress_1099.py`) は測定 commit `f29c59648` のまま。 `git diff f29c59648 HEAD -- tools/ott/lift tools/plugins/slayer_engine_ia32/lift_text.py tools/plugins/slayer_engine_ia32/x64_regress_1099.py` の出力は 0 行 (§4・§5 の数値は HEAD でも同じ)。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` (`$FL_WIN64_DIR/extracted/`) と生成した試行のみ。

## 1. 結論

- x87 unsup (`lift_text.py` pass1 の `lift_meta.json` の `unsup`) を **87 → 36 件** に減らした。 lower した 51 件: 整数 `fiadd` 4・`fimul` 1、比較・状態 `ftst` 3・`fxam` 3・`fnclex` 2、平方根 `fsqrt` 2、定数 `fldl2e` 8・`fldlg2` 1・`fldpi` 1、丸め・スケール `frndint` 11・`fscale` 15。
- 残り 36 件は子 issue に送った: 超越・剰余 32 件 (`fsin` 15・`fcos` 2・`f2xm1` 8・`fyl2x` 2・`fprem` 5) を [PLG-G2-29] (#3687)、状態の保存・復元 4 件 (`fnsave`・`frstor`・`fnstenv`・`fldenv`) を [PLG-G2-30] (#3688)。 番号は issue 本文と最終回答に書く。
- x64 の生成 C は不変: `x64_regress_1099.py` 8/8 一致 (§5)。 lift の被覆 (pass2 後) は 85.37% で before/after 同じ (§4)。
- 差分試験 (native と lowered、10 万試行、seed 1、測定 commit `c508291cf`): bit 一致 **96,510 (96.51%)**。 定数 3 種 (`fldpi`・`fldlg2`・`fldl2e`) を op 表から外すと 98,487 (98.49%) (§3)。
- RC 試行 (`--rc`: `fldcw` + `fist`/`fistp`/`frndint` 等): 値 145,441 件はすべて 0 ulp。 slot 不一致 1,289 件は全て `fst`/`fstp` m32 を含む (ADR D28 制限 2)。
- **C1 (符号) の模型化**: `fxam` は C1 に符号を立て (`x87_fsw()` が返す)、比較命令 (`fcom`・`fcomp`・`fcompp`・`ftst`) は C1 を 0 にする。 native で実測した結果、比較命令の後の C1 は常に 0、`fxam` の後の C1 は ST(0) の符号と一致した (§3)。 差分試験は比較・`fxam` の直後の C1 も比べる。
- 比較・`fxam` 27,863 件のうち C0〜C3 (TOP を除く) が一致したのは 27,784 件。 不一致 79 件は、すべて FSW 不一致の 77 試行に含まれ、その入力は f64 の指数域外 (大きすぎる指数・f80 の非正規) を含む (§3)。
- C1 のネガティブコントロール (新規 `--nega-c1`: fxam の直後に C1 を反転): 96,510 → 93,000 (−3,510) で検出する。 FSW 不一致 3,705 試行。
- ネガティブコントロール (既存: `fsub`/`fsubr` の取り違え 1 種): 96,510 → 96,189 (−321) で検出する。
- **C1 の影響箇所** (レビュー指摘の lift 出力 `ott_lifted.c` の `1000b7bd` 周辺): fxam は `0x1000b7bd`・`0x1000b824`・`0x1000b842` の 3 箇所。 `0x1000b7bd` は fxam の直後に `fnstsw word ptr [ebp-0xa0]` で FSW を読む。 模型化した C1 は fxam の符号で、fxam と fnstsw の間に C1 を変える他の x87 命令が無ければ native と一致する。 3 箇所それぞれの間の命令列の確認は本 run では未実施 (未解決 §6 に起票先を書く)。
- C1 の未模型化: 比較・fxam 以外の命令の C1 は native では丸めの上向きフラグ等になる (例: `fadd st(1)`・`fmul`・`fst m32` の直後)。 f80 を持たない f64 lowering では丸め方向が無いので模型化しない (`ott_x87.h` の制限 (6)・ADR D28 制限 (6))。 差分試験もこれらの直後の C1 は比べない。

## 2. 対象と方法

- op 表 (`x87_diff.py` の `templates()`): 本 PR で 13 個を追加 (機械語の形: reg/none 9 種・mem 4 種)。 main の op 表と合わせて計 78 template・**246 instance**。
- lowering (`tools/ott/lift/x64c.py` の ia32 経路。 runtime は `tools/ott/rt/ott_x87.h`):

  | 命令 | lowering | 注 |
  |---|---|---|
  | `fiadd`・`fimul` m16/m32 | `x87_arith(op, 0, (double)(intN)LDN(ea), 0)` | 整数を double に変換してから算術 |
  | `ftst` | `x87_fcom(st0, 0.0)` | 比較の C 値 (未順序は 111)。 C1 = 0 |
  | `fxam` | `x87_fxam()`: NaN→C0、有限→C2、inf→C2\|C0、0→C3、符号→C1 | double の非正規は f80 では正規なので有限扱い |
  | `fnclex` | no-op | 例外フラグは未モデル化 (ADR 制限 4) |
  | `fsqrt` | `sqrt(st0)` | |
  | `frndint` | `x87_rc(st0)` | native と同じく FCW.RC に従う。 ADR D28 制限 5 (RC は fist/fistp の丸めだけ) を frndint に広げる (§3 の RC 試行で検証) |
  | `fscale` | `x87_fscale()`: st0·2^trunc(st1)。 指数は ±65536 に丸める | double の指数域外は inf/0 になる (f80 では有限)。 差分試験の入力域での出現は §3 の FSW 不一致で確認 |
  | `fldl2e`・`fldlg2`・`fldpi` | 定数 (double) を push | f80 の定数 (64 bit 仮数) は double に乗らない (§3) |

- 比較の定義 (`x87_diff.py` の `compare`): 試行が bit 一致 = F・V (ST(0..d-1))・S (slot 8 個) が全て一致。 F は各 op 後の FSW の C0/C2/C3/TOP で、 **比較命令・`fxam` (`cmp=True`) の直後だけ C1 も比べる** (それ以外の命令の C1 は native の丸めフラグで、模型化していないので比べない)。 `fnstsw m16` の格納値は CMASK (C3/C2/C0/TOP) だけを比べる (ADR 制限 4)。
- 試行列は main (#2967) の生成規則のまま (入力 slot は 16 byte・`e` 型は m80)。 方法は付録 1099 §2 と同じ (native は機械語を `.byte` で実行、lowered は x64c が出す C を実行)。 driver は FSW を `& 0x7f00` (C1 を含む) で出し、比べる bit は `x87_diff.py` 側で選ぶ。

## 3. 実測 (測定 commit `c508291cf`・以後の HEAD との差は docs のみ)

| 試験 (コマンド) | n | bit 一致 | 試行の最大 ulp (0 / 1 / 2 / ≥3) | 値の ulp (0 / 1 / 2 / ≥3, 値数) | C0-C3 一致 (比較・fxam 直後) | FSW 不一致 試行 | slot 不一致 試行 |
|---|---:|---:|---|---|---:|---:|---:|
| 主 (`--n 100000 --seed 1`) | 100,000 | 96,510 (96.51%) | 97,817 / 1,951 / 35 / 197 | 123,994 / 2,027 / 35 / 205 (126,261) | 27,784 / 27,863 | 77 | 1,296 |
| ネガコン (`--nega`: fsub/fsubr の取り違え) | 100,000 | 96,189 (96.19%) | 97,501 / 1,925 / 34 / 540 | 123,660 / 2,000 / 34 / 567 (126,261) | 27,774 / 27,863 | 87 | 1,301 |
| ネガコン C1 (`--nega-c1`: fxam 直後の C1 反転) | 100,000 | 93,000 (93.00%) | 97,817 / 1,951 / 35 / 197 | 123,994 / 2,027 / 35 / 205 (126,261) | 24,079 / 27,863 | 3,705 | 1,296 |
| 定数除外 (`--skip fldpi,fldlg2,fldl2e`) | 100,000 | 98,487 (98.49%) | 99,062 / 684 / 20 / 234 | 116,940 / 703 / 20 / 242 (117,905) | 26,620 / 26,747 | 120 | 509 |
| RC (`--rc`) | 100,000 | 98,711 (98.71%) | 100,000 / 0 / 0 / 0 | 145,441 値すべて 0 ulp | 対象なし | 0 | 1,289 |

- 試行の最大 ulp の ≥3 には、f80 の指数域外の値 (f64 では inf か 0) を比べた試行が入る。 その最大値 (`4704357450214544768` など) は inf と有限値の距離で、ulp としての意味は無い。
- 所要 (1 driver 実行の `time` の real): 主 11.97 s (native 0.31 s・lowered 0.31 s、load1 開始時 0.28)。 `--nega` 11.69 s・`--nega-c1` 11.53 s・`--skip` 12.22 s・`--rc` 7.23 s。
- ulp cross-check (nextafter の歩進との独立算法の検算) は全て一致 (`ulp cross-check bad 0`)。
- m80 を含む試行 (`fld`/`fstp` m80): 14,269 試行中 12,525 が bit 一致 (87.78%)。 op 種別の内訳 (bit 一致/試行): 算術 59,315/61,947・fst m32 2,570/2,595・算術と fst m32 4,484/4,637・どちらも無し 30,141/30,821。
- **C1 の判定** (native 実測、主試行の全 op 遷移から): 比較命令 (`fcom`・`fcomp`・`fcompp`・`ftst`) の後の C1 は全件 0。 `fxam` の後の C1 は ST(0) の符号と一致 (不一致 0)。
- **FSW 不一致 77 試行 (主) の原因**: `x87_crosscheck.py` (a) で、77 試行はすべて `fld` m80 の入力を含み、その類は `exp_out_of_f64` (指数が f64 を超える) 53 試行・`denormal` (f80 の非正規) 24 試行 (1 試行に 1 類)。 最初に食い違う op は `fxam` 35・`ftst` 22・`fcom` 11・`fcomp` 8・`fcompp` 1 で、すべて比較・`fxam` (cmp=True)。 `x87_f80_to_f64` は f64 の指数域外を 0 / inf に丸めるので (`ott_x87.h`)、この不一致は ADR D28 (f80→f64) の帰結。 比較・`fxam` の C0〜C3 不一致 79 件も同じ 77 試行に含まれる。
- **slot 不一致 1,296 件 (主) の内訳** (`x87_crosscheck.py` (b)): `fst`/`fstp` m32 を含む 59 件 (うち m80 を含む 55 件)、含まない 1,237 件 (うち m80 を含む 1,169 件、m80 も m32 も含まない 68 件)。 m80 も m32 も含まない 68 件の原因は本 run では未確認 (§6)。
- **RC 試行の slot 不一致 1,289 件**: `fst`/`fstp` m32 を含む試行が 1,289 件 (`x87_crosscheck.py rc` (b))。 含まない試行は 0 件。 `fst m32` の丸めは C の cast (nearest) 固定による (ADR 制限 2)。
- 定数の寄与: 主の一致率 96.51% に対し、定数 3 種を外すと 98.49%。 定数の f80 値 (64 bit 仮数) は double に丸めると f64 の値と一致せず、後続の算術で 1 ulp 級の差になる。 これは ADR D28 の帰結 (f80 を持たない) で、方式は変えない。
- 取り込み前 (`139c2c9b5`) の値 (主 97,857・nega-c1 94,282 など) は、main の試行列と揃わないため使わない。 試行列が変わったので bit 一致は 97.86% から 96.51% に動いた。 その内訳は上記の FSW・slot の不一致 (m80 入力を含む試行) のとおり。

## 4. lift の被覆 (before / after)

before = `origin/main` (`e99fe343c`) を detached worktree で展開して `lift_text.py` を実行。 after = 測定 commit `f29c59648` (lift のコードは `c508291cf` まで同じ。 §1 の差分 0 の確認)。 `lift_text.py` の pass1 は roots 254 本の lift、pass2 は gap の (b) 5 区間を roots に加えた再 lift。

| 版 | pass | x87 unsup (件) | 非 x87 unsup | 関数 / 命令 | 被覆 (命令の起点 / バイト) |
|---|---|---:|---:|---:|---|
| origin/main (`e99fe343c`) | pass1 | 87 | 0 | 465 / 20,632 | 未計測 |
| origin/main | pass2 | 89 | 0 | 472 / 21,354 | 20,431 / 62,320 of 73,002 B (85.37%) |
| `f29c59648` | pass1 | 36 | 0 | 465 / 20,632 | 未計測 |
| `f29c59648` | pass2 | 36 | 0 | 472 / 21,354 | 20,431 / 62,320 of 73,002 B (85.37%) |

- pass1 の before (87 件) は付録 1099 §8 の 87 件と一致する。
- pass2 の before が 89 件なのは、(b) の roots 追加で `fscale` が 2 件多く現れるため (pass2 の関数数が 465 → 472 に増える)。
- 被覆は before/after で同じ (lift の起点は増えず、unsup だった x87 が lift されただけ)。
- `139c2c9b5` の C1 修正は lift の出力を変えない (`x64c.py` は未変更)。 main の取り込み (`c508291cf`) も `tools/ott` を変えない。 lift の数値は再測定していない (範囲の差分 0 行は §0 の確認どおり)。

## 5. x64 回帰 (x64 出力が変わらないこと)

- `x64_regress_1099.py <origin/main の tools/ott を展開した dir> 8` (測定 commit `f29c59648`): `[x64-regress] same 8/8`。 x64c は `ia32_only` の handler だけを追加し、x64 の経路は `Unsup` のまま。 `ott_x87.h` は ia32 の生成 C だけが include するので、C1 修正の後も x64 の出力は変わらない。 `tools/ott/lift` と `x64_regress_1099.py` は `f29c59648` から HEAD まで差分 0 行 (§0)。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 超越・剰余 `fsin` 15・`fcos` 2・`f2xm1` 8・`fyl2x` 2・`fprem` 5 (32 件) の lowering と差分試験・ネガコン | lift の unsup が 32 件残る | [PLG-G2-29] (#3687) (子 issue) |
| 状態の保存・復元 `fnsave`・`frstor`・`fnstenv`・`fldenv` (4 件) | lift の unsup が 4 件残る | [PLG-G2-30] (#3688) (子 issue) |
| 影響箇所 `0x1000b7bd`・`0x1000b824`・`0x1000b842` (fxam) の間に C1 を変える命令が無いことの lift 出力での確認 | 間に他の x87 命令があれば、模型化した C1 が native と違う値になる | 本 PR では未確認。 PM 判断 (#2966 の未解決) |
| 比較・fxam 以外の命令の C1 (丸めの上向きフラグ。 例: `fadd st(1)`・`fmul`・`fst m32`) | fnstsw で C1 を読むコードは、これらの直後では値が違う。 差分試験の対象外 | ADR D28 制限 (6) に明記済み。 残りは PM 判断 (#3749) |
| slot 不一致 68 件 (`fst`/`fstp` m32 も m80 も含まない試行) の原因 | 差分試験の不一致の一部が未説明 | PM 判断 (原因未確認) |
| 定数の f80 精度 (`fldpi`・`fldlg2`・`fldl2e`) による 1 ulp 級の差 (主試行の不一致の主因) | 比較・桁落ちの差の源 (D28 の帰結) | 起票なし: 付録 1099 §6 の行案 (D24 案) に含む。 `DEFECTS.md` は PM 判断 |
| f80 の指数域外の入力による FSW 不一致 77 試行 (§3) | f64 で inf/0 になる値を比較・fxam したときに FSW が違う | ADR D28 の帰結。 方式は変えない (PM 判断) |
| `frndint` の RC 適用が ADR D28 制限 5 (RC は fist/fistp だけ) の文言を広げる | ADR の文言と実装の範囲が 1 命令ずれる | PM 判断 (#3749) |
| `fnclex` の例外フラグ (ADR 制限 4) | 例外フラグは未模型化 | #1223 (PLG-G2-11) |
| `fscale` の指数域外 (double 外は inf/0) | f80 の有限値と差が出る。 差分試験の入力には f64 の指数域外が入るが、`fscale` を含む試行の一致は本 run では個別に確認していない | [PLG-G2-29] (#3687) の受入 |
| x87 を含む関数の native と wasm の差分 | lowered の実 wasm での一致は未確認 | #2989 (PLG-G2-25) |

## 7. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PATH=$RUNNER_TEMP/bin:$PATH   # emcc 名の gcc ラッパ (lift_text.py 用)
cd tools/plugins/slayer_engine_ia32
python3 x87_diff.py --n 100000 --seed 1                      # 主
python3 x87_diff.py --n 100000 --seed 1 --nega               # ネガコン (fsub/fsubr)
python3 x87_diff.py --n 100000 --seed 1 --nega-c1            # ネガコン (fxam の C1 反転)
python3 x87_diff.py --n 100000 --seed 1 --rc                 # RC
python3 x87_diff.py --n 100000 --seed 1 --skip fldpi,fldlg2,fldl2e   # 定数の寄与
python3 x87_crosscheck.py main                               # §3 の FSW・slot の内訳 ((d) は --rc-arith 0..3 の結果が要る。 本 REPORT の数値には使わない)
python3 x87_crosscheck.py rc                                 # §3 の RC の slot 内訳
python3 lift_text.py                                         # §4 の after (before は origin/main を worktree で展開して同じ手順)
mkdir -p $RUNNER_TEMP/before && git archive origin/main tools/ott | tar -x -C $RUNNER_TEMP/before
python3 x64_regress_1099.py $RUNNER_TEMP/before 8            # §5
```
