# tools/python REPORT: PY-168 (#3182) flrack.rack.loop_starter_config の PE 契約と e2e 再測定

> 正本: `tools/python/REPORT_PY166.md` (属性表・PE 読み)・`tools/python/REPORT_PY167.md` (flr の pyc 根拠)。本付録は PY-168 の実測のみ。

## 結論

- 前提 PR #3183 (PY-166) は 2026-10-14 23:42Z に merge 済み。本 PR は main から切った `3182-loop-starter-config` で作業した。
- `src/` の flrack 実装は無く、変更は tests の mock 2 箇所だけ。`flrack.flr` の mock を外した (PE に `flrack.flr` は無く、pyc も読まない。`REPORT_PY167.md` §3)。`loop_starter_config` の mock は、PE 契約 (書込み可・未設定で AttributeError) に**置換していない**。根拠の無い JSON 値であることを残す。
- HEAD (本 PR のコミット) の e2e は 41/41 PASS・`--neg` は 34/41 (FAIL 7) で、`REPORT_PY22.md` の記載と一致した。
- `loop_starter_config` を未設定にした場合、`rack.Rack().load_config()` 単体は例外なく `OK` で返る (`tests/loop_starter_unset_probe.mjs`)。`rack.pyc` の `load_config` は 140 行目で `json.loads(flrack.rack.loop_starter_config)` を `try` で囲み、`AttributeError` を `remote_config = {}` に置き換えるため、AttributeError は外へ出ない。未設定の影響は後段の `KeyError: 'genres'` として現れる (e2e で 4 件 FAIL)。受入条件の「AttributeError を probe で実測」は、この経路では AttributeError 自体は観測できないという結果になった。
- probe (9 関数) は `load_config` を経由しないため、set / 未設定のどちらでも 3/9 で同じ結果。未設定の影響を測る対象として不適切だった。

## 実測 (HEAD、コミット済み)

測定 commit: `cb53d6096` (コードを変えた最後の commit)。以後の commit は本 REPORT の文言だけを変える。

| 項目 | 結果 |
|---|---|
| `chord_progression_e2e.mjs` | 41/41 PASS・0.4 s (`mock: true`) |
| `chord_progression_e2e.mjs --neg` | 34/41・FAIL 7・exit 1 |
| `chord_progression_call_probe.mjs` (`loop_starter_config` 設定) | 9 関数中 `OK` 3・失敗 6 (`called: 3, failed: 6`) |
| `loop_starter_unset_probe.mjs` (未設定で `rack.Rack().load_config()`) | `OK` (例外なし) |
| e2e・loop_starter_config 未設定 (一時コピーで除去・測定後に削除) | 37/41・FAIL 4 (`Notes/drums.pyc`・`control_rack.pyc`・`util_rack.pyc`・`stack.pyscript` の `KeyError: 'genres'`)。この測定は `flrack.flr` mock の除去 (cb53d6096) より前に行った |

## 手段

- 素材: `fl-win64` (`$ARTIFACTS_DIR`・`tar --zstd -xf` で 7.5 秒で展開)。`toolchain-emsdk` は `EMSDK_DIR` (既定) に存在 (`docs/REFERENCES.md` §4 の `[EMSDK]`)。
- `build_cpython_wasm.sh` (rc 0・約 4 分)、`fetch_inputs.sh` (stubs 取得)、`build_flpy.sh` (rc 0)。
- `extract_pyc_blocks.py` (pyc 40・pyscript 2・drum_patterns 1)。
- 同 probe の出力は `work/` 配下 (gitignore)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未設定時の `AttributeError` を直接観測する probe。`load_config` を経由する入口が要る | 現在は `KeyError: 'genres'` でしか観測できない | 本 PR では未実装。要 follow-up |
| `loop_starter_config` の既定 mock 値 (`{"mock": true, ...}`) の実 FL 照合 | 実値は未確認 | #3182 のコメントで追跡 (旧 #81 は CLOSED) |
| 全行 offset 0 の理由 (PyMemberDef 前提) | T_OBJECT_EX・書込み可の読みは前提付き | `REPORT_PY166.md` の未確定表のまま |
| `flr` の各メソッド・属性の戻り値 (`rack.py` の `Rack` 本体) | mock (根拠なし) のまま | `REPORT_PY167.md` §4 のまま |
