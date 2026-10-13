# tools/python REPORT: PY-27 ui / general / screen / arrangement / launchMapPages (#1138, 親 #941)

> 正本: `tools/python/REPORT.md` (250 行上限のため本付録に分離)。

## 結論

- mock に意味論がある未実装関数は **0 件追加**。対象 5 module のうち mock が持つのは `ui.getVisible` / `ui.showWindow` / `ui.hideWindow` / `general.getVersion` の 4 件で、いずれも `provider/fl_engine.c` に既に実装済み (PY-21 以前の commit)。
- 本 PR で追加したのは差分検査 `tests/ui_diff.mjs` のみ。in-range 17 呼出しで mock と diffs 0。
- 残り **150 件** (ui 69 / general 29 / screen 28 / arrangement 12 / launchMapPages 12) は mock に意味論が無く、実機値の確定が必要。保留 (下表・未解決)。

## 対象 module の現況 (`analysis/flapi/flapi_table.json` 実測)

| module | 表の関数 | 実装 (C) | 未実装 | mock 有 | 扱い |
|---|---|---|---|---|---|
| ui | 72 | 3 | 69 | getVisible / showWindow / hideWindow | 3 件は実装済み・diff 検査済み。残り 69 は保留 |
| general | 30 | 1 | 29 | getVersion | getVersion は実装済み (下記の未実測注記)。残り 29 は保留 |
| screen | 28 | 0 | 28 | なし | 保留 |
| arrangement | 12 | 0 | 12 | なし | 保留 |
| launchMapPages | 12 | 0 | 12 | なし | 保留 |

provider 全体: 435 関数 / 実装 70 / 未実装 365 (変化なし。`provider_check.mjs` PASS)。

## 保留 (mock に意味論が無い。実機値の確定方法が未確定)

受入条件 2 に従い、実装せず保留する。残り 150 件の起票先は親 #941 (PY-21) の残件。実機値の確定 (未実測) は本 issue では行えないため、#941 で扱う (新規子 issue は起票していない)。
- 実機値の確定: FL 26.1.7 の win64 (`$FL_WIN64_DIR`) に対し、各関数を呼んで戻り値を取る実測が必要 (mock 追加より先)。
- `screen` / `arrangement` / `launchMapPages` は MCPTools.pyc からの参照が 0 (`mcp_tools` が空)。優先度は低い。

## 差分検査 `tests/ui_diff.mjs`

同じ呼出し列を mock (`host/fl_mock.mjs`) と C provider に流し、戻り値と code を比較する。

- in-range 17 呼出し (index 0〜5 の getVisible / showWindow / hideWindow の組合せと `general.getVersion`): **diffs 0**
- 範囲外 index 3 件 (-1 / 64 / 100): mock は範囲検査をせず、C は code 4 (Index out of range) を返す。**既知の差分**として分けて報告し、差分が消えたら検査が失敗するように書いている。

## 検証

測定 commit: `832f985d` (main 取り込み後の HEAD)。`832f985d` から HEAD まで `tools/python` のコード差分は 0 (下記)。
runner 4 core / node 22.23.3 / emsdk 6.0.12 ([EMSDK] へ symlink) / `FL_WIN64_DIR` は fl-win64 の展開先。
`tools/python/work/` は `fetch_inputs.sh` で fl-win64 から作成 (gitignore)。負荷: 測定中 load average 0.8〜3.5 (4 core)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | exit 0・ハンドラ 70 | 1 秒 |
| `build_cpython_wasm.sh` | exit 0 (python.wasm 5.93 MB) | 271 秒 (4 分 31 秒) |
| `FLPY_SKIP_TABLE=1 build_flpy.sh` | exit 0 (flpy.wasm 5.92 MB) | 6 秒 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 70 / 未実装 365 / MCP 静的 60) | 0.44 秒 |
| `node tests/ui_diff.mjs` | calls 17、diffs 0、範囲外既知差分 3、PASS | 0.05 秒 |
| `node tests/device_diff.mjs` | calls 7、rejects 4、midi_out 4、diffs 0、PASS | 0.05 秒 |
| `node tests/transport_diff.mjs` | calls 7、diffs 0、PASS | 0.05 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 2.0 秒 |

注: 4 本の node テストは `dist/` 生成後に実行 (並列実行すると `dist/flprov.js` 未生成で失敗する)。

コード差分 (測定 commit から HEAD まで、`tools/python` の .md 以外):
```
$ git diff 832f985d HEAD -- tools/python ':!*.md'
(空。tools/python の .md 以外は変更なし)
```

## 未解決

- `general.getVersion` の戻り値 1 は実機値ではない (mock の固定値と C 側が揃っているだけ)。実機での MIDI scripting version は未実測。
- ui の範囲外 index: mock に範囲検査が無い (C は code 4)。どちらが実機に近いかは未確定。実機確認まで既知差分として扱う。
- 残り 150 件の実機値確定 (上記「保留」)。
