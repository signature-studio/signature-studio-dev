> **正本**: 本付録 (`tools/pm/REPORT_APPENDIX_2349.md`)。対象は PM Worker の日次 digest (#2349・CI-70)。`tools/pm/REPORT.md` は 250 行上限のため、測定値は本付録だけに置く (REPORT.md からは参照を足さない)。

## 1. 測定の対象と環境

- 測定 commit: `222ad49b` (コードを変えた最後の commit)。範囲は `infra/pm-worker/`・`.github/`・`tools/pm/launch_issues.py`・`tools/pm/test_launch_issues.py`。`main` (`582aa49e`) を merge した `5baedd0f` の後に、rolling issue の除外 `3f993ef1` と docs の修正 `222ad49b` を積んだ。
- 作業ツリーは clean (`git status --short` 0 行) の `222ad49b` で測定。`infra/pm-worker` は `npm ci` (86 packages) 後。
- load average: `npm test` の直前 0.21 (14:56 UTC) / shell テストの直前 0.08 (14:59 UTC)。

## 2. 結果

| 検証 | コマンド | 結果 | 所要 (wall) |
|---|---|---|---:|
| Worker の node テスト (`digest.test.ts` 7 件を含む) | `npm test` (`infra/pm-worker`) | 167 / 167 PASS・0 FAIL | 9.1 s |
| Worker の workerd テスト (vitest・実 Durable Object) | `npm run test:workers` | 3 / 3 PASS | 1.8 s |
| pm.md と dispatch 文脈の検査 (digest 節 11 項目・user_answered 5 項目・rolling 題名の一致を含む) | `bash .github/scripts/tests/test-dispatch-context.sh` | 135 passed・0 failed | 4.8 s |
| launch 判定の Python テスト (rolling 除外のネガコンを含む) | `python3 -m unittest test_launch_issues` (`tools/pm`) | 8 / 8 OK | 0.06 s |

ネガコン (mutation 検出。どれも元に戻した後の `git status` は clean):

- 24 時間ガード: `engine.ts` `digest()` の `if (now - this.meta.digestAt < DIGEST_EVERY_MS) return "skipped";` を `if (false && ...)` に置換 → `digest.test.ts` の 4 件が FAIL (初回・(a)・(b)・送信失敗)。`222ad49b` の作業ツリーで実施。
- rolling 除外: `classify.ts` の `if (DIGEST_ROLLING_RE.test(i.title)) continue;` と `launch_issues.py` の同等行を無効化 → `digest.test.ts` (e) と `test_launch_issues.py` の `test_digest_rolling_issue_is_not_ready` が FAIL。実施は `3f993ef1` の作業ツリー (`git diff 3f993ef1 222ad49b -- infra/pm-worker/src/classify.ts infra/pm-worker/src/pm.ts tools/pm/launch_issues.py` は 0 行。同一内容)。

## 3. 受入条件との対応

| 受入 | 実装 | 検証 |
|---|---|---|
| 1 Worker が 24 時間ごとに `oc-pm kind=digest ref=0` を送る | `engine.ts` `digest()` を `tickInner` が毎 tick 呼ぶ。初回は起点のみ (`meta.digestAt`)。payload は `{kind:"digest", ref:0}` | `digest.test.ts` 初回・(a) |
| 1 dry-run は記録のみ | `would_dispatch_pm` に `digest#0`、`counters.wouldDispatchPm` (POST 0 回) | `digest.test.ts` dry-run |
| 1 pm.md の digest 節 (件数・rolling issue の本文更新・緊急は 1 日 1 件) | `.github/prompts/pm.md` `### digest`。緊急は stuck の天井だけ (投稿先: rolling issue、観測元: `oc:stuck` の open PR 件数) | `test-dispatch-context.sh` 10b |
| 1 rolling issue は launch の対象外 | `classify.ts` と `launch_issues.py` が題名 `DIGEST_ROLLING_RE` で除く (`pm.ts` と同じ形) | `digest.test.ts` (e)・`test_launch_issues.py`・`test-dispatch-context.sh` (題名の一致) |
| 1 緊急の Worker 停止・率制限の alert | 未実装 (PM agent からは観測できない)。pm.md の緊急の一覧から外した | 子 issue #2539 (`[CI-102]`) へ移した。#2349 の本文からも外した |
| 2 pm.md の user_answered 節 (反映・除去・確定コメント・曖昧なら聞き直し) | `.github/prompts/pm.md` `### user_answered` | `test-dispatch-context.sh` 10b |
| 4 (a) 24 時間以内の 2 回目は送らない | `digest.test.ts` (a) | PASS・mutation で FAIL を確認 |
| 4 (b) digest の送信は 1 日 1 件 (毎分の tick が 3 日続く) | `digest.test.ts` (b) は **Worker の送信回数** (24 時間に 1 件) を検査する | PASS。コメント数の上限 (1 日 1 件) は検査していない。pm.md の文言 (`1 日 1 件まで`) を `test-dispatch-context.sh` が grep するだけ |
| 4 (c) 件数だけ・個票を書かない | pm.md digest 節 (「本文は件数の表だけ」「個票は書かない」) | `test-dispatch-context.sh` 10b (文言の grep。実行による検査は無い) |
| 4 (d) `config.ts` に Team・2026-11-13 が無い | 変更なし (既に 0 件) | `digest.test.ts` 最後 (`/team\|2026-11-13/i` が 0 件) |

## 4. 差分 (測定 commit から HEAD まで)

`git diff 222ad49b HEAD -- infra/pm-worker .github` の出力は 0 行。HEAD は本付録の commit で、変えたのは `tools/pm/REPORT_APPENDIX_2349.md` と `docs/DOC_MAP.md` だけ。

前回の測定 commit `2d35bd02` の結果は無効にした。その後に `main` の merge (`5baedd0f`) と rolling 除外の修正が入り、コードが変わったため。

## 5. 未解決・範囲外

- 反映 (`wrangler deploy` や Workers Builds) は範囲外。merge 後、Worker が次の tick で起点を置き、24 時間後に最初の digest を送る。
- rolling issue の初回起票と本文更新は PM agent (pm.md の digest 節) の実行で行う。Worker のテストの対象外。最初の digest で実機確認する。
- 緊急の Worker 停止・率制限の alert は PM agent の入力に無い。観測元の設計を含めて子 issue #2539 (`[CI-102]`) に移した。
- `oc-auto-close` の印は pm.md で定義した。既存の close (R5) は次の PM 実行から印が付く。過去分は数えない。

## 6. main 取り込み後の再実行 (#2481 の競合解消)

- 再測定 commit: `b324d224` (`origin/main` (`3ef67b40`) の merge。競合は `docs/DOC_MAP.md` の索引表 1 箇所だけ。`infra/pm-worker/`・`.github/`・`tools/pm/` の競合は無い)。
- 差分: `git diff 222ad49b b324d224 -- infra/pm-worker/ .github/ tools/pm/launch_issues.py tools/pm/test_launch_issues.py` の出力は 0 行。§2 の測定と同じコードを検証した。
- load average: `npm test` の前後 4.37 → 4.90、他 3 件の前後 4.75 → 4.87。§1 の 0.21 より高い負荷の下で測った。所要時間は下表の値をそのまま記録し、§2 の値とは比べない。

| 検証 | コマンド | 結果 | 所要 (wall) |
|---|---|---|---:|
| Worker の node テスト | `npm test` (`infra/pm-worker`) | 167 / 167 PASS・0 FAIL | 24.1 s |
| Worker の workerd テスト | `npm run test:workers` | 3 / 3 PASS | 4.3 s |
| pm.md と dispatch 文脈の検査 | `bash .github/scripts/tests/test-dispatch-context.sh` | 135 passed・0 failed | 6.1 s |
| launch 判定の Python テスト | `python3 -m unittest test_launch_issues` (`tools/pm`) | 8 / 8 OK | 0.14 s |
