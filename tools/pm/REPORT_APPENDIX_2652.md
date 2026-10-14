# tools/pm REPORT 付録 (#2652): PM Worker の保存値の版による補完

- 対象: `infra/pm-worker` の保存値の版 (`SIGNAL_VER`)。版が保存値と違う最初の tick で全体同期を 1 回走らせる (失敗は `SIGNAL_RETRY_MS` = 15 分ごとに再試行)。
- PR: #2671 (`2652-pm-worker-no-pr-detect`)。`Closes #2652` (根因は子 #2757 に移した。§0)。運用の正本は `infra/pm-worker/README.md`。

## 0. 結論

- 修正のコード (版による全体同期と再試行・テスト 4 件) は、pm-worker の全テスト・vitest (unit・workers) で PASS (§2)。ネガコンで 1・2・4 が FAIL、修正のままは 4/4 PASS (§3)。
- 本番の `/status` (17:55Z 台) の `no_pr_by_reason` と `pm_detected.no_pr` は、同時刻の 4.1 時間窓の census と一致し、24 時間窓の census とは一致しなかった (§5)。
- **根因を特定した** (子 #2757 [CI-131]・§9)。保存値 (issue の `assoc`・`authorType`、コメント由来の `sig.outcome`) を作るコードは PR #2423 で main に入り (13:56:28Z merge)、13:17:10Z の全体同期はそれより前のコードで走った。以後の補完は、次の周期 (19:17Z 予定) を待つか、版の補完 (#2671) の全体同期を待つしかなかった。
- 版の補完の効果は確認済み (§9): 18:11:15Z の全体同期の後、`pm_detected.no_pr` は 24 時間窓の census と一致する (19:33Z の `/status` と 19:37Z の census で 33 = 33)。

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
- 機構は §9 (#2757) で確認した。4.1 時間窓の起点 13:49Z は #2423 の merge (13:56:28Z) の約 7 分前。一致は『保存値が merge 以降の webhook で入った』ことと整合する (13:49〜13:56 の扱いは未確認)。
- 同じ census の前回 (17:18:51Z 24 時間・17:20:10Z 4.1 時間) の値は、24 時間 9,828 件・open oc:no-pr 228 件・検出 50、4.1 時間 1,226 件・outcome 50 件・検出 1 件だった。窓内のコメントと open issue が時間とともに変わるため、今回の値とは一致しない。比較は同時刻の値で行う。
- 注 1: 24 時間窓で `unknown` の検出は census では数えない。`pm.ts` の `detectPm` は `unknown` を『再投入後の run が終わった』場合 (`npCount ≥ 1` かつ outcome が最新の launch より後) だけ検出する。
- 注 2: census は `npCount` を 0 に固定する (本番は DO の `relaunch/np:<n>` を読む)。そのため census の検出は、本番の検出より少ない側に偏る可能性がある。`unknown` の 22 件のうち再投入済みの件数は未計測。
- 版の補完の効果: 確認済み (§9)。18:11:15Z の全体同期の後、`/status` (19:33Z) は 24 時間窓の census (19:37Z) と一致する (`pm_detected.no_pr` 33 = 33)。

## 6. vitest (`test:unit`・`test:workers`) の結果

- `63e2e584` で実行: unit 4 files / 45 tests PASS (§2)・workers 1 file / 4 tests PASS (§2)。
- 旧版の『`pnpm install` が minimumReleaseAge で拒否』は、現在の lockfile (main の版固定 #2691 の後) では再現しなかった。release-age のポリシーは変えていない (迂回していない)。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 根因 (保存値が導入前の分を補完されない) | 解決 (§9)。`no_pr` の検出は 24 時間窓の census と一致 (33 = 33) | 子 #2757 [CI-131] (`親: #2652`)。根因の特定は同 issue の PR (§9) |
| deploy の時刻 (`wrangler versions`) は CI から確認できない。18:11:15Z と #2671 の merge (18:08:30Z) の一致は推定 | 根因の時刻の精度のみ | 記録の範囲外 (本付録 §9 に『未確認』と明記) |
| 補完の窓は 24 時間 (`commentWindowH`)。窓より古い outcome は保存値に入らない | 古い outcome の `oc:no-pr` は検出されない | PM agent の判断待ち: 窓を広げるか。既定案 = 24 時間のまま |
| 人間起票の `oc:no-pr` は `author_association` が CONTRIBUTOR のため対象外 (`src/pm.ts` の `authorAllowed`)。19:37Z の census で 48 件 (§9) | 人間起票の `no_pr` は検出されない | PM agent の判断待ち: 対象に含めるか。既定案 = 対象外のまま |
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

## 9. 根因 (子 #2757): 保存値が導入前のコメントを補完されない

- 測定 commit: `3b866a61` (作業ツリーの HEAD。読み取りのみ・コードは変えていない)。`git diff --stat 3b866a61 bae12679 -- infra/pm-worker/src infra/pm-worker/test` は 0 行 (origin/main `bae12679` と同一)。

**時刻 (UTC)。merge は `git log --first-parent` の時刻、全体同期と /status は本番の値**

| 時刻 | 出来事 |
|---|---|
| 13:17:10.427Z | 全体同期 (`last_full_sync`)。この時点の main に、保存値を作るコードは無い |
| 13:56:28Z | PR #2423 (`803d5164`・実装 `891e33ca`・`feat(pm-worker): 終端状態 ... (#2333)`) が main に merge。`issue.assoc`・`issue.authorType` (webhook.ts:213-214)・`sig.outcome` (webhook.ts:322-325) を初めて作る |
| 18:08:30Z | PR #2671 が main に merge (版 `SIGNAL_VER` = 2。engine.ts:52) |
| 18:11:15.877Z | 全体同期 (`last_full_sync`)。版の補完の条件 `stale` (engine.ts:1418-1420) が成り立つ (`meta.signalVer` が未記録) ので、一致すると推定 |
| 19:17Z 頃 | 周期 (`FULL_SYNC_EVERY_MS` = 6 時間・engine.ts:49) の次回。18:11:15Z が無ければ、ここまで全体同期は走らない |

- 13:17:10Z の全体同期は、`assoc`・`authorType`・`sig.outcome` を作れないコードで走った。よって、それより前に保存された issue の `assoc` と、導入前のコメントの outcome は、補完されないまま残った。`infra/pm-worker/README.md` の再デプロイ手順 4 は deploy を main の merge の後と定めるので、13:56:28Z より前に #2423 のコードが動いたとは考えにくい (deploy 時刻は GitHub に記録が無く、未確認)。
- 導入後、新しいコードで全体同期が走ったのは 18:11:15Z が最初。周期の次回は 19:17Z (13:17:10Z の 6 時間後) だった。版が無かったので、導入で補完を起こす仕組みは無かった。
- 初版 (#2671 の最初の根因: 6 時間周期の補完待ち) を取り下げた理由 (『13:17:10Z の同期が補完したはず』) は誤りだった。13:17:10Z の同期は導入前のコードで走ったので補完できない。周期の補完待ちという初版の見方は、結果として正しかった。

**保存値の件数 (`/status` と census。census は REST だけで `applyEvent`・`detectPm` に通す。`npCount` = 0 (注 2))**

| 計測 | 時刻 | `no_pr_by_reason` (split / artifact / unknown / blocked / stop) | `pm_detected.no_pr` |
|---|---|---|---:|
| `/status` (§4 と同じ URL) | 19:33Z 台 (`last_tick` 19:33:03.802Z・`last_full_sync` 18:11:15.877Z・`comment_window_h` 24・`comment_max_pages` 150) | 63 / 88 / 13 / 29 / 7 (合計 200) | 33 |
| census 24 時間窓 | 19:37:16Z (コメント 9,151 件・打ち切り無し・open issue 442・open `oc:no-pr` 199) | 63 / 88 / 12 / 29 / 7 (合計 199) | 33 |

- 1 件の差 (`unknown` 13 と 12) は 19:33Z と 19:37Z の間の変化として扱う (未確認)。`pm_detected.no_pr` は 33 で一致する。
- 18:11:15Z の前の値は §4 (16:58Z: 43 件・検出 1) と §5 (17:55Z 台: 79 件・検出 7) の通り。17:55Z から 19:33Z までに 79 から 200 へ増えた。その大半が 18:11:15Z の全体同期によると読む (17:55〜19:33 の webhook の分は切り分けていない・未確認)。

**検出 0 の issue の読み取り (census 19:37Z。検出の条件は `pm.ts` の `detectPm`)**

| 内訳 (open `oc:no-pr` 199 件) | 件数 | 落ちる条件 |
|---|---:|---|
| 検出 (`no_pr`) | 33 | - |
| `authorAllowed` で落ちる | 48 | 起票者が `pycabbage` (`User`・`author_association` = CONTRIBUTOR)。`pm.ts:55` の ASSOC_OK (MEMBER / OWNER / COLLABORATOR) にも、許可 bot にも当たらない |
| `HOLD_LABELS` (`pm-apply` / `needs-user-input`) | 12 | `pm.ts` の `HOLD_LABELS` |
| `answeredAfter` (PM の応答が後) | 4 | `pm.ts` の `answeredAfter` |
| outcome の reason が検出の対象外 | 102 | artifact 74・blocked 20・unknown 8 (unknown は注 2 の `npCount` = 0 の影響を受ける) |

- 例 (b): #2457 (`pycabbage`・User・CONTRIBUTOR・`oc:no-pr`) は `authorAllowed` で落ちる。#2405 (`opencode-for-signature-studio[bot]`・Bot) は検出される。
- open `oc:no-pr` 199 件の起票者の内訳 (`gh api` GET): bot 151 件 (許可) と `pycabbage` の 48 件 (除外)。48 件は census の `authorAllowed` の 48 件と一致する。

**結論と未解決**

- 根因: 保存値 (issue の `assoc`・`authorType`、コメントの `sig.outcome`) は PR #2423 (13:56:28Z merge) で導入された。導入後に新しいコードで全体同期が走ったのは 18:11:15Z が最初で、それまでの間 (13:57〜18:11) は導入前の分が補完されず、`/status` は 24 時間窓の census と一致しなかった。版が無かったため、導入で補完を起こす仕組みも無かった (版の補完 #2671 がその仕組み)。
- 版の補完 (18:11:15Z の全体同期) の後、`/status` は 24 時間窓の census と一致した (33 = 33)。
- 残り: 人間 (CONTRIBUTOR) 起票の 48 件は設計上の対象外 (上の §7 の行)。deploy の時刻は未確認 (CI に Cloudflare の認証が無く、`wrangler versions list` を読めない)。
- 再現: `curl -sS https://signature-studio-pm.pycabbage.workers.dev/status`・`node --experimental-strip-types --no-warnings tools/pm/no_pr_census.ts 24`・`gh api --paginate -X GET "repos/signature-studio/signature-studio-dev/issues?state=open&labels=oc:no-pr&per_page=100"` (起票者の内訳)・`git log -S'assoc: i.author_association' --format='%h %aI %s' -- infra/pm-worker/src/webhook.ts`。
