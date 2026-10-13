# REPORT_N715 — #715: m11_e2e.sh の回帰ゲート化 (期待値の fail-closed・実測の所在)

## 1. 結論
- 期待値ファイル無し・期待値の非整数は非 0 で終了する (fail-closed, §3)。判定単体・分岐は本 run で実測した。
- e2e 本体 (lift → IR → build → 実行) の再現は **本 run では未達**。必要な入力 (`work-m11` と m2 の Ghidra CSV) が runner に無く、`m11_bounds.py` で fail-closed 停止した (§4)。
- 受入の測定値 (stage 4/6・ok 870 等) は PR 作成者の報告であり、本 REPORT では再現済みとは扱わない (§5)。

## 2. 検証環境・HEAD
| 項目 | 値 |
|---|---|
| 検証 HEAD (fail-closed 分岐・初回 e2e 試行) | `028ec002` (`715-m11-e2e-gate`。merge 元 `origin/main` = `87effc70`) |
| 検証 HEAD (現ヘッド確認・e2e 試行 2) | `30ba7fd3` (差分は REPORT_N715.md と DOC_MAP.md のみ。`dfeb2d26` から) |
| 期待値修正 commit | `885d6304` (fail-closed 化)・`028ec002` (main merge) |
| PR 作成者の測定 HEAD | `b5a4c90d` (レビュー時点の PR head) |
| 本 run の runner | 4 vCPU・15 GiB・load avg 0.9 (16:38 時点) |
| 素材 | `$ARTIFACTS_DIR` に `fl-win64.tar.zst` のみ (`work-m11`・`toolchain-*` は無し)。`fl-win64` は `tar --zstd -xf` で展開 (7.1 s)。展開先は `FL_WIN64_DIR` で指定 |
| RetDec / emsdk | 本 run では導入していない。`toolchain-retdec`・`toolchain-emsdk` の素材指定が必要 |
| python | capstone・pefile を `pip install --user` で導入 (本 run で import 確認 ok) |

## 3. fail-closed の分岐 (本 run で実測)
HEAD `028ec002` の `bash tools/m11/m11_e2e.sh` (期待値ファイル・環境変数を変えて実行) の結果:

| 条件 | 出力 | rc |
|---|---|---|
| `e2e_expect.env` 無し | `e2e_expect.env 無し: 回帰ゲートの期待値が読めない (fail-closed)` | 1 |
| `M11_EXPECT_SURVEY_OK=abc` | `M11_EXPECT_SURVEY_OK が整数でない: 'abc' (fail-closed)` | 1 |
| `M11_EXPECT_STAGE=` (空) | `source` で既定値 4 に戻り、前提確認へ進む (仕様どおり) | 1 (前提不足) |
| `m11_judge.py --require-stage 4 --min-survey-ok 800` (work 無し) | 判定失敗 | 1 |

`e2e_expect.env` は検証後に元どおり復元した。

現ヘッド `dfeb2d26` (`028ec002` からの差分は REPORT_N715.md と DOC_MAP.md のみ) で同じ 2 条件を再実行した:

| 条件 (HEAD `dfeb2d26`) | 出力 | rc |
|---|---|---|
| `e2e_expect.env` 無し | `e2e_expect.env 無し: 回帰ゲートの期待値が読めない (fail-closed)` | 1 |
| `M11_EXPECT_SURVEY_OK=abc` | `M11_EXPECT_SURVEY_OK が整数でない: 'abc' (fail-closed)` | 1 |

`e2e_expect.env` は再実行後に復元し、`git status` で差分が無いことを確認した。

## 4. e2e 再現の試行 (本 run)
- 試行 1 (HEAD `028ec002`): `m11_scan` は成功 (57,816 fn)。続く `m11_bounds.py` が `tools/m2/work/ghidra_dll/functions_dll.csv` を要求して失敗 → fail-closed で rc=1 (32.8 s)。
- 試行 2 (HEAD `30ba7fd3`・`FL_WIN64_DIR` 指定・capstone/pefile 導入済み): `m11_e2e.sh` が前提確認で停止 → rc=1 (0.06 s)。`emsdk 無し` (emsdk の素材が無い)。
- 結論: `work-m11` (lift 済み `work/boot*.lift.ll`・`work/boot_final.ll` 相当)・`m2/work/ghidra_dll/`・emsdk・RetDec が runner に無く、正 (rc=0) もネガコン (rc=1) も本 run では実行できない。
- 必要素材: `oc_artifacts: fl-win64 toolchain-emsdk toolchain-retdec work-m11`。取得後に `m11_e2e.sh` (`--full` 無し) で再実行し、HEAD・rc・所要を本節に追記する。
- 未検証: `m11_build.sh`・`m11_run.mjs`・`m11_survey.mjs`・`m11_judge.py` の e2e 経路での判定。

## 4-1. judge の引数仕様
- `M11_EXPECT_STAGE=0` (`--require-stage 0`) は usage で rc=2 になる。`--require-stage` の N は 1〜6 の仕様 (`m11_judge.py` の usage 行)。0 は期待値として不正で、fail-closed 側の挙動として許容する (本 run で rc=2 を確認)。

## 5. PR 作成者の報告値 (未再現・参考)
PR 作成者の run (HEAD `b5a4c90d`・RetDec を PATH に追加・load 0.5〜0.8) の報告:

| 実行 | 期待値 | 結果 | 所要 | rc |
|---|---|---|---|---|
| 正 (`m11_e2e.sh`) | stage≥4, ok≥800 | reached 4/6・survey ok 870 / trap 25 / oom 1 | 2m31s | 0 |
| ネガコン | ok≥900 | `SURVEY_OK_FAILED: survey ok=870 < required=900` | 45s | 1 |
| 判定単体 (既存 work/) | stage≥5 | `REQUIRE_STAGE_FAILED` | - | 1 |

注: 既存 `work-m11` の出力 (ok 812) とは `gen_ir2` 再生成で値が異なる (ok 870)。下限 800 は両方を通す。
PE パスの既定値フォールバック (`FL_WIN64_DIR` 未設定時に使われる) は次のとおり: `m11_bounds.py:14`・`m11_data_gen.py:15`・`m11_icall_audit.py:14`・`m11_scan.py:11`・`m11_tail.py:12`・`m11_image_gen.py:16`・`m11_reloc_gate.sh:9`、および `tools/shared/env.sh` 経由 (`m11_e2e.sh`・`m11_build.sh`・`qstore/qstore_e2e.sh`)。直書きの実行パスではなく既定値のみ。

## 6. 次の一手
- `oc_artifacts: fl-win64 work-m11` で再起動し、`m11_e2e.sh` を (`--full` 無し) 再実行して本節の表を実測値で置き換える。HEAD と rc を必ず併記する。
- `m11_bounds.py` 等の既定値フォールバック (§5 の一覧) を除去するかは別 issue で扱う (#351 系)。
