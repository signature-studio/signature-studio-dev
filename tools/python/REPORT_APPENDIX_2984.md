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

### 履歴: 再取り込み後の再測定 (merge `a2a56bf8`・main `5191cf9f`・HEAD `0549e22b` で測り直し)

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

- static_mt の host_calls (37,424) と all_tools・static_browser_check (37,425) の 1 差は原因未調査 (計数元の違いかは未確認。各 check の判定条件どおりで FAIL ではない)。
- 負のコントロール: 前節の結果を引き継ぐ。`fl_mock.mjs` の `launchPages` の既定値は 0 のまま。
- コード差分 (測定 commit `a2a56bf8` から HEAD まで、テスト・mock・C・解析に効く範囲): 下の出力を HEAD で取った。

```
$ git diff a2a56bf8 HEAD -- tools/python/host tools/python/provider tools/python/tests tools/python/analysis/flapi
(空)
```

## 検証 (履歴・再取り込み後の再測定 (2)〜(4))

`REPORT_PY120_2984.md` の §検証 から移した過去の測定節の全文 (250 行上限のための分割移動。内容は削除していない)。

### 履歴: 再取り込み後の再測定 (2) (merge `a0b6f97f`・main `f81c46bb`。当時の HEAD の結果)

main (`f81c46bb`) を取り込んだ merge `a0b6f97f` の競合は 3 ファイル 7 箇所。`host/fl_mock.mjs`・`provider/fl_engine.c` は、main の PY-96 (選択範囲 4 件) と PY-121 (#2982・表示・メニュー 6 件) の追加と、本件の `launchPages`・`lm_pages`・`launchMapPages.length` を両側残しで解消した。`tests/provider_check.mjs` は集合定義と条件式に main の `pe96`・`pe121_2982` と本件の `pe120` を並べ、期待値を実装 120 / 未実装 315 にした (main の 119 / 316 に本件の 1 件を加えた値)。rebase・force push はしていない。

測定 commit: `a0b6f97f` (コードを変えた最後の commit。merge)。環境: runner (4 core)。素材は `fl-win64` から DATA block 4 件と PE 本体 (`block00031_PE.bin`) を、`toolchain-emsdk` を展開した emsdk ([EMSDK] 6.0.12) で使った。vite は本体 checkout の `node_modules` を symlink して解決した (コミットしない)。CPython wasm (32 bit・64 bit・pthread) は HEAD で再ビルドした (流用なし)。

| コマンド | 結果 | wall (s) |
|---|---|---|
| `fetch_inputs.sh` / `provider/build.sh` | rc 0 (fl_table.c: 435 関数・ハンドラ 120) | 1 / 13 |
| `build_cpython_wasm.sh` / `CPY_PTHREADS=1 build_cpython_wasm.sh` / `build_cpython_wasm64.sh` | 全て rc 0 | 230 / 124 / 173 |
| `FLPY_SKIP_TABLE=1 build_flpy.sh` / `build_flpy_static.sh` / `CPY_PTHREADS=1 … build_flpy_static.sh` / `FLPY_MEMORY64=1 … build_flpy_static.sh` | 全て rc 0 | 10 / 6 / 18 / 7 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 120 / 未実装 315 / MCP 静的 60) | 0 |
| `launchmap_diff` / `general_diff` / `ui_state_diff` / `screen_diff` / `arrangement_diff` / `arrangement_selection_diff` | 全て diffs 0、PASS (calls 3 / 25 / 12 / 32 / 25 / 8) | 0 |
| `ui_display_diff` | PASS (ok 12・bad 11・diffs 0) | 0 |
| `channels` / `device` / `ilmcp` / `midi_path` / `mixer` / `transport` / `ui` の `*_diff.mjs` | 全て diffs 0、PASS (calls 161 / 8 / 32 / 30 cases / 59 / 7 / 17) | 0 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、soft_error 0、raised 0、host_calls 37,425、callback_roundtrip true | 2 |
| `browser_check` / `static_check` | BROWSER OK (tools 48) / STATIC CHECK OK (1 回) | 10 / 0 |
| `static_browser_check` | STATIC BROWSER OK (sab_host_calls 37,425・static_in_worker true) | 3 |
| `STATIC_WASM=flpy_static STATIC_MEM64=0 static_subinterp_browser` | STATIC SUBINTERP OK (12/12 PASS) | 22 |
| `static_subinterp_browser` (flpy_static64・MEMORY64=1) | **FAIL (12 check 中 11 PASS)**。付録の merge `a2a56bf8` 節と同じ失敗 (150 回の作成/実行/破棄で wasm メモリが増える: 33,554,432 → 48,365,568 B、+14,811,136 B)。#2918 (既知) | 27 |
| `STATIC_WASM=flpy_static_pthread static_mt_check` | STATIC MT CHECK OK (runs 50・threads_2_tools 48・threads_4_tools 2・thread_mismatch 0) | 1 |
| `mcp_ui_check` / `midi_ui_check` | MCP UI OK (tools/list = 48) / MIDI UI OK | 3 / 2 |
| `python3 analysis/flapi/pe_launchmap_entries.py` | 12/12 OK | 0 |

