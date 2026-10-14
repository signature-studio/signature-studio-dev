# tools/pm REPORT 付録 (#2795): launch の安全装置の既定反転と停止の可視化

- 対象: `infra/pm-worker` の `IMPORT_REQUIRED` の既定 (反転)・launch の停止 (`launch_halted` / `launch_halted_overdue`)・PM agent への通知 (`digest` ref 0)。
- PR: #2854 (`2795-pm-launch-halt`・`Closes #2795`)。運用の正本は `infra/pm-worker/README.md` の『launch の停止と通知』節。

## 0. 結論

- 測定 commit `cf5bd08a` (origin/main `a3e24270` の取り込み後) で、node:test 353 件・vitest unit 70 件・vitest workers 7 件がすべて PASS。変異テストは 7 変異すべて killed (§2・§3)。
- 取り込みで main 由来の増分が入った。node:test は `dc2723cc` の 344 件から 353 件 (`test/demote_shadow.test.ts` 9 件)、vitest unit は 45 件から 70 件 (`test/unit/build_import.test.ts` 25 件)。§1・§2。
- 本番 `/status` (2026-10-14T19:54:43Z・読み取りのみ) には `launch_halted` のキーが無い。本番は未 deploy のため (§4)。停止区間は無く、`imported_at` は設定済み。
- 本番の launch の挙動はまだ変わらない。deploy 後の停止の観測は未測定 (§5)。

## 1. 測定の対象

- 測定 commit: `cf5bd08a` (`Merge remote-tracking branch 'origin/main' into 2795-pm-launch-halt`)。`infra/pm-worker` を変えた最後の commit。
- 経緯 (時系列):
  - `2c8eb023`: レビュー時の head。本 PR の実装。
  - `dc2723cc`: 差し戻し (review round 1) への対応。README 15 行目の『取り込み前は launch しない』を `IMPORT_REQUIRED=1` のときだけに限定した。minor への対応で、`src/engine.ts` の同じ趣旨のコメント 1 行も限定した。
  - `e8102f9e`・`37d34aba`: 本付録と `docs/DOC_MAP.md` の索引。`tools/pm/` と `docs/DOC_MAP.md` だけを変える。
  - `3fb1dd18`: origin/main `b2b052ce` の取り込み merge。`docs/DOC_MAP.md` の表の衝突 1 件を解消した (両方の行を残し、`tools/pm/REPORT.md` の目安は main の `~250` を採用)。
  - `cf5bd08a`: origin/main `a3e24270` の取り込み merge。`infra/pm-worker/README.md` の衝突 1 件を解消した。main 側の『取り込み前は launch しない』と『反映の順序』は、#2795 が未 merge の前提で書かれていた (既定 1)。#2795 の merge 後の状態 (既定 0・`IMPORT_REQUIRED=1` のときだけ求める) に合わせ、main 側の補助スクリプトの段落は残した。
- レビューは `2c8eb023` から HEAD までの差分 0 を想定していた。実際には、コメント 1 行の変更と main の取り込みで差分が出た。そのため測定 commit `cf5bd08a` で全テストを取り直した (§2)。
- レビュー時の head `2c8eb023` から `dc2723cc` までの差分 (`git diff 2c8eb023 dc2723cc -- infra/pm-worker ':!infra/pm-worker/README.md'`。README の変更は 1 行で、実行されない文書):

```diff
diff --git a/infra/pm-worker/src/engine.ts b/infra/pm-worker/src/engine.ts
index 89059e7d..0e242b15 100644
--- a/infra/pm-worker/src/engine.ts
+++ b/infra/pm-worker/src/engine.ts
@@ -1614,7 +1614,7 @@ export class Engine {
       open_prs_excl_stuck: plan.open_prs_excl_stuck,
       stuck_prs: plan.stuck_prs,
       launch_stop: plan.stop ?? null,
-      // VM の状態を取り込む前は "no-import" (launch しない)。取り込んだ時刻は imported_at (#2343)。
+      // IMPORT_REQUIRED=1 のとき、VM の状態を取り込む前は "no-import" (launch しない)。取り込んだ時刻は imported_at (#2343)。
       launch_blocked: plan.blocked ?? null,
       imported_at: this.meta.importedAt ?? null,
       blocked: c("blocked"),
```

- main の取り込みで `infra/pm-worker` に入った変更 (`dc2723cc` から `cf5bd08a` まで。`git diff --stat dc2723cc cf5bd08a -- infra/pm-worker` は 8 ファイル・747 行追加・17 行削除。内訳は 2 回の取り込みごと):
  - 1 回目 (`3fb1dd18`・`git diff --stat dc2723cc 3fb1dd18 -- infra/pm-worker`): `src/app.ts`・`src/engine.ts`・`test/demote_shadow.test.ts`・`test/status.test.ts` の 4 ファイル (386 行追加・12 行削除)。
  - 2 回目 (`cf5bd08a`・`git diff --stat 3fb1dd18 cf5bd08a -- infra/pm-worker`): `README.md`・`scripts/build_import.mjs`・`scripts/measure_import.mjs`・`test/unit/build_import.test.ts` の 4 ファイル (361 行追加・5 行削除)。
