# tools/python REPORT: PY-94 general 保留 25 件の PE 確定のうち 7 件と C provider 実装 (#2830, 親 #2738, 子 #2977・#2978・#2979)

既知類型との関係: 該当なし (lift・IR pass ではなく、PE の読出し (逆アセンブル) と mock/C の実装のみ。`docs/DEFECTS.md` の D1a〜D23 は対象外)。
> 正本: `tools/python/REPORT_PY87.md` (PY-87 の手段と保留 146 件の内訳)。本付録は PY-94 の実測のみ。

## 結論

- 保留 25 件のうち **7 件** の読み元を PE で確定し、mock と C provider に実装した (mock と C の差分 0)。
  内訳: int 3 件 (`getUndoHistoryPos` / `getUndoHistoryCount` / `getUndoHistoryLast`)、bool 1 件 (`safeToEdit`)、str 3 件 (`getProjectTitle` / `getProjectAuthor` / `getProjectGenre`)。
- **値は未確定**。7 件とも仮置き (int `0` / bool `true` / str `""`)。実機の値は未実測で、mock の値を正として扱わないこと。
- 残り **18 件** は子 issue 5 件に分けた (下の表)。確定に至らなかった理由は、setter の status と Python 例外 code の対応 (`0xd82c20`)、undo 系の共通処理 (`0xd6a8e0`・`0xd84680`)、`getRecPPB` の状態切替 (`0xd68d90`) が未同定のため。

| 子 issue | 対象 | 件数 | 状態 |
|---|---|---|---|
| #2977 (PY-119) | setNumerator・setDenominator・setRecPPQ・setUndoHistoryPos・setUndoHistoryCount・setUndoHistoryLast | 6 | open |
| #2978 (PY-120) | undo・undoUp・undoDown・undoUpDown・restoreUndo・restoreUndoLevel・saveUndo・getUndoLevelHint | 8 | open |
| #3001 (PY-125) | clearLog・dumpScoreLog | 2 | open |
| #3002 (PY-126) | processRECEvent | 1 | open |
| #3003 (PY-127) | getRecPPB | 1 | open |

#2979 (PY-121) は closed。log・rec 系 4 件の PE 根拠は main の `tools/python/REPORT_PY121.md` (#3004) にあり、残りの実装は #3001〜#3003 が追跡する。

## 手段

