# REPORT_APPENDIX_3688 — x87 の状態の保存・復元 (fnsave・frstor・fnstenv・fldenv) の ia32 lowering (#3688 PLG-G2-30 の部分達成)

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない)。 FLDENV/FRSTOR 後のタグ語の差は残りの issue ([PLG-G2-48] #4110) で扱う。

- 親 REPORT: `REPORT_APPENDIX_2966.md` §6 (状態の保存・復元 4 件を #3688 に送った)。 方式: `docs/DECISIONS.md` D28 (f80→f64)。 本付録が本 issue の測定値の正本。
- 測定 commit: `0995187a8` (コードを変えた最後の commit)。 `git diff 0995187a8 HEAD -- tools/ott tools/plugins/slayer_engine_ia32` の出力は 0 行 (本付録の commit は docs のみ)。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` と生成した試行のみ。

## 1. 結論

- x87 unsup (`lift_text.py` pass1) を **36 → 32 件** に減らした。 fnsave・frstor・fnstenv・fldenv の 4 件を lower し、残りは超越・剰余 32 件 (#3687 [PLG-G2-29])。
- 差分試験 (`x87_diff.py --env`、10 万試行、seed 1): bit 一致 **99,982 (99.98%)**。 不一致 18 件は全てタグ語 (TW) の差 (FLDENV の復元規則。 §3)。 **受入条件の「bit 一致」は全件では満たしていない**。
- ネガティブコントロール (`--nega-env`: 格納した環境の TW を壊す): bit 一致 **0 (0.00%)** で検出する。
- x64 の生成 C は不変: `x64_regress_1099.py` 8/8 一致 (§5)。
- 既存の x87 差分試験 (主・RC・C1 のネガコン・定数除外) は基準 (origin/main) と数値が一致 (§4)。

## 2. 方法

- lowering (`tools/ott/lift/x64c.py` の ia32 経路。 runtime は `tools/ott/rt/ott_x87.h`):

  | 命令 | lowering | 注 |
  |---|---|---|
  | `fnstenv` | `x87_fnstenv(ea)` | 環境 28 B (CW @0・SW @4・TW @8)。 FIP/FCS/FOO/FOS は 0 (未モデル)。 格納後 FCW |= 0x3f |
  | `fldenv` | `x87_fldenv(ea)` | CW・TOP・C0/C2/C3 を戻す。 タグは読んだ TW をそのまま使う |
  | `fnsave` | `x87_fnsave(ea)` | 環境 28 B + ST(0..7) 各 80bit (f64→f80)。 格納後 FINIT |
  | `frstor` | `x87_frstor(ea)` | 環境を読み、ST(0..7) を f80→f64 で戻す |

- タグ語: `ott_x87.h` に物理レジスタごとの 2 bit (`ott_tag`) を追加 (00 valid / 01 zero / 10 special / 11 empty)。 値の書込みで分類し直す (`x87_cls`)。 `fxch` はタグも入れ替える。
- 差分試験 (`x87_diff.py --env`): env 専用の試行列 (`--env`)。 主試行列 (乱数列) は変えていない (§4 で確認)。 比べるのは F (op ごとの FSW・CMASK)・V (ST)・S (slot)・E (格納した環境の CW・SW の CMASK・TW)。
- 所要 (1 driver 実行の `time` の real): env 10 万 24.05 s (wall native 0.47 s・lowered 0.48 s)・`--nega-env` 23.14 s。 load1 開始時 0.71。

## 3. 実測 (測定 commit `0995187a8`)

| 試験 (コマンド) | n | bit 一致 | FSW 不一致 | slot 不一致 (E 欄を含む) |
|---|---:|---:|---:|---:|
| env (`x87_diff.py --env --n 100000 --seed 1`) | 100,000 | 99,982 (99.98%) | 0 | 18 |
| ネガコン (`--nega-env --n 100000 --seed 1`) | 100,000 | 0 (0.00%) | 0 | 100,000 |

- env の不一致 18 件はすべて E 欄 (格納環境の TW) の差。 F 欄 (FSW) は全件一致。
- 代表 (試行 3087): op 列 `fnclex, fld d, fnsave, fldz, fst, fcomp d, fldenv, fnstenv`。 最後の `fnstenv` の TW が native `7fff`・lowered `3fff` (物理 7 のタグ: native zero 01 / lowered valid 00)。
- 原因の切り分け (`work/x87/env/probe_*.c`、調査用・commit しない):
  - 実機 (native) で FLDENV の TW を読み、そのまま次の FNSTENV に出るとは限らない。 TOP と占有 (空/非空) に依存して書き直されるように見える。
    - ケース C: 全 empty で TW=3fff を FLDENV → FNSTENV の TW は 7fff (物理 7 の 00 は残らない)。
    - ケース A (3fff のまま残る) との違いは、直前の状態 (TOP と占有) だけで、規則は未確定。
  - lowered は「読んだ TW をそのまま保持」の方針なので、この規則と一致しない。
  - 推測で `ott_x87.h` を直すと他の試行で不一致が出るため、規則の確定は子 issue へ送った。
- 比較・丸めの試験で C1 は比べていない (ADR D28 制限 6。 env 試行でも CMASK = 0x7d00 で比べ、C1 は比べない)。

## 4. 既存の差分試験の不変 (基準 origin/main と一致)

| 試験 | HEAD (`0995187a8`) | 基準 (origin/main) |
|---|---|---|
| 主 (`--n 100000 --seed 1`) | 96,510 (96.51%)・FSW 77・slot 1,296・m80 14,269/12,525 | 2966 付録の値と一致 |
| `--rc-arith 0 --n 20000` | 19,306 (96.53%) | 19,306 (96.53%) |
| `--nega-c1 --n 20000` | 18,550 (92.75%) | 18,550 (92.75%) |
| `--skip fldpi,fldlg2,fldl2e --n 20000` | 19,694 (98.47%) | 19,694 (98.47%) |

## 5. lift の被覆 (before / after)

`lift_text.py` (pass1): x87 unsup の内訳は `fyl2x` 2・`fsin` 15・`fcos` 2・`f2xm1` 8・`fprem` 5 = **32 件**。 `fnsave`・`frstor`・`fnstenv`・`fldenv` は 0 件。 非 x87 unsup = 0。
pass2 の被覆は 20,431 / 62,320 B (85.37%)。 2966 付録の `f29c59648` と同じ (lift の起点は増えず、unsup だった x87 が lift されただけ)。

## 6. x64 回帰

`x64_regress_1099.py <origin/main の tools/ott を展開した dir> 8`: `[x64-regress] same 8/8` (2.69 s)。 `ott_x87.h` は ia32 の生成 C だけが include するので x64 の出力は変わらない。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FLDENV/FRSTOR 後の TW の復元規則 (TOP と占有に依存する書き直し) と env 差分 18 件 | 状態の保存・復元の bit 一致が全件では未達 | [PLG-G2-48] (#4110) |
| 超越・剰余 `fsin`・`fcos`・`f2xm1`・`fyl2x`・`fprem` (32 件) | lift の unsup が残る | [PLG-G2-29] (#3687) |
| FIP/FCS/FOO/FOS (環境の 12..27 B) は未モデル (0 で格納) | 環境を読み戻して実行アドレスを見る処理は一致しない | 起票なし: ADR D28 の制限に追記が要る (PM 判断) |
| x87 を含む関数の native と wasm の差分 | lowered の実 wasm での一致は未確認 | #2989 (PLG-G2-25) |

## 8. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PATH=$RUNNER_TEMP/bin:$PATH   # emcc 名の gcc ラッパ (lift_text.py 用)
cd tools/plugins/slayer_engine_ia32
python3 x87_diff.py --env --n 100000 --seed 1          # §3 の env
python3 x87_diff.py --nega-env --n 100000 --seed 1     # §3 のネガコン
python3 x87_diff.py --n 100000 --seed 1                # §4 の主
python3 lift_text.py                                    # §5
mkdir -p $RUNNER_TEMP/before && git archive origin/main tools/ott | tar -x -C $RUNNER_TEMP/before
python3 x64_regress_1099.py $RUNNER_TEMP/before 8      # §6
```
