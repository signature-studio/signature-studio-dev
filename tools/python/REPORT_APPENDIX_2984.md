# tools/python REPORT 付録 (PY-120・#2984): 再測定の履歴 (分割移動)

> 正本: `tools/python/REPORT_PY120_2984.md` (結論・PE 根拠・最新の検証)。本付録は、同 REPORT の §検証 から移した過去の測定節の全文。内容は削除していない (250 行上限のための分割移動)。

## 検証 (履歴)

### 履歴: 初回測定 (測定 commit `eba7e821`・main 取り込み前。当時の HEAD の結果)

測定 commit: `eba7e821` (当時のコードを変えた最後の commit。`feat(flapi): confirm launchMapPages.length from PE 0xd791b0 (PY-120, #2984)`)。ベース `eec639a3` (main 取り込み済み)。

環境: runner (4 core)。開始時の load average 0.51 (`uptime`)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。前提の生成物 (gitignore・work/ と dist/): `fetch_inputs.sh` rc 0 (初回は DATA block が無く rc 1。`block24429`・`block24430`・`block25159`・`block24618*` を展開して再実行し rc 0)、`build_cpython_wasm.sh` rc 0 (初回 chain 全体 4 分 14 秒、cpython 込み)、`FLPY_SKIP_TABLE=1 build_flpy.sh` rc 0、`provider/build.sh` rc 0。

| コマンド | 結果 | wall |
|---|---|---|
| `node tests/provider_check.mjs` | PASS (435 / 実装 84 / 未実装 351 / MCP 静的 60) | 0.37 秒 |
| `node tests/launchmap_diff.mjs` | calls 3、diffs 0、PASS | 0.05 秒 |
| `node tests/general_diff.mjs` (回帰) | calls 9、diffs 0、PASS | 0.05 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 2.11 秒 |
| `python3 analysis/flapi/pe_launchmap_entries.py` | 12 件、全て OK (flags 照合) | — |

- ベース (変更前、同じ環境): `provider_check` は実装 83 / 未実装 352 で PASS、`all_tools` 48/48、`general_diff` PASS。
- ネガティブコントロール: `host/fl_mock.mjs` の `launchPages` を 0 から 1 にすると、`node tests/launchmap_diff.mjs` は `AssertionError [ERR_ASSERTION]: launchMapPages 差分 1 件` で rc 1 (FAIL)。0 に戻すと PASS (rc 0)。
- 当時 (HEAD `eba7e821`) のコード差分 (テスト・mock・C に効く範囲): 空 (0 行)。現 HEAD では空ではない (後続の main 取り込みによる差分。§再取り込み後の再測定 を参照)。

  この REPORT と解析スクリプト (`analysis/flapi/pe_launchmap_entries.py`) は測定 commit の後に加えた。どちらもテスト・provider のビルドに入らない。

### 履歴: main 取り込み後の再測定 (merge `53835669`・main `00ca9f1b`。当時の HEAD の結果)

main (`00ca9f1b`) を取り込んだ merge `53835669` で、競合は 2 件だった。(1) `tests/provider_check.mjs` の集合定義と条件式: main の `pe119` (ui ゲッター 6 件) と本件の `pe120` の両方を残した。(2) `docs/DOC_MAP.md` の表末尾: main の `REPORT_PY119.md` 行と本件の `REPORT_PY120_2984.md` 行の両方を残した。期待値は実装 93 / 未実装 342 (main の 92 / 343 に本件の 1 件を加えた値)。

