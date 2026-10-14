> **正本**: `tools/pm/REPORT.md` (250 行上限のため分割)。対象は PM Worker の日次 digest (#2349・CI-70)。

## 1. 測定の対象と環境

- 測定 commit: `2d35bd02` (コードを変えた最後の commit。`infra/pm-worker/`・`.github/prompts/pm.md`・`.github/scripts/tests/test-dispatch-context.sh`)。
- 作業ツリーは clean (`git status --short` 0 行) の `2d35bd02` で測定。Node v22.23.3。`infra/pm-worker` は `npm ci` (86 packages・4 s) 後。
- load average: `npm test` の前 1.37 / workerd テストの前 2.19 / shell テストの前 2.09 (14:39 UTC 台)。

## 2. 結果

| 検証 | コマンド | 結果 | 所要 (wall) |
|---|---|---|---:|
| Worker の node テスト (`digest.test.ts` 6 件を含む) | `npm test` (`infra/pm-worker`) | 153 / 153 PASS・0 FAIL | 14.4 s |
| Worker の workerd テスト (vitest・実 Durable Object) | `npm run test:workers` | 3 / 3 PASS | 2.6 s |
| pm.md と dispatch 文脈の検査 (digest 節 11 項目・user_answered 5 項目を含む) | `bash .github/scripts/tests/test-dispatch-context.sh` | 133 passed・0 failed | 4.0 s |

ネガコン (mutation 検出): `engine.ts` の `digest()` にある 24 時間ガード `if (now - this.meta.digestAt < DIGEST_EVERY_MS) return "skipped";` を一時的に `if (false)` へ置き換えると、`digest.test.ts` の 4 件 (初回・(a)・(b)・送信失敗) が FAIL した。元に戻した後の `git status` は clean。

## 3. 受入条件との対応

| 受入 | 実装 | 検証 |
|---|---|---|
| 1 Worker が 24 時間ごとに `oc-pm kind=digest ref=0` を送る | `engine.ts` `digest()` を `tickInner` が毎 tick 呼ぶ。初回は起点のみ (`meta.digestAt`)。payload は `{kind:"digest", ref:0}` | `digest.test.ts` 初回・(a) |
| 1 dry-run は記録のみ | `would_dispatch_pm` に `digest#0`、`counters.wouldDispatchPm` (POST 0 回) | `digest.test.ts` dry-run |
| 1 pm.md の digest 節 (件数・rolling issue の本文更新・緊急は 1 日 1 件) | `.github/prompts/pm.md` `### digest` | `test-dispatch-context.sh` 10b |
| 2 pm.md の user_answered 節 (反映・除去・確定コメント・曖昧なら聞き直し) | `.github/prompts/pm.md` `### user_answered` | `test-dispatch-context.sh` 10b |
| 4 (a) 24 時間以内の 2 回目は送らない | `digest.test.ts` (a) | PASS・mutation で FAIL を確認 |
| 4 (b) digest は 1 日 1 件 (毎分の tick が 3 日続く) | `digest.test.ts` (b) | PASS (送信は 24 時間以上の間隔) |
| 4 (c) 件数だけ・個票を書かない | pm.md digest 節 (「本文は件数の表だけ」「個票は書かない」) | `test-dispatch-context.sh` 10b |
| 4 (d) `config.ts` に Team・2026-11-13 が無い | 変更なし (既に 0 件) | `digest.test.ts` 最後 (`/team\|2026-11-13/i` が 0 件) |

## 4. 差分 (測定 commit から HEAD まで)

`git diff 2d35bd02 HEAD -- infra/pm-worker .github` の出力は 0 行 (測定時の HEAD は `2d35bd02` そのもの)。その後に足したのは本付録と DOC_MAP の索引行だけで、コード範囲の差分は 0 のまま。

## 5. 未解決・範囲外

- 反映 (`wrangler deploy` や Workers Builds) は範囲外。merge 後、Worker が次の tick で起点を置き、24 時間後に最初の digest を送る。
- rolling issue の初回起票と本文更新は PM agent (pm.md の digest 節) の実行で行う。Worker のテストの対象外。最初の digest で実機確認する。
- `oc-auto-close` の印は pm.md で定義した。既存の close (R5) は次の PM 実行から印が付く。過去分は数えない。
