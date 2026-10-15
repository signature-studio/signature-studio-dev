# REPORT_APPENDIX_3688 — x87 の状態の保存・復元 (fnsave・frstor・fnstenv・fldenv) の ia32 lowering (#3688 PLG-G2-30 の部分達成)

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない)。 FLDENV/FRSTOR 後のタグ語の差は残りの issue ([PLG-G2-48] #4110) で扱う。

- 親 REPORT: `REPORT_APPENDIX_2966.md` §6 (状態の保存・復元 4 件を #3688 に送った)。 方式: `docs/DECISIONS.md` D28 (f80→f64)。 本付録が本 issue の測定値の正本。
- 測定 commit (コードを変えた最後の commit): `36dd4f614` (origin/main を取り込んだ merge commit)。 検証 HEAD: `20298774e` (本付録と DOC_MAP の文言の修正のみ)。 `git diff 36dd4f614 20298774e -- tools/ott tools/plugins/slayer_engine_ia32 ':(exclude)*.md'` の出力は 0 行 (`#1268` の規則: 差分 0 なので再測定は要らない。 ただし以下の数値は、 `36dd4f614` で再測定した値)。
- 旧測定 commit `0995187a8` からのコード差分 (main 取り込みを含む): `git diff 0995187a8 36dd4f614 -- tools/ott tools/plugins/slayer_engine_ia32` は 19 files・959+/46-。 差分の中身は main 側の x87 変更 (`#3687` の超越関数 lower・試験の `--nega-trig`・`--only`・`--no-e`・定義域の判定) と本 PR の lowering。
- 比較基準: main の第 2 親 `feec9980a` (本 PR が取り込んだ main の commit) を `git archive` で展開して同じ試験を実行した。 基準の値は HEAD と全て一致 (§4)。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` と生成した試行のみ。
- 素材: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst`)。

## 1. 結論

- x87 unsup (x64c の `lift_meta.json` の `unsup`、`lift_text.py` pass1 と同じ入力) は **0 件**。 測定 commit `0995187a8` の 32 件 (超越・剰余) と、main の 4 件 (`fnsave`・`frstor`・`fnstenv`・`fldenv`) を、本 PR と main の `#3687` 側が lower して 0 件になった (§5)。
- 差分試験 (`x87_diff.py --env`、10 万試行、seed 1): bit 一致 **99,982 (99.98%)**。 不一致 18 件は全てタグ語 (TW) の差 (FLDENV の復元規則。 §3)。 **受入条件の「bit 一致」は全件では満たしていない**。
- ネガティブコントロール (`--nega-env`: 格納した環境の TW を壊す): bit 一致 **0 (0.00%)** で検出する。
- x64 の生成 C は不変: `x64_regress_1099.py` 8/8 一致 (§6)。
- 既存の x87 差分試験 (主・RC・C1 のネガコン・定数除外) は main 第 2 親と数値が一致 (§4)。 旧版の 96.51% は現 main と合わない古い基準値。

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
- 所要 (検証 HEAD・`time` の real): env 10 万 24.32 s (driver の wall native 0.47 s・lowered 0.47 s)・`--nega-env` 24.11 s。 load1 開始時 0.77〜0.98。

## 3. 実測 (検証 HEAD `36dd4f614`)

| 試験 (コマンド) | n | bit 一致 | FSW 不一致 | slot 不一致 (E 欄を含む) |
|---|---:|---:|---:|---:|
| env (`x87_diff.py --env --n 100000 --seed 1`) | 100,000 | 99,982 (99.98%) | 0 | 18 |
| ネガコン (`--nega-env --n 100000 --seed 1`) | 100,000 | 0 (0.00%) | 0 | 100,000 |

- env の不一致 18 件はすべて E 欄 (格納環境の TW) の差。 F 欄 (FSW) は全件一致。
- 不一致 18 件の試行番号 (0 始まり): 7827・19130・20991・25645・26204 ほか。 代表は試行 7827 (op 列 `fld1, fld1, fcomp, fnsave, fldz, fldenv, fnstenv`)。 最後の `fnstenv` の TW が native `7fff`・lowered `3fff`。
- 原因の切り分け (`work/x87/env/probe_*.c`、調査用・commit しない):
  - 実機 (native) で FLDENV の TW を読み、そのまま次の FNSTENV に出るとは限らない。 TOP と占有 (空/非空) に依存して書き直されるように見える。
    - ケース C: 全 empty で TW=3fff を FLDENV → FNSTENV の TW は 7fff (物理 7 の 00 は残らない)。
    - ケース A (3fff のまま残る) との違いは、直前の状態 (TOP と占有) だけで、規則は未確定。
  - lowered は「読んだ TW をそのまま保持」の方針なので、この規則と一致しない。
  - 推測で `ott_x87.h` を直すと他の試行で不一致が出るため、規則の確定は子 issue へ送った。
- 比較・丸めの試験で C1 は比べていない (ADR D28 制限 6。 env 試行でも CMASK = 0x7d00 で比べ、C1 は比べない)。

## 4. 既存の差分試験の不変 (基準 = main 第 2 親 `feec9980a`、HEAD と同値)

| 試験 | HEAD (`36dd4f614`) | 基準 (`feec9980a`) |
|---|---|---|
| 主 (`--n 100000 --seed 1`) | 93,985 (93.98%)・FSW 166・slot 1,560 | 93,985 (93.98%)・FSW 166・slot 1,560 |
| `--rc-arith 0 --n 20000` | 18,791 (93.95%)・FSW 28・slot 348 | 18,791 (93.95%)・FSW 28・slot 348 |
| `--nega-c1 --n 20000` | 18,112 (90.56%)・FSW 738・slot 315 | 18,112 (90.56%)・FSW 738・slot 315 |
| `--skip fldpi,fldlg2,fldl2e --n 20000` | 19,230 (96.15%)・FSW 46・slot 172 | 19,230 (96.15%)・FSW 46・slot 172 |

- 主試験の 93.98% は main 単体でも同じ (本 PR の変更による差はない)。 旧版の 96.51% (測定 commit 時点) は現 main と合わない。
- `--nega-c1` の検出は 93.98% → 90.56% (FSW 不一致 738) で、基準の値と同じく検出する。

## 5. lift の被覆 (x87 unsup の数え直し)

`lift_text.py` の pass1 と同じ入力 (`block22434_PE.bin`・export 1 + データ/即値由来の root) で x64c を実行し、`lift_meta.json` の `unsup` を数えた (emcc は本 run に無いので pass2・被覆の計算は省いた。 unsup の数は x64c の出力だけで決まる)。

| 版 | x87 unsup | 内訳 |
|---|---:|---|
| 測定 commit `0995187a8` | 32 | `fsin` 15・`f2xm1` 8・`fprem` 5・`fyl2x` 2・`fcos` 2 |
| main 第 2 親 `feec9980a` (`origin/main` 55fa456 の時点も同じ) | 4 | `fnsave` 1・`frstor` 1・`fnstenv` 1・`fldenv` 1 |
| 検証 HEAD `36dd4f614` | **0** | (なし) |

- 非 x87 unsup = 0。 関数 465・命令 20,632 (測定 commit と HEAD で同じ)。
- main の 32 件 → 4 件の差は `#3687` (PLG-G2-29) の超越 lower。 `i_fsin`・`i_fcos`・`i_fprem` は main の `tools/ott/lift/x64c.py` 874〜878 行で lower 済み。 `#3687` は CLOSED。
- HEAD の 0 件は本 PR の 4 命令の lower を含む。 **受入条件 1 (unsup 0) は満たす**。

## 6. x64 回帰

`x64_regress_1099.py <main 第 2 親 feec9980a の tools/ott と tools/plugins/slayer_engine_ia32 を展開した dir> 8`: `[x64-regress] same 8/8` (検証 HEAD と同じ生成 C・lift_meta)。 `ott_x87.h` は ia32 の生成 C だけが include するので x64 の出力は変わらない。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FLDENV/FRSTOR 後の TW の復元規則 (TOP と占有に依存する書き直し) と env 差分 18 件 | 状態の保存・復元の bit 一致が全件では未達 | [PLG-G2-48] (#4110) |
| FIP/FCS/FOO/FOS (環境の 12..27 B) は未モデル (0 で格納) | 環境を読み戻して実行アドレスを見る処理は一致しない | ADR D28 の制限への追記 (既定案: 制限 (7) として「FIP/FCS/FOO/FOS は 0 で格納・読み戻しは捨てる」を追記)。 PM 判断待ち。 |
| x87 を含む関数の native と wasm の差分 | lowered の実 wasm での一致は未確認 | #2989 (PLG-G2-25) |

- FIP/FCS/FOO/FOS の扱いは、ADR D28 の制限への追記で既定値 0 のまま格納する案を既定とし、PM の判断を待つ。 子 issue は起票しない (未達の受入条件ではなく、制限の記録)。

## 8. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PATH=$RUNNER_TEMP/bin:$PATH   # emcc 名の gcc ラッパ (lift_text.py 用)
cd tools/plugins/slayer_engine_ia32
python3 x87_diff.py --env --n 100000 --seed 1          # §3 の env
python3 x87_diff.py --nega-env --n 100000 --seed 1     # §3 のネガコン
python3 x87_diff.py --n 100000 --seed 1                # §4 の主
python3 x87_diff.py --rc-arith 0 --n 20000 --seed 1    # §4
python3 x87_diff.py --nega-c1 --n 20000 --seed 1       # §4
python3 x87_diff.py --skip fldpi,fldlg2,fldl2e --n 20000 --seed 1   # §4
python3 lift_text.py                                    # §5 (emcc が必要。 unsup は lift_meta.json の unsup)
mkdir -p $RUNNER_TEMP/base && git archive feec9980a tools/ott tools/plugins/slayer_engine_ia32 | tar -x -C $RUNNER_TEMP/base
python3 x64_regress_1099.py $RUNNER_TEMP/base 8        # §6
```
