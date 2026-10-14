# PY-70 (#2500): channels.processRECEvent の flapi 署名を生成元で修正 (残り 3 関数は子 issue へ)

親: #1527 (PY-39 / PY-37 の残り)。兄弟: #2499 (PY-69)・#2501 (PY-71)。前段の解析: `tools/python/REPORT_PY39.md`。
既知類型との関係: 該当なし (lift 作業ではない。flapi 表の生成器の読取り不具合)。

## 結論

- `channels.processRECEvent` の署名が 0 引数だった原因は、生成器 `tools/python/analysis/flapi_table.py` が stub の**位置専用引数 (`/`)** を読んでいなかったこと。stub の定義は `def processRECEvent(eventId: int, value: int, flags: int, /) -> int` (`tools/python/work/fl-stubs/src/midi_controller_scripting/channels/__properties.py:826`)。
- 修正後の表は `(eventId, value, flags)` の 3 引数になり、PE の書式 `Iii` (required 3 / max 3) と一致した。
- 同じ原因で 15 関数の引数個数が 0 から実際の個数になった。このうち 14 関数は PE の max と一致する。残り 1 件 (`screen.addTextLine`) は stub と PE が食い違う (§3)。
- 4 関数の意味論確定と provider / mock 実装は**未着手**。issue の範囲を縮めて、残りを子 #2544・#2547・#2548 へ移した。推測での実装はしていない。

## 測定

- 測定 commit: `1530a544` (コード変更の最後の commit)。以下の数値はこの commit の内容で測った。
- 差分 0 の証跡: `git diff 1530a544 HEAD -- tools/python/analysis/flapi/flapi_table.json tools/python/analysis/flapi_table.py tools/python/provider tools/python/host tools/python/tests` の出力は 0 行。本 REPORT の commit で増えたのは `tools/python/REPORT_PY70.md`・`tools/python/analysis/flapi/sig_arity_check.py`・`docs/DOC_MAP.md` だけ。
- main の取り込み: 測定後に `origin/main` が進んだ (`582aa49e` → `1bb996f0`)。その間に `tools/python` で変わったのは `analysis/py59_handle.py` (新規) と `REPORT_PY59.md` だけで、上の測定パスには触れない。取り込み後の `git diff 1530a544 HEAD -- <同じパス>` も 0 行。
- 環境: GitHub Actions runner (4 コア)。測定中の load average は 15:02 時点で 1 分 0.00・5 分 0.37 (`uptime`)。
- 素材: `fl-win64` を `tar --zstd -xf <ARTIFACTS>/fl-win64.tar.zst --wildcards '*block00031_PE.bin' '*block24429_DATA.bin' '*block24430_DATA.bin' '*block25159_DATA.bin' '*block24618_DATA.bin'` で展開 (1.8 s)。emsdk は [EMSDK] (`toolchain-emsdk`)。`toolchain-retdec` は今回の検証では使っていない (逆コンパイルは子 issue の範囲)。

## 1. 原因 (生成器)

stub の定義には位置専用引数 (`def f(a, b, /)`) を含むものがある。旧 `stub_sigs` は `FunctionDef.args.args` だけを読んだため、位置専用の引数が落ち、`params: []` になっていた。`processRECEvent` 以外にも同じ落ちが 15 件あった。

修正前後の表 (`sig.params` の個数と PE 書式の kwsig):

| 関数 | 変更前 | 変更後の params | PE 書式 (fmt / required / max) |
|---|---|---|---|
| channels.closeGraphEditor | 0 | index | `i` / 1 / 1 |
| channels.processRECEvent | 0 | eventId, value, flags | `Iii` / 3 / 3 |
| device.directFeedback | 0 | eventData | `O` / 1 / 1 |
| device.sendMsgGeneric | 0 | id, message, lastMsg, offset=0 | `Lss\|i` / 3 / 4 |
| general.setUndoHistoryLast | 0 | index | `i` / 1 / 1 |
| mixer.remoteFindEventValue | 0 | index, flags=0 | `I\|i` / 1 / 2 |
| patterns.ensureValidNoteRecord | 0 | index, playNow=0 | `i\|i` / 1 / 2 |
| patterns.getChannelLoopStyle | 0 | pattern, channel | `ii` / 2 / 2 |
| patterns.getPatternGroupName | 0 | index | `i` / 1 / 1 |
| patterns.getPatternsInGroup | 0 | index | `i` / 1 / 1 |
| patterns.setChannelLoop | 0 | channel, loopPoint | `ii` / 2 / 2 |
| screen.addTextLine | 0 | text, line | `siiii` / 5 / 5 (**不一致のまま。§3**) |
| screen.fillRect | 0 | 5 個 | `iiiii` / 5 / 5 |
| screen.init | 0 | 6 個 | `iiiiii` / 6 / 6 |
| screen.setup | 0 | 6 個 | `Liiiii` / 6 / 6 |

## 2. 修正 (commit `1530a544`)

