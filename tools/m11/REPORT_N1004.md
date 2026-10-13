# M11 実行後の guest ポインタ検査 (#1004, 部分達成)

親: #403 (受入 3 の後半)。素材: fl-win64 (`block00031_PE.bin` 22,227,016 B, sha256 先頭 `b2c64da4…`)・work-m11・work-liftdiff。
toolchain-retdec はツール台帳 `docs/REFERENCES.md` の `[RETDEC]` を参照。
結果を `REPORT_N1004.md` に置く理由: 本 PR は #1004 の部分達成で、#403 の REPORT (`REPORT_N403.md`) への追記は親 issue の受入をまとめて閉じる段階で行う (本 PR では親の REPORT を書き換えない)。

## 1. 実装 (完了)

- `tools/m11/m11_ptrcheck.mjs` — 実行後の guest メモリ全体で、4 バイト整列 word のうち image VA 範囲 `[0x400000, 0x400000+0x1ac0000)` に入り、かつ実行前には無かったものを数える。`M11_PTRCHECK_INJECT=<offset>` で既知の未 remap 値 `0x400000` を書き込めるようにした (ネガティブコントロール用)。
- `tools/m11/m11_run.mjs` / `m11_survey.mjs` — 実行後に `ptrcheck` の結果を JSON に出す (情報出力)。

## 2. 実測 (work-m11 の既存 wasm・image, LB=0 相当)

| 条件 | 所要 | 結果 |
|---|---|---|
| `m11_run.mjs` クリーン | 0.99 s (wall) | `image_va_words_pre=406576`・`image_va_words_new=68938`・`ok=false` |
| `m11_run.mjs` + `M11_PTRCHECK_INJECT=22519877` | — | `image_va_words_new=68939` (+1 を検出) |
| `m11_survey.mjs` | 0.26 s で異常終了 | `_m11_set_va_unit_budget is not a function`。work-m11 の wasm は現行 `m11_rt.c` より古い |
| `m11_ptrcheck_negctl.sh` (ネガティブコントロール) | 3.1 s (wall, 2 回実行の合計) | `clean=68938`・`injected(offset=22519877)=68939`・`diff=1`。`NEGCTL OK`・exit 0 |

- `m11_survey.mjs` に加えた `ptrcheck` の出力は **未検証 (survey 起動不可のため)**。実行されていない。
- 注入の +1 は検出器が注入語を数えることの確認。クリーン実行の 68,938 件は判定基準ではない (§3 参照)。

## 3. 未達 (受入条件との対応)