- 負のコントロール (`launchPages` を 1 にすると `launchmap_diff` が FAIL する確認) は今回は再実行していない。付録の merge `a2a56bf8` 節の結果を引き継ぐ。mock の `launchPages` の既定値は 0 のまま。
- コード差分 (測定 commit `a0b6f97f` から HEAD まで、テスト・mock・C・解析に効く範囲): 下の出力を HEAD で取った。

```
$ git diff a0b6f97f HEAD -- tools/python/host tools/python/provider tools/python/tests tools/python/analysis/flapi
(空)
```

### 再取り込み後の再測定 (3) (merge `71005b39`・main `150a83fa`・HEAD で測り直し)

main の取り込みは 2 回。`1b37410c` を取り込んだ merge `38927307` (競合 2 ファイル 2 箇所) を push した後、main が `150a83fa` へ進んだため、`150a83fa` を取り込んだ merge `71005b39` (競合 1 ファイル 1 箇所) を作った。解消は両側残し:
- `host/fl_mock.mjs` (`38927307`): 本件の `launchMapPages.length` と main の PY-125 (`general.clearLog`・`general.dumpScoreLog`) を両方残した。
- `tests/provider_check.mjs` (`38927307`・`71005b39`): 判定集合に `pe120`・`pe125` と main の PY-102 (`pe102`・`playlist.muteTrackLock`) を全て入れた。期待値は main `150a83fa` の 122/313 に本件の 1 件を加えた 123/312。
- `provider/fl_engine.c` は自動マージ。`launchMapPages.length`・`general.clearLog`・`playlist.muteTrackLock` の登録が C と mock に各 1 回ずつ残ることを grep で確認した。

測定 commit: `71005b39` (コードを変えた最後の commit。merge)。環境: runner (4 core・load average 約 1)。素材: `fl-win64` から DATA block 4 件と PE 本体 (`block00031_PE.bin`) を展開。emsdk は [EMSDK] (6.0.12・runner 同梱。`toolchain-emsdk` の tarball は展開していない)。ブラウザ系は本体 checkout の `node_modules` を symlink して実行した (commit しない)。CPython wasm (32 bit) は `38927307` の測定で再ビルド (rc 0・255 s) したものを流用した。`71005b39` までの main 差分に `tools/python` の build スクリプト・CPython 取得の変更は無い (`git diff --stat 992d430b 71005b39 -- tools/python` の一覧に `.sh` は無い)。

| コマンド | 結果 | wall (s) |
|---|---|---|
| `fetch_inputs.sh` / `build_cpython_wasm.sh` (32 bit) | `38927307` で rc 0 / rc 0 (`71005b39` では流用) | 1 / 255 |
| `provider/build.sh` / `build_flpy.sh` / `build_flpy_static.sh` | 全て rc 0 (`fl_table.c`: 435 関数・ハンドラ 123) | 1 / 7 / 7 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 123 / 未実装 312 / MCP 静的 60) | 0 |
| `launchmap` / `general` / `ui_state` / `screen` / `arrangement` / `arrangement_selection` / `ui_display` / `channels` / `device` / `ilmcp` / `midi_path` / `mixer` / `transport` / `ui` / `playlist` の `*_diff.mjs` | 全て diffs 0、PASS (calls 3 / 32 / 12 / 32 / 25 / 8 / ok 12・bad 11 / 161 / 8 / 32 / 30 cases / 59 / 7 / 17 / 23) | 0〜1 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、soft_error 0、raised 0、host_calls 37,425、callback_roundtrip true | 2 |
| `python3 analysis/flapi/pe_launchmap_entries.py` / `static_check.mjs` | 12/12 OK / STATIC CHECK OK | 0 / 0 |
| `browser_check` / `static_browser_check` / `mcp_ui_check` / `midi_ui_check` | BROWSER OK (tools 48) / STATIC BROWSER OK (sab_host_calls 37,425) / MCP UI OK (tools/list = 48) / MIDI UI OK | 1 / 4 / 2 / 2 |
| `STATIC_WASM=flpy_static STATIC_MEM64=0 static_subinterp_browser` | STATIC SUBINTERP OK (12/12 PASS) | 24 |

- 今回は未実行: `static_subinterp_browser` (flpy_static64・MEMORY64=1)・`static_mt_check`・負のコントロール (`launchPages` を 1 にして `launchmap_diff` が FAIL する確認)。いずれも CPython の再ビルド (64 bit・pthread) か再実行が要る。前回の結果は本測定の根拠にしない。
- コード差分 (測定 commit `71005b39` から HEAD まで、テスト・mock・C・解析に効く範囲): 下の出力を HEAD で取った (REPORT のみの commit が HEAD)。

