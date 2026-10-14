# tools/pm REPORT 付録 (#2795): launch の安全装置の既定反転と停止の可視化

- 対象: `infra/pm-worker` の `IMPORT_REQUIRED` の既定 (反転)・launch の停止 (`launch_halted` / `launch_halted_overdue`)・PM agent への通知 (`digest` ref 0)。
- PR: #2854 (`2795-pm-launch-halt`・`Closes #2795`)。運用の正本は `infra/pm-worker/README.md` の『launch の停止と通知』節。

## 0. 結論

- 測定 commit `28d33f67` (main `217ceb3e` の取り込み `694ac41c` の後・降格中の停止通知の修正)。node:test 387 件 (3 回とも全件 PASS)・vitest unit 70 件・vitest workers 7 件がすべて PASS。変異テストは 9 変異すべて killed (§2・§3)。
- 降格 (#2340) 中の停止通知は送らず、解除の後に送る (`haltNotify` の降格ゲート・§1)。降格を `launch_halted` に含めない理由は `infra/pm-worker/README.md` の表の直後に書いた。
- 本番 `/status` (2026-10-14T20:18:35Z・読み取りのみ) には `launch_halted` のキーが無い。本番は未 deploy のため (§4)。停止区間は無く、`imported_at` は設定済み。
- 本番の launch の挙動はまだ変わらない。deploy 後の停止の観測は未測定 (§5)。

## 1. 測定の対象

- 測定 commit: `28d33f67` (`fix(pm-worker): hold the launch-halt notice while demoted (review round 2)`)。`infra/pm-worker` を変えた最後の commit。
- 経緯 (時系列):
  - `2c8eb023`: 差し戻し (round 1) 時の head。`dc2723cc` で README と `src/engine.ts` のコメントを `IMPORT_REQUIRED=1` のときだけに限定した。付録と DOC_MAP の索引は `e8102f9e`・`37d34aba`。
  - `cf5bd08a`: origin/main `a3e24270` の取り込み merge (round 1 の測定 commit)。
  - `733d09a8`: round 2 の指摘時の head。
  - `694ac41c`: origin/main `217ceb3e` の取り込み merge (38 commit)。衝突は無し (`git merge-tree` で確認)。`infra/pm-worker` の差分は `git diff --stat 733d09a8 694ac41c -- infra/pm-worker` で 13 files・604 行追加・23 行削除 (main 側の ratealert・launch・webhook・engine などを含む)。
  - `28d33f67`: 降格中の停止通知の修正 (round 2 の指摘 1)。`src/engine.ts`・`test/halt_engine.test.ts`・`scripts/mutation_halt.mjs`・`README.md` を変える。
- 降格中の停止通知の修正 (`git diff 694ac41c 28d33f67 -- infra/pm-worker/src/engine.ts` の要点):
  - 旧: `if (!this.d.cfg.liveDispatch || !gh)` で送るかを決めていたため、降格中でも `LIVE_DISPATCH=1` なら live で送っていた。
  - 新: 送るかは `dispatchLive()` (降格を含む) で決める。降格中 (`held`) は区間の `notifiedAt` を立てず保留する。解除の後に送る。dry-run (`LIVE_DISPATCH=0`) は従来どおり 1 区間 1 回。降格中の would は pmWould 履歴の 60 分の重複抑止に従う。
- 測定 commit から HEAD までの差分: `git diff 28d33f67 HEAD -- infra/pm-worker ':!infra/pm-worker/README.md'` は 0 行。`infra/pm-worker` で変わるのは `README.md` だけ (round 3 の文書修正: 変異テストの件数の記載を外した)。テストと `scripts/` は README を読まない (`readFile` の対象は `src/config.ts`・`wrangler.toml`・fixture のみ)。このため §2・§3 は測定 commit `28d33f67` の値のまま。

## 2. テスト (`infra/pm-worker`・測定 commit `28d33f67`)

測定はコミット済みの作業ツリー (`git status` は clean) で行った。依存は `pnpm install --frozen-lockfile`。`load` は 1 分平均 (`/proc/loadavg`) で、各コマンドの終了時に読んだ値。

| コマンド | 件数 | 結果 | 所要 (real) | load (1 分平均・終了時) |
|---|---:|---|---:|---|
| `node --experimental-strip-types --no-warnings --test 'test/*.test.ts'` (n=3) | 387 | 387 PASS / 0 FAIL (3 回とも) | 23.79 / 22.11 / 22.60 s | 1.93 → 3.03 → 3.10 |
| `npm run test:unit` (vitest unit・fetch モック) | 70 (5 files) | 70 PASS / 0 FAIL | 2.89 s | 2.63 |
| `npm run test:workers` (vitest + workerd・実 Durable Object) | 7 (2 files) | 7 PASS / 0 FAIL | 2.85 s | 2.50 |
| `npm run test:mutation` | 9 変異 | killed 9・survived 0 | 5.27 s | 3.02 |

- 旧値 (`cf5bd08a`・main `a3e24270` 取り込み時): node:test 353 件、vitest unit 70 件、vitest workers 7 件、変異 7 件 (killed 7)。node:test は 353 → 387 (+34)。内訳は、取り込みで入った main 側のテストと、本 round の新規 1 件 (`test/halt_engine.test.ts` の『降格中は停止通知を送らず would に数え、解除の後に 1 回送る』)。
- 本 PR の停止・通知のテストは `test/halt.test.ts` と `test/halt_engine.test.ts` にある (変異テストの対象)。`test/demote_shadow.test.ts` は降格の既存テスト (main 由来を含む)。

## 3. 変異テスト (`npm run test:mutation`・測定 commit `28d33f67`)

`scripts/mutation_halt.mjs` が規則を 1 か所ずつ壊し、`test/halt.test.ts` と `test/halt_engine.test.ts` が落ちることを確かめる。各変異の後は元の `src/` に戻す (`finally`)。終了後の `git status` は clean。

| # | 変異 (1 か所) | 対象 | 結果 |
|---|---|---|---|
| 1 | 既定の `IMPORT_REQUIRED` を 0 扱い (取り込み必須) に戻す | `src/config.ts` | killed |
| 2 | overdue の閾値を 16 分にする (15 分が正) | `src/halt.ts` | killed |
| 3 | 通知の閾値を 29 分にする (30 分が正) | `src/halt.ts` | killed |
| 4 | overdue の条件から着手待ち (`ready`) を外す | `src/halt.ts` | killed |
| 5 | 止まっている間に起点 `since` を毎回今にする | `src/halt.ts` | killed |
| 6 | 条件が 0 になっても区間を消さない | `src/halt.ts` | killed |
| 7 | 同じ停止区間の重複抑止 (`notifiedAt`) を外す | `src/halt.ts` | killed |
| 8 | 降格中も停止通知を live で送る (降格ゲートを外す) | `src/engine.ts` | killed |
| 9 | 降格中の停止通知も区間の 1 回を使う (保留しない) | `src/engine.ts` | killed |

結果: `mutants=9 survived=0` (5.27 s。load 3.02)。

## 4. 本番 `/status` (読み取りのみ)

- 取得: `GET https://signature-studio-pm.pycabbage.workers.dev/status` (URL は `tools/pm/worker_url`)。取得時刻 2026-10-14T20:18:37Z。書き込みは行っていない。本番は本 PR のコードを含まない。
- 本番 Worker は未 deploy で、`launch_halted` と `launch_halted_overdue` のキーを返さない (`has("launch_halted") = false`)。以下は既存の項目の値 (`last_tick` 2026-10-14T20:18:35.716Z)。

| キー | 値 (20:18:37Z) |
|---|---|
| `launch_stop` / `launch_blocked` | null / null (停止の条件に当たらない) |
| `imported_at` | 2026-10-14T19:16:26.615Z (取り込み済み) |
| `mode` / `mode_launch` / `mode_dispatch` | live / live / live |
| `phase` | launch |
| `open_prs` / `open_prs_excl_stuck` / `stuck_prs` | 36 / 36 / 0 (Review-Only の閾値は 80) |
| `active_all` / `target_eff` / `room` | 63 / 58 / 0 |
| `ready` | 15 |
| `fresh` | true |
| `demoted_reason` | null (降格していない) |
| `pm_dispatch_1h` | 12 (1 時間の上限 12 に達している) |
| `counters.pmDispatched` / `counters.wouldDispatchPm` | 70 / 0 |
| `rest_remaining` | 4909 |

- `room` が 0 で launch が待つのは、同時実行の上限に達しただけの正常な待ち。README の停止の条件に含まれない。
- `pm_dispatch_1h` が上限に達している。通知の送信は 1 時間 12 件の上限で落ちる (送らず次の tick で再試行する)。通知が増えたときの影響は deploy 後に測る (§5)。

## 5. 未解決

- deploy していない。deploy 後の停止の観測 (`launch_halted` の出方・30 分後の digest の送信・降格中の保留と解除後の送信) は未測定。deploy は PM が行う。
- 通知の頻度 (Review-Only・rate-guard が 30 分続いた回数) は本番で未測定。deploy 後に `counters.pmDispatched` と `pm_dispatch_1h` で確認する。
- digest の PM run は `/status` を読めない (oc-pm の workflow に `PM_WORKER_URL` が無い)。起票先は子 #2848 (CI-135)。未解決の表は PR 本文が正本。

## 6. 再現手順

```sh
cd infra/pm-worker
pnpm install --frozen-lockfile
node --experimental-strip-types --no-warnings --test 'test/*.test.ts'
npm run test:unit
npm run test:workers
npm run test:mutation
git diff 28d33f67 HEAD -- infra/pm-worker ':!infra/pm-worker/README.md'
curl -fsS "$(tr -d '\n' < ../../tools/pm/worker_url)/status"
```
