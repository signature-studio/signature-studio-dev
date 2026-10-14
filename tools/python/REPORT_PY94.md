# tools/python REPORT: PY-94 general 保留 25 件の PE 確定のうち 7 件と C provider 実装 (#2830, 親 #2738, 子 #2978・#3001〜#3003。#2977・#2979 は closed)

既知類型との関係: 該当なし (lift・IR pass ではなく、PE の読出し (逆アセンブル) と mock/C の実装のみ。`docs/DEFECTS.md` の D1a〜D23 は対象外)。
> 正本: `tools/python/REPORT_PY87.md` (PY-87 の手段と保留 146 件の内訳)。本付録は PY-94 の実測のみ。

## 結論

- 保留 25 件のうち **7 件** の読み元を PE で確定し、mock と C provider に実装した (mock と C の差分 0)。
  内訳: int 3 件 (`getUndoHistoryPos` / `getUndoHistoryCount` / `getUndoHistoryLast`)、bool 1 件 (`safeToEdit`)、str 3 件 (`getProjectTitle` / `getProjectAuthor` / `getProjectGenre`)。
- **値は未確定**。7 件とも仮置き (int `0` / bool `true` / str `""`)。実機の値は未実測で、mock の値を正として扱わないこと。
- 残り **12 件** は子 issue 4 件に分けた (下の表)。setter 6 件 (#2977) は main の #3015 で実装済み (PE 根拠は `tools/python/REPORT_PY119_2977.md`)。確定に至らなかった理由は、undo 系の共通処理 (`0xd6a8e0`・`0xd84680`) と、`getRecPPB` の状態切替 (`0xd68d90`) が未同定のため。

| 子 issue | 対象 | 件数 | 状態 |
|---|---|---|---|
| #2977 (PY-119) | setNumerator・setDenominator・setRecPPQ・setUndoHistoryPos・setUndoHistoryCount・setUndoHistoryLast (main #3015 で実装) | 6 | closed |
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

## 残り 12 件 (子 issue へ)

- undo 系 8 件 (#2978): `undo` / `undoUp` / `undoDown` / `undoUpDown` は対象オブジェクト取得 `0xd6a8e0`・bool 取得 `0xfdd270`・dispatch `0xd84680` を使い、コマンド id は `undo` `0x14`・`undoUp` `0x15`・`undoDown` `0x16` (`undoUpDown` は同じ `0x16` で第 4 引数が引数の値)。`restoreUndoLevel` は `0xd843d0` とコールバック `0xd690f0`。`saveUndo` は書式 `si|i` を読むが、その後は未解析。`getUndoLevelHint` は `0x1016e60` の結果から文字列を得るが、由来は未同定。
- log・rec 系 4 件 (#3001〜#3003): `clearLog` は引数なしで `0xd843d0` を呼び、コールバック `0xd6a1a0`。`dumpScoreLog` は書式 `i|i`。`processRECEvent` (general) は `0xd84740` に int 3 個を渡す。`getRecPPB` は `0xd68d90` の戻り値の dword `+0xb20` を読む。`0xd68d90` は `F = [0x15e4558]` とし、`[F] != 0` なら `[F]`、`[F] == 0` なら `[[0x15e35c8]]` を返す。どちらが正かは未同定。

## 実装

- `host/fl_mock.mjs`: 状態 `undoPos` / `undoCount` / `undoLast` / `safeEdit` / `projTitle` / `projAuthor` / `projGenre` と、7 件の getter (NOARGS)。
- `provider/fl_engine.c`: 同名の static 状態と `FL_H(general, ...)` 7 件。`fl_engine_reset` で初期化。`fl_ret_i` / `fl_ret_b` / `fl_ret_s`。
- `tests/general_diff.mjs`: 呼出し 7 件を追加。引数個数違い 2 件 (`safeToEdit [1]`・`getProjectTitle [0]`) を追加。main の setter 16 件 (引数個数違い) と両方を残した。件数は下の `## 検証` 節。
- `tests/provider_check.mjs`: `pe94` 集合 7 件を追加。期待値 (実装 126 / 未実装 309) は下の `## 検証` 節。
- main 取り込み (`3e76267f`) での解消: main の undo setter 3 件は別名の状態 (`undoHistoryPos` 等) に書いていたため、getter と同じ `undoPos`・`undoCount`・`undoLast` (C は `undo_pos`・`undo_count`・`undo_last`) に統一した。C 側の `static` 再宣言は重複するため削除した。

## 検証

測定 commit: `10bfa15b` (main `91610209` の取り込みの merge。`tools/python` のコードを変えた最後の commit)。以降の commit は `.md` だけを変える。

main の取り込みで 4 ファイルが競合した (`docs/DOC_MAP.md`・`host/fl_mock.mjs`・`provider/fl_engine.c`・`tests/provider_check.mjs`)。解消方針:
- `docs/DOC_MAP.md`: 本 PR の `REPORT_PY94.md` 行と main の `REPORT_PY96.md` 行を両方残した。
- `host/fl_mock.mjs`・`provider/fl_engine.c`: 両側の項目を残した。main の選択範囲の状態 (`selStart`・`selEnd`、C は `sel_start`・`sel_end`) と `arr_time` を残した。main 側の `undoHistory*` の状態行は採らず、前の取り込みからの統一 (`undoPos`・`undoCount`・`undoLast`) を保った。
- `tests/provider_check.mjs`: `pe94`・`pe96`・`pe121_2982` を含む判定集合を全て残した。期待値は **実装 126 / 未実装 309** (main の 119 (pe96 の 4 件と pe121_2982 の 6 件を含む) に pe94 の 7 件を足した値。total 435、MCP 静的 60)。

環境: runner 4 core。検証開始直前の load average 0.14 / 0.25 / 0.12 (`uptime`)。素材は `$ARTIFACTS_DIR` の `fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に展開し (5 秒)、`FL_WIN64_DIR` に指定した。emsdk は runner の `[EMSDK]` (`/opt/emsdk`) を `provider/build.sh` が既定の `EMSDK_ENV` で読んだ。`toolchain-emsdk.tar.zst` は展開していない。

前提の生成物 (gitignore。worktree を新規に作ったため `work/` は再利用せず、すべて新規に生成した):

| コマンド | 結果 |
|---|---|
| `bash fetch_inputs.sh` | rc 0 (0.3 秒。win64 の DATA block から取得) |
| `bash build_cpython_wasm.sh` | rc 0 (実測 4 分 1.7 秒) |
| `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | rc 0 (6.1 秒) |
| `bash build_flpy_static.sh` | rc 0 (6.5 秒) |

テスト (測定 commit `10bfa15b`):

| コマンド | 結果 |
|---|---|
| `bash provider/build.sh` | rc 0・ハンドラ 126 (`fl_table.c`: 435 関数) |
| `node tests/provider_check.mjs` | PASS (435 / 実装 126 / 未実装 309 / MCP 静的 60) |
| `node tests/general_diff.mjs` | calls 34・diffs 0・PASS |
| `node tests/ui_diff.mjs` | calls 17・diffs 0・範囲外既知差分 3・PASS |
| `node tests/channels_diff.mjs` | calls 161・diffs 0・PASS |
| `node tests/mixer_diff.mjs` | calls 59・diffs 0・PASS |
| `node tests/screen_diff.mjs` | calls 32・diffs 0・PASS |
| `node tests/ui_state_diff.mjs` | calls 12・diffs 0・PASS |
| `node tests/device_diff.mjs` | calls 8・rejects 4・midi_out 5・diffs 0・PASS |
| `node tests/arrangement_diff.mjs` (main 由来) | calls 25・diffs 0・PASS |
| `node tests/arrangement_selection_diff.mjs` (main 由来) | calls 8・diffs 0・PASS |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok・host_calls 37,425・callback_roundtrip true |
| `node tests/static_check.mjs` | `STATIC CHECK OK` |

- ネガティブコントロール (`docs/WORKFLOW.md` §5): `host/fl_mock.mjs` の `undoPos` 既定値 (24 行目) を 0 から 1 にすると、`node tests/general_diff.mjs` は `AssertionError [ERR_ASSERTION]: general 差分 1 件` で rc 1 (FAIL)。元に戻す (cmp で一致を確認し、`git diff` が空) と calls 34・diffs 0・PASS (rc 0)。
- コード差分 (測定 commit から HEAD まで。`tools/python` の .md 以外):

```
$ git diff 10bfa15b HEAD -- tools/python ':!*.md'
(空)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 7 関数の値 (`0` / `true` / `""`) は仮置き・未実測 | mock と C は揃うが、実機の値との一致は未確認。実測には FLEngine の起動が要る | 親 #2738 へ提案 (実測の単独 issue は、起動の前提が揃ってから起票) |
| 残り 12 関数 | 未実装 | #2978 (PY-120)・#3001 (PY-125)・#3002 (PY-126)・#3003 (PY-127) |
| `0xd6a8e0`・`0xd84680`・`0xd843d0`・`0xd82c20` の意味 (共通処理) | undo の範囲 code と status 対応が未確定。setter の未確定点は `tools/python/REPORT_PY119_2977.md` の未解決表 (#2977 は closed) | #2978 (受入条件に含む) |
| `getProjectTitle` / `Author` / `Genre` の vtbl スロットの意味 (`+0x20`・`+0x28`・`+0x30`) | 関数名からの対応で、スロットの同定は未了 | 親 #2738 へ提案 (単独の子 issue にするほどではない) |
