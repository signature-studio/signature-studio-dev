# tools/pm REPORT 付録 (#2652): PM Worker の保存値の版による補完

- 対象: `infra/pm-worker` の保存値の版 (`SIGNAL_VER`)。版が保存値と違う最初の tick で全体同期を 1 回走らせる (失敗は `SIGNAL_RETRY_MS` = 15 分ごとに再試行)。
- PR: #2671 (`2652-pm-worker-no-pr-detect`)。`Closes #2652` (根因は子 #2757 に移した。§0)。運用の正本は `infra/pm-worker/README.md`。

## 0. 結論

- 修正のコード (版による全体同期と再試行・テスト 4 件) は、pm-worker の全テスト・vitest (unit・workers) で PASS (§2)。ネガコンで 1・2・4 が FAIL、修正のままは 4/4 PASS (§3)。
- **根因は未特定。** 子 #2757 ([CI-131]・`親: #2652`) に移した。この PR の初版の根因 (6 時間周期の補完待ち) は取り下げ済み。
- 本番の `/status` (17:55Z 台) の `no_pr_by_reason` と `pm_detected.no_pr` は、同時刻の 4.1 時間窓の census と一致し、24 時間窓の census とは一致しない (§5)。その機構は未確認。
- 版の補完が本番の件数を直すかは**未確認**。この PR は deploy していない。

## 1. 測定の対象

- 測定 commit: `63e2e584` (origin/main `e74375d5` を merge した commit。`infra/pm-worker/src`・`infra/pm-worker/test` を変えた最後の commit)。
- 測定は `63e2e584` の作業ツリーで行った。コードは HEAD と同一 (`git diff 63e2e584 HEAD -- infra/pm-worker/src infra/pm-worker/test` は 0 行。§8)。
- 本付録と README の変更は docs だけで、pm-worker の src・test には触れていない。

## 2. テスト (`infra/pm-worker`・測定 commit `63e2e584`)

| コマンド | 件数 | 結果 | 所要 | load (1 分平均 開始→終了) |
|---|---:|---|---:|---|
| `cd infra/pm-worker && node --experimental-strip-types --no-warnings --test 'test/*.test.ts'` | 298 | 298 PASS / 0 FAIL | 10,979 ms (TAP duration) | 0.20 → 0.69 |
| `cd infra/pm-worker && pnpm run test:unit` (vitest・fetch モック) | 4 files / 45 tests | 45 PASS / 0 FAIL | 1.66 s (Duration) | 0.59 (開始前) |
| `cd infra/pm-worker && pnpm run test:workers` (vitest + workerd・実 Durable Object) | 1 file / 4 tests | 4 PASS / 0 FAIL | 1.27 s (Duration) | 0.78 (終了後) |

- 依存: `cd infra/pm-worker && pnpm install --frozen-lockfile` は通った (`Lockfile is up to date`・79 packages 追加・`@cloudflare/vitest-plugin` 1.4.1・`vitest` 4.1.11・`wrangler` 4.150.0)。
- 単一の run (n=1)。

## 3. ネガコン (`63e2e584`)

- 変更: `src/engine.ts` の `tickInner` の `const stale = this.meta.signalVer !== SIGNAL_VER && …` の 1 行を `const stale = false;` に置き換えて `test/no_pr_backfill.test.ts` を実行し、元の行に戻した。戻した後、同じテストは 4/4 PASS。
- 結果:

| テスト (`test/no_pr_backfill.test.ts`) | 修正のまま | `stale = false` |
|---|---|---|
| 1. 保存値の版が無い状態で、最初の tick の全体同期で補完され、Bot 起票の split が対象になる | PASS | **FAIL** |
| 2. ネガコン: 外部起票者・ラベル無し・outcome 無し・保留ラベル・PM の後続応答・reason が artifact・CONTRIBUTOR 起票は対象外 | PASS | **FAIL** |
| 3. 版が最新なら、周期内の tick は全体同期せず reconcile だけ行う | PASS | PASS |
| 4. 補完の全体同期が失敗しても、再試行は `SIGNAL_RETRY_MS` (15 分) ごと | PASS | **FAIL** |

