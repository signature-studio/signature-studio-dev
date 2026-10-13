# tools/python REPORT 付録: PY-1 ilmcp 意味論の整合 (#74, PR #763)

> 正本: `tools/python/REPORT.md` §7b-3。250 行上限のため、§7b-3 の実測表をここに置く。

## 7b-3. ilmcp 8 ハンドラを `host/ilmcp.mjs` の意味論に合わせる

対象 commit: `8674fa6` (コード)。本節の実測は 8674fa6 のビルド・実行結果。以後の commit は REPORT 文書のみで provider / host / tests を変えない。

| 関数 | 変更 |
|---|---|
| getBrowserNames | `{name,items}` 固定 3 件 → `analysis/ilmcp/plugin_catalog.json` の木から list を返す。不明パスは code 1 (Invalid value) |
| getHighlightNames | 4 件 → FLEngine rodata 実測 21 件 |
| addChannel | generator 名のみ受理。effect 名・未知名は code 1 |
| addEffect | effect 名のみ受理。`plugin=""` はスロット消去 |
| storePRScript | 名前に `/ \ :` を含む・空は code 1 |
| removeChannel / showHighlight / runPRScript / forwardTutorialEvent | 意味論は従来どおり (差分なし) |

データ: `provider/gen/ilmcp_data.h` は `gen_provider.py` が `analysis/ilmcp/{plugin_catalog,highlight_names}.json` から生成 (dir 28 / plugin 141 / highlight 21)。C から JSON を読めないため事前計算する。木の walk と並びは `host/ilmcp.mjs` と同じ規則。

### 実測 (HEAD 8674fa6、Actions runner 4 core、node 22.23.3、emsdk 6.0.12 = [EMSDK]、直列 1 本)

入力: `$RUNNER_TEMP/fl-win64` に `fl-win64.tar.zst` を展開 (7.4 秒) → `FL_WIN64_DIR` で `fetch_inputs.sh` → `build_cpython_wasm.sh` (3m39.8s) → `build_flpy.sh` (5.6 秒)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | 成功・警告 0 (`-Wall -Wextra`)。`gen_provider.py --check-handlers`: 435 関数 / ハンドラ 60 / ilmcp_data.h dir 28 plugin 141 highlight 21 | 0.96 秒 |
| `node tests/ilmcp_e2e.mjs` (JS mock 相手) | checks 25 / pass 25 / fail 0、exit 0 | 0.35 秒 |
| `node tests/provider_check.mjs` | functions 435 / implemented 60 / unimplemented 375 / mcp_static 60、PASS | 0.27 秒 |
| `node tests/ilmcp_diff.mjs` (新規: wasm と JS mock の差分) | calls 32 / state_checks 9 / diffs 0、PASS | 0.05 秒 |
| `node tests/all_tools.mjs` (mock) | 48/48 ok、soft_error 0、raised 0、host_calls 37,425、callback_roundtrip true | 1.25 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、soft_error 0、raised 0、host_calls 37,425、callback_roundtrip true | 1.34 秒 |
| `node tests/poc_mcp.mjs` | POC OK | 0.85 秒 |
| `node tests/midi_script.mjs` | checks 29 / failed [] | 0.62 秒 |
| `python3 tests/kwsig_check.py` | kwsig_check: OK | 0.04 秒 |

負荷: 各テストの直前 load average 1.6〜2.6 (4 core)。全て直列 1 本。

### ネガティブコントロール

addEffect の plugin 名検証 (`fl_engine.c` の `if (pn[0] && !plugin_kind_ok(pn, "effect")) ...`) を `if (0 && ...)` に変えて再ビルドし、`ilmcp_diff.mjs` を実行 (作業ツリーは変更せず、`$RUNNER_TEMP` の scratch コピーで実施)。

- 結果: `ilmcp 差分 2 件` で AssertionError、exit 1。差分は `ilmcp.addEffect` の `['Nope', 1, 0]` (mock = code 1、wasm = ok) を含む 2 件。
- 元のコードでは diffs 0 (上記)。

### 既知の未解決 (文字の扱い)

- JS の `host/ilmcp.mjs` `norm` は `String.prototype.trim()` (Unicode 空白も除去)、C の `browser_key` は `isspace` (ASCII のみ)。`"\u00a0Plugin database"` のような非 ASCII 空白を含むパスで JS は成功し C は code 1 になる。今回の差分テストは ASCII 入力のみのため検出されない。FL の木は ASCII のため現状の実害はない。扱いは #74 の子チケットで決める (起票先: #74)。
