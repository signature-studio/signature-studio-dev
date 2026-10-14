> **正本**: 本書 (`tools/pm/REPORT_APPENDIX_2591.md`) が #2591 の検証記録の正本。`tools/pm/REPORT.md` は 250 行上限のため本体へ追記しない (`docs/DOC_MAP.md` §1)。pm.md の文字列検査の前歴は `tools/pm/REPORT_APPENDIX_2349.md`。

# #2591: pm.md の needs_decision を PR 起点に直し、rule=skip と投稿前の確認を足す (検証記録)

修正本体は PR #2603 (merge commit `c1d1df36`・本体 commit `e6bff4e1`) で main に入り、#2591 は closed になった。
本 PR (`2591-pm-needs-decision`) は同じ #2591 の重複で、pm.md・`docs/WORKFLOW.md`・`test-dispatch-context.sh` の変更は main と競合した。
競合は main の版を採った (main の版は同じ修正に後続の編集 `ab088b8f` 等を加えたもの。本 PR の版で上書きすると main の変更が戻る)。
本 PR に残るのは本付録と `docs/DOC_MAP.md` の登録行だけで、main の版の検証記録である。

既知類型との関係: 該当なし (lift の欠陥ではなく PM 運用の prompt)。

## 1. 現状

- 本 PR の main 基準の差分: `tools/pm/REPORT_APPENDIX_2591.md` と `docs/DOC_MAP.md` の 1 行。
- `.github/`・`docs/WORKFLOW.md`・`infra/pm-worker/` は main と同一 (差分 0 行)。
- 前の head `57f65cea` の pm.md 版は main に無い。その版の測定は §2 の履歴に残す。

## 2. 測定

- 測定 commit: `cd414208` (origin/main `588c0457` を取り込んだ merge。`.github` は origin/main と同一)。
- 環境: GitHub Actions の runner。測定時の load average `0.02 0.19 0.16`。

| 測定 | 結果 | 所要 |
|---|---|---:|
| `bash .github/scripts/tests/test-dispatch-context.sh` | 143 passed, 0 failed | 3.5 s |
| ネガコン: pm.md から `<!-- oc-pm-decision: rule=skip reversible=yes -->` の行を削除 (測定用の detached worktree で行い、本 PR の作業ツリーは変えない) | 142 passed, 1 failed (FAIL: `pm.md: rule=skip for no target (R9 is not reused)`) | — |

他のテスト (測定 commit `cd414208`):

- `.github/scripts/tests/test-*.sh` の残り 7 本は rc 0: `no-pr-outcome` (18 passed)・`opencode-stdin` (rc 0)・`pr-lint` (pass=22 fail=0)・`pr-loop` (72 passed)・`run-outcome` (49 passed)・`watchdog` (116 passed)・`workflow-pm-job` (40 passed)。
- `python3 -m unittest discover -s tools/pm -p 'test_*.py'`: `Ran 42 tests` で OK。

履歴 (前の head の pm.md 版。測定 commit `870c381e`。main には無い): 変更前 135 passed → 変更後 150 passed, 0 failed。その版のネガコンは 148 passed, 2 failed。

## 3. 受入条件の判定 (issue #2591 の 8 条件・main の版)

| # | 受入条件 | 判定 | 根拠 (main の `.github/prompts/pm.md`・`docs/WORKFLOW.md`) |
|---|---|---|---|
| 1 | `needs_decision` を PR 起点に書き直す | 達成 | pm.md 行 172〜187 (ref は PR 番号。Worker の条件は行 177) |
| 2 | `rule=skip` を新設し R9 の流用をやめる | 達成 | pm.md 行 71 (`rule` の欄)・行 76〜89 (「対象なし」)・行 116 (R9 の欄) |
| 3 | `/oc` を含む文字列を書かない・投稿前に件数を検査・言い換え | 達成 | pm.md 行 33〜36 (書いてはいけない操作)・行 146 (不変条件)・行 224〜225 (完了時) |
| 4 | 質問の前に対象の closed・merge 済み・post-merge review を確かめる | 達成 | pm.md 行 132〜138 |
| 5 | closed の issue から `needs-user-input` を外す | 達成 | pm.md 行 140〜141 |
| 6 | marker 仕様・`infra/pm-worker/`・`.github/workflows/` は変えない | 達成 | `git show --stat e6bff4e1` の変更は pm.md・テスト・WORKFLOW の 3 ファイルのみ (`infra/pm-worker/`・`.github/workflows/` は含まない)。`infra/pm-worker/` は後続の main (#2592) で変わったが、#2591 の変更ではない |
| 7 | WORKFLOW §12 は pm.md を参照する範囲だけ | 達成 | `docs/WORKFLOW.md` 行 429〜436 |
| 8 | `test-dispatch-context.sh` の pm.md 節が通る | 達成 | 143 passed, 0 failed (§2) |

- issue 本文の「post-merge review」は repo の文書に定義が無い。pm.md 行 138 は「merge 済みの PR に、merge より後に付いた reviewer の verdict またはコメント」と具体的に書いている。

## 4. 測定後のコード差分

`git diff cd414208 HEAD -- .github infra/pm-worker` の出力: 0 行。本付録を含む docs-only の commit は、この範囲の外だけを変える。

## 5. 未解決 (追跡のみ・子は起票しない: `docs/WORKFLOW.md` §3)

- live の PM run で `needs_decision` が PR 起点で動き、判断の印が PR に付くことは、次の実 run の digest (`rule=skip` の件数) で観測する。本付録は文書と検査だけを測り、live の挙動は測っていない。