```
$ git diff 71005b39 HEAD -- tools/python/host tools/python/provider tools/python/tests tools/python/analysis/flapi
(空)
```

### 再測定 (4) (測定 commit `71005b39`・HEAD `4f855fde` で実行)

測定 commit は `71005b39` (コードを変えた最後の commit)。`4f855fde` は REPORT のみの commit。(3) の表にあった未実行の項目を、HEAD のコードで実行した。素材は `fl-win64` から `block00031_PE.bin` と DATA block 4 件を `$RUNNER_TEMP` の `fl-win64-3039` へ展開した (`tar --zstd -xf --wildcards`)。emsdk は [EMSDK] (runner 同梱・6.0.12)。`toolchain-emsdk` は展開していない (不使用)。`mcp_ui_check`・`midi_ui_check` は本体 checkout の `node_modules` を symlink して実行した (commit していない)。CPython wasm は 32 bit・pthread・64 bit の 3 種を HEAD で再ビルドした (流用なし)。

| コマンド | 結果 | wall (s) |
|---|---|---|
| `fetch_inputs.sh` / `provider/build.sh` | rc 0 / rc 0 (fl_table.c: 435 関数・ハンドラ 123) | 2 (合計) |
| `build_cpython_wasm.sh` (32 bit・native 込み) / `CPY_PTHREADS=1 build_cpython_wasm.sh` / `EMSDK_ENV=<[EMSDK] の emsdk_env.sh> build_cpython_wasm64.sh` | 全て rc 0 | 254 / 146 / 192 |
| `FLPY_SKIP_TABLE=1 build_flpy.sh` / `build_flpy_static.sh` / `CPY_PTHREADS=1 … build_flpy_static.sh` / `FLPY_MEMORY64=1 CPY_BUILD=… STATIC_OUT=flpy_static64 … build_flpy_static.sh` | 全て rc 0 | 27 (4 本の合計) |
| `node tests/provider_check.mjs` | PASS (435 / 実装 123 / 未実装 312 / MCP 静的 60) | 6 (下の 5 行の合計) |
| `launchmap_diff` / `general_diff` / `ui_state_diff` / `screen_diff` | 全て diffs 0、PASS (calls 3 / 32 / 12 / 32) | 同上 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、soft_error 0、raised 0、host_calls 37,425、callback_roundtrip true | 同上 |
| `static_check.mjs` | STATIC CHECK OK | 同上 |
| `STATIC_WASM=flpy_static_pthread static_mt_check.mjs` | STATIC MT CHECK OK (runs 50・threads_2_tools 48・threads_4_tools 2・thread_mismatch 0) | 1 |
| `tests/fulltext_parity.mjs` | FULLTEXT PARITY OK (mock/wasm・mock/static・wasm/static の 48 tool 全文 text_diff 0)。ネガコン: 300 字目 (160 字より後ろ) の 1 字変更を全文比較が検出 (1)、先頭 160 字のゲートは検出せず (false) | 8 |
| `STATIC_WASM=flpy_static64 STATIC_MEM64=1 static_subinterp_browser.mjs` | **FAIL** (checks 12 中 failed 1: 150 回の作成/実行/破棄で wasm メモリが増える。mem_before 33,554,432 → mem_after 48,365,568 B)。既知 #2918 と同じ失敗 | 下の 3 行の合計 77 |
| `STATIC_WASM=flpy_static STATIC_MEM64=0 static_subinterp_browser.mjs` | STATIC SUBINTERP OK (12/12 PASS) | 同上 |
| `static_browser_check.mjs` | STATIC BROWSER OK (sab_host_calls 37,425・static_in_worker true・diff_tools 0) | 同上 |
| `browser_check.mjs` | BROWSER OK (tools 48) | 1 |
| `mcp_ui_check.mjs` / `midi_ui_check.mjs` | MCP UI OK (tools/list = 48) / MIDI UI OK | 2 / 3 |
| `python3 analysis/flapi/pe_launchmap_entries.py` | 12/12 OK | 0 |
| 負のコントロール: `host/fl_mock.mjs` の `launchPages` を 1 にして `launchmap_diff.mjs` | rc 1・`launchMapPages 差分 1 件` (mock ok 1 / wasm ok 0) で検出。確認後に 0 へ戻し、再実行で PASS (calls 3・diffs 0) | 0 |

- コード差分 (測定 commit `71005b39` から HEAD まで): 上の結果はコードが 71005b39 と同じ作業ツリーで得たもの。下の出力を最終 HEAD で取った (REPORT の変更のみ)。

```
$ git diff 71005b39 HEAD -- tools/python/host tools/python/provider tools/python/tests tools/python/analysis/flapi
(空)
```