- 結果 (要約): `stale = false` で 1 FAIL・2 FAIL・3 PASS・4 FAIL。元に戻すと 4/4 PASS。`git status` はクリーン (編集の往復後)。

## 4. 本番 `/status` (読み取りのみ・取得時刻付き)

取得: `curl -sS https://signature-studio-pm.pycabbage.workers.dev/status` (HTTP 200)。17:55Z 台 (`last_tick` 17:55:24.110Z の直後)。

| キー | 16:58:54Z (初版の取得) | 17:55Z 台 (本 fix の取得) |
|---|---|---|
| `mode_launch` / `mode_dispatch` | live / live | live / live |
| `fresh` / `sync_truncated` | true / 空 | true / 空 |
| `last_full_sync` | 2026-10-14T13:17:10.427Z | 2026-10-14T13:17:10.427Z |
| `last_full_sync_rest_calls` / `last_full_sync_comment_rest_calls` | 123 / 102 | 123 / 102 |
| `comment_window_h` / `comment_max_pages` | 24 / 150 | 24 / 150 |
| `no_pr_by_reason` (split / artifact / unknown / blocked / stop) | 5 / 27 / 0 / 11 / 0 (合計 43) | 20 / 42 / 0 / 15 / 2 (合計 79) |
| `pm_detected.no_pr` | 1 | 7 |
| `open_issues` | — | 438 |
| `pm_dispatch_1h` | — | 12 |

- `/status` には版 (`SIGNAL_VER`) を出していない。そのため本番がこの PR の版で動いているかは、この表からは判定できない。

## 5. 保存 outcome の再計算 (census) と本番の対比

計測: `node --experimental-strip-types --no-warnings tools/pm/no_pr_census.ts <窓の時間数>` (`gh api` の GET だけ。本番の Worker には書き込まない)。open issue の全件と窓内のコメントを読み、`infra/pm-worker` の `applyEvent` (webhook.ts) と `detectPm` (pm.ts) に通す。入力の順序は `fullSync` (engine.ts の `syncComments` は `sort=created&direction=desc`、`applyAll` の順) と同じ。ただし `npCount` は 0 に固定 (下の注 2)。

**照合 (census の入力が一覧を落としていないこと):** 17:54:47Z の REST `issues?state=open` の件数 (PR を除く) = 438 で、GraphQL の `repository.issues(states: OPEN).totalCount` (17:53Z) = 438 と一致。17:55:10Z は 439 (その間に 1 件起票)。census は REST の 1 頁が 100 件未満で止まる作りなので、件数が合わないと open issue を少なく数える。レビュー (round 4) の環境では REST が 27 件 (`Link` なし) を返し、census が open issue を 0 件と数えた。この run では 100 件の頁と `Link` が返り、件数も一致した。件数が合わないときは結果を使わない。

| 計測 (UTC) | 窓 | 窓内のコメント | open oc:no-pr | outcome あり (split / artifact / unknown / blocked / stop) | outcome 無し | `no_pr` の検出 |
|---|---|---:|---:|---|---:|---:|
| 17:54:47Z | 24 時間 | 9,816 | 205 | 205 件 (64 / 83 / 22 / 29 / 7) | 0 | 48 |
| 17:55:10Z | 4.1 時間 (13:49Z から) | 1,454 | 203 | 79 件 (20 / 42 / 0 / 15 / 2) | 124 | 7 |
| 17:55Z 台 (本番 `/status`・§4) | 保存値 | - | - | 79 件 (20 / 42 / 0 / 15 / 2) | - | 7 |