- 測定 commit から HEAD までの差分: `git diff cf5bd08a HEAD -- infra/pm-worker` は 0 行 (付録の commit は `tools/pm/` と `docs/DOC_MAP.md` だけを変える。§6)。

## 2. テスト (`infra/pm-worker`・測定 commit `cf5bd08a`)

測定はコミット済みの作業ツリー (`git status` は clean) で行った。依存は `pnpm install --frozen-lockfile`。Node は v22.23.3。

| コマンド | 件数 | 結果 | 所要 (real) | load (1 分平均) |
|---|---:|---|---:|---|
| `node --experimental-strip-types --no-warnings --test 'test/*.test.ts'` (n=3) | 353 | 353 PASS / 0 FAIL (3 回とも) | 13.34〜14.04 s (min–max) | 開始時 0.08・0.52・1.06 |
| `npm run test:unit` (vitest unit・fetch モック) | 70 (5 files) | 70 PASS / 0 FAIL | 2.09 s | 1.22 → 1.22 |
| `npm run test:workers` (vitest + workerd・実 Durable Object) | 7 (2 files) | 7 PASS / 0 FAIL | 2.17 s | 1.22 → 1.20 |
| `npm run test:mutation` | 7 変異 | killed 7・survived 0 | 2.80 s | 1.20 → 1.20 |
| `node ... test/halt.test.ts test/halt_engine.test.ts` | 8 (本 PR の新規。6 + 2) | 8 PASS / 0 FAIL | — | — |
| `node ... test/demote_shadow.test.ts` (main 取り込みの新規) | 9 | 9 PASS / 0 FAIL | — | — |

- 旧値 (`3fb1dd18`・同じ手順): node:test 353 件 (n=3・13.35〜13.45 s)、vitest unit 45 件 (4 files)、vitest workers 7 件、変異 7 killed。`cf5bd08a` で増えたのは vitest unit の 25 件 (`test/unit/build_import.test.ts`)。
- 旧値 (`dc2723cc`・取り込み前): node:test 344 件 (n=3・12.77〜13.18 s)。
- `halt*.test.ts` の 8 件は、本 PR の既存の node:test の件数に含まれる。既存の `test/status.test.ts` の snapshot にキーを 2 つ足した (件数は増えない)。

## 3. 変異テスト (`npm run test:mutation`・測定 commit `cf5bd08a`)

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

結果: `mutants=7 survived=0` (2.80 s。load 1.20 → 1.20)。

## 4. 本番 `/status` (読み取りのみ)

- 取得: `GET https://signature-studio-pm.pycabbage.workers.dev/status` (URL は `tools/pm/worker_url`)。取得時刻 2026-10-14T19:54:43Z。書き込みは行っていない。本番は本 PR のコードを含まない。
- 本番 Worker は未 deploy で、`launch_halted` と `launch_halted_overdue` のキーを返さない (`has("launch_halted") = false`)。以下は既存の項目の値。

| キー | 値 (19:54:43Z) |
|---|---|
| `launch_stop` / `launch_blocked` | null / null (停止の条件に当たらない) |
| `imported_at` | 2026-10-14T19:16:26.615Z (取り込み済み) |
| `mode` / `mode_launch` / `mode_dispatch` | live / live / live |
| `phase` | launch |
| `open_prs` / `open_prs_excl_stuck` / `stuck_prs` | 33 / 33 / 0 (Review-Only の閾値は 80) |
| `active_all` / `target_eff` / `room` | 62 / 58 / 0 |
| `ready` | 24 |
| `fresh` / `last_tick` | true / 2026-10-14T19:54:41.119Z |
| `pm_dispatch_1h` | 12 (1 時間の上限 12 に達している) |
| `counters.pmDispatched` / `counters.wouldDispatchPm` | 66 / 0 |
| `rest_remaining` | 4961 |

- `room` が 0 で launch が待つのは、同時実行の上限に達しただけの正常な待ち。README の停止の条件に含まれない。
- `pm_dispatch_1h` が上限に達している。通知の送信は 1 時間 12 件の上限で落ちる (送らず次の tick で再試行する)。通知が増えたときの影響は deploy 後に測る (§5)。

## 5. 未解決

- deploy していない。deploy 後の停止の観測 (`launch_halted` の出方・30 分後の digest の送信) は未測定。deploy は PM が行う。
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
git diff cf5bd08a HEAD -- infra/pm-worker
curl -fsS "$(tr -d '\n' < ../../tools/pm/worker_url)/status"
```