- ハンドラ探索: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_handler_probe.py <名前...>` (PY-87 と同じ。PyMethodDef のエントリ VA と fn VA と先頭 40 命令)。
- 任意 VA の逆アセンブル: `python3 analysis/flapi/pe_disasm.py <VA(16進)> [命令数]` (今回は `0xd69350`・`0xd68d90` の確認に使用)。
- 展開: fetch_inputs.sh は DATA block (`block24429_DATA.bin` 等) を要るため、`fl-win64` は全体を `$RUNNER_TEMP/fl-win64` に展開した (`extracted/` が `FL_WIN64_DIR` の直下)。PE だけなら `--wildcards '*block00031_PE.bin'` でも足りる。
- 注意: `processRECEvent` は PE に名前が 2 つある (entry `0x15171c8` は別モジュール (fn `0xd58e00`)、general の entry は `0x151ac40` → fn `0xd69f00`)。general 側を採った。
- 変換: int と bool は同じ間接スロット `0x15e4280` を通る (PY-87 と同じ。bool/int は PE から区別できない)。str は別の間接スロットを通る。
- 注記: `undo` (entry `0x151a960`) と `restoreUndo` (entry `0x151a9e0`) は同じ fn `0xd68dc0` を指す。子 issue #2978 で同一性を確認する。

## 確定した 7 関数 (PE 根拠)

RIP 相対の参照先は「次命令の VA + disp」で求めた。`**[G]` は `[[G]]` (二重間接)。

| 関数 | entry | fn (VA) | 読む状態 (PE) | 変換 | stub の戻り型 | 仮置き (mock/C) |
|---|---|---|---|---|---|---|
| `general.getUndoHistoryPos` | 0x151ab60 | 0xd69a90 | `[[0x15e1c78]]` の dword `+0x1c` | int (0x15e4280) | int | 0 |
| `general.getUndoHistoryCount` | 0x151ab80 | 0xd69ab0 | 同じ `[[0x15e1c78]]` の dword `+0x24` | int | int | 0 |
| `general.getUndoHistoryLast` | 0x151aba0 | 0xd69ad0 | 同じ `[[0x15e1c78]]` の dword `+0x20` | int | int | 0 |
| `general.safeToEdit` | 0x151aca0 | 0xd6a2c0 | `[[[0x15e4790]]+8]` の vtbl `+0x98` の戻り値 (bool) | movzx → 0x15e4280 | bool | true |
| `general.getProjectTitle` | 0x151acc0 | 0xd6a2f0 | `[[[0x15e4790]]+0x10]` の vtbl `+0x20` が FL 文字列を埋める → 0x41c420 → 0x414000 → str 変換 | str | str | `""` |
| `general.getProjectAuthor` | 0x151ace0 | 0xd6a3a0 | 同 `+0x10` の vtbl `+0x28` | str | str | `""` |
| `general.getProjectGenre` | 0x151ad00 | 0xd6a450 | 同 `+0x10` の vtbl `+0x30` | str | str | `""` |

- 4 系統の確認: (1) `getUndoHistory*` の 3 件は同じ global `0x15e1c78` の先の 1 つの構造体で、オフセットだけが違う。(2) `safeToEdit` と `getProjectTitle` 系は、同じ global `0x15e4790` の先を読むが、オフセットが違う (`+8` と `+0x10`)。
- `safeToEdit` のゲートは、`setRecPPQ` のコールバック `0xd69350` と、`setUndoHistoryPos` のコールバック `0xd69af0` が使う vtbl `+0x98` と同じ式。setter 側の判定と、ここで読む bool は同じ値になる。
- **vtbl スロットの意味 (`+0x20` = title、`+0x28` = author、`+0x30` = genre) は関数名からの対応で、未同定**。PE から言えるのは「3 関数が別々のスロットを呼ぶ」ことまで。

## 保留 18 件 (子 issue へ)

- setter 6 件 (#2977): 6 件とも引数を `i` で読み、dispatch `0xd843d0` に値・kind・コールバックを渡す。`setRecPPQ` のコールバック `0xd69350` は、ゲート偽なら status `-2` (`0xfffffffffffffffe`)、値が `24..960` (`0x18..0x3c0`) の外なら status `-3`、通過時のみ `0x1362c60` を呼ぶ。`setNumerator` / `setDenominator` / `setRecPPQ` は kind `0`、`setUndoHistoryPos` / `Count` / `Last` は kind `0` / `1` / `2`。status の Python 例外 code への対応 (`0xd82c20`) は未同定。
- undo 系 8 件 (#2978): `undo` / `undoUp` / `undoDown` / `undoUpDown` は対象オブジェクト取得 `0xd6a8e0`・bool 取得 `0xfdd270`・dispatch `0xd84680` を使い、コマンド id は `undo` `0x14`・`undoUp` `0x15`・`undoDown` `0x16` (`undoUpDown` は同じ `0x16` で第 4 引数が引数の値)。`restoreUndoLevel` は `0xd843d0` とコールバック `0xd690f0`。`saveUndo` は書式 `si|i` を読むが、その後は未解析。`getUndoLevelHint` は `0x1016e60` の結果から文字列を得るが、由来は未同定。
- log・rec 系 4 件 (#3001〜#3003): `clearLog` は引数なしで `0xd843d0` を呼び、コールバック `0xd6a1a0`。`dumpScoreLog` は書式 `i|i`。`processRECEvent` (general) は `0xd84740` に int 3 個を渡す。`getRecPPB` は `0xd68d90` の戻り値の dword `+0xb20` を読む。`0xd68d90` は `F = [0x15e4558]` とし、`[F] != 0` なら `[F]`、`[F] == 0` なら `[[0x15e35c8]]` を返す。どちらが正かは未同定。

## 実装

- `host/fl_mock.mjs`: 状態 `undoPos` / `undoCount` / `undoLast` / `safeEdit` / `projTitle` / `projAuthor` / `projGenre` と、7 件の getter (NOARGS)。
- `provider/fl_engine.c`: 同名の static 状態と `FL_H(general, ...)` 7 件。`fl_engine_reset` で初期化。`fl_ret_i` / `fl_ret_b` / `fl_ret_s`。
- `tests/general_diff.mjs`: 呼出し 7 件を追加 (calls 9 → 18)。引数個数違い 2 件 (`safeToEdit [1]`・`getProjectTitle [0]`) を追加。
- `tests/provider_check.mjs`: `pe94` 集合 7 件を追加。main 取り込み後の期待値 (実装 104 / 未実装 331) は下の `## 検証` 節。

