# python REPORT §7g の付録 (#2649)

REPORT_PY2.md §7g の全文 (250 行上限のため分割移動)。結論と測定 commit は REPORT_PY2.md §7g。

## 7g. run_all.sh を fl-win64 + toolchain-emsdk だけで rc=0 にする (#2649)

既知類型との関係: 該当なし (lift / 逆アセの欠陥類型ではない。素材の有無による前提分岐と step の skip)。

- 測定 commit: `2bb9811d` (コードを変えた最後の commit は `9784323b` の `run_all.sh`。`2bb9811d` は run が再生成した MCP 分類 2 件のみ)。
- 差分 0 の証跡: `git diff 2bb9811d HEAD -- tools/python ':!tools/python/REPORT_PY2.md'` の出力は 0 行 (本節のコミットは REPORT_PY2.md だけを変える)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf`、5.6 秒)、`FL_WIN64_DIR` に設定。`toolchain-emsdk` は agent-setup が [EMSDK] に展開済み (版 6.0.12 を `emscripten-version.txt` で確認)。`analysis-mac-shared` は展開しない。mac 無しを再現するため `FL_MAC_DIR=$RUNNER_TEMP/no-mac-pkg` (存在しないパス) を設定し、`ANALYSIS_DIR` の既定値 (tools/shared/env.sh) の先が無いことも確認。
- 実行: `cd tools/python && bash run_all.sh` (foreground、`timeout 1500`)。rc=0、最終行 `== ALL OK`。

### 変更点 (`tools/python/run_all.sh`)

| 変更 | 理由 |
|---|---|
| 前提チェックを `FL_WIN` (`block00031_PE.bin`) だけにした | mac pkg の欠如で rc=2 にしない |
| `MAC_PKG` = `FLEngine_x64.dylib` と mac 版 `MCPTools.pyc` の両方があるときだけ mac 依存 step を実行 | pkg の有無で分岐する |
| step 3b・4 の mac 版 (`raw_mac_{x86_64,arm64}.json`)・7 を `MAC_PKG=0` で `SKIP:` と出して追跡済み出力を使う | issue #2649 の受入条件 (明示 skip) |
| step 15 は `drum_patterns.json` と `pyscript/{cpt,stack}.pyscript` が無いとき `SKIP:` (#2663) | `extract_pyc_blocks.py` がそれらを出力しない (下の未解決) |
| step 15 の抽出呼び出しで `FL_WIN64_DIR` を `$FL_WIN64_DIR/extracted` に向けた | extractor の契約 (ヘッダ: `FL_WIN64_DIR=<展開先>/extracted`) どおり。直さないと 0 件抽出になる |

### step 別の所要と結果 (HEAD `2bb9811d`、タイムスタンプ付き再実行、1 秒単位)

work/ が残っていたため step 2 は incremental。初回 (work/ 無し) の step 2 は run 1 の実測 253 秒 (同じ `build_cpython_wasm.sh`)。

| step | 秒 | 結果 |
|---|---|---|
| 1 inputs (fetch_inputs.sh。win64 DATA block から配置) | 0 | PASS |
| 2 CPython 3.12.1 wasm (incremental) | 1 | PASS |
| 3 MCPTools.pyc 解析 | 0 | PASS (tools: 48) |
| 3b scripts_inventory | 0 | **SKIP** (mac pkg 依存。追跡済み `analysis/scripts_inventory.json` を使用) |
| 4 flapi 抽出 (win) + flapi_table | 1 | PASS。mac 版 2 本は **SKIP** (追跡済み `raw_mac_*.json`)。`flapi_table.py` は `midi_script_callbacks_in_binary` を既存値で引き継ぐ WARN 経路 |
| 5 flpy link | 7 | PASS |
| 6 smoke | 1 | PASS |
| 7 builtin 一覧 / py_inventory | 0 | dump_builtins PASS。py_inventory は **SKIP** (追跡済み `analysis/python_inventory.json`) |
| 8 PoC (MCPTools.pyc on wasm + flapi mock) | 1 | POC OK |
| 8b kwsig_bind_check | 0 | PASS |
| 9 48 tools 全実行 | 2 | PASS |
| 9b C provider 版 48 tools | 4 | PASS |
| 9c PY-2 静的リンク (pybind / static_check) | 6 | PYBIND CHECK OK、STATIC CHECK OK (48/48、host_calls 37,425) |
| 9c ilmcp 9 関数 e2e | 1 | PASS |
| 9c .pyscript ローダ + flpianoroll 回帰 | 3 | PASS |
| 9c' flpianoroll 64 メンバ | 0 | 11/11、64/64 |
| 9d 同梱 Piano roll 5 本 (Chrome) | 8 | 72/72、outputs_mismatch 0 |
| 10 headless Chrome (Worker + SAB) | 1 | BROWSER OK (tools 48) |
| 11 MCP UI / devtools | 2 | MCP UI OK |
| 12 MIDI scripting (合成 fixture + 同梱 device) | 2 | MIDI SCRIPT OK、MIDI BUNDLED OK (checks 9/9) |
| 13 サブインタプリタ | 85 | SUBINTERP OK (checks 19/19) |
| 14 MIDI UI | 3 | MIDI UI OK |
| 15 Chord progression | 0 | **SKIP** (#2663) |
| 合計 (incremental) | 128 | rc=0、`ALL OK` |

- load average (1 分値): incremental 再実行 開始 1.37 → 終了 1.44 (`uptime`)。
- 初回 (work/ 無し) の全体: 362 秒、rc=0、`ALL OK`。load 0.17 → 1.62。この run の step 別内訳は取っていない (タイムスタンプ無し)。
- 負のコントロール (ログ上の `FAIL` 行は全てこれ。本体は PASS): step 12 `midi_script.mjs --neg` → `NEG-CONTROL DETECTED` (27 callback 中 OnDirtyChannel が欠落、検出)。step 13 `subinterp_probe.mjs --neg` → `NEG-CONTROL DETECTED` (拒否 builtin 4/66 の期待違反を検出)。`subinterp_negcontrol_old.sh` → `NEG-CONTROL(old flpy.c) DETECTED`。`pyscript_compare.py --neg` は `NEG が不一致を検出しなかった` が出なければ rc=1 で正常。

### 生成物の再生成差分 (`2bb9811d` の 2 件)

step 9c の `mcp_classify.py` が、追跡済みの 2 件を再生成すると変えた。`mcp_classify.py` は `FL_MAC_DIR`・`FL_WIN64_DIR` を読まないため (grep で確認)、素材の有無による差ではない。

- `analysis/mcp/mcp_classification.json`: `plugins.getParamValueString/4` を追加 (`mcp_tools.json` の現行内容どおり。追跡版が古かった)。
- `analysis/mcp/MCP_TOOLS.md`: 先頭の手書きの見出し (`# 自動生成: ...` と「人手編集禁止」の行) が消えた。生成元 `mcp_classify.py` は見出しを出さない。内容差は見出しと空行のみ。