- 対比: 本番 (17:55Z 台) と 4.1 時間窓 (17:55:10Z) は、outcome の内訳 (20 / 42 / 0 / 15 / 2) と検出 (7) が一致する。24 時間窓 (205 件・検出 48) とは一致しない。本番の `unknown` は 0 件で、24 時間窓の open oc:no-pr には `unknown` が 22 件ある。例: #2306 は 24 時間窓の `unknown` に入る (census の examples) が、本番の `unknown` は 0 件。
- 機構は未確認。なぜ保存値が 4.1 時間窓の結果と一致するのか (窓の起点が 13:49Z になる理由を含む) は、子 #2757 で確かめる。
- 同じ census の前回 (17:18:51Z 24 時間・17:20:10Z 4.1 時間) の値は、24 時間 9,828 件・open oc:no-pr 228 件・検出 50、4.1 時間 1,226 件・outcome 50 件・検出 1 件だった。窓内のコメントと open issue が時間とともに変わるため、今回の値とは一致しない。比較は同時刻の値で行う。
- 注 1: 24 時間窓で `unknown` の検出は census では数えない。`pm.ts` の `detectPm` は `unknown` を『再投入後の run が終わった』場合 (`npCount ≥ 1` かつ outcome が最新の launch より後) だけ検出する。
- 注 2: census は `npCount` を 0 に固定する (本番は DO の `relaunch/np:<n>` を読む)。そのため census の検出は、本番の検出より少ない側に偏る可能性がある。`unknown` の 22 件のうち再投入済みの件数は未計測。
- 版の補完の効果: deploy すると、版の変更で全体同期が 1 回走る。その結果が 24 時間窓の値 (205・48) に近づくかは、deploy 後の `/status` (`no_pr_by_reason`・`pm_detected`) で測るまで未確認。

## 6. vitest (`test:unit`・`test:workers`) の結果

- `63e2e584` で実行: unit 4 files / 45 tests PASS (§2)・workers 1 file / 4 tests PASS (§2)。
- 旧版の『`pnpm install` が minimumReleaseAge で拒否』は、現在の lockfile (main の版固定 #2691 の後) では再現しなかった。release-age のポリシーは変えていない (迂回していない)。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 根因: 保存 outcome が 24 時間窓の内側のコメントを反映しない原因 (§5) | `no_pr` の検出が 24 時間窓の census より少ない (本番 7・24 時間窓 48)。根因は未特定 | 子 #2757 [CI-131] (`親: #2652`・PM が起票。#2652 の受入 1 を原文のまま移した) |
| 版の補完が本番の件数を直すかは未確認 (deploy していない) | deploy 後の PM 起動の増加量は未測定 | PM agent の判断待ち: deploy の時期。既定案 = `LIVE_LAUNCH` / `LIVE_DISPATCH` の状態を確認してから。deploy 後に §4・§5 で確かめる |
| 補完の窓は 24 時間 (`commentWindowH`)。窓より古い outcome は保存値に入らない | 古い outcome の `oc:no-pr` は検出されない | PM agent の判断待ち: 窓を広げるか。既定案 = 24 時間のまま |
| 人間起票の `oc:no-pr` は `author_association` が CONTRIBUTOR のため対象外 (`src/pm.ts` の `authorAllowed`) | 人間起票の `no_pr` は検出されない | PM agent の判断待ち: 対象に含めるか。既定案 = 対象外のまま |
| census の `npCount` = 0 (§5 注 2)・`unknown` の再投入済み件数 | census の内訳の精度 | 本付録の範囲外 (根因の切り分け #2757 で扱う) |

## 8. 再現

```
cd infra/pm-worker && node --experimental-strip-types --no-warnings --test 'test/*.test.ts'
cd infra/pm-worker && pnpm run test:unit
cd infra/pm-worker && pnpm run test:workers
cd <repo> && node --experimental-strip-types --no-warnings tools/pm/no_pr_census.ts 24
cd <repo> && node --experimental-strip-types --no-warnings tools/pm/no_pr_census.ts 4.1
curl -sS https://signature-studio-pm.pycabbage.workers.dev/status
git diff 63e2e584 HEAD -- infra/pm-worker/src infra/pm-worker/test
```

- `git diff 63e2e584 HEAD -- infra/pm-worker/src infra/pm-worker/test` の出力は 0 行 (この付録を含む commit の時点)。
- ネガコン (§3) の再現: `src/engine.ts` の `const stale = …` の行を `const stale = false;` に変えて `node --experimental-strip-types --no-warnings --test test/no_pr_backfill.test.ts` を実行し、元に戻す。
- `no_pr_census.ts` は `gh` の読み取り (GET) だけを使う。
