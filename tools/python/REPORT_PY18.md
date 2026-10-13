# REPORT 付録 PY-18 — 省略表現の統一・tool_coverage 再生成・UI 3 チェック (#712)

> 本体: [REPORT.md](REPORT.md)。親: #653 (PY-15)。起点 HEAD: `1f83c5ee` (origin/main)。

## 1. 省略表現の統一 (provider の None = JS mock の undefined)

既知類型との関係 (DEFECTS.md): 該当なし (Python 側の引数表現。lift ではない)。

- Python で省略された末尾引数は tuple が短くなり、どちらの engine にも届かない (`src/fl_api.py` の `bind`)。
- Python の明示的な `None` は、wasm 経路で `N` タグ (`provider/fl_dispatch.c`: 既定値扱い) になる。
- 修正前、JS mock は `null` をそのまま渡していたため、既定値 (`slot = -1` 等) が効かなかった。
  - 実測 (修正前): `plugins.getPluginName(0, None)` → mock `""` / wasm `"Sampler"` (不一致)。
- 修正: `host/fl_mock.mjs` の `call` で引数の `null` を `undefined` に正規化し、JS 既定値を効かせる。

修正後の probe (`plugins.getPluginName` 系 4 通り + `mixer.muteTrack` 系):

| 呼出し | mock | wasm |
|---|---|---|
| `getPluginName(0)` | Sampler | Sampler |
| `getPluginName(0, null)` | Sampler (修正前 `""`) | Sampler |
| `getPluginName(0, -1)` | Sampler | Sampler |
| `getPluginName(0, -1, null)` | Sampler | Sampler |

回帰: `tests/provider_check.mjs` §6 に上記 3 件の mock/wasm 一致 assert を追加。

## 2. 48 tools の一致 (受入条件)

| 実行 | 結果 | 所要 |
|---|---|---|
| `node tests/all_tools.mjs` (mock) | 48/48 ok、soft_error 0、raised 0、host_calls 37,425、callback_roundtrip true | 1.15 / 1.11 秒 (n=2、load 0.46〜0.64) |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback_roundtrip true | 1.06 / 1.08 秒 (n=2) |
| `node tests/static_check.mjs` | STATIC CHECK OK、SAB+provider 差 0/48、mock 差 0/48、host_calls 37,425 | — |
| `node tests/provider_check.mjs` | PASS (functions 435、implemented 60、§6 一致) | — |

## 3. tool_coverage.json の再生成

- `all_tools.mjs` (mock) の再生成結果は tracked 版と **バイト一致** (`git status` に差分なし)。
  - 旧 REPORT (PY15 §) の「tracked 37,424 vs 生成 37,425」は、現 main では解消済み。
- `analysis/mcp/tool_coverage.json` は本 PR で変更なし。

## 4. UI 3 チェック (headless Chrome + Vite)

素材: `fl-win64` / `toolchain-emsdk` を展開、`fetch_inputs.sh` (win64 DATA block 経路)、`build_cpython_wasm.sh` (clean ビルド 2 分 57 秒、rc=0)、`build_flpy.sh` / `provider/build.sh` / `build_flpy_static.sh`。Chrome は `/usr/bin/google-chrome`、`pnpm install --frozen-lockfile`。

| チェック | 結果 | 所要 (wall) |
|---|---|---|
| `tests/browser_check.mjs` | BROWSER OK (crossOriginIsolated true、48 tools、host_calls 542) | 10.6 秒 |
| `tools/python/tests/mcp_ui_check.mjs` | MCP UI OK (tools/list = 48、devtools set_tempo 140 → 140) | 11.5 秒 |
| `tools/python/tests/midi_ui_check.mjs` | MIDI UI OK (deliveries notes 60 / ccPort 3 / pcPort 1、failPath 検出) | 12.0 秒 |

上記は GitHub Actions runner (本 run) 上での実測。headless Chrome は `/usr/bin/google-chrome`。

## 5. 未解決

- `run_all.sh` 全体は step 4 (mac 固定パス) が要るため未実施 (#630)。

## 6. commit 済み HEAD での再現 (2256be5a、作業ツリー clean)

| 検証 | 結果 (rc) |
|---|---|
| `all_tools.mjs` (mock) | 48/48 ok、host_calls 37,425、callback true |
| `FL_ENGINE=wasm all_tools.mjs` | 48/48 ok、host_calls 37,425、callback true |
| `provider_check.mjs` | PASS (§6 の mock/wasm 一致 assert を含む) |
| `static_check.mjs` | STATIC CHECK OK |
| `browser_check.mjs` | rc=0 (BROWSER OK) |
| `mcp_ui_check.mjs` | rc=0 (MCP UI OK、tools/list = 48) |
| `midi_ui_check.mjs` | rc=0 (MIDI UI OK) |

実行後も `git status` は clean (`tool_coverage.json` の書き換えなし)。
