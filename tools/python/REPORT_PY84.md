# PY-84 (#2663): chord progression の pyscript 2 本と drum patterns を fl-win64 から抽出する

- 対象: `tools/python/analysis/extract_pyc_blocks.py` (抽出器) と `tools/python/run_all.sh` の step 15。
- 測定 commit: `a623fec6` (抽出器と step 15 を変えた最後のコード commit)。

## 1. 結論

fl-win64 の DATA block だけから、抽出器が `drum_patterns.json` と `pyscript/{cpt,stack}.pyscript` を出すようになった。`tests/chord_progression_e2e.mjs` は 3 回とも 41/41 PASS (exit 0)。step 15 の 2 行を単独で実行しても PASS。

**run_all 全体は未達**。先頭の mac pkg 前提チェックで rc=2 のまま止まる (§8)。これは #2649 (PY-83) の範囲で、本 run では触らない。e2e の入力は mock 条件つき (§9)。実 FL との照合は #81。

## 2. 既知類型との関係

`docs/DEFECTS.md` の該当 ID: **該当なし**。lift・逆アセ・IR pass ではなく、抽出スクリプトの出力経路の変更。

## 3. 受入条件

| 条件 | 結果 | 根拠 |
|---|---|---|
| (1) run_all の step 15 が fl-win64 だけで SKIP されず動く | **run_all 全体は未達** (前提チェックで rc=2)。step 15 の 2 行は単独で実行して PASS | §6 (step 15 単独)、§8 |
| (2) `chord_progression_e2e.mjs` が PASS | 達成: 41/41 PASS × 3 回 | §6 |
| (3) drum_patterns.json と pyscript の同定経路を書く | 達成 | §4.2 |
| (4) 所要・load average・PASS/FAIL を書く | 達成 | §6 |

## 4. 入力・同定経路・出力の一致

### 4.1 入力

| 素材 | 扱い |
|---|---|
| fl-win64 (`$ARTIFACTS_DIR/fl-win64.tar.zst`) | `$RUNNER_TEMP/fl-win64/extracted/` に展開済み (`FL_WIN64_DIR` = `$RUNNER_TEMP/fl-win64`)。DATA block は 20310 件 |
| toolchain-emsdk | `tar --zstd -xf` で `$RUNNER_TEMP/emsdk/` (`EMSDK_DIR`)。flpy.js のビルドに必要。e2e の入力そのものではない |
| retdec | 未使用 |
| fl-stubs | `fetch_inputs.sh` が GitHub から clone (HEAD `9b4c7fa`)。成功 |

fl-win64 の 3 block の sha256:

```
1dd818c3ecb1200c851d70bec7b7807c8c2ff927cc6c9fdca50e5948c557f0ef  block24797_DATA.bin (drum_patterns.json)
1e5da4bce851f794d3acd98c78f7142827662d859021f7e706d31d1c7165f4e5  block24772_DATA.bin (cpt.pyscript)
c333d1b327b5cb139e749d9c1c3be329290a7a3e0c85b229443af54dcdee344a  block24775_DATA.bin (stack.pyscript)
```

### 4.2 同定経路

magic `cb0d0d0a` の pyc block (40 件) は従来どおり pyc として扱う。残りの非 pyc block 20270 件に 3 規則を適用する。

| block | bytes | sha256 (先頭 8) | 出力 file | 規則 | 当たった件数 |
|---|---|---|---|---|---|
| block24772_DATA.bin | 63 | 1e5da4bc | `pyscript/cpt.pyscript` | 先頭が `"""\r?\nCPT comms script;…"""\r?\nfrom control import \*` | 1 |
| block24775_DATA.bin | 105 | c333d1b3 | `pyscript/stack.pyscript` | 先頭が `"""\r?\nStack / Generator comms script;…"""\r?\nfrom control_rack import \*` | 1 |
| block24797_DATA.bin | 191356 | 1dd818c3 | `drum_patterns.json` | `{` 始まりの UTF-8 JSON で、dict が `compatible_from` と `genres` を持つ | 1 |

