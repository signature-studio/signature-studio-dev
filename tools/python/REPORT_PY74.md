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

## 7b-4. device 5 関数 (MIDI scripting 用) の C 実装 (#74)

`device.getPortNumber` / `isAssigned` / `setHasMeters` / `forwardMIDICC` / `midiOutMsg` を `fl_engine.c` に追加 (mock の模擬と同じ意味: forwardMIDICC / midiOutMsg は呼出し件数を数える)。実装 60 → 65、未実装 375 → 370。`tests/device_diff.mjs` (新規) が mock と戻り値・code・件数 (midiOut 4) の差分 0 を確認し、署名違反 4 件が code 5 で拒否されることを wasm 単独で確認する。`fl_engine_midi_out_count` を export して状態を検査可能にした。

| 検証 (HEAD = 本 PR, runner, node 22.23.3, emsdk 6.0.12) | 結果 |
|---|---|
| `bash provider/build.sh` | 成功・警告 0。`gen_provider.py --check-handlers`: ハンドラ 65 |
| `node tests/device_diff.mjs` | calls 7 + reject 4、diffs 0、PASS |
| `node tests/provider_check.mjs` | PASS (435 / 実装 65 / 未実装 370 / MCP 静的 60) |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true、wall 1.53 秒 |
| `node tests/all_tools.mjs` (mock) | 48/48 ok、host_calls 37,425 (wasm と一致) |
| `node tests/midi_script.mjs` | PASS 29 checks、wall 0.59 秒 (mock) |
| `node tests/ilmcp_e2e.mjs` / `ilmcp_diff.mjs` | PASS (回帰なし) |

素材: `fl-win64` から `block25159/24429/24430/24618_DATA.bin` のみ展開 (`tar --zstd -xf` で 2.2 秒)。`build_cpython_wasm.sh` 3 分 08 秒、`FLPY_SKIP_TABLE=1 build_flpy.sh` 4.7 秒 (flapi 表は再生成せず、コミット済みの表を使用)。

## 7b-5. transport.isPlaying の C 実装 (#941 / PY-21)

`transport.isPlaying` の C 実装 (`fl_engine.c`、`playing` 状態を返す。mock の `st.playing` と同じ意味) は main 側で既に入っている (ハンドラ 70 / 未実装 365)。本 PR が追加するのは差分検査 `tests/transport_diff.mjs` (start/stop/isPlaying の 7 呼出しを mock と照合) と、その検出力のネガティブコントロール。`general.getVersion` は mock 側が固定のモック値 (未実測) のため対象外 (子 issue #1138 で扱う)。

検証 (merge 後 HEAD = 48df7e9b, runner 4 core, node 22.23.3, emsdk 6.0.12。wall は実測。未計測は `—`):

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | exit 0・ハンドラ 70 | — |
| `build_cpython_wasm.sh` | exit 0 (dist/python.wasm 5.9 MB) | 3 分 04 秒 (184 秒) |
| `FLPY_SKIP_TABLE=1 build_flpy.sh` | exit 0 (dist/flpy.wasm 5.9 MB) | 4 秒 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 70 / 未実装 365 / MCP 静的 60) | 0.24 秒 |
| `node tests/transport_diff.mjs` | calls 7、diffs 0、PASS | 0.03 秒 |
| `node tests/device_diff.mjs` | calls 7 + reject 4、diffs 0、PASS | 0.04 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 1 秒 |
| `node tests/all_tools.mjs` (mock) | 48/48 ok、host_calls 37,425 | 1 秒 |
| `node tests/midi_script.mjs` | checks 29、failed [] | — |
| `node tests/ilmcp_diff.mjs` | calls 32、state_checks 9、diffs 0、PASS | — |
| `node tests/midi_path_diff.mjs` | cases 30、diffs 0、PASS | — |

wall の `1 秒` は `date +%s` の整数差。`—` は今回計時していない。

素材: `fl-win64` から block25159/24429/24430/24618 のみ展開 (`tar --zstd -xf`)。`toolchain-emsdk` は `[EMSDK]` (docs/REFERENCES.md) を使用。

ネガティブコントロール (`transport_diff.mjs` が壊れを検出することの確認): `provider/fl_engine.c` の `transport.isPlaying` の戻りを `!playing` に反転 → `provider/build.sh` 再ビルド → `transport_diff.mjs` は `transport 差分 4 件` で AssertionError・終了コード 1 (FAIL)。`git checkout` で復元 → 再ビルド → calls 7、diffs 0、PASS・終了コード 0。

### 既知の未解決 (文字の扱い)

- JS の `host/ilmcp.mjs` `norm` は `String.prototype.trim()` (Unicode 空白も除去)、C の `browser_key` は `isspace` (ASCII のみ)。`"\u00a0Plugin database"` のような非 ASCII 空白を含むパスで JS は成功し C は code 1 になる。今回の差分テストは ASCII 入力のみのため検出されない。FL の木は ASCII のため現状の実害はない。扱いは #74 の子チケットで決める (起票先: #74)。
