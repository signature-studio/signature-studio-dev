# liftdiff — flelift closure 再採点 (LD-26 / #978) 実測

親: [`REPORT.md`](REPORT.md) §1 の flelift 行 / 付録 [`REPORT_APPENDIX.md`](REPORT_APPENDIX.md) §13 (前回の参考値・未確定)。

測定 commit: `2ca85816` (origin/main 時点・コード変更なし)。実行環境: GitHub Actions runner 4 vCPU・開始時 load 約 1.6 (batch 中は 12〜14)。素材: fl-win64・work-m11・work-liftdiff (展開先は `tools/m11/work/`・`tools/liftdiff/work/`)。

## 1. 工程の実測 (単一 run・推定なし)

| 工程 | コマンド | 結果 |
|---|---|---|
| lift 再生成 | `bash tools/flelift/fle_lift.sh` | rc 0・**73 s** (lift 38 s・emcc 35 s) |
| build | `python3 liftdiff.py build targets/flelift.json` | rc 0・**31 s**・`sig_mismatch 0`・`undefined 0` |
| 起動 | `bootstate --mode hybrid --nobuild` | rc 0・**16 s**・`units_run 928/942`・`first_fail 830` |
| 全数採点 | `batch targets/flelift.json --set closure --shards 14 --state auto` | rc 0・**894 s** (batch 表示 891 s・`real 14m54s`) |
| e2e | `FL_WIN64_DIR=... bash tools/liftdiff/liftdiff_e2e.sh --m11-only` | rc 0・**3m13.7 s**・`LIFTDIFF_E2E PASS` |

## 2. 全数採点の結果 (7,421 関数・単一 JSONL)

出力: `tools/liftdiff/work/flelift/batch_closure_full.jsonl` (7,421 行・gitignore の生成物)。

- 一致 **4,217** / 不一致 **807** / 実行不能 **2,397** (合計 7,421)
- 不一致の主因: unlifted_callee 418・callee_divergence 120・zero_init_drop 117・callsite_arg_drop 82・ret_only 23・memory_semantics 15・wasm_trap 12・arg_drop 11・xmm_arg_drop 8・simd_int_semantics 1
- 実行不能の内訳: native_fault_all_patterns 1,036・native_null_deref_all_patterns 698・no_wasm_definition 402・hang 211・unsupported_sig 50

## 3. 前回値との比較 (参考)

前回 (REPORT_APPENDIX §13・1795f8ff tree) の参考値 4,280 / 805 / 2,336 とは一致しない (差 −63 / +2 / +61)。前回は前半 5,600 件を 1,500 s の timeout で打ち切り、後半を別 run で流した結果の合算で、一意数が未検証だった。今回は 7,421 件を一本で完走したため、この値が本 commit の全数値である。前回値との差は測定 tree の違い (1795f8ff と 2ca85816 の間の liftlib / ldlib 変更) による可能性があるが、未切り分け。

## 4. 未達・残件

- 前回 run で報告された `session.py:179` の `patterns.index` ValueError は、commit `ae802a4c` (`fix(liftdiff): skip refine for fvm pattern`) で修正済みのため、本 run では発生せず。
- `liftdiff_e2e.sh` の既定フラグ (`--m11-only` 無し) は [2/4] で `targets/ott_old.json` の PE `${PLUGINS_DIR}/ott/binaries/OTT_vst2_win64.dll` を読む。この PE は `analysis-ott-binaries` (`$HOME/analysis/plugins/ott/binaries/`) にあり、本 run では `$ARTIFACTS_DIR` にも `$HOME/analysis` にも無く、ファイル検索 (`find /`) でも見つからなかった (`work-m6-ott` は展開済みで `tools/ott/work/ott.ll` は存在)。既定 e2e の不足は `analysis-ott-binaries`。受入条件の既定フラグ PASS は未実測。起票先: 本 issue #978 (`oc_artifacts` に `analysis-ott-binaries` を追加した run で再実行)。