- 各規則がちょうど 1 block に当たったときだけ書く。0 件・2 件以上は stderr に理由を出し exit 3。何も書かない (§6 (b) で確認)。
- 旧規則 `ScriptDialog\(|def createDialog` は どの block にも当たらず未使用だったため削除した。
- 既存の text 候補 (`manifest.json` の `text`、18 件) の抽出条件は変えていない。

### 4.3 出力の一致

| 比較 | 結果 |
|---|---|
| `cmp work/fl_extract/drum_patterns.json` と block24797 | SAME_drum |
| `cmp work/fl_extract/pyscript/cpt.pyscript` と block24772 | SAME_cpt |
| `cmp work/fl_extract/pyscript/stack.pyscript` と block24775 | SAME_stack |
| 独立検算 (`json.load` で keys と genres 数): 出力 file と block24797 の直接読み | 同一。keys 29 件 (`compatible_from`・`genres` を含む)、`len(genres)` = 17 |

`manifest.json`: `pyc` 40、`text` 18、`skipped` 0、`pyscript` = [cpt 63 B, stack 105 B]、`drum_patterns` = 191356 B。

## 5. 抽出器の変更点

- 同定を 2 段にした。第 1 段で全 block を分類し、件数を検証する。第 2 段で書き出す。検証に失敗したら何も書かない。
- 出力: `<out>/pyscript/{cpt,stack}.pyscript`・`<out>/drum_patterns.json` (いずれもバイト列をそのまま書く)・`manifest.json` の `pyscript` と `drum_patterns` キー。`pyc`・`text`・`skipped` は変えていない。
- 要約 JSON に `pyscript` と `drum_patterns` の件数を追加。
- `FL_WIN64_DIR` は `extracted/` を指す契約のまま。
- `run_all.sh` step 15 は、抽出を毎回実行し (古い出力の再利用をやめた)、`$PY312` と `FL_WIN64_DIR/extracted` を使う。

## 6. 実測

測定 commit `a623fec6`。手順の時刻は UTC。

| 工程 | 回 | wall | load avg (1 分, 開始時 uptime) | 結果 |
|---|---|---|---|---|
| `build_cpython_wasm.sh` (timeout 900) | 1 | 4 分 12 秒 | — | rc=0 |
| `FLPY_SKIP_TABLE=1 build_flpy.sh` (timeout 300) | 1 | 23.5 秒 | — | rc=0 |
| 抽出器 (PY312、出力 dir 削除後) | 1 | 4.35 秒 | 2.50 (16:52:09) | rc=0 |
| `chord_progression_e2e.mjs` | 1 | 0.575 秒 | 2.28 (16:52:17) | 41 PASS / 0 FAIL、rc=0 |
| `chord_progression_e2e.mjs` | 2 | 0.57 秒 | 2.10 (16:52:23) | 41 PASS / 0 FAIL、rc=0 |
| `chord_progression_e2e.mjs` | 3 | 0.56 秒 | 2.10 (16:52:23) | 41 PASS / 0 FAIL、rc=0 |

- load average: e2e の 3 回で 1 分平均は 2.10–2.28 (nproc = 4)。
- e2e の末尾 JSON は 3 回とも `{"total":41,"pass":41,"fail":0,"mock":true,"sec":"0.5"}`。
- step 15 の 2 行を単独実行 (`PY312` と `FL_WIN64_DIR` は run_all と同じ値。`set -euo pipefail` 下): wall 4.9 秒、rc=0。抽出の出力 `{"pyc": 40, "text_candidates": 18, "skipped": 0, "pyscript": 2, "drum_patterns": 1}`、e2e の出力 `{"total":41,"pass":41,"fail":0,"mock":true,"sec":"0.5"}`。
- 測定後の差分: `git diff a623fec6 HEAD -- tools/python/analysis tools/python/run_all.sh` は空 (REPORT と DOC_MAP の commit だけが HEAD 側に増える)。

