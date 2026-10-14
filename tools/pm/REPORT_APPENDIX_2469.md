> **正本**: 本付録 (`tools/pm/REPORT_APPENDIX_2469.md`)。対象は PM Worker の降格 (#2340・PR #2469)。PR #2469 の round 3〜9 の修正と測定。`tools/pm/REPORT.md` は 250 行上限のため、測定値は本付録に置き、REPORT.md §20 には参照だけを書く。

## 1. 測定の対象と環境

- 測定 commit: `7c7bcc74` (main `3b866a61` (#2783) の取り込み merge。コードを変えた最後の commit)。競合 4 ファイル (`docs/DOC_MAP.md`・`infra/pm-worker/src/engine.ts`・`infra/pm-worker/test/status.test.ts`・`tools/pm/REPORT.md`) は両側を残して解消した。以後 HEAD までの commit は `infra/pm-worker` を変えない (§5)。
- 直前の測定 (`e78527db`・件数 210) は main の pnpm 移行 (`pnpm-lock.yaml`・`pnpm-workspace.yaml`) より前の依存で測った。main の手順 (`infra/pm-worker/README.md`) に合わせ、本付録の数字で置き換える。
- 依存: `cd infra/pm-worker && pnpm install --frozen-lockfile` (pnpm 12.10.1・既定の `minimumReleaseAge` のまま。79 packages・2.1 s・エラーなし)。Node v22.23.3・bun 1.4.3。作業ツリーは worktree (`ws-2469`) の `infra/pm-worker`。
- load average (1 分): `npm test` の 5 回の直前は 1.78・1.80・2.27・2.44・2.99。

## 2. 結果

| 検証 | コマンド | 結果 | 所要 (wall) |
|---|---|---|---:|
| 統合・単体 (5 回連続) | `npm test` (`node --experimental-strip-types --no-warnings --test 'test/*.test.ts'`) | 1〜5 回目とも tests 336 / pass 336 / fail 0 (rc 0) | 12.4・12.4・12.6・12.2・11.8 s |
| Workers | `npm run test:workers` (`vitest run --config vitest.config.ts`) | Test Files 1 passed・Tests 4 passed | 1.9 s (vitest Duration 1.22 s) |
| unit | `npm run test:unit` (`vitest run --config vitest.unit.config.ts`) | Test Files 4 passed・Tests 45 passed | 1.6 s (vitest Duration 1.30 s) |
| build | `npm run build` (`bun build src/index.ts --target=browser --format=esm --external 'node:*' --minify`) | exit 0 (Bundled 25 modules・index.js 104.78 KB) | 0.08 s |

件数 336 は main (#2783 まで) の取り込みで増えた分を含む。前回の 210 件とは数えた対象が違う。

flake (round 8): round 8 で 1 回だけ出た `降格 (ネガ)` の `edge` の FAIL は、`npm test` の 5 回連続 pass と、§4 の変異前の `demote_shadow.test.ts` 単独の 1 回で再現しなかった。原因は特定できていない (コード上で `edge` が降格する経路は見つかっていない)。再発したら本付録に追記し、原因を特定してから直す。

## 3. 変更の内容

### 3-1. 降格中の digest (round 3・B1・`a258a7d8`)

- `digest()` の判定を `if (!this.d.cfg.liveDispatch || !gh)` から `if (!this.dispatchLive() || !gh)` に変えた。`dispatchLive()` は `cfg.liveDispatch && !meta.demoted` なので、降格中は digest も would のみになる (`counters.wouldDispatchPm` が増え、`would_dispatch_pm` に `digest#0` が残る)。
- テスト `降格中は oc-pm digest を送らず would に数える。解除の後は送る`: VM の `/oc` (+1 分) と PM App の `/oc` (+2 分) で降格 → +24 時間の tick で digest が送られず `wouldDispatchPm` が増える → `POST /demote/reset` → +48 時間の tick で 1 件送る。

### 3-2. 降格の組を Worker と個人の `/oc` に限る (round 4・`76932e18`)

- 決定: ADR D26 (`docs/DECISIONS.md`・採用・PM 補助 subagent の代理判断。経緯は PM のコメント 2026-10-14 15:36Z)。
- `noteOc` は `vm` (個人アカウント = `cfg.pmLogins`) を記録し、判定の条件に `x.vm !== vm` を足した。組は「同じ issue・`OC_DOUBLE_MS` 以内・反対の種別」だけ (先後は問わない)。記録は従来どおり両方 (shadow の突き合わせは `vm` を使う)。
- 旧 (`76932e18` より前): PM のログイン全部の組。Worker 自身の launch と再投入 (Worker 同士) で自己降格していた。

### 3-3. main の取り込みと、ネガコンの組み直し (round 5・`e78527db`・round 6)

- `origin/main` (`f3102162`・#2485) を merge で取り込んだ (rebase・force push はしていない)。競合は 3 ファイル (`engine.ts` の初期化、`DOC_MAP.md` の行、`REPORT.md` の節)。REPORT の節は衝突を避けて §16 に置いたが、その後 main の §16〜§19 と衝突したため §20 に直した (3-4)。
- テスト (`test/demote_shadow.test.ts`) の組み直し:
  - 「同じコメントの再配送」は、個人の投稿 (VM) の 2 回配送と、39 分後の Worker の投稿 (PM_BOT) の組に直した。記録は 2 件 (`ocPosts.length`)。
  - 窓より前のネガコンを 1 件足した: Worker の `/oc` (窓の中・+1 分) と、窓より前の個人の `/oc` (−10 分) の組は降格しない。外側の `at >= from` だけを外すと、この組で降格する。

### 3-4. main (#2783) の取り込みと競合の解消 (round 9・`7c7bcc74`)

- `origin/main` (`3b866a61`) を merge で取り込んだ (rebase・force push はしていない)。`infra/pm-worker` の main 側の変更は 48 ファイル (pnpm 移行・同時実行の数え方・規則 A の close・失敗配送の再送・VM の状態の取り込み・`wrangler.toml` の TARGET・`observability` など)。
- 競合の解消 (両側を残した):
  - `engine.ts`: `NO_IMPORT` (#2343) と本 PR の `demote`・`restore` の kind。`zero()` の計数は `closed`・`wouldClose` (main) と `demoted`・`restored` (本 PR) の両方。`/status` は `mode_close`・`auto_close_detected` (main) と `demoted_reason`・`shadow` (本 PR) の両方。`mode`・`mode_launch`・`mode_dispatch` は `launchLive()`・`dispatchLive()` を使う (降格ゲート)。
  - `status.test.ts`: `ADDED_KEYS` は両方。`counters` の deepEqual は 2 組の計数の両方。`mode_close`・`auto_close_detected` の assert を残した。
  - `docs/DOC_MAP.md`: 本付録の行と main の `REPORT.md` の行 (~250)。
  - `tools/pm/REPORT.md`: main の §16〜§19 を残し、本 PR の節は §20 (1 行・全文は本付録)。
- 降格ゲート: `git grep -n "cfg.live" 7c7bcc74 -- infra/pm-worker/src/engine.ts` の結果は 5 行。`cfg.liveLaunch`・`cfg.liveDispatch` は `launchLive()` (425 行)・`dispatchLive()` (428 行) の定義だけ。残る 3 行は main の別機能 (`cfg.liveClose` 1364・1630 行 (規則 A の自動 close と `mode_close`)、`cfg.liveRedeliver` 1475 行 (失敗配送の再送))。ADR D26 は降格で止めるのは launch と dispatch と定めており、これら 2 つは対象外 (PR 本文の未解決表に書いた)。

## 4. ネガコン (測定 commit `7c7bcc74` の内容に対して 1 つずつ変異)

各変異は `src/engine.ts` に 1 か所だけ入れ、`node --experimental-strip-types --no-warnings --test test/demote_shadow.test.ts` を流した後、バックアップから戻して `cmp` で一致を確認した。

| 変異 | 内容 | 結果 |
|---|---|---|
| (base) | 変異なし | 9 / 9 pass |
| (a) 降格ゲート | `async digest(` 内の `if (!this.dispatchLive() \|\| !gh)` を `if (!this.d.cfg.liveDispatch \|\| !gh)` に戻す | `not ok 7` (降格中の oc-pm digest): 8 pass・1 fail |
| (b) 組の条件 | `noteOc` の ` && x.vm !== vm` を外す (Worker 同士・個人同士も数える) | `not ok 3` (降格 (ネガ)): 8 pass・1 fail |
| (c) id 重複除去 | `if (this.ocPosts.some((x) => x.id === id)) return;` を外す | `not ok 3` (降格 (ネガ)): 8 pass・1 fail |
| (d) 窓判定 | ` && Math.abs(x.at - at) <= OC_DOUBLE_MS` を外す (30 分超の組も数える) | `not ok 3` (降格 (ネガ)): 8 pass・1 fail |
| (e) 窓より前 | 外側の `if (at >= from && this.ocPosts` の `at >= from &&` を外す | `not ok 3` (降格 (ネガ)): 8 pass・1 fail |

- 元に戻した後の `demote_shadow.test.ts`: 9 件 pass / 0 fail。`src/engine.ts` はバックアップと `cmp` で一致 (作業ツリーに差分なし)。

## 5. 差分 (測定 commit から HEAD まで)

- `git diff 7c7bcc74 HEAD -- infra/pm-worker` の出力は空 (差分 0)。`7c7bcc74` の後の commit (本付録・REPORT.md・`docs/DOC_MAP.md`・PR 本文の変更) は `infra/pm-worker` の外だけ。本付録を commit した後の HEAD で確認した。
- PR の main に対する差分 (`git diff --stat origin/main HEAD`): `infra/pm-worker/src/app.ts`・`engine.ts`・`test/demote_shadow.test.ts`・`test/status.test.ts`・`docs/DOC_MAP.md`・`tools/pm/REPORT.md`・本付録の 7 ファイル。`wrangler.toml` は含まない。

## 6. 未解決

- 降格の組 (3-2) は ADR D26 のとおり。戻すには D26 を改訂し、`x.vm !== vm` の条件を外す (旧来の組み方)。`wrangler.toml` は main の版 (`LIVE_*` は変えていない) のままなので、この変更を入れてから再デプロイする (D26 の影響の項)。
- PM 判断 (突き合わせの元と窓・降格の dispatch の範囲・昇格) は PR 本文の未解決表に残す。本付録の対象外。
- flake (round 8) の原因は特定できていない (§2)。
