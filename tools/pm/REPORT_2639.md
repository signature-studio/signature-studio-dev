# tools/pm REPORT 付録 (#2639): 停止印 (oc-fix-limit) の作者を github-actions[bot] (型 Bot) に限る

- 対象: `infra/pm-worker/src/webhook.ts` (停止印の信頼)・`src/engine.ts` (reconcile の REST 取り込み)・`src/config.ts` (`MARK_LOGIN`)・`.github/scripts/prepare-event-context.sh` (oc-pm の `kind=stuck` の文脈)。
- issue: #2639 (`[CI-122]`)・親: #2622。前提はいずれも merge 済み: #2640 (MERGED 2026-10-14T16:23:37Z)、issue #2638 の workflow 変更 = PR #2851 (MERGED 2026-10-14T20:43:31Z)。

## 0. 結論

- 停止印 `<!-- oc-fix-limit -->` は、作者 `github-actions[bot]` (型 Bot) の投稿だけを信じる。実装 App 名義の偽の停止印 (+ `oc-pm-intent: stuck`) では、oc-pm の stuck 対象にならない。
- 測定 commit `a1085785`。node:test 395 件 (n=3 とも全件 PASS)・vitest 70 + 7 件・変異テスト 9 件 (killed 9)・本件の変異 5 件 (killed 5)・`.github/scripts/tests/test-*.sh` 11 本 (全 PASS)。
- 本番 (deploy 後): launch は止まらない (`stuck-ceiling` は label 基準)。deploy は保存済みの停止印を消さない。旧 workflow で実装 App 名義に付いた印 (PR #2819 の 1 件) は、保存値として残る。oc-pm の stuck 対象 (`detectPm`) かどうかは、停止印より後の PM 応答 (`pmAt`) で決まる。作者 `github-actions[bot]` の停止印 3 件 (#2842・#2885・#2995) は、deploy 前は未検出 (`pm_detected.stuck=0`)。deploy 後は次の full sync で取り込まれ、stuck 対象になりうる (open な `oc:stuck` 4 件の実測は §5)。

## 1. 測定の対象

- 実装と測定の commit: `a1085785` (`fix(pm-worker): trust the stop mark (oc-fix-limit) only from github-actions[bot] (#2639)`)。コードはこの commit で確定。
- 測定時の作業ツリーは `git status --porcelain` が 0 行 (コミット済み HEAD で再現)。
- `git diff a1085785 HEAD -- infra/pm-worker .github/scripts` は、§6 の確認で 0 行。本 REPORT の commit は `tools/pm` と `docs/DOC_MAP.md` だけを変える。

## 2. テスト (測定 commit `a1085785`・`pnpm install --frozen-lockfile` 済み)

`load` は `/proc/loadavg` の 1 分平均で、各コマンドの開始時に読んだ値。

| コマンド | 件数 | 結果 | 所要 (real) | load (開始時) |
|---|---:|---|---:|---|
| `node --experimental-strip-types --no-warnings --test 'test/*.test.ts'` (n=3) | 395 | 395 PASS / 0 FAIL (3 回とも) | 21.96 / 22.32 / 22.45 s | 0.17 → 1.21 → 1.79 |
| `npm run test:unit` (vitest) | 70 (5 files) | 70 PASS / 0 FAIL | (実行時の load 1.80) | 1.80 |
| `npm run test:workers` (vitest + workerd) | 7 (2 files) | 7 PASS / 0 FAIL | (同上) | 1.80 |
| `npm run test:mutation` (halt の既存 9 変異) | 9 変異 | killed 9・survived 0 | (同上) | 1.73 |
| `.github/scripts/tests/test-*.sh` (scripts-test の glob と同じ) | 11 本 | 11 PASS | 33 s | 1.61 |

- 件数の増分: 新規 4 件 (`test/pmdispatch.test.ts` 2・`test/webhook.test.ts` 1・`test/engine.test.ts` 1)。`^test(` の数で origin/main 380 → HEAD 384 (+4)。
- `test-dispatch-context.sh` は 156 件 PASS (新規の 2 件を含む)。`test-pr-loop.sh` 133 件・`test-watchdog.sh` 144 件も PASS (両方とも本件では変更していない。`watchdog.sh` は説明コメントのみ変更)。

## 3. ネガティブコントロール (本件の防御を 1 か所ずつ壊す)

一時の変異スクリプト (repo 外・commit しない) で、src / 文脈スクリプトの 1 行を下表のとおり壊して該当テストを流し、元に戻した (戻したあと `git status --porcelain` が 0 行)。

| 変異 | 壊し方 | 落ちたテスト (FAIL 件数) |
|---|---|---|
| 実装 App の印も信じる | `stopper` に `login === botLogin` を足す | 3 (reconcile・検出 stuck の偽装・webhook の偽印) |
| 型の判定を外す | `stopper` を `login === mark` だけにする | 3 (同上。型 User の同じ login を含む) |
| reconcile の slim が型を落とす | `slim` の `user.type` を外す | 1 (reconcile の REST 取り込み) |
| reconcile の本文保存から markLogin を外す | `mine` から `markLogin` を外す | 1 (本文が空になり、印を読めない) |
| oc-pm の stuck 文脈の作者を外す | `prepare-event-context.sh` の `$mark` 条件を外す | 2 (test-dispatch-context.sh の 11d') |

- 変異 5 件はすべて killed (FAIL が 1 件以上)。
- 新しい pmdispatch の検出テストは、実装 App・reviewer・型 User の偽印 (+ intent stuck) で `targets` が空、作者 `github-actions[bot]` の印で `stuck#10` になることを確かめる。`MARK_LOGIN` を変えると既定の作者は信じないことも確かめる。

## 4. 変更の中身

- `webhook.ts`: `stopper = c.user.type === "Bot" && login === markLogin`。`markLogin` は `DEFAULT_MARK_LOGIN` (`github-actions[bot]`)。`trusted` (実装 App・reviewer を含む) は、終了の記録 (`oc-run-outcome`)・PM のマーカーでは従来どおり使う (本件の対象外)。
- `engine.ts` (reconcile): REST の一覧から取る停止印も webhook と同じ判定にする。`mine` に `markLogin` を足して本文を残し、`slim` は `user.type` を残す。どちらも無いと、reconcile で取り込んだ停止印は信じられない (変異 2 件で確認)。
- `config.ts`: `MARK_LOGIN` (Worker の環境変数・既定 `github-actions[bot]`)。`wrangler.toml` の `[vars]` には足していない (既定で足りる)。
- `prepare-event-context.sh`: `kind=stuck` の文脈を `.user.type == "Bot" and .user.login == $mark` にする。`$mark` は `OC_MARK_LOGIN` (既定 `github-actions[bot]`)。`watchdog.sh` は #2622 から同じ規則。

## 5. 本番への影響 (deploy 後の挙動・実測)

取得: 2026-10-14T22:26:44Z、`gh pr list --label oc:stuck --state open` と、各 PR の最新の `<!-- oc-fix-limit -->` のコメント (作者は `gh api` の `user.login` と `user.type`)。

| PR | 最新の停止印 (UTC) | 作者 (型) | deploy 後の oc-pm の stuck 対象 |
|---|---|---|---|
| #2995 | 2026-10-14T22:20:03Z | github-actions[bot] (Bot) | deploy 前は未検出 (旧 Worker は `github-actions[bot]` の停止印を信じない)。deploy 後は次の full sync で取り込まれ、stuck 対象になりうる (以後の PM 応答なし) |
| #2885 | 2026-10-14T21:40:13Z | github-actions[bot] (Bot) | deploy 前は未検出 (同上)。deploy 後は次の full sync で取り込まれ、stuck 対象になりうる (以後の PM 応答なし) |
| #2842 | 2026-10-14T21:01:37Z | github-actions[bot] (Bot) | deploy 前は未検出 (同上)。deploy 後は次の full sync で取り込まれ、stuck 対象になりうる (以後の PM 応答なし) |
| #2819 | 2026-10-14T20:29:50Z | opencode-for-signature-studio[bot] (Bot) | 変わらない見込み。印は #2851 の merge (20:43:31Z) より前に、旧 workflow で実装 App の token から投稿された。deploy は保存値を消さないので、印は保存値として残る。停止印より後の PM 応答 `oc-pm-decision` (20:53:48Z・`botLogin` の投稿なので `pmAt` になる) を取り込み済みなら、`detectPm` は対象にしない |

- launch: 止まらない。`launch_halted` の `stuck-ceiling` は `countOpenPrs` の label 数 (`src/phase.ts`) で決まり、停止印を読まない。現在 4 件 (`STUCK_HIGH` = 40 未満)。既定のままで止まる条件は増えない。
- `/status` の `stuck_age_max_min`: 保存済みの停止印の時刻を起点にする (`engine.ts` の `stuckAges`)。停止印が無い PR だけ PR の `updated_at` を起点にする。#2819 は保存済みの停止印があるため、起点は 20:29:50Z のまま変わらない。
- 本番の実測 (2026-10-14T22:42:20Z・deploy 前・本番 `/status`): `mode=live`・`fresh=true`・`stuck=4`・`stuck_age_max_min=132` (20:29:50Z からの経過)・`pm_detected.stuck=0`。
- 既存の状態の扱い: 新しい印 (#2851 以後) は `github-actions[bot]` で投稿される。Worker は保存値を起動時に読み直し (`store.ts` の `loadState`)、保存値の作者は再検査しない。作者の判定が効くのは、届いた・reconcile で取り込んだコメントだけ。保存済みの停止印を消すのは、閉じた issue / PR の掃除 (`engine.ts` の `prune`) だけ。watchdog.sh は Worker が live のとき oc-pm を起動せず、live でないときだけ最新の停止印 (作者が `MARK_LOGIN` の投稿) で判定する。
- deploy: 本 PR は deploy しない (deploy は PM の作業)。deploy 後は `/status` の `pm_detected.stuck` (stuck の対象数) と `stuck_age_max_min` を見る。`pm_detected.stuck` の期待値は 3 件 (#2842・#2885・#2995。次の full sync の後に確認する。#2819 は PM 応答があるため対象外の見込み)。#2819 の起点が 20:29:50Z のままなら、保存値が残っている。

## 6. 差分確認・未解決・範囲

- 差分確認: `git diff a1085785 HEAD -- infra/pm-worker .github/scripts | wc -l` → 0 (本 REPORT の commit 後に実行)。
- 未解決 (起票先付き):

| 未解決 | 影響 | 起票先 |
|---|---|---|
| #2819 (`oc:stuck`) の停止印は実装 App 名義で、deploy 前に保存された。保存値は deploy 後も残る。停止印より後に PM 応答 (20:53:48Z) があり、取り込み済みなら `detectPm` は対象にしない | `detectPm` の対象外は deploy の前後で変わらない。`stuck_age_max_min` の起点は 20:29:50Z のまま (ラベルは残る) | PM 判断済み (`oc-pm-decision` R7・2026-10-14): ラベルと印は触らず、現状のまま残す。子 issue は未起票 |
| `fix-progress.sh` は `OC_MARK_TOKEN` が空のとき、停止印を実装 App の `GH_TOKEN` で投稿する (`GH_TOKEN="${MARK_TOKEN:-${GH_TOKEN:-}}"`)。現行 workflow は常に `OC_MARK_TOKEN` を渡すため、この経路には入らない | 将来 `OC_MARK_TOKEN` が外れると、停止の印は PM に届かない (ラベルは付く) | PM 判断済み (`oc-pm-decision` R7・2026-10-14): フォールバックは外さず現状のまま。外すなら別の変更として扱う。子 issue は未起票 |
| deploy 後の本番 `/status` (`pm_detected.stuck` の期待値 3 件・`launch_halted`・`stuck_age_max_min`) と oc-pm の stuck 起動は未測定 | 本番での効き方は未確認 | PM (deploy 後に確認) |

- 検証範囲: `infra/pm-worker` のテスト (fake の webhook・fake gh)、`prepare-event-context.sh` の fake gh 試験、停止印の実投稿元 (`gh api` の実測 4 件)。
- 範囲外: 本番 Worker の受信・deploy 後の挙動、Actions 上の実 run での停止印の投稿 (実 run の確認は deploy 後の PM の作業)。
- 素材: `oc_artifacts: none` (FL・plugins の素材は使わない)。KPI (FLEngine 起動・ウィンドウ) は起動・GUI に関わらないため書かない。