### 検証範囲 / 範囲外

- 範囲: `run_all.sh` の 15 step を fl-win64 + toolchain-emsdk だけで実行。mac 版の step (3b・4 の mac 版・7) は SKIP で追跡済み出力を使い、step 15 は SKIP。
- 範囲外: mac pkg がある環境での `run_all.sh` (SKIP した 4 件の mac 側実行) は未実行。`analysis-mac-shared` を入れた run も未実行 (issue の受入条件は win64 のみ)。`docs/REFERENCES.md` の素材原本の扱いは変えていない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| step 15 (Chord progression 41 本) が素材だけでは検証できない。`extract_pyc_blocks.py` が `drum_patterns.json` と `pyscript/{cpt,stack}.pyscript` を出力しない | step 15 が SKIP のまま。以前の検証 (VM の `work/fl_extract`) の回帰は素材だけでは見られない | 子 #2663 (PY-84) |
| mac pkg がある環境で SKIP 対象の mac 側 step を再実行していない | mac 側の追跡出力 (`raw_mac_*.json`・`scripts_inventory.json`・`python_inventory.json`) を mac 素材で再生成したときの差分は未確認 | 未確認。mac 素材の run で再確認 (PM 判断) |

### main 取り込み後の再測定 (HEAD `6bec0214`)

測定 commit: **`6bec0214`** (`origin/main` (`89b23ed3`) を PR の `328c1bcf` に取り込んだ merge commit。コードを変えた最後の commit)。以降の commit は REPORT 系と `docs/DOC_MAP.md` の索引だけ。差分 0 の証跡: `git diff 6bec0214 HEAD -- tools/python ':(exclude)tools/python/REPORT*.md'` の出力は 0 行。