## 検証

測定 commit: `219d9688` (main (`3e8c8d25`) の取り込みの merge。`tools/python` の .md 以外で最後にコードを変えた commit。検証 HEAD も同じ commit)。
main の取り込みで `docs/DOC_MAP.md`・`host/fl_mock.mjs`・`provider/fl_engine.c`・`tests/provider_check.mjs` が競合した。解消は両側を残した (PR コメントに方針)。
期待値は、PR の `pe94` 7 件と main の `pe121` 5 件・`pe119` 6 件を合算して **実装 104 / 未実装 331** (total 435、MCP 静的 60)。
前回 (`bdd66a55`・`932c3dbc`) の測定値は PR の履歴に残り、本節には載せない。

環境: runner 4 core。開始時の load average 1.85 / 1.16 / 0.55。`FL_WIN64_DIR` は `fl-win64` の展開先 (`extracted/`)。emsdk は runner の `[EMSDK]` (`toolchain-emsdk` は `$RUNNER_TEMP` に展開して `EMSDK_ENV` で指定し、provider のビルドに使った)。

前提の生成物 (gitignore): `fetch_inputs.sh` (rc 0)・`build_cpython_wasm.sh` (rc 0・164 秒)・`FLPY_SKIP_TABLE=1 build_flpy.sh` (rc 0・4 秒)・`build_flpy_static.sh` (rc 0・4 秒)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0 | 1 秒未満 (実測 `date` の差 0 秒) |
| `node tests/provider_check.mjs` | PASS (435 / 実装 104 / 未実装 331 / MCP 静的 60) | 1 秒未満 |
| `node tests/general_diff.mjs` | calls 18、diffs 0、PASS | 1 秒未満 |
| `node tests/ui_diff.mjs` | calls 17、diffs 0、範囲外既知差分 3、PASS | 1 秒未満 |
| `node tests/channels_diff.mjs` | calls 161、diffs 0、PASS | 1 秒未満 |
| `node tests/mixer_diff.mjs` | calls 59、diffs 0、PASS | 1 秒未満 |
| `node tests/screen_diff.mjs` | calls 32、diffs 0、PASS | 1 秒未満 |
| `node tests/ui_state_diff.mjs` | calls 12、diffs 0、PASS | 1 秒未満 |
| `node tests/device_diff.mjs` | calls 8、rejects 4、midi_out 5、diffs 0、PASS | 1 秒未満 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425 | 1 秒 |
| `node tests/static_check.mjs` | rc 0、`STATIC CHECK OK` | 1 秒未満 |

- 件数: 実装 104 / 未実装 331 (total 435、MCP 静的 60)。`provider_check` の期待値 (104 / 331) と一致。
- ネガティブコントロール (`docs/WORKFLOW.md` §5): `host/fl_mock.mjs` の `undoPos` 既定値 (24 行目) を 0 から 1 にすると、`node tests/general_diff.mjs` は `AssertionError [ERR_ASSERTION]: general 差分 1 件` で rc 1 (FAIL)。元に戻す (cmp で一致を確認) と calls 18・diffs 0・PASS (rc 0)。

コード差分 (測定 commit から HEAD まで。`tools/python` の .md 以外): 測定 commit = HEAD のため 0 行。

```
$ git diff 219d9688 HEAD -- tools/python ':!*.md'
(空)
```

本 REPORT の commit は .md のみのため、この式の出力は 0 行のまま。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 7 関数の値 (`0` / `true` / `""`) は仮置き・未実測 | mock と C は揃うが、実機の値と一致する保証は無い。値の実測には FLEngine の起動が要る | 親 #2738 へ提案 (実測の単独 issue は、起動の前提が揃ってから起票) |
| 残り 18 関数 | 未実装 | #2977 (PY-119)・#2978 (PY-120)・#3001 (PY-125)・#3002 (PY-126)・#3003 (PY-127) |
| `0xd6a8e0`・`0xd84680`・`0xd843d0`・`0xd82c20` の意味 (共通処理) | setter・undo の範囲 code と status 対応が未確定 | #2977・#2978 (受入条件に含む) |
| `getProjectTitle` / `Author` / `Genre` の vtbl スロットの意味 (`+0x20`・`+0x28`・`+0x30`) | 関数名からの対応で、スロットの同定は未了 | 親 #2738 へ提案 (単独の子 issue にするほどではない) |
