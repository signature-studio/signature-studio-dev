# tools/pm REPORT 付録 (#2652): PM Worker の保存値の版による補完

- 対象: `infra/pm-worker` の保存値の版 (`SIGNAL_VER`)。版が保存値と違う最初の tick で全体同期を 1 回走らせる (失敗は `SIGNAL_RETRY_MS` = 15 分ごとに再試行)。
- PR: #2671 (`2652-pm-worker-no-pr-detect`)。`Refs #2652` (根因は未特定。§0)。運用の正本は `infra/pm-worker/README.md`。

## 0. 結論

- 修正のコード (版による全体同期と再試行・テスト 4 件) は、pm-worker の全テストで PASS (§2・§3)。
- **根因は未特定。** PR の初版の根因 (「導入前の保存値は次の 6 時間周期の全体同期まで補完されなかった」) は取り下げる。13:17Z の一時ビルドの全体同期は既に 24 時間窓を読んでおり (REST コメント 102 頁。§4)、周期の待ちでは説明できない。
- 計測 (§5): 本番の保存 outcome は 13:08Z 頃より後のコメントの分しか反映していない。現行コードの全体同期が 24 時間窓から導く件数 (228 件・検出 50 件) と一致しない。例: #2306 の `unknown` (11:37:15Z) は窓の内側だが、本番の `unknown` は 0 件。
- 版の補完が本番でこの欠落を直すかは**未確認**。この PR は merge もデプロイもしていない。

## 1. 測定の対象

- 測定 commit: `99750f00` (PR ブランチに origin/main `6aa8a94d` を merge した commit)。コードを変えた最後の commit。
- 差分の証跡: `git diff 99750f00 HEAD -- infra/pm-worker/src infra/pm-worker/test` の出力は 0 行 (README は docs のため除く) (本付録を含む commit より後の HEAD でも確認する。§8)。
- main の取り込み前は `9b63061b` (pm-worker 294/294)。取り込みで pm-worker に main の変更が入ったため、測定 commit を移した。

## 2. テスト (`infra/pm-worker`)

コマンド: `cd infra/pm-worker && node --experimental-strip-types --no-warnings --test 'test/*.test.ts'`

| 測定 commit | 件数 | 結果 | 所要 (TAP duration) |
|---|---:|---|---:|
| `c03a80a8` (main 取り込み前) | 281 | 281 PASS / 0 FAIL | 15.76 s (wall) |
| `9b63061b` (main `5d88dda2` 取り込み後) | 294 | 294 PASS / 0 FAIL | 14,872 ms |
| `99750f00` (main `6aa8a94d` 取り込み後・本付録の測定) | 297 | 297 PASS / 0 FAIL | 19,401 ms |

- `99750f00` の測定は取り込み直後の作業ツリー (コードは commit と同じ) で行った。単一の run (n=1)。

## 3. ネガコン (`stale` の固定・`9b63061b` の値)

- 変更: `src/engine.ts` の `tickInner` の `const stale = ...` を `const stale = false;` に置換して `test/no_pr_backfill.test.ts` を実行し、元に戻した。
- 結果: 修正のまま 4/4 PASS。`stale = false` で 1 FAIL・2 FAIL・3 PASS・4 FAIL。
- 注: この値は `9b63061b` のもの。`99750f00` では再実行していない (main の取り込みで engine.ts の周辺が変わったため、再現は未実施)。

## 4. 本番 `/status` (読み取りのみ・取得時刻付き)

取得: `curl -sS https://signature-studio-pm.pycabbage.workers.dev/status` (2026-10-14T16:58:54Z・HTTP 200)。

| キー | 値 |
|---|---|
| `mode_launch` / `mode_dispatch` | live / live |
| `fresh` / `sync_truncated` | true / 空 |
| `last_full_sync` | 2026-10-14T13:17:10.427Z |
| `last_full_sync_rest_calls` / `last_full_sync_comment_rest_calls` | 123 / 102 |
| `comment_window_h` / `comment_max_pages` | 24 / 150 |
| `no_pr_by_reason` | split 5 / artifact 27 / unknown 0 / blocked 11 / stop 0 (合計 43) |
| `pm_detected.no_pr` | 1 (16:58:54Z)・1 (17:09Z。レビューの取得値) |

- 13:17:10Z の全体同期は REST のコメント 102 頁。これは 24 時間窓 (約 9,800 件) を読んだ量と合う (§5 の窓内の件数)。
- `/status` には版 (`SIGNAL_VER`) を出していないので、本番がこの PR の版で動いているかは判定できない。

## 5. 保存 outcome の検算 (REST 再計算・未特定の根因の材料)

