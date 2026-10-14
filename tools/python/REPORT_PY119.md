# tools/python REPORT: PY-119 general の setter 6 件の PE 確定と C provider 実装 (#2977, 親 #2830, 先行 #2738・PY-87)

> 正本: `tools/python/REPORT_PY87.md` (getter 4 件・手本)。本付録は setter 6 件の実測のみ。PY-94 (#2830) の REPORT は存在しなかった (枝・PR も無し)。

## 結論

- `general.setRecPPQ` / `setNumerator` / `setDenominator` / `setUndoHistoryPos` / `setUndoHistoryCount` / `setUndoHistoryLast` の 6 件を PE で確定し、mock と C provider に実装した。`tests/general_diff.mjs` は 21 呼出し + 引数個数違い 4 件で差分 0。
- 6 件とも「ゲートが偽なら status -2 / 範囲外なら status -3 / 通過時のみ本体を呼ぶ」の型。範囲は PE の即値で確定 (下表)。undo 3 件は範囲検査が無く、値を kind 別の engine 状態フィールドへ書くだけ。
- **未確定**: ゲート (`safeToEdit` 相当) の実機値、status → Python 例外型の同定、本体 setter の副作用。ゲートは真と仮定した (mock/C とも `-2` 経路は実行されない)。既定値 (numerator 4 / denominator 4 / undo 0) は仮置きで実測していない。

## 手段

- 先行: 共通 dispatch `0xd843d0`・status 文言表 (-1..-4)・guard G は `REPORT_PY72.md` (setChannelPitch) で確定済み。本付録は setter 6 件の範囲・kind・書込み先を追加する。
- 入力: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64 --wildcards '*block00031_PE.bin'` (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)。
- ハンドラ特定: `python3 analysis/flapi/pe_handler_probe.py setNumerator setDenominator setRecPPQ setUndoHistoryPos setUndoHistoryCount setUndoHistoryLast`。
- 本体・共通処理: `python3 analysis/flapi/pe_disasm.py <VA> <命令数>`。文言: `python3 analysis/flapi/pe_cstr.py <VA...>` (本 PR で追加)。
- 6 関数の wrapper は同形: IAT 経由の引数解析 (書式 `"i"`・文字列 VA 0xd694d4 ほか。関数名は未同定) → `0xd6a8e0(self)` → 共通 dispatch `0xd843d0`。dispatch の 5 番目引数が値 ([rbx+0x18])、6 番目が kind ([rbx+0x20])。dispatch は out `[rsi]` を -2 で初期化し、callback の終了後に callback の status `[rbx+0x60]` を写す。status は `0xd82c20` で Python 例外へ変換する。

## 6 関数の確定表 (PE VA)

| 関数 | entry | wrapper fn | callback | 範囲 (通過条件) | 本体 (通過時) | kind |
|---|---|---|---|---|---|---|
| `general.setRecPPQ` | 0x151aa80 | 0xd693c0 | 0xd69350 | 24 ≤ v ≤ 960 (0x18..0x3c0) | `0x1362c60`(`[[0x15e13b8]]`, v) | - |
| `general.setNumerator` | 0x151aaa0 | 0xd69550 | 0xd694e0 | 1 ≤ v ≤ 16 (0x10) | `0x1366950`(`[[0x15e13b8]]`, v) | - |
| `general.setDenominator` | 0x151aac0 | 0xd696e0 | 0xd69670 | 2 ≤ v ≤ 16 (0x10) | `0x13669d0`(`[[0x15e13b8]]`, v) | - |
| `general.setUndoHistoryPos` | 0x151abc0 | 0xd69b80 | 0xd69af0 (共有) | 範囲検査なし | v を `[[0x15e1c78]]+0x1c` へ | 0 |
| `general.setUndoHistoryCount` | 0x151abe0 | 0xd69ca0 | 0xd69af0 (共有) | 範囲検査なし | v を `[[0x15e1c78]]+0x24` へ | 1 |
| `general.setUndoHistoryLast` | 0x151ac00 | 0xd69dc0 | 0xd69af0 (共有) | 範囲検査なし | v を `[[0x15e1c78]]+0x20` へ | 2 |

- `[[X]]` は「X の値 (ポインタ) の指す値」。VA は各 `mov rax, [rip+d]` の次命令アドレス + d で求めた (例: 0xd69367 + 0x87b429 = 0x15e4790)。

- 範囲は callback の `cmp rax, imm` の即値 (`0xd69350`: 0x18/0x3c0、`0xd694e0`: 1/0x10、`0xd69670`: 2/0x10)。範囲外で `[rbx+0x60] = -3` を書く箇所は 0xd693ac (setRecPPQ)・0xd6953a (setNumerator)・0xd696ca (setDenominator)。
- undo 3 件の kind は wrapper の 6 番目引数 (`mov [rsp+0x28], 0/1/2`・それぞれ 0xd69bf7・0xd69d17・0xd69e37)。callback `0xd69af0` の分岐 (`sub eax,1` の連鎖) で書込み先が決まる。kind が 0〜2 以外なら書かずに status 0。
- 3 関数 (Pos/Count/Last) は同じ global `0x15e1c78` から同じオブジェクトを取り、別フィールド (+0x1c/+0x24/+0x20) に書く。オブジェクトの型・フィールド名は未同定 (名前は issue の `setUndoHistory*` に従った)。

## ゲート (-2 "Operation unsafe at current time")

- 4 callback は共通の先頭処理として `[[G]]+8` の vtbl[0x98] の戻り値 (bool) を見る。G = 0x15e4790 (4 callback とも同じ。PY-72 の guard G と同じ)。
- PY-87 の `general.safeToEdit` (0xd6a2c0) が同じ vtbl[0x98] を返すことから、このゲートは `safeToEdit` 相当と推定 (推定。object の同一性は未確定)。
- 偽なら status -2 (callback 内で `[rbx+0x60]` が -2 のまま)。mock/C は真と仮定。

## status → Python 例外 (`0xd82c20`)

| status | 文言 (VA) | 分岐 (0xd82c…) |
|---|---|---|
| 0 | (文言は使わず None を返す: `PyErr_Occurred` が無ければ `0xc38bc0`) | 0xd82c35 |
| -1 | Unspecified error (0xd82e24) | 0xd82d03 |
| -2 | Operation unsafe at current time (0xd82e44) | 0xd82d18 |
| -3 | Range error (0xd82e74) | 0xd82d2a |
| -4 | Index out of range (0xd82e8c) | 0xd82d3c |
| -5 | Wrong number of function parameters or wrong parameter type (0xd82eac) | 0xd82d4e |
| -6 | Linked device not assigned (0xd82ef4) | 0xd82d60 |
| -7 | Device not assigned (0xd82f1c) | 0xd82d72 |
| -8 | Plugin not valid (0xd82f3c) | 0xd82d84 |
| その他の負数 | Unknown error (0xd82f5c) | 0xd82d96 |

- 文言は `0xd82c20` の `lea rdx` 先の C 文字列 (`pe_cstr.py` で読んだ)。例外型は global `0x15e1140` の `*(*(0x15e1140))` で、全 status で共通。型 object の同一性は未確定。
- 負数で、ゲート (G = 0x15e4790 の `[[G]]+8` の vtbl[0x88]) が偽なら例外無しで None (0xd82c6a〜0xd82c86)。vtbl[0x88] の意味は未同定。
- C 側は `provider/fl_api.h` の暫定 code (2 Unspecified・3 Unsafe・4 Range/IndexError・5 WrongParam) をそのまま使った。PE の status (-1..-8) と C の code (1..8) の対応は本 PR では確定していない。PE の単一型とも整合しない可能性があり、未解決。

## 実装

- `host/fl_mock.mjs`: 6 関数。範囲外は `RANGE("Range error")` (code 4)。undo 3 件は値を `st.undoHistoryPos/Count/Last` に記録。既定値 `numerator 4`・`denominator 4`・undo 0 は仮置き。
- `provider/fl_engine.c`: 同じ 6 関数。`RANGE_MSG(m)` マクロを追加 (文言を変えるため)。`fl_table.c` は再生成していない (weak 宣言が既にある)。
- `tests/provider_check.mjs`: 実装 86 → 92、未実装 349 → 343 (総数 435 は不変)。`pe119` 集合 6 件を追加。基準の 86 は main の `pe100` (`channels.getStepParam`・`getCurrentStepParam`) と `pe115` (`mixer.getTrackColor`, PY-115) を含む (main 取り込み後の値。PR 単独の差分は 83 → 89)。
- `tests/general_diff.mjs`: 呼出し 21 件 (setRecPPQ 4・setNumerator 4・setDenominator 4・undo 4 と既存 5) + 引数個数違い 4 件 = 計 25。

## 検証

測定 commit: `07dfe30d` (コードを変えた最後の commit。main `940c0d6a` を merge した commit)。merge の競合は 2 件。`tests/provider_check.mjs` は main 側の `pe100`・`pe115` と本 PR の `pe119` の 3 集合を残し、件数を 92 / 343 に直した。`docs/DOC_MAP.md` は両側の行 (PY-119 と PY-121) を残した。作業ツリーは `git status` 空で測定した。前提: `fetch_inputs.sh` (rc 0)・`build_cpython_wasm.sh` (rc 0、4 分 05 秒。この実行は main 取り込み前の `fd542167` で行い、`8afbdbef`→`940c0d6a` の間にビルド側の変更は無い)・`FLPY_SKIP_TABLE=1 build_flpy.sh` (rc 0、5.9 秒) と `provider/build.sh` を `07dfe30d` で再実行。`fl-win64` は `$ARTIFACTS_DIR` から DATA block 4 件だけを展開 (`midi.py`・`utils.py`・`MCPTools.pyc`・device script)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0・ハンドラ 92 | 0.90 秒 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 92 / 未実装 343 / MCP 静的 60) | 0.36 秒 |
| `node tests/general_diff.mjs` | calls 25、diffs 0、PASS | 0.05 秒 |
| `node tests/ui_diff.mjs` | calls 17、diffs 0、範囲外既知差分 3、PASS | 0.06 秒 |
| `node tests/channels_diff.mjs` | calls 161、diffs 0、PASS | 0.07 秒 |
| `node tests/mixer_diff.mjs` | calls 57、diffs 0、PASS | 0.07 秒 |
| `node tests/device_diff.mjs` | calls 8、rejects 4、midi_out 5、diffs 0、PASS | 0.07 秒 |
| `node tests/ilmcp_diff.mjs` | calls 32、state_checks 9、diffs 0、PASS | 0.07 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 2.17 秒 |

- 測定時の load average: 0.39 (1 分平均、`uptime` 21:21:34、4 core)。
- ネガティブコントロール (`07dfe30d` で実施): `host/fl_mock.mjs` の `setNumerator` の上限を 16 → 15 に変えると `node tests/general_diff.mjs` は `general.setNumerator` の args `[16]` の差分で rc 1 (FAIL)。元に戻すと calls 25・diffs 0・PASS (rc 0)。
- コード差分 (測定 commit から PR HEAD まで、`tools/python` の .md 以外): 本 REPORT を含む md のみの commit を後から足しても 0 行。

```
$ git diff 07dfe30d HEAD -- tools/python ':!*.md'
(空)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ゲート (`safeToEdit` 相当 vtbl[0x98]・4 slot) の実機値と、ゲート偽の経路 (-2) | mock/C は真と仮定。-2 は未検証 | 親 #2830 にコメント (PY-94 の `safeToEdit` 確定と併せる) |
| 例外型 global `0x15e1140` と、C 側 code 表 (暫定) の一致 | Python 側の例外型が PE と一致する保証なし | 親 #2830 にコメント |
| 本体 setter `0x1362c60`・`0x1366950`・`0x13669d0` と undo 書込み先 (+0x1c/+0x24/+0x20) の副作用 | mock は値を記録するだけ。engine 状態への影響は未確認 | 親 #2830 にコメント |
| 既定値 numerator 4・denominator 4・undo 0 | 仮置き。実機値は未測定 | 親 #2830 にコメント |
| 0xd84f30 (dispatch の [obj+0x50] 判定) と 0xd82c6a の gate の意味 | 負数時の None 返しの条件が未確定 | 親 #2830 にコメント |

## 範囲外

- undo 系の getter・`undo`/`saveUndo` 等 (#2830 の残り) と log/rec 系は本 issue の範囲外。