- **受入 1 (実行後検査)**: 実装済み。ただし上記 68,938 語のクリーン実行の「新規」範囲内 word は、正当な LVA の整数値とも未 remap の VA とも値だけでは区別できない。このため不合格ゲートにはしていない (e2e に組み込むと常に失敗する)。
- **受入 2 (不合格で非 0 終了)**: ゲート化を見送ったため未達。判定基準 (どの offset を未 remap とみなすか) を確定させる必要がある。
- **受入 3 (ネガティブコントロール同梱)**: 達成。`tools/m11/m11_ptrcheck_negctl.sh` を同梱し、§2 のとおり clean と注入の差 +1 を実測 (`NEGCTL OK`)。判定基準 (受入 1・2) は未確定のまま。
- **受入 4 (`M11_LB_BASE=0` / `0x10000` の e2e 比較)**: 未実施。理由:
  - `m11_e2e.sh` が全再生成モードに入り、`m11_bounds.py` が素材に無い `tools/m2/work/ghidra_dll/functions_dll.csv` を要求して落ちる (fail-closed)。
  - work-m11 に `lift_pe.sha256`・`ir_conditions.json`・`ir_lb_base.stamp` が無く、WORKFLOW §11 のとおり pre-qstore 版。
  - 既存 wasm が現行 `m11_rt.c` と一致しないため、survey を実行できない。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 「未 remap の image VA」を実行後の値だけで判定できない (LB=0 は LVA=RVA で範囲が重なる) | 受入 1・2・3 の判定基準 | 本 issue (#1004) で継続 |
| `m11_e2e.sh` の全再生成が素材に無い `functions_dll.csv` を要求する | e2e 比較 (受入 4) が実行できない | PM 起票を要求 (素材 `work-m11` の再生成手順) |
| work-m11 の wasm・work/ が古い (`m11_set_va_unit_budget` 無し・units_run 17) | 解消 (§5 で IR・data・image・wasm を LB ごとに再生成し survey 実測)。work-m11 素材自体の更新は未対応 | PM 起票を要求 (work-m11 素材の再生成手順) |

## 5. 再測定 (2026-10-13, 測定 commit 916d9932 = main。tools/m11 のコード差分 0 行)

### 5.1 差分 0 の証跡

検証 HEAD は `f9c54171` (PR head)。測定 commit `916d9932` から HEAD までの `tools/m11` のコード差分は、REPORT 1 ファイルの追加のみ。

```sh
git diff --stat 916d9932 HEAD -- tools/m11
# tools/m11/REPORT_N1004.md | 37 +++++++++++++++++++++++++++++++++++++
# 1 file changed, 37 insertions(+)
git diff 916d9932 HEAD -- tools/m11 ':!tools/m11/REPORT_N1004.md' | wc -c
# 0   (REPORT 以外の差分は 0 バイト)
```

### 5.2 環境と測定条件

- 並列数: `nproc` = 4。load average は各測定の直前の `/proc/loadavg` (1 分値) を併記。
- 素材: `fl-win64.tar.zst` を `tar --zstd -xf` で `$RUNNER_TEMP/extracted/` に展開 (`block00031_PE.bin` sha256 先頭 `b2c64da4…` を確認)。`toolchain-emsdk.tar.zst` を `$RUNNER_TEMP/emsdk` に展開。
- 既存の `work/` (2026-10-10 生成) は古く、そのまま使うと run が units_run=17 になるため使わない。IR・data・image・wasm を LB ごとに作り直した。
- `m11_build.sh` は emsdk 環境スクリプト (`[EMSDK]` 系の固定位置) を前提にするため、runner では `work/m11_build_local.sh` (その参照先を `work/emsdk_env_local.sh` に置換しただけの複製) で実行した。`HERE` も `tools/m11` に固定。
- `m11_e2e.sh` は `functions_dll.csv` を要求して落ちるため使わず、以下の個別コマンドで代替した。
- 所要は単発値ではなく、run・survey とも各 LB で n=3 の min–max を採った。

### 5.3 IR の指紋

| LB | `ir_sha256` (`work/ir_conditions.json`) | 生成条件 |
|---|---|---|
| `M11_LB_BASE=0` | `2c68ceaeb0518ef841f27fd46ca986a6c4fc174def26e3acdf1ce70a15bcaf18` | ldfix=applied, qstore=not-applied |
| `M11_LB_BASE=0x10000` | `e14a943d84cb59f2e10f3fa729ef76092666eaa33d86b484ce014721df622b41` | ldfix=applied, qstore=not-applied |

`m11_gen_ir2.sh` は LB が違うと IR が別物になる (LB ごとに指紋が違う) ことを確認した。REPORT_N403 の ir_sha256 (`1fc847d4…` / `b529a344…`) とは一致しない。

### 5.4 再現コマンド (実際に実行したもの)

共通: `export FL_WIN64_DIR=$RUNNER_TEMP` (`block00031_PE.bin` を含む `extracted/` の親)、`PE=$RUNNER_TEMP/extracted/block00031_PE.bin`、ツールは `tools/m11` で実行。

```sh
# IR 生成 (LB ごと。M11_LB_BASE を指定して実行)
M11_LB_BASE=0 bash m11_gen_ir2.sh          # → ir_sha256 2c68ceae…
M11_LB_BASE=0x10000 bash m11_gen_ir2.sh    # → ir_sha256 e14a943d…
# data / image (LB 依存。古いものを消してから作る)
rm -f work/m11_data.c work/m11_image.bin
python3 m11_data_gen.py "$PE"; python3 m11_image_gen.py "$PE"
# wasm (emsdk を PATH に載せた上で、/opt を置換した複製を実行)
bash work/m11_build_local.sh
# 測定
M11_LB_BASE=<LB> node m11_run.mjs          # M11_RESULT 行を集計
M11_LB_BASE=<LB> node m11_survey.mjs       # M11_SURVEY 行
bash m11_ptrcheck_negctl.sh                # NEGCTL 判定 (LB=0 の wasm を使う)
python3 lb_check.py "$PE" work/m11_image.bin 0x10000   # LB=0x10000 の image 静的検査 (PASS)
```

`M11_LB_BASE` は **wasm のビルド時に `-D` で焼き込まれる** (`m11_build.sh`・`m11_data_gen.py`・`m11_image_gen.py` が参照)。`m11_run.mjs` / `m11_survey.mjs` は実行時に読まないため、LB を変えるには IR→data→image→wasm を作り直す必要がある。

### 5.5 結果 (n=3・min–max。load average は各 run 直前の 1 分値)

| 条件 | 所要 (wall) | 結果 |
|---|---|---|
| `M11_LB_BASE=0` run | 0.67–0.69 s (n=3) | units_run 52・boot_stage 1・Halt0 0・threw `unreachable`・ptrcheck new 69,306 (n=3 一致) |
| `M11_LB_BASE=0` survey | 8.42–8.52 s (n=3) | ok 870 / noproc 1 / miss 47 / trap 24 (n=3 一致) |
| `M11_LB_BASE=0x10000` run | 0.42–0.43 s (n=3) | units_run 36・Halt0=1・boot_stage 1・threw なし・ptrcheck new 69,044 (n=3 一致) |
| `M11_LB_BASE=0x10000` survey | 7.97–8.04 s (n=3) | ok 868 / noproc 1 / miss 47 / trap 26 (n=3 一致) |
| ネガコン (`m11_ptrcheck_negctl.sh`, LB=0, 1 回) | 2.0 s | clean 69,306・injected 69,307・diff +1・NEGCTL OK |

load average は run で 0.16–0.70、survey で 0.62–0.88 (1 分値。並列 run は無し、単独実行)。

**#403 の記録との比較 (受入 4)**: 記録は LB=0 で 53/870/25、LB=0x10000 で 37/868/27 (`REPORT_N403.md` §2)。今回の再測定は LB=0 で 52/870/24、LB=0x10000 で 36/868/26。survey ok は一致するが、units_run と trap が各 1 ずつ違う。今回の IR 指紋は REPORT_N403 の指紋と一致せず、IR が別物であることを確認した。したがって受入 4 は未達のまま (差の原因は IR の指紋差と見られるが、REPORT_N403 側の指紋が未記録のため照合できない)。

**judge について**: `m11_judge.py` の判定は本 fix では再実行していない。以前の記述 (rc 0 だが reached_stage が一致しない) は、今回の再生成後の run では確認していない。根拠にはしない。

**ptrcheck の判定基準 (受入 1・2)**: clean 実行で 69,306 語が範囲内に残る (LB=0)・69,044 語 (LB=0x10000)。値だけでは未 remap と正当な整数を区別できないため、不合格ゲートは未実装のまま。

## 6. 受入条件の状態 (本 PR 時点)

| 受入 | 状態 |
|---|---|
| 1. 実行後 guest ポインタ検査 | 実装済み (PR #1209)。ゲート化は判定基準未確定のため未了 |
| 2. 不合格で非 0 終了 | 未達 (上記の基準未確定) |
| 3. ネガティブコントロール同梱 | 達成 (再測定 §5 で NEGCTL OK) |
| 4. LB=0 / 0x10000 の e2e 比較が #403 から変わらない | 未達 (§5.5: units_run・trap が記録と各 1 ずれ。IR 指紋が記録と不一致) |
| 5. REPORT_N403 に実測 | 未達 (受入 4 が未達のため、親 REPORT は書き換えず本ファイルに記録) |

## 7. 未解決 (起票先)

| 未解決 | 起票先 |
|---|---|
| ptrcheck の不合格判定基準 (受入 1・2) | 本 issue (#1004) で継続 |
| #403 記録 (53/870/25・37/868/27) と現 IR での再測定 (52/870/24・36/868/26) の差。IR 指紋の照合 | PM 起票を要求 (親 #403 の再現性) |
| `m11_judge.py` が既存出力を読んで rc 0 を返す可能性 | PM 起票を要求 |
| `m11_e2e.sh` が `lift_pe.sha256` 無しで全再生成に入り `functions_dll.csv` で落ちる | PM 起票を要求 (work-m11 の再生成手順) |