## 7. 検証範囲

- 範囲内: fl-win64 から抽出器が出す 3 ファイルと、それを入力にした e2e。
- 範囲外: run_all 全体 (#2649)、実機 FL との照合 (#81)、`flcpt`/`flrack` の関数実装 (#1327)。
- `FLPY_SKIP_TABLE=1` で `build_flpy.sh` の flapi 表の再生成を省き、追跡済みの `flapi_table.json` を使った。表は更新されていない。
- toolchain-emsdk は flpy.js のビルドに必要 (`build_flpy.sh` が `EMSDK_DIR` を要求する)。e2e の入力そのものではない。
- e2e の PASS は「取り出した pyc / pyscript / json が import・exec できる」ことの確認。値の正しさは示さない (§9)。

## 8. run_all 全体の前提チェック

`bash run_all.sh` (HEAD `a623fec6`、`FL_MAC_DIR` は既定値 = `env.sh` の値のまま): rc=2。`ERROR: 前提不足で停止: …FLEngine_x64.dylib が無い`。step 1 より前で止まり、何も生成しない。mac pkg の `pkg_extract` が無いため。#2649 の範囲なので直していない。

## 9. e2e の mock 条件

`tests/chord_progression_e2e.mjs` の mock (根拠なし。FL 実機の値ではない):

| 対象 | mock 値 |
|---|---|
| `flrack.rack.loop_starter_config` | 同梱 drum patterns の `genres` を流用した dict。`mock: true` 付き |
| `flpianoroll.score.PPQ` | 96 |
| `Notes/pattern_presets.cpt` | 空ファイル |
| `flcpt` / `flrack` の属性 | import 時に参照される名前だけのダミー型 |

実 FL の値との照合は #81 (PY-9)。

## 10. 再現コマンド

作業 dir は `tools/python` (worktree `ws-2663` の中)。

```bash
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64" EMSDK_DIR="$RUNNER_TEMP/emsdk"
mkdir -p "$RUNNER_TEMP" && tar --zstd -xf "$ARTIFACTS_DIR/toolchain-emsdk.tar.zst" -C "$RUNNER_TEMP"
bash fetch_inputs.sh
timeout 900 bash build_cpython_wasm.sh | tail -4
FLPY_SKIP_TABLE=1 timeout 300 bash build_flpy.sh | tail -4
PY312=work/build-native/install/bin/python3.12
FL_WIN64_DIR="$FL_WIN64_DIR/extracted" "$PY312" analysis/extract_pyc_blocks.py work/fl_extract | tail -1
node tests/chord_progression_e2e.mjs | tail -1
node tests/chord_progression_e2e.mjs --neg; echo rc=$?
cmp work/fl_extract/drum_patterns.json "$FL_WIN64_DIR/extracted/block24797_DATA.bin" && echo SAME_drum
```

## 11. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| run_all 全体の mac 前提チェック (`FL_MAC_DIR` の `pkg_extract` 不在で rc=2) | run_all 全体が通らない。step 1 以降は未検証 | #2649 (PY-83) |
| mock 値 (`loop_starter_config` の genres 流用・PPQ 96・`pattern_presets.cpt` 空) の実 FL 照合 | e2e の PASS は import・exec 可否の確認まで | #81 (PY-9) |
| `flcpt` / `flrack` の関数実装 | e2e は属性のダミーで動かしている | #1327 |
| `REPORT_PY7.md` の抽出手順と `tests/chord_progression_e2e.mjs` 冒頭コメントの旧コマンド (`python3 analysis/extract_pyc_blocks.py work/fl_extract`) | 現行の CLI (`FL_WIN64_DIR`・`PY312`) と食い違う | 未起票 (PM 判断) |
| `REPORT_PY22.md` の「pyscript 2 本は手動配置」 | 本 run の抽出器で自動取得できるようになった | 未起票 (PM 判断) |
