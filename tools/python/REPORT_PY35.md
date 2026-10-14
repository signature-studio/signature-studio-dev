# PY-35 (#1345): patterns 未実装 31 関数の意味論の分類と分割

親: #1336 (PY-32) / #1345 (PY-35)。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- patterns の未実装 31 関数は、C provider・mock ともに実装 0 件 (`provider/fl_engine.c` に `FL_H(patterns, *)` 無し、`host/fl_mock.mjs` に patterns 定義無し)。
- 意味論の根拠は repo 内に無い。`analysis/flapi/flapi_table.json` は docstring 1 行と署名のみ、`analysis/flapi/FLAPI.md` は件数表のみ。
- 実機 (FL 26.1.7 `fl-win64`) の逆解析無しに戻り値・副作用を決めると推測実装になるため、本 PR ではコードを変えない。
- 31 件を読み取り系 14 件と、選択・移動・書き込み系 17 件に分けて子 issue に分割する。
  - 読み取り系: #1667 (`[PY-42]`)
  - 選択・移動・書き込み系: #1668 (`[PY-43]`)

## 分類

分類は `analysis/flapi/flapi_table.json` の署名と docstring (動詞) に基づく。実機で副作用が無いと確かめたものではない。

### 読み取り系 (14) → #1667

戻り値のみで、名前から状態変更を示さないもの。

| 関数 | 署名 (flapi_table) |
|---|---|
| getActivePatternGroup | () -> int |
| getBlockSetStatus | (int left, int top, int right, int bottom) -> int |
| getChannelLoopStyle | () -> int |
| getPatternColor | (int index) -> int |
| getPatternGroupCount | () -> int |
| getPatternGroupName | () -> str |
| getPatternLength | (int index) -> int |
| getPatternName | (int index) -> str |
| getPatternsInGroup | () -> tuple[int, ...] |
| isPatternDefault | (int index) -> bool |
| isPatternSelected | (int index) -> bool |
| patternCount | () -> int |
| patternMax | () -> int |
| patternNumber | () -> int |

### 選択・移動・書き込み系 (17) → #1668

選択状態・パターン/チャンネル状態・名前・色・長さ・クローン/移動など、状態を変えると名前から読めるもの。`ensureValidNoteRecord` は戻り値 int だが、名前から記録の整備 (副作用) を含むと読んで書き込み側に入れた。

| 関数 | 種別 |
|---|---|
| deselectAll / selectAll / selectPattern | 選択 |
| jumpToPattern / movePattern / findFirstNextEmptyPat | 移動・探索 |
| ensureValidNoteRecord | 記録の整備 (副作用の疑い) |
| burnLoop / setChannelLoop / setLoopStarterRootNote | ループ系の書き込み |
| clearPattern / clonePattern / duplicatePatternData | パターン内容の書き込み |
| incrementPatternLength / setPatternLength / setPatternColor / setPatternName | パターン属性の書き込み |

## 測定

- 測定 commit: `9fdb44e3` (worktree `ws-1345` の起点 = `origin/main`)。本 PR はコード変更 0 件。
- `git diff 9fdb44e3 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (コード差分 0)。
- `provider_check.mjs` と `all_tools.mjs` は再測定していない (コード差分 0 のため、`docs/WORKFLOW.md` §6 に従う)。

## 未解決

- 31 関数の実機意味論 (戻り値の範囲・副作用・型 code) は未決定。#1667・#1668 で決める。
- 逆解析の方法: `toolchain-retdec` で `fl-win64` の PE を読むか、関数ごとに手作業で追うかは子 issue の担当が決める。