計測: `node --experimental-strip-types --no-warnings tools/pm/no_pr_census.ts <窓の時間数>` (`tools/pm/no_pr_census.ts`)。open issue の全件と窓内のコメントを `gh api` で読み (読み取りのみ)、`infra/pm-worker` の `applyEvent` (webhook.ts) と `detectPm` (pm.ts) に通す。`fullSync` と同じ入力・同じ純関数。永続化・ページ上限 (150) は同じ。

| 計測 (UTC) | 窓 | 窓内のコメント | open oc:no-pr | outcome あり (split / artifact / unknown / blocked / stop) | `no_pr` の検出 |
|---|---|---:|---:|---|---:|
| 17:18:51Z | 24 時間 | 9,828 | 228 | 228 件 (67 / 93 / 30 / 33 / 5) | 50 |
| 17:20:10Z | 4.1 時間 (13:08Z 頃から) | 1,226 | 228 | 50 件 (6 / 30 / 0 / 14 / 0) | 1 |
| 16:58:54Z (本番) | 保存値 | - | 不明 | 43 件 (5 / 27 / 0 / 11 / 0) | 1 (17:09Z) |

- 読み取り: 本番の outcome (43 件) と検出 (1) は、4.1 時間の窓 (50 件・1 件) に近い。24 時間の窓 (228 件・50 件) とは一致しない。差 7 件 (43 対 50) は時間差を含み、内訳は未分析。
- 具体例: #2306 は `unknown` の outcome が 11:37:15Z (REST で確認)。24 時間の計測では `reason=unknown` に入る。13:17Z の全体同期の窓 (前日 13:17Z から) の内側にある。本番の `unknown` は 0 件。
- 判断: 13:17Z の全体同期の後も、本番の保存値に窓の前半のコメントの outcome が残っていない。同期は窓を読んだ (§4) ので、この欠落の原因は周期の待ちではない。原因は未特定 (候補: 一時ビルドの版が現行の同期と違った・outcome の保存の経路。どちらも未確認)。
- 作成者の過去の記録 (218 件・49 件) は、本計測 (228 件・50 件) と近いが、同一の計測ではない。再現は §8 のコマンドで行う。
- 版の補完の効果: この PR を deploy すると、版の変更で全体同期が 1 回走る。その結果が本計測の 24 時間の値 (228・50) に近づくかは、deploy 後の `/status` (`no_pr_by_reason`・`pm_detected`) で測るまで未確認。

## 6. 未実行: vitest (`test:unit`)・`test:workers`

- **未実行。** 理由: `pnpm install --frozen-lockfile` が `ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION` で拒否された (この run で再確認)。拒否された lockfile のエントリは `@cloudflare/vitest-plugin@1.4.2`・`miniflare`・`wrangler@4.151.0`。release-age のポリシーは変更していない (迂回していない)。
- 静的な影響 (読解。実行による確認ではない): `test/unit` の tick は `markFresh` を直前に呼ぶため、補完の分岐 (`stale`) には入らない。`launchobs.test.ts` は `launch` を直接呼ぶ。`test:workers` も同じ理由で未実行。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 本番の保存 outcome が窓の前半 (13:08Z より前) のコメントを反映しない原因 (§5) | oc:no-pr の検出が現行の同期の結果より少ない (本計測 50 対 1)。根因は未特定 | 子 issue (PM が起票。本 PR の根因はこの問題の切り分けまで) |
| 版の補完が本番で件数を直すかは未確認 (deploy していない) | deploy 後の PM 起動の増加量は未測定 | PM (deploy の判断。deploy 後に §5 の 24 時間の計測と `/status` で確かめる) |
| 補完の窓は 24 時間 (`commentWindowH`)。窓より古い outcome は保存値に入らない | 古い outcome の `oc:no-pr` は検出されない | PM の判断 (既定案 = 24 時間のまま) |
| 人間起票の `oc:no-pr` は `author_association` が CONTRIBUTOR のため対象外 (`src/pm.ts` の `authorAllowed`) | 人間起票の `no_pr` は検出されない | PM (既定案 = 対象外のまま) |
| `test:unit` (vitest) と `test:workers` を未実行 | vitest の結果が未確認 | 次の検収 (vitest が入る環境) |

## 8. 再現

```
cd infra/pm-worker && node --experimental-strip-types --no-warnings --test 'test/*.test.ts'
cd <repo> && node --experimental-strip-types --no-warnings tools/pm/no_pr_census.ts 24
cd <repo> && node --experimental-strip-types --no-warnings tools/pm/no_pr_census.ts 4.1
curl -sS https://signature-studio-pm.pycabbage.workers.dev/status
git diff 99750f00 HEAD -- infra/pm-worker/src infra/pm-worker/test
```

- `no_pr_census.ts` は `gh` の読み取り (GET) だけを使う。本番の Worker には書き込まない。