理由: 上の `2bb9811d` の測定の後に main が `tools/python` を変えた。`git diff --stat 2bb9811d 6bec0214 -- tools/python ':(exclude)tools/python/REPORT*.md'` は次のとおり。測定経路は `run_all.sh` の step 10b 追加 (PY-81 #2634。静的版の Worker 比較) を含み、旧 測定 commit の 10 ファイル 315 行の追加を含む。

```
 tools/python/analysis/flapi/pe_rip_refs.py   | 49 ++++++++++++++++++
 tools/python/analysis/flapi/pe_scan_store.py | 49 ++++++++++++++++++
 tools/python/host/fl_mock.mjs                |  7 +++
 tools/python/provider/fl_engine.c            |  6 +++
 tools/python/run_all.sh                      |  1 +
 tools/python/tests/browser/static.html       | 77 ++++++++++++++++++++++++++++
 tools/python/tests/browser/static_worker.mjs | 66 ++++++++++++++++++++++++
 tools/python/tests/channels_diff.mjs         | 16 ++++++
 tools/python/tests/provider_check.mjs        |  8 +--
 tools/python/tests/static_browser_check.mjs  | 39 ++++++++++++++
 10 files changed, 315 insertions(+), 3 deletions(-)
```

#### 測定の手順

- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf`、5 秒)、`FL_WIN64_DIR` に設定。`toolchain-emsdk` は [EMSDK] (版 6.0.12)。mac 無しの再現は `FL_MAC_DIR=$RUNNER_TEMP/no-mac-pkg` (存在しないパス)。
- 依存: 新しい worktree には `node_modules` が無い。初回の run は step 11 で `Cannot find package 'vite'` により rc=1 (293 秒。step 1〜10b は PASS)。コードの不具合ではなく依存の欠落。`pnpm install --frozen-lockfile` (commit 済みの `pnpm-lock.yaml`) の後に全体を再実行した。
- 実行: repo root で `timeout 1500 bash tools/python/run_all.sh` (foreground)。各行に epoch 秒を付けた再実行を正式の測定とする。**rc=0**、最終行 `== ALL OK`、**132 秒**、load (1 分値) 開始 1.25 → 終了 2.65。タイムスタンプ無しの再実行 (同 HEAD) も rc=0・134 秒。
- 実行後の `git status` は空 (追跡生成物の差分 0)。

#### step 別の所要と結果 (HEAD `6bec0214`、時刻付き実行)

| step | 秒 | 結果 |
|---|---|---|
| 1 inputs | 0 | PASS |
| 2 CPython 3.12.1 wasm (incremental) | 1 | PASS |
| 3 MCPTools.pyc 解析 | 0 | PASS (tools: 48) |
| 3b scripts_inventory | 0 | **SKIP** (mac pkg 無し。追跡済み出力) |
| 4 flapi 抽出 (win) + flapi_table | 2 | PASS。mac 版 2 本は **SKIP** (追跡済み) |
| 5 flpy link | 7 | PASS |
| 6 smoke | 0 | PASS |
| 7 builtin 一覧 / py_inventory | 0 | dump_builtins PASS。py_inventory は **SKIP** (追跡済み) |
| 8 PoC (MCPTools.pyc on wasm + flapi mock) | 2 | POC OK |
| 8b kwsig_bind_check | 0 | PASS (6,122 ケース、misbind 0) |
| 9 48 tools 全実行 | 2 | PASS (48/48、host_calls 37,425) |
| 9b C provider 版 48 tools | 3 | PASS (48/48、provider_check PASS) |
| 9c PY-2 静的リンク (pybind / static_check) | 7 | PYBIND CHECK OK、STATIC CHECK OK (48/48) |
| 9c ilmcp 9 関数 e2e | 0 | PASS |
| 9c .pyscript ローダ + flpianoroll 回帰 | 3 | PASS (checks 25/25) |
| 9c' flpianoroll 64 メンバ | 1 | PASS |
| 9d 同梱 Piano roll 5 本 (Chrome) | 8 | 72/72、outputs_mismatch 0 |
| 10 headless Chrome (Worker + SAB) | 1 | BROWSER OK (tools 48) |
| 10b 静的版 Worker と SAB 版の比較 (main 由来の step) | 3 | **STATIC BROWSER OK** (48/48、差 0/48、host_calls 37,425 = 37,425、Worker 内 true) |
| 11 MCP UI / devtools | 2 | MCP UI OK |
| 12 MIDI scripting | 3 | MIDI SCRIPT OK、MIDI BUNDLED OK (checks 9/9) |
| 13 サブインタプリタ | 85 | SUBINTERP OK (checks 19/19) |
| 14 MIDI UI | 2 | MIDI UI OK |
| 15 Chord progression | 0 | **SKIP** (#2663) |
| 合計 | 132 | rc=0、`== ALL OK` |

- 負のコントロール (ログ上の `FAIL` 行 3 件は全てこれ。本体は PASS): step 12 `midi_script.mjs --neg` → `NEG-CONTROL DETECTED` (27 callback 中 OnDirtyChannel が欠落)。step 13 `subinterp_probe.mjs --neg` → `NEG-CONTROL DETECTED` (拒否 builtin 4/66 の期待違反)。`subinterp_negcontrol_old.sh` → `NEG-CONTROL(old flpy.c) DETECTED` (旧 flpy.c で probe の FAIL 行 150 回分を検出)。

#### 検証範囲 / 範囲外

- 範囲: `run_all.sh` の 15 step を fl-win64 + toolchain-emsdk だけで実行。mac 版の step (3b・4 の mac 版・7) は SKIP で追跡済み出力を使い、step 15 は SKIP。
- 範囲外: mac pkg がある環境での `run_all.sh` は未実行。`analysis-mac-shared` を入れた run も未実行 (issue の受入条件は win64 のみ)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `run_all.sh` は `pnpm install` 済みを前提とする (step 11・14 が repo root の `vite` を要る)。前提チェックに無い | 依存の無い worktree では step 11 で止まる (本 run の初回失敗) | PM 判断 (軽微。次に `run_all.sh` を触るときに前提チェックへ追加) |