測定 commit: `53835669` (当時のコードを変えた最後の commit)。環境: runner (load average 0.4〜3.0)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` は fl-win64 から DATA block 4 件 (block24429・block24430・block25159・block24618) だけを展開した先。emsdk は `[EMSDK]` (docs/REFERENCES.md)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0 (fl_table.c: 435 関数・ハンドラ 93) | 1.5 秒 |
| `bash build_cpython_wasm.sh` | rc 0 (前提。CPython 3.12.1 wasm) | 249 秒 |
| `FLPY_SKIP_TABLE=1 build_flpy.sh` | rc 0 | 6 秒 |
| `FLPY_SKIP_TABLE=1 build_flpy_static.sh` | rc 0 | 6 秒 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 93 / 未実装 342 / MCP 静的 60) | 0.36 秒 |
| `node tests/launchmap_diff.mjs` | calls 3、diffs 0、PASS | 0.05 秒 |
| `node tests/general_diff.mjs` (回帰) | calls 9、diffs 0、PASS | 0.05 秒 |
| `node tests/ui_state_diff.mjs` (回帰・pe119) | calls 12、diffs 0、PASS | 0.05 秒 |
| `channels` / `device` / `ilmcp` / `midi_path` / `mixer` / `transport` / `ui` の `*_diff.mjs` | 全て diffs 0、PASS (calls 161 / 8 / 32 / 30 cases / 59 / 7 / 17) | 各 0.05 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback_roundtrip true | 2.1 秒 |
| `node tests/browser_check.mjs` | BROWSER OK (tools 48) | 8.9 秒 |
| `node tests/mcp_ui_check.mjs` / `node tests/midi_ui_check.mjs` | MCP UI OK / MIDI UI OK | 2.2 秒 / 2.8 秒 |
| `node tests/static_check.mjs` | STATIC CHECK OK | 0.4 秒 |
| `node tests/static_browser_check.mjs` | STATIC BROWSER OK (sab_host_calls 37,425・static_host_calls 37,425・static_in_worker true) | 4.5 秒 |
| `node tests/static_mt_check.mjs` | **未再測定**。pthread 版 (`CPY_PTHREADS=1` の CPython wasm) の再ビルドが要り、この run の時間枠に入らなかった。`236a8106` 時点の結果は本 HEAD の値ではない | — |
| `python3 analysis/flapi/pe_launchmap_entries.py` | **未再実行**。`block00031_PE.bin` (PE 本体) を展開していない。`tools/python/analysis/flapi` は main 取り込みで変わっていない (下の diff) | — |

- 前提の順序: `provider_check` は `dist/flpy.js` (CPython wasm) と `work/midi.py` 等 (`fetch_inputs.sh`) を要するため、上の build を先に行った。
- 当時 (HEAD `53835669`) のコード差分: 空 (0 行)。現 HEAD では空ではない (後続の取り込みによる差分)。

- 測定 commit 以前の main 側差分 (参考): `git diff --stat 236a8106 53835669 -- tools/python/analysis/flapi` は空。`tools/python/host`・`provider`・`tests` は取り込みで 8 files 変わった (main の `pe119`・`ui_state_diff` と、競合解消の `provider_check.mjs` を含む)。

### 再取り込み後の再測定 (merge `a2a56bf8`・main `5191cf9f`・HEAD `0549e22b` で測り直し)

測定 commit: `a2a56bf8` (コードを変えた最後の commit。merge)。測定時の HEAD: `0549e22b` (差し戻し対応の測定。以後の commit は本 REPORT と PR 本文のみ)。環境: runner (4 core)。`FL_WIN64_DIR` は fl-win64 から DATA block 4 件と PE 本体 (`block00031_PE.bin`) だけを展開した先。emsdk は [EMSDK] (6.0.12)。vite は本体 checkout の `node_modules` を symlink して解決した (コミットしない)。

CPython wasm は HEAD で再ビルドした (流用なし): `fetch_inputs.sh` → `build_cpython_wasm.sh` (rc 0)、`build_cpython_wasm64.sh` (rc 0。`EMSDK_ENV` に [EMSDK] の `emsdk_env.sh` を指定する。未指定では rc 1)、`CPY_PTHREADS=1 build_cpython_wasm.sh` (rc 0)。

| コマンド | 結果 | wall (s) |
|---|---|---|
| `provider/build.sh` / `FLPY_SKIP_TABLE=1 build_flpy.sh` / `FLPY_SKIP_TABLE=1 build_flpy_static.sh` | 全て rc 0 (fl_table.c: 435 関数・ハンドラ 110) | — |
| `FLPY_MEMORY64=1 CPY_BUILD=… STATIC_OUT=flpy_static64 FLPY_SKIP_TABLE=1 build_flpy_static.sh` / `CPY_PTHREADS=1 FLPY_SKIP_TABLE=1 build_flpy_static.sh` | 全て rc 0 (flpy_static64・flpy_static_pthread) | — |
| `node tests/provider_check.mjs` | PASS (435 / 実装 110 / 未実装 325 / MCP 静的 60) | 0 |
| `node tests/launchmap_diff.mjs` | calls 3、diffs 0、PASS | 0 |
| `node tests/general_diff.mjs` (回帰) | calls 25、diffs 0、PASS | 0 |
| `node tests/ui_state_diff.mjs` / `screen_diff.mjs` / `arrangement_diff.mjs` (main 由来) | calls 12 / 32 / 25、diffs 0、PASS | 0 |
| `channels` / `device` / `ilmcp` / `midi_path` / `mixer` / `transport` / `ui` の `*_diff.mjs` | 全て diffs 0、PASS (calls 161 / 8 (rejects 4・midi_out 5) / 32 (state_checks 9) / 30 cases / 59 / 7 / 17) | 0〜1 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、soft_error 0、raised 0、host_calls 37,425、callback_roundtrip true | 1 |
| `node tests/browser_check.mjs` | BROWSER OK (tools 48) | 1 |
| `node tests/static_check.mjs` | STATIC CHECK OK。ただし 12 回実行のうち 1 回目 (ループ内) だけ rc 1 (`STATIC CHECK FAIL (1)`)。FAIL 行は採取していない。残り 11 回は全て OK | 1 |
| `node tests/static_browser_check.mjs` | STATIC BROWSER OK (sab_host_calls 37,425・static_host_calls 37,425・static_in_worker true) | 2 |
| `node tests/static_subinterp_browser.mjs` (既定 flpy_static64・MEMORY64=1) | **FAIL (12 check 中 11 PASS)**。失敗は「150 回 (50×3) の作成/実行/破棄で wasm メモリが増えない」: 33,554,432 → 48,365,568 B (+14,811,136 B)。`REPORT_PY109.md` の記録と同値。既知 (#2918) | 20 |
| `STATIC_WASM=flpy_static STATIC_MEM64=0 node tests/static_subinterp_browser.mjs` (wasm32 静的版) | STATIC SUBINTERP OK (12/12 PASS) | 17 |
| `STATIC_WASM=flpy_static_pthread node tests/static_mt_check.mjs` | STATIC MT CHECK OK (runs 50、threads_2_tools 48、threads_4_tools 2、thread_mismatch 0) | 1 |
| `node tests/mcp_ui_check.mjs` | MCP UI OK (tools/list = 48) | 2 |
| `node tests/midi_ui_check.mjs` | MIDI UI OK | 2 |
| `python3 analysis/flapi/pe_launchmap_entries.py` | 12/12 OK (PE 本体を展開して再実行) | 0 |

- static_mt の host_calls (37,424) と all_tools・static_browser_check (37,425) の 1 差は計数元の違い。原因は未調査 (各 check の判定条件どおりで FAIL ではない)。
- 負のコントロール: 前節の結果を引き継ぐ。`fl_mock.mjs` の `launchPages` の既定値は 0 のまま。
- コード差分 (測定 commit `a2a56bf8` から HEAD まで、テスト・mock・C・解析に効く範囲): 下の出力を HEAD で取った。

```
$ git diff a2a56bf8 HEAD -- tools/python/host tools/python/provider tools/python/tests tools/python/analysis/flapi
(空)
```