- `tools/python/analysis/flapi_table.py`: 引数の名前と既定値を `a.posonlyargs + a.args` の順に対応させる (5 行)。
- 再生成: `FLPY_TABLE_ONLY=1 bash build_flpy.sh` (`flapi_table.json` +225 −15 行)、`python3 provider/gen_provider.py` (`provider/gen/fl_table.c` の 15 行を置換)。
- 修正前の生成器で再生成すると、追跡中の 3 ファイル (`flapi_table.json`・`flapi_ids.json`・`FLAPI.md`) とバイト一致した (差分 0)。このため再生成の差分は修正だけに由来する。
- `tools/python/tests/kwsig_check.py`: 比較件数の期待値を `(224, 208)` から `(229, 213)` に更新した。増えた 5 件は全て同結果で、差の出る関数 (11 件) は変わらない。

## 3. 引数個数の一致 (`analysis/flapi/sig_arity_check.py`)

```
$ git show 1530a544~1:tools/python/analysis/flapi/flapi_table.json > before.json
$ python3 analysis/flapi/sig_arity_check.py before.json analysis/flapi/flapi_table.json
before: 対象 273 件・一致 235・不一致 38
after : 対象 273 件・一致 249・不一致 24
署名の引数個数が変わった関数: 15 件
```

- 14 件は PE の max と一致する。
- `screen.addTextLine`: stub は `addTextLine(text: str, line: int, /)` (2 引数)、PE 書式は `siiii` (5 引数)。変更前は 0 引数、変更後は 2 引数で、どちらも PE と一致しない。生成器は stub を署名の正としている。
- 残りの不一致 23 件 (`screen.addTextLine` を除く) は変更前から存在する stub と PE の食い違い。例: `channels.soloChannel` 2/3・`patterns.clonePattern` 1/2・`screen.drawText` 0/6。

## 4. 検証 (測定 commit の内容)

| 検証 | 実行 | 結果 |
|---|---|---|
| 生成器の再現 | `FLPY_TABLE_ONLY=1 bash build_flpy.sh` (修正前の生成器) | 追跡中の 3 ファイルと一致 (0.8 s) |
| 表の検査・ネガコン | `bash tests/flapi_table_check.sh` | 正常系の差分 0/3・win_pair_verified 388 件。ネガコン 6/6 PASS (1.8 s) |
| kwsig 照合 | `python3 tests/kwsig_check.py` | OK (比較 229 件・同結果 213・差 11 関数) |
| kwsig 束縛 | `python3 tests/kwsig_bind_check.py` | PASS (103 関数・6122 ケース・misbind 0・mismatch 0) |
| C provider build | `bash provider/build.sh` | 成功 (0.99 s)。`gen_provider.py --check-handlers`: 435 関数・ハンドラ 70 (変更前と同じ) |
| CPython wasm | `bash build_cpython_wasm.sh` | 163 s (2 分 43 秒。issue の『約 4 分』より短い) |
| flpy wasm | `FLPY_SKIP_TABLE=1 EMSDK_DIR=[EMSDK] bash build_flpy.sh` | 3.9 s |
| wasm 全 tool | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok・soft_error 0・raised 0 (1.15 s) |
| mock 全 tool | `node tests/all_tools.mjs` | 48/48 ok (`analysis/mcp/tool_coverage.json` 変更なし) |
| channels 差分 | `node tests/channels_diff.mjs` | calls 53・diffs 0・PASS |
| provider ABI | `node tests/provider_check.mjs` | PASS (functions 435・implemented 70・unimplemented 365) |
| device / mixer 差分 | `node tests/device_diff.mjs`・`node tests/mixer_diff.mjs` | device: calls 7・diffs 0。mixer: calls 48・diffs 0 |

ネガコン (生成器の修正の効き): `analysis/flapi_table.py` の `posonlyargs + args` を `args` に戻した複製で再生成すると、`channels.processRECEvent` の params は `[]` に戻り、修正後の表との差は 15 件になった。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `processRECEvent` の戻り値・範囲外 code・副作用の確定と実装 | 呼出しは未実装エラー | #2544 (PY-72) |
| `incEventValue`・`midiNoteOn` の戻り値・範囲外 code・副作用の確定と実装 | 同上 | #2547 (PY-73) |
| `setStepParameterByIndex` の戻り値・範囲外 code・副作用の確定と実装 | 同上 | #2548 (PY-74) |
| `screen.addTextLine`: stub 2 引数 / PE 5 引数 | 2 引数の呼出しは通り、5 引数の呼出しは個数違反になる | #1527 へ提案 (生成器で PE 書式を個数の正とする案) |
| stub と PE の引数個数の不一致 23 件 (`screen.addTextLine` を除く・変更前から存在・`screen.*` の 0 引数表記を含む) | 表の個数が PE と違う関数がある | #1527 へ提案 (同上) |

## 6. DEFECTS.md への行案 (報告のみ。DEFECTS.md は未編集)

- 類型 (候補): 位置専用引数の読み落とし (生成器)。症状: `/` 付きの stub 署名が 0 引数の表になり、正しい呼出しが個数違反で失敗する。根本原因: `FunctionDef.args.args` だけを読み `posonlyargs` を捨てた。観測: `channels.processRECEvent` の表 params=`[]`・PE 書式 `Iii`。検出信号: `analysis/flapi/sig_arity_check.py` の不一致数。修復: `posonlyargs + args` (`1530a544`)。

## 7. 事前推定と実測の差

- issue の『`build_cpython_wasm.sh` 約 4 分』: 実測 163 s。
- issue の『processRECEvent の flapi 署名の修正』: 生成器の 1 行 (`posonlyargs`) で足りた。下位関数の解析は不要だった。
