# PY-84 (#2663): chord progression の pyscript 2 本と drum patterns を fl-win64 から抽出する

- 対象: `tools/python/analysis/extract_pyc_blocks.py` (抽出器) と `tools/python/run_all.sh` の step 15。
- 測定 commit: `0537b23e` (コードを変えた最後の commit。`tests/chord_progression_e2e.mjs` の冒頭コメント 2 行の変更で、実行される文は変えていない)。抽出器と step 15 の最後の変更は `0b6417df`。run_all 全体 (§8) は `41d9c3b9` で測定した (その後の commit は docs のみ)。

## 1. 結論

fl-win64 の DATA block だけから、抽出器が `drum_patterns.json` と `pyscript/{cpt,stack}.pyscript` を出すようになった。`tests/chord_progression_e2e.mjs` は 3 回とも 41/41 PASS (exit 0)。step 15 の 2 行を単独で実行しても PASS。

**run_all 全体が fl-win64 と toolchain-emsdk だけで rc=0** (最終行 `== ALL OK`、測定 commit `41d9c3b9`、§8)。step 15 は SKIP されず実行される。mac pkg を読む step (3b・4 の mac 版・7) は既存の SKIP 分岐 (#2649) に入り、追跡済みの出力を使った。e2e の入力は mock 条件つき (§9)。実 FL との照合は #81。

## 2. 既知類型との関係

`docs/DEFECTS.md` の該当 ID: **該当なし**。lift・逆アセ・IR pass ではなく、抽出スクリプトの出力経路の変更。

## 3. 受入条件

| 条件 | 結果 | 根拠 |
|---|---|---|
| (1) fl-win64 だけで `run_all.sh` が rc=0 になり、step 15 が SKIP されず通る | **達成**: run_all 全体 rc=0 (`== ALL OK`、§8)。step 15 は SKIP ガードなしで実行。素材は fl-win64 と toolchain-emsdk (後者は flpy のビルド道具で FL の素材ではない) | §8、§6 (step 15 の抽出・e2e) |
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

- 各規則がちょうど 1 block に当たったときだけ書く。0 件・2 件以上は stderr に理由を出し exit 3。何も書かない (§6.1 の抽出器 NC で確認)。
- 旧版 (`a623fec6^`) の `PYSCRIPT_RULES["cpt"]` `ScriptDialog\(|def createDialog` は、非 pyc の **106 block** に当たる (`re.search` で再現)。例: `block07944_DATA.bin` は ARPEGGIATOR の VFX スクリプトの `def createDialog():`。汎用の dialog 定義を含むため同定に使えない。旧版では定義されるだけで参照されていなかったので削除した。
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
- 要約 JSON に `pyscript` と `drum_patterns` を追加。`drum_patterns` は manifest にあれば 1、無ければ 0 で、件数ではなく存在判定。成功時は規則がちょうど 1 block (0 件・2 件以上は exit 3 で何も書かない) なので、成功した run では常に 1。
- `FL_WIN64_DIR` は `extracted/` を指す契約のまま。
- `run_all.sh` step 15 は、実行前に `work/fl_extract` を `rm -rf` してから抽出する (古い出力の残骸を残さない。§6 で確認)。`$PY312` と `FL_WIN64_DIR/extracted` を使う。

## 6. 実測

測定 commit `0537b23e` (コードを変えた最後の commit)。ビルドは `work/build-native`・`work/build-wasm` を消してから作り直した。時刻は runner の時計 (`uptime`・`date`)。

| 工程 | 回 | wall | load avg (1 分, 開始時) | 結果 |
|---|---|---|---|---|
| `build_cpython_wasm.sh` (timeout 900、build-native・build-wasm 削除後) | 1 | 164 秒 | 0.71 (17:40:59) | rc=0 |
| `FLPY_SKIP_TABLE=1 build_flpy.sh` (timeout 300) | 1 | 4 秒 | 2.01 (17:43:50) | rc=0 |
| step 15 の抽出 (`rm -rf work/fl_extract` の後、PY312) | 1 | 3.403 秒 | 2.42 (17:38:33) | rc=0 |
| step 15 の抽出 (同上) | 2 | 4 秒 | 2.01 (17:43:50) | rc=0 |
| `chord_progression_e2e.mjs` | 1 | 0.381 秒 | 1.71 (17:44:02) | 41 PASS / 0 FAIL、rc=0 |
| `chord_progression_e2e.mjs` | 2 | 0.403 秒 | 1.71 | 41 PASS / 0 FAIL、rc=0 |
| `chord_progression_e2e.mjs` | 3 | 0.380 秒 | 1.71 | 41 PASS / 0 FAIL、rc=0 |
| step 15 の 2 行 (`set -euo pipefail` 下、抽出 + e2e) を main 取り込み後の `ad343fd4` で再実行 | 1 | 3.925 秒 | 0.20 (17:46:25) | rc=0、SAME 3 件、41 PASS / 0 FAIL |

- load average: e2e の 3 回は 1 分平均 1.71 (nproc = 4)。
- e2e の末尾 JSON は `0537b23e` の 3 回と `ad343fd4` の 3 回 (378 / 439 / 387 ms) のすべてで `"total":41,"pass":41,"fail":0`。
- step 15 の抽出 (`PY312` と `FL_WIN64_DIR` は run_all と同じ値): rc=0、出力 `{"pyc": 40, "text_candidates": 18, "skipped": 0, "pyscript": 2, "drum_patterns": 1}`。`cmp` で SAME_drum・SAME_cpt・SAME_stack (§4.3 と同じ)。
- 残骸の確認 (`0b6417df` で実施。以後 step 15 の `rm -rf` の行は変えていない): 抽出前に `work/fl_extract/stale/old_test.pyc` を置いてから step 15 (`rm -rf` + 抽出) を実行 → 残骸は消えていた (`stale_exists=no`)。
- main の取り込み (`ad343fd4`、main `69b1bc82` との merge): 競合は `tools/python/run_all.sh` の step 15 だけ。main 側の SKIP ガード (`[ -s … ] || SKIP`) は外し、PR 側の 2 行 (`rm -rf` + `$PY312` の抽出、続けて e2e) にした。抽出器は 3 ファイルを書き、`set -euo pipefail` により失敗時は run_all が止まる。SKIP で通さないため、受入条件 (1) に合う。
- 測定対象の差分: `git diff 0537b23e HEAD -- tools/python/analysis/extract_pyc_blocks.py tools/python/build_cpython_wasm.sh tools/python/build_flpy.sh tools/python/fetch_inputs.sh tools/python/host tools/python/src tools/python/tests/chord_progression_e2e.mjs | wc -l` の出力は `0`。main 側で増えたファイル (`analysis/py71_*`・`tests/static_browser_check.mjs` 等) は測定対象の外。
- 0b6417df から 0537b23e までの差分 (`git diff 0b6417df 0537b23e -- tools/python ':!tools/python/REPORT_PY84.md'`): REPORT_PY22.md (1 行)・REPORT_PY7.md (手順 2 行)・`tests/chord_progression_e2e.mjs` の冒頭コメント 2 行。実行される文は変わっていない。

### 6.1 ネガティブコントロール (測定 commit `0537b23e`)

| 対象 | 操作 | 結果 |
|---|---|---|
| e2e | `node tests/chord_progression_e2e.mjs --neg` (`Chords/data.pyc` の先頭 1 バイトを反転) | `{"total":41,"pass":34,"fail":7}`、FAIL 7 件、rc=1。内訳: `Chords/data.pyc` 自身 1 件、それを import する `control.pyc`・`control_rack.pyc`・`util.pyc`・`util_rack.pyc` の 4 件、pyscript の `cpt.pyscript`・`stack.pyscript` の 2 件 (いずれも `ImportError: bad magic number in 'Chords.data'`) |
| 抽出器 | `extracted/` の全 25166 entry から `block24797_DATA.bin` だけを除いた symlink dir (25165 件・`$RUNNER_TEMP/nc84b/src`) を `FL_WIN64_DIR` に指定して抽出 | stderr は `ERROR: drum_patterns: 0 block () が一致 (期待 1)` の 1 行だけ (pyscript 2 規則はエラーにならなかった)、rc=3、`work/nc84_out` は作られない |

## 7. 検証範囲

- 範囲内: fl-win64 から抽出器が出す 3 ファイルと、それを入力にした e2e。
- 範囲外: mac pkg を読む step の実測 (CI に mac pkg の素材が無いため、3b・4 の mac 版・7 は SKIP。#2649 の SKIP 分岐)、実機 FL との照合 (#81)、`flcpt`/`flrack` の関数実装 (#1327)。
- `FLPY_SKIP_TABLE=1` で `build_flpy.sh` の flapi 表の再生成を省き、追跡済みの `flapi_table.json` を使った。表は更新されていない。
- toolchain-emsdk は flpy.js のビルドに必要 (`build_flpy.sh` が `EMSDK_DIR` を要求する)。e2e の入力そのものではない。
- e2e の PASS は「取り出した pyc / pyscript / json が import・exec できる」ことの確認。値の正しさは示さない (§9)。

## 8. run_all 全体 (測定 commit `41d9c3b9`)

- 測定 commit: `41d9c3b9`。`ad343fd4` 以降の差分は docs だけ (末尾の差分確認)。worktree `ws-2686` を新規作成 (`work/` 無し) し、root で `pnpm install --frozen-lockfile` (rc=0) を済ませてから実行した。
- 素材: `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR`、`extracted/` 25166 件)、`$RUNNER_TEMP/emsdk` (`EMSDK_DIR`、toolchain-emsdk。flpy のビルド道具で FL の素材ではない)。`FL_MAC_DIR=$RUNNER_TEMP/no-such-mac` (存在しないパス) で mac pkg を無しにした。
- コマンド: `timeout 1200 bash tools/python/run_all.sh` (ログは step の見出しごとに時刻と load を付けて記録)。

**結果: rc=0、最終行 `== ALL OK`。** 18:13:07 から 18:19:47 まで (合計 6 分 40 秒)。開始時の load avg は 1 分 0.95・5 分 0.58 (nproc = 4)。実行後の `git status --short` は空 (追跡ファイルは変わらなかった)。

| step | 開始 | 所要 | load 1 分 (開始時) | 結果 |
|---|---|---|---|---|
| 1 inputs (`fetch_inputs.sh`) | 18:13:07 | 1 秒未満 | 0.95 | rc=0 |
| 2 CPython 3.12.1 wasm (`build_cpython_wasm.sh`、native・wasm を新規ビルド) | 18:13:07 | 241 秒 | 0.95 | rc=0 |
| 3・3b・4 (MCPTools 解析・65 本の import・flapi 抽出) | 18:17:08 | 2 秒 | 3.06 | 3b と 4 の mac 版は **SKIP** |
| 5 flpy link (`build_flpy.sh`、flapi 表の再生成を含む) | 18:17:10 | 23 秒 | 2.89 | rc=0 |
| 6・7 (smoke・builtin 一覧) | 18:17:33 | 1 秒未満 | 3.07 | 7 の `python_inventory` は **SKIP** |
| 8・8b・9・9b (PoC・kwsig・48 tools・C provider 版) | 18:17:33 | 7 秒 | 3.07 → 2.91 | 48/48 ok (kwsig: misbind 0) |
| 9c PY-2 (`pybind_extract`・`build_flpy_static`・`static_check`) | 18:17:40 | 6 秒 | 2.75 | STATIC CHECK OK |
| 9c ilmcp・pyscript・flpianoroll (9c・9c') | 18:17:46 | 4 秒 | 3.01 → 2.93 | ilmcp 25/25、pyscript 72/72、flpianoroll 11/11 (members 64/64) |
| 9d pyscript を Chrome で実行 (`tools/e2e` の `npm ci` を含む) | 18:17:50 | 18 秒 | 2.93 | 72 checks PASS |
| 10・10b・11・12 (Chrome・static 比較・MCP UI・MIDI) | 18:18:08 | 9 秒 | 3.06 → 3.12 | BROWSER OK・STATIC BROWSER OK・MCP UI OK・MIDI SCRIPT OK (29 checks、failed 0)・MIDI BUNDLED OK |
| 13 サブインタプリタ (probe・NEG・旧 flpy.c のネガコン) | 18:18:17 | 82 秒 | 3.12 → 2.07 | SUBINTERP OK (19 checks)・NEG DETECTED・旧版のネガコン DETECTED |
| 14 MIDI UI (Chrome) | 18:19:39 | 3 秒 | 2.07 | MIDI UI OK |
| 15 chord progression (抽出 + e2e) | 18:19:42 | 5 秒 | 2.38 | 抽出 rc=0、e2e 41/41 PASS |
| `== ALL OK` | 18:19:47 | — | 2.35 | rc=0 |

- SKIP は 3 件で、いずれも `MAC_PKG=0` の分岐 (#2649): 3b (`analysis/scripts_inventory.json`)、4 の mac 版 (`analysis/flapi/raw_mac_{x86_64,arm64}.json`)、7 (`analysis/python_inventory.json`)。追跡済みの出力を使った。win64 側 (`raw_win64.json`・`flapi_table`) は実行した。
- step 5 は `FLPY_SKIP_TABLE` を使わず、flapi 表の再生成を含めて実行した。再生成の結果は追跡ファイルと一致した (`git status` 空)。
- 9d の `npm warn EBADENGINE`: `agent-browser@0.39.0` は node >= 24 を要求し、実行環境は node v22.23.3。警告のみで、step 9d は PASS した。
- 取り込み前の `0537b23e` の run_all は、step 1 より前の mac pkg 前提チェックで rc=2 だった (`FLEngine_x64.dylib` が無い)。その後 #2649 で SKIP 分岐が入り、上の結果になった。

差分確認 (測定 commit から現 HEAD まで): `git diff 41d9c3b9 HEAD -- tools/python ':!tools/python/REPORT_PY84.md' | wc -l` の出力は `0`。

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
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
mkdir -p "$RUNNER_TEMP" && tar --zstd -xf "$ARTIFACTS_DIR/toolchain-emsdk.tar.zst" -C "$RUNNER_TEMP"
bash fetch_inputs.sh
timeout 900 bash build_cpython_wasm.sh | tail -4
FLPY_SKIP_TABLE=1 timeout 300 bash build_flpy.sh | tail -4
PY312=work/build-native/install/bin/python3.12
rm -rf work/fl_extract; FL_WIN64_DIR="$FL_WIN64_DIR/extracted" "$PY312" analysis/extract_pyc_blocks.py work/fl_extract | tail -1
node tests/chord_progression_e2e.mjs | tail -1
node tests/chord_progression_e2e.mjs --neg; echo rc=$?
cmp work/fl_extract/drum_patterns.json "$FL_WIN64_DIR/extracted/block24797_DATA.bin" && echo SAME_drum
```

## 11. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| mock 値 (`loop_starter_config` の genres 流用・PPQ 96・`pattern_presets.cpt` 空) の実 FL 照合 | e2e の PASS は import・exec 可否の確認まで | #81 (PY-9) |
| `flcpt` / `flrack` の関数実装 | e2e は属性のダミーで動かしている | #1327 |
