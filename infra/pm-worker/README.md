# signature-studio-pm (PM Worker)

PM の launch / watchdog を、VM のポーリング (systemd timer) から **webhook 駆動 + Cron / alarm** の Cloudflare Worker に移す (#1751)。
コードの既定は **dry-run** (GitHub へは書き込まない)。稼働中の `wrangler.toml` は 2026-10-14 から **live** (後述『切替の記録』)。書き込みの有効化と VM timer の停止は PM の判断。
書き込みは経路ごとに独立したスイッチを持つ: launch の `/oc` コメント投稿 = `LIVE_LAUNCH`、`repository_dispatch` (`oc-watchdog` と `oc-pm`) の送信 = `LIVE_DISPATCH` (#2417)、失敗した webhook 配送の再送 = `LIVE_REDELIVER` (#2339。未設定なら記録のみ)。

## 構成

| 要素 | 役割 |
|---|---|
| `POST /webhook` | GitHub App の webhook。`X-Hub-Signature-256` を HMAC-SHA256 (定数時間) で検証してから状態に反映する。対象: `issues` `issue_comment` `issue_dependencies` `pull_request` `pull_request_review` `workflow_run` |
| Durable Object `PmDO` (SQLite) | issue / PR / run / 最後の bot 報告 / blocked_by / launch 時刻を保持。App の鍵は AES-GCM で封じて保管 |
| alarm (webhook の 2 秒後 / 毎分) と Cron Trigger (毎分) | `tick`: 同期 (6 時間ごとに full、5 分ごとに reconcile)・`repository_dispatch` (`oc-watchdog`、前回の送信から 5 分未満は送らない。`LIVE_DISPATCH`。検出した `oc-pm` も同じスイッチ)・launch (`LIVE_LAUNCH`) |
| `POST /admin/resync` | 管理用の全体同期 (#2339)。派生状態を REST の内容で作り直す (`fullSync` と同じ。永続状態は触らない)。認証は呼び出し側の GitHub token (Bearer) が repo の push 権限を持つこと (新規の API token は作らない)。**未認証・不明な token・読み取りだけの token は 404** (入口で DO を呼ばない)。1 時間に 2 回まで、3 回目は 429 (`retry-after`) |
| `GET /setup` `GET /setup/callback` | GitHub App `oc-pm-for-signature-studio` の manifest flow (org 所有)。`/setup` は無認証だが、期限内 (1 時間) の state があれば上書きせず同じ state を返す。state は org 所有の App への変換に成功したときだけ消費する |
| `GET /status` | 集計のみ (実行中 run 数・ready/blocked 数・最終 reconcile 時刻・モード・健全性の観測。下の『/status の観測』)。`mode_launch` / `mode_dispatch` が経路ごとのモード (`live` / `dry-run`)。`mode` は両方 `live` のときだけ `live` (片方だけなら `partial`、どちらもなら `dry-run`。`tools/pm/pm_gate.sh` は `mode=live` を『VM の command を止めてよい』と読む)。`?detail=1` は repo の push 権限を持つ GitHub token (Bearer) が必要 |

launch の規則は `tools/pm/launch_issues.py` の `classify` と同じ入出力 (固定 JSON を Python 版と TS 版の両方で読む突き合わせテスト: `test/classify.test.ts`)。差分は次の 5 点で、いずれも issue 本文を解析しない。

1. blocked_by の一覧が不明な issue は着手しない。
2. open な子 (`親: #N`) を持つ親 issue は着手対象から外す。
3. ラベル `oc:no-pr` は『PR を出さずに終わった』run の後。最後の `oc-run-outcome` の reason で再着手を決める (`plan()` の `noPr`)。cooldown (既定 3 時間) の間は着手しない。cooldown の後は次のとおり。
   - `unknown`: 1 回だけ再着手する。
   - `artifact`: 前回の `oc_artifacts` に無い allowlist 内の素材が本文から増えるときだけ 1 回再着手する (増えなければ再投入しない)。
   - `stop`・`split`: 再投入せず、PM agent (`oc-pm`・下の oc-pm 節) に回す。
   - `blocked`: blocker が close されるまで再投入しない。
   - 再投入の計数は `unknown` と `artifact` の再投入だけ (上限 3 回)。`launch-unobserved` (投稿の run が 5 分で現れなかった) は再投稿せず stopped に残す。
   `oc:stuck` は人の判断待ち。`pm-apply`・`needs-user-input` は下の oc-pm 節のとおり、再着手せず `user` 行に置く。
4. 同期が 15 分以上止まっている間、または一覧を上限ページで打ち切った間 (下の「同期の窓と打ち切り」) は、投稿も `oc-watchdog` の dispatch もしない (`/status` の `fresh=false`)。
5. relaunch (`oc:no-pr` の再投入・素材の追加) も 1 tick の枠 `min(room, BATCH, relaunch + ready)` に入り、残りの枠を ready が使う (`src/launch.ts` の `planLaunch`)。relaunch は room や BATCH を超えても全件出す。枠を `ready` の件数だけで頭打ちにする VM の `launch_issues.py` の式とは、relaunch がある tick で最大 relaunch の件数だけ差が出る (VM の式は変えていない)。relaunch は classify が issue ごとに 2 回までに絞る。

`/oc` コメントの本文は固定テンプレートで、可変なのは `oc_artifacts:` 行と、再投入の意図に `focus=K` があるときの受入条件 1 行だけ。素材名は `.github/scripts/prepare-event-context.sh` の `ARTIFACT_RE` と同じ集合 (`ALLOW_ARTS`) を通ったものだけ。webhook の自由文 (タイトル・本文・コメント) は指示文に入らない。

再投入の意図 (`<!-- oc-pm-intent: relaunch issue=N arts="..." focus=K -->`、#2475): issue ごとに最新の意図マーカーを保持する。実装 App の意図は第三者の意図より優先する。意図のコメントは bot の投稿でも `botLast` (停止報告の窓) を動かさない。次を**全て**通ったときだけ `/oc` を投稿する。
  - 検査 (`src/launch.ts` の `checkRelaunchIntent`): 書き手は実装 App・`issue=` がコメントの issue と一致・`arts` が `ALLOW_ARTS` の部分集合・`focus` は 1〜9 (任意)・同じ issue に 24 時間で 3 回まで。
  - 分類 (`plan()` の rows): 投稿してよいのは picks と同じ `ready`・`relaunch`・`stopped` (PM の判断待ち) だけ。`user`・`blocked`・`started` は投稿しない。`recent` (着手直後の待ち) は処理済みにせず、次の tick に回す。`oc:stuck`・`pm-apply`・`needs-user-input` は投稿しない。`oc:no-pr` は picks の再着手と同じ cooldown (`NO_PR_COOLDOWN_H`) と上限 (3 回) を見る。`stopped` のうち親の子待ち (`parent/stuck`) と未観測の launch (`launch-unobserved`) は投稿しない。
  - 順序: 意図は picks より先に処理し、意図で扱った issue は picks から外す (picks が先だと、同じ issue の意図が focus なしで処理済みになるため)。403/429 や REST の残量で止まったら、同じ tick の picks も止める。
  - 投稿後に出た意図 (PM の手動の `/oc` を含む) と、停止中 (review-only・stuck 上限・REST の残量不足) は処理しない。
  - 拒否は理由ごとに `counters.intentRejected` へ数え (語彙: `author` `issue` `arts` `focus` `limit` `user` `blocked` `started` `stopped`)、その意図は処理済みにする。
  - 投稿の可否は `LIVE_LAUNCH` に従う (既定 dry-run。`counters.intentWouldLaunch` に記録)。dry-run で保留した意図は処理済みにならないので、`LIVE_LAUNCH` を `"1"` にすると、保留分がその tick で投稿される。切替の前に `GET /status` の `counters.intentWouldLaunch` と `would_launch_now` を確認する。

## oc-pm: PM agent を起こす終端状態の検出と送信 (#2333)

PM の判断が要る終端状態を **決定的に** (ラベル・マーカー・正規表現だけ。LLM も本文の解析も使わない) 検出し、`repository_dispatch` の `oc-pm` を送る。入口側は `.github/scripts/prepare-event-context.sh` (#2327)。

| kind | 検出 (すべて open の対象。起票者は後述の絞り込みを通ったものだけ) |
|---|---|
| `stuck` | `oc:stuck` の PR で、最新の停止コメント (`<!-- oc-fix-limit -->`、bot 投稿) に `<!-- oc-pm-intent: stuck pr=N ... -->` がある (`pr=` が当該 PR の番号) |
| `no_pr` | `oc:no-pr` の issue で、最後の `<!-- oc-run-outcome: no-pr reason=... -->` が `split` / `stop`、または `unknown` で Worker が再投入済み (再投入の後の run でも `unknown`) |
| `needs_decision` | reviewer の最新の verdict が CHANGES_REQUESTED で、本文が `NEEDS_KEY` (`src/needs.ts`。`tools/pm/pm_needs.py` の `KEY` と同じ正規表現・同じ行分割) に一致し、その後に PM 応答が無い |
| `user_answered` | `needs-user-input` の issue に、ラベルが付いた後に非 bot のユーザーのコメントが付いた (コメント者が `MEMBER` / `OWNER` / `COLLABORATOR` のものだけ。第三者のコメントでは起こさない #2461) |

- マーカーは **bot (実装 App・reviewer App) の投稿だけ** を信じる (誰でもコメントできるため)。PM 応答は、PM のログイン (`PM_LOGINS` と PM App) のコメント、または bot の `oc-pm-decision` / `oc-pm-intent: relaunch` マーカー付きコメント。根拠より後にあれば、その対象は送らない。
- 状態は `sig` (issue / PR 番号ごとの時刻・列挙値・真偽。本文は持たない)。webhook の増分で更新し、webhook で埋まらない reviewer の verdict と `needs-user-input` の付与時刻は reconcile で REST から一度だけ補う (best effort)。
- 送信: payload は `{"event_type":"oc-pm","client_payload":{"kind":<列挙>,"ref":<数字>}}` だけ。値は検証済みの列挙・整数から組み立て、issue / PR の自由文は入らない。PM App の installation token で送る。スイッチは `LIVE_DISPATCH` (oc-watchdog と同じ。別スイッチは作らない)。
- 絞り込み: 起票者が `MEMBER` / `OWNER` / `COLLABORATOR`、または許可 bot (`opencode-for-signature-studio[bot]` `oc-reviewer-for-signature-studio[bot]`) の対象だけ。起票者が未取得の対象は送らない。
- 抑止 (DO の `meta/pmDispatch`): 同じ (kind, ref) は 60 分に 1 回・全体で 1 時間に 12 起動・同じ ref に 24 時間で 3 回まで。未送信の対象を先に、送信済みは古い順に選ぶ。失敗した試行も数える (403 / 429 はその tick を打ち切る)。同期が 15 分以上止まっている間は送らない。
- **dry-run (既定。`LIVE_DISPATCH` が `"1"` でないとき)**: 送らず、`/status` の `would_dispatch_pm` (`?detail=1` のみ) と `counters.wouldDispatchPm`、`pm_detected` (kind ごとの検出数) に記録する。履歴は live と分ける (`meta/pmWould`)。`LIVE_LAUNCH` は関係しない。
- ラベル `pm-apply` / `needs-user-input` の issue (着手しても PR を出さない/出せない) は、`no_pr` の検出から除く。`plan()` は、この 2 ラベルの issue を ready・再投入の対象であっても着手せず `user` 行に置く (`oc:no-pr` の有無に依らない)。`user_answered` は `needs-user-input` が対象。`tools/pm/launch_issues.py` との差は PR 本文の未解決表に書く。
- 検出するのは上の 4 kind。`refs_orphan` は [CI-58]、`supply` / `digest` は [CI-71] / [CI-70] が担当する。

## /status の観測 (#2338)

Worker の健全性を外から判断するための集計。既存のキーは変えず、次を足した (個票・自由文は出さない)。

| キー | 意味 |
|---|---|
| `last_webhook_at` | 署名を検証できた webhook の最後の受信時刻 (401 では進めない)。無ければ `null` |
| `last_dispatch_at` | `repository_dispatch` (`oc-watchdog`) に成功した最後の時刻。dry-run では `null` のまま (would は既存の `last_watchdog`) |
| `running` | `{in_progress, queued, pending}`: DO が持つ未完了 run を状態別に数えた値。event は問わない (TARGET に数える `active_runs` とは別) |
| `dry_run_skipped_posts` | dry-run のために投稿しなかった書き込み (`/oc` 投稿 + `repository_dispatch`) の累計 (`counters.wouldLaunch + wouldDispatch`) |
| `reconcile_diff` | `{last, total}`: reconcile が REST を適用して DO の内容が変わった entity (issue・PR・run・bot/PM のコメント) の件数と累計。webhook の欠落の指標。`updatedAt` だけの違い (コメント追加で進む) と full sync は数えない。配送遅延の最中の差も数えるので、1 回の小さな値は欠落とは限らない |
| `rest_remaining` / `rest_used` / `rest_reset_at` | Worker の GitHub REST クライアント (installation token) の全応答の `x-ratelimit-remaining` / `-used` / `-reset` (ヘッダが正。`gh api rate_limit` の本文は食い違う)。失敗応答も含む。ヘッダの無い応答・数値でない値では更新しない。一度も観測していなければ `null` (0 ではない)。JWT で叩く `/app/*` と、`/status?detail=1` の呼び出し側の token は別枠なので記録しない |

自律運転の指標 (#2335)。件数と時間だけを返す (題名・本文・login は出さない。issue / PR 番号は可)。

| キー | 意味 |
|---|---|
| `stuck` | open な PR のうち `oc:stuck` の数 |
| `stuck_age_max_min` | 上の PR の経過分の最大。起点は最新の停止コメント (無ければ PR の更新時刻)。該当が無ければ `null` |
| `needs_pm` | open な issue と PR のうち `needs-pm` の付いた数 (合計) |
| `needs_user` | open な issue と PR のうち `needs-user-input` の付いた数 (合計) |
| `no_pr_by_reason` | `{split, artifact, unknown, blocked, stop}`: open な `oc:no-pr` の issue を、最新の outcome の理由別に数えた値。outcome の無いものは数えない |
| `refs_only_merge_rate_24h` | `{merged, refs_only, rate}`: 直近 24 時間に merge された PR の件数 (`merged`) と、そのうち本文が `Refs #N` のみ (`Closes` / `Fixes` / `Resolves` が 1 つでもあれば数えない) の件数 (`refs_only`) と率。0 件なら `rate` は `null`。merge 済み PR の『Refs のみ』は merge 時点の本文から取った真偽値だけを持つ (本文は保存しない)。導入前に merge された PR は、次の全体同期 (6 時間以内) で埋まる |
| `open_issues_delta_24h` | 現在の open issue 数から、24 時間前以前で最も新しい 1 時間ごとの点 (`meta/openHist`、最大 48 点) の数を引いた差。点が無い (履歴が 24 時間分に満たない) ときは `null`。同期が古い間と一覧を打ち切った間は点を残さない |
| `pm_dispatch_1h` | 直近 1 時間の `oc-pm` の送信数 (dry-run の would を含む。`pmHistory` と同じ live / dry-run の別) |

**rate-guard**: `rest_remaining` が 1,500 未満の間は launch を止める (`launch_stop: "rate-guard"`)。1,499 で止まり、1,500 で継続する。未観測 (`null`) は止めない。
reconcile の読み取りと watchdog の dispatch は続く。launch の途中でも、投稿の応答で残量が下がれば残りを投稿しない。遷移 (on/off) のときだけログに 1 行残す。
`stuck-ceiling` (既存) が立っているときは `launch_stop` はそちらを返す。dry-run でも計画 (`would_launch_now`) は止まる (投稿はもともとしない)。

## /oc 投稿の観測 (#2342)

投稿した `/oc` (launch) に対して、題名が issue 題名と一致する `issue_comment` 由来の run (`in_progress`・`queued`・`pending`・`completed`) が現れたかを DO (`launchObs`) に記録する。
投稿の応答時刻から 5 分以内に観測できなければ `failed` (着手失敗) とし、`/status.launch_unobserved` に issue 番号を出す。`failed` の issue は**自動では再投稿しない** (`stopped` に `launch-unobserved` として置く)。
後から同じ題名の run が作成時刻 (投稿の 1 分前以降) で現れたら `observed` に直す。dry-run は投稿しないので記録しない。
観測の判定は同期が新しいときだけ `failed` にする。観測済み・記録の無い古い launch は従来どおり 3 時間の `recent` 判定を残す (完了済みで報告の無い run を即時に再投稿しないため)。

**secrets を出さない**: `/status` は集計だけで、issue のタイトル・本文・コメントは載せない。自由文は `last_error.what` とログの `note` だけ (どちらも `?detail=1` のみ)。
これらと `console.log` は `src/redact.ts` を通し、PEM・`gh*_` / `github_pat_` の token・JWT・`Bearer …`・`sha256=…` と、実行時に分かっている secret (webhook secret・PEM・STORE_KEY・直近の installation token) を `[redacted]` にする。

## 失敗した webhook 配送の回収と `/admin/resync` (#2339)

- **再送**: GitHub は失敗した配送を自動で再送しない。tick は 5 分ごとに、App の JWT (`appJwt`。installation token とは別枠) で `GET /app/hook/deliveries?per_page=100` を 1 ページ読み、`status != OK` の配送を古い順に `POST /app/hook/deliveries/{id}/attempts` で再送する。同じ `guid` に OK の配送が 1 つでもあれば回収済みとみなして触らない。再送された配送 (`redelivery: true`) は、失敗しても再送しない (連鎖させない。元の配送の上限だけで止まる)。
- **上限**: 1 回の走査で再送は 10 件まで (試行の少ないものから)。同じ `guid` は 3 回まで (失敗した試行も数える)。rate-guard (`rest_remaining` < 1,500) の間は再送しない。
- **スイッチ**: `LIVE_REDELIVER` が `"1"` のときだけ POST する。`LIVE` には従わない (単独のスイッチ)。未設定 (既定) は一覧を読むだけで、送るはずだった配送を guid ごとに 1 回ずつ `counters.wouldRedeliver` に数える。
- **観測**: `/status` の `counters.redelivered` (送った件数の累計)・`counters.wouldRedeliver`・`last_redeliver_scan` (最後の走査の時刻)・`hook_failed_last_scan` (直近の一覧で `status != OK` だった配送の件数)。
- **限界**: 1 走査は最新 100 件の 1 ページだけを読む。それより古い失敗は読まない (GitHub は配送を約 3 日保持する)。失敗が 1 日に 100 件を超えると取りこぼし得る。
- **`POST /admin/resync`**: 派生状態 (issue・PR・run・コメント・blocked_by・レビュー) を `fullSync` で作り直す。ページ上限と REST の回数は全体同期と同じ。永続状態 (`launchedAt`・`relaunch`・`planned`・`phase`・`counters`) は同期が触らないので残る。1 時間に 2 回まで (試行は失敗しても数える)、3 回目は 429。tick と同時には走らせない (409)。認証と 404 の扱いは上の表を参照。

## 同期の窓と打ち切り

- 全体同期 (6 時間ごと) と reconcile (5 分ごと) は、GitHub の一覧を `per_page=100` のページで読む。`Gh.list` は、上限ページで止めて続きがあるときだけ `truncated=true` を返す
  (上限ちょうどで読み尽くしたときは、次の 1 ページを読んで空 (または窓の外だけ) なら `false`)。
- コメントは `sort=created&direction=desc` で**新しい順**に読み、`created_at` が窓より古いコメントに達したら止める。窓は全体同期で `COMMENT_WINDOW_H` 時間 (既定 24。24 未満は 24)、
  reconcile は `reconcileAt - 2 分`。ページ上限は `COMMENT_MAX_PAGES` (既定 80 = 8,000 件。`wrangler.toml` の値は実測に合わせて引き上げてある)。
  状態に使うコメント (bot と PM) 以外は本文を持たない。`botLast` / `pmArt` / `launchedAt` は適用の順序に依らず `created_at` (同時刻は comment id) が最新のものになる。
- PR は全体同期で open を全件・closed を `sort=updated&direction=desc` で窓の中だけ読む (`state=all` の全件は PR の増加で上限を超える)。reconcile も起点より古い更新で止める。
- 打ち切った一覧は `meta.syncTruncated` (対象名・読んだページ数・時刻。本文・題名は入れない) に残し、1 件でもあれば `fresh=false`。同じ一覧を次に読んで打ち切りが無ければ自動で消える。
  打ち切ったときは『一覧に無い』ことを根拠にした close / completed 扱い (issue・PR・run) をしない。`/status` は `sync_truncated` と `last_full_sync_rest_calls` (全体同期の REST 回数。うちコメントは `last_full_sync_comment_rest_calls`) を出す。

## ファイル構成

- `src/index.ts` Worker の入口 (対象外のイベントは DO を起こさず捨てる)。`src/do.ts` Durable Object `PmDO` (SQLite の `kv` 表 + alarm)。
- `src/app.ts` HTTP 面 (`/webhook` `/setup` `/setup/callback` `/status` `/tick`)。`src/engine.ts` 同期・分類・launch・watchdog・status。`src/ratelimit.ts` `src/redact.ts` は #2338 の rate limit の解釈と自由文の redact (純関数)。
- `src/webhook.ts` `src/classify.ts` `src/launch.ts` `src/hmac.ts` は純関数 (#1751 / #1795)。`src/pm.ts` (oc-pm の検出・抑止) と `src/needs.ts` (PM 判断を求める語彙) も純関数 (#2333)。
- `src/store.ts` `src/route.ts` は #1882 の entity 単位の SQLite 増分保存 (`receiveWebhook`)。`src/kvstore.ts` は Engine が使う汎用の保管 (bucket/key)。
  Worker の本番経路は `index.ts` → `do.ts` → `app.ts` → `engine.ts` (kvstore)。`store.ts` / `route.ts` は #1882 のテスト (`test/route.test.ts`) で検証される増分保存の実装で、
  PmState の全 entity (pmArt / blockedBy / launchedAt を含む) を保存・読み出せる。経路の一本化は #1882 側の判断 (本 PR では両方を残す)。

## テスト

```
cd infra/pm-worker && npm test      # Node >= 22.6 (--experimental-strip-types)。依存パッケージなし。Python 3 が要る (突き合わせ)
cd infra/pm-worker && npm run test:unit   # vitest (fetch モック・workerd なし)。test/unit/。/admin/resync と失敗配送の回収 (#2339) のネガコン
cd infra/pm-worker && npm run test:workers # vitest + workerd (実 Durable Object)。test/runtime/
```

`npm ci` が要る (`test:unit` と `test:workers` は devDependencies の vitest を使う)。

`npm run build` は bun、デプロイは wrangler を使う。wrangler は `login --device` がある版 (公式 docs の例は 4.119.0 の出力。VM は 4.151.0 で `--device` の存在を `wrangler login --help` で確認済み)。VM では root 不要で `$HOME/.local/bin` に置く
(`npm install --prefix $HOME/.local/wrangler wrangler@<版>`、bun は npm の `bun` パッケージ)。

## デプロイ (dry-run)

### 依頼者の操作 (デプロイ前に 1 回)

VM のシェルで `wrangler login` を行う。VM にブラウザが無く localhost の callback (8976) に届かないため `--device` を使う。

```
wrangler login --device --browser=false
```

表示された URL (`https://dash.cloudflare.com/oauth2/device`) を手元のブラウザで開き、表示されたコードを入力して **Allow** を押す (コードの有効期限は 5 分。切れたら再実行)。
ログインする Cloudflare のメンバーには、後述の **Workers の Admin** (Workers product スコープ) が要る。デプロイ後も `wrangler logout` はしない。保存された OAuth を VM に残し、以後の再デプロイに PM が使う (PM 判断 2026-10-14、#2357。手順は後述の「再デプロイ」)。新規 API token は作らない。

### 必要な Cloudflare の権限

- **新規 Worker の作成 (初回の `wrangler deploy`) には、Workers の `Admin` (Workers product スコープ) が要る。`Workers Scripts: Edit` (= Workers の `Editor`) では足りない。**
  公式: 「Creating new Workers requires product-level `Admin` access」「per-Worker permissions can only apply to Workers that already exist」。
  根拠: <https://developers.cloudflare.com/workers/authorization/workers/> (Wrangler の表に『Create a new Worker: product-level Admin』)、<https://developers.cloudflare.com/workers/authorization/> (Common access patterns: 『Create or delete Workers: Workers product / Admin』)。
- `Editor` で足りるのは**既存 Worker** の更新: script・settings・schedules (cron)・versions・deployments・`wrangler secret put` まで。作成と削除はできない。2 回目以降の deploy と `STORE_KEY` の更新は `Editor` でよい。
- Durable Object には別の権限は無い。DO を実装する Worker への Workers ロールで決まる (<https://developers.cloudflare.com/workers/authorization/durable-objects/>)。
- 旧名との対応: `Workers Scripts: Edit` = `Editor`、旧 `Workers Admin` (改名後 `Workers Platform Admin`) = `Admin` (Developer Platform スコープ)。旧名の対応表は上の Workers ページの『Legacy Workers permissions』、改名は <https://developers.cloudflare.com/changelog/post/2025-06-16-workers-platform-admin-role/>。
- 補足: `wrangler login` の OAuth は、粒度の細かい権限 (granular authorization) に未対応と公式にある (<https://developers.cloudflare.com/workers/authorization/>)。OAuth で Worker を作れるかどうかは、ログインしたメンバー自身のロール (Workers の Admin か、アカウントの Administrator 等) で決まる。公式には、API token は『platform-level の権限を持てない』とある。この手順は API token を作らず OAuth だけを使う (指示 4・9)。
- 未確認 (docs に記載なし): `workers.dev` サブドメインの有効化 (`POST .../subdomain`) と、アカウントに workers.dev のサブドメインが未登録のときの登録に必要な権限。

```
npm run build                                   # dist/index.js (bun)
npm run metadata > metadata.json                # wrangler.toml と同じ bindings / migration
# PUT /accounts/{id}/workers/scripts/signature-studio-pm  (multipart: metadata + index.js (application/javascript+module))
# PUT /accounts/{id}/workers/scripts/signature-studio-pm/schedules  [{"cron":"* * * * *"}]
# POST /accounts/{id}/workers/scripts/signature-studio-pm/subdomain  {"enabled":true}
# PUT /accounts/{id}/workers/scripts/signature-studio-pm/secrets  {"name":"STORE_KEY","text":"<32 バイトの base64url>","type":"secret_text"}
```

`wrangler deploy` でも同じ (`wrangler.toml`)。`STORE_KEY` は `openssl rand -base64 32 | tr '+/' '-_' | tr -d '='` で作り、シェルの履歴・ファイル・ログに残さない。
`LIVE_LAUNCH` / `LIVE_DISPATCH` は、初回のデプロイでは `"0"` (dry-run)。今の `wrangler.toml` は `"1"` (下記『切替の記録』)。

## 依頼者の操作 (1 回、ブラウザ)

1. `https://signature-studio-pm.<subdomain>.workers.dev/setup` を開く。
2. **Create GitHub App** を押す (org `signature-studio` の owner。App 名は `oc-pm-for-signature-studio`)。
3. 次の画面で **Install** を押し、`signature-studio-dev` だけを選ぶ。

App の id・private key・webhook secret は Worker が受け取って暗号化保管する。依頼者には表示されない。
権限: issues write / pull_requests write / contents write (`repository_dispatch` のため) / actions read / metadata read。

## 切替の記録 (2026-10-14、#2443)

VM の `pm-launch.timer` `pm-watchdog.timer` は依頼者の指示で停止済み。Worker が着手と `oc-watchdog` の dispatch を担う状態にするため、`LIVE_LAUNCH` `LIVE_DISPATCH` を `"1"` にした。VM の timer は**再開しない**。

- 前提 (merged): #2398 (Review-Only と `oc:stuck` の上限)、#2418 (LIVE の分離)、#2420 (#2380 コメントを新しい順に 24 時間分読む)、#2422 (#2338 `/status` の観測・redact・rate-guard。Worker の REST 残量が 1,500 未満の間は launch を止める)。未 merge の #2343 (VM 状態の取り込み)・#2334 (no-pr の理由別再着手)・#2340 (shadow の自己昇格) は前提から外した。VM が止まっているので二重着手の窓が無く、phase は『open PR < 10 で解除』の規則で足りる。
- merge 後に動く版は #2422 (rate-guard) と #2423 (#2333 oc-pm) を含む (この PR の差分には無い)。rate-guard は Worker の REST 残量 (`rest_remaining`) が 1,500 未満の間 launch を止める (`launch_stop: rate-guard`。未観測の間は止めない)。**`LIVE_DISPATCH="1"` は `oc-pm` (PM agent の起動) も送る**(別スイッチは無い。上限は全体で 1 時間に 12 起動・同じ (kind, ref) は 60 分に 1 回・同じ ref に 24 時間で 3 回。pm job の token は issues / pull-requests の write だけで contents を持たない)。止めるときは `LIVE_DISPATCH="0"` (`oc-watchdog` も止まる)。oc-pm を含めて live にするのは既定案 (#2319 の設計どおり)。PM の判断は PR #2453 の未解決表と PM のコメントに記録した。突き合わせはこの版 (`e88e1890`) で測り直した。
- 暫定の安全装置: `TARGET="50"` (最初の 1 時間。80 に戻す作業は #2458)、`NO_PR_COOLDOWN_H="24"` (#2334 が入るまで)。Review-Only は `phase.ts` / `engine.ts` が既に持つ (open PR が 80 超で launch しない、`oc:stuck` が `STUCK_HIGH` 超で止める)。
- 突き合わせ: dry-run の Worker と VM の `launch_issues.py` の差は、open な子を持つ親の除外・`pm-apply` の user 扱い・`oc:no-pr` の cooldown・VM の `relaunch.json` の有無で説明がつく (推定を含む。測定は #2422・#2423 を含む版。内訳と未解決は `tools/pm/REPORT.md` §12)。`NO_PR_COOLDOWN_H` の既定 (3) では `oc:no-pr` の issue が大量に候補へ戻るので、24 にした。
- 初回のデプロイでだけ、保存状態を整える一時ビルド (全体同期の前倒しと、phase を VM の `phase.json` に合わせる) を使った。リポジトリの差分には無い。理由と結果は `tools/pm/REPORT.md` §12-5。

戻し方 (VM の timer は再開しない): `wrangler.toml` の `LIVE_LAUNCH` を `"0"` にして再デプロイ (`npx wrangler deploy`)。dispatch も止めるなら `LIVE_DISPATCH` も `"0"`。`/status` の `mode_launch` / `mode_dispatch` が `dry-run` になる。`STORE_KEY` は変わらない。

## 切替 (PM の判断)

> **旧案 (段階的な切替) の記録。** 2026-10-14 の切替は上の『切替の記録』の手順で行った (`LIVE_LAUNCH` と `LIVE_DISPATCH` を一度に `"1"`、VM の timer は再開しない)。戻し方は『切替の記録』が正本。下の A・B にある『VM の timer を再開する』は VM の timer を使っていた当時の手順で、今は使わない。

スイッチは `wrangler.toml` の `[vars]` にある 2 つ。値は秘密ではない (`wrangler secret` は使わない)。`"1"` だけが live で、それ以外 (`"0"`・`""`・`"true"`・未設定) は dry-run。

| 変数 | 経路 | `wrangler.toml` の既定 |
|---|---|---|
| `LIVE_LAUNCH` | launch の `/oc` コメント投稿 (`POST /repos/{o}/{r}/issues/{n}/comments`) | `"1"` (2026-10-14〜。コードの既定は dry-run) |
| `LIVE_DISPATCH` | `repository_dispatch` の送信 (`POST /repos/{o}/{r}/dispatches`)。`oc-watchdog` と、oc-pm 節の `oc-pm` (PM agent の起動) の両方。別スイッチは無い | `"1"` (同上) |
| `LIVE` (旧) | 上の 2 つのうち、未設定のほうにだけ効く (両方の既定値) | (置かない) |
| `TARGET` | 同時に走らせる run の目標 (room = TARGET − active) | `"50"` (暫定。80 に戻す作業は #2458) |
| `NO_PR_COOLDOWN_H` | `oc:no-pr` の issue を再着手するまでの時間 | `"24"` (暫定。コードの既定は 3) |

個別の設定があれば `LIVE` より優先する (`LIVE=1` かつ `LIVE_LAUNCH=0` なら launch だけ dry-run)。`LIVE=1` だけの旧デプロイは従来どおり両方 live。
切替は `[vars]` を書き換えて**再デプロイ**する (`cd infra/pm-worker && npx wrangler deploy`。`STORE_KEY` の secret は変わらない)。リポジトリと稼働中の値を一致させるため、書き換えは PR で merge してから、その main でデプロイする。

### A. repository_dispatch を先に live にする (oc-watchdog と oc-pm)

`LIVE_DISPATCH` を `"1"` にすると **oc-pm も live になる** (oc-pm 専用のスイッチは無い)。launch は dry-run のまま。
`oc-watchdog` の送信は Actions の watchdog job を起こすだけで、VM の `pm-launch.timer` と二重着手にならない (watchdog job は同じ concurrency group `opencode-watchdog` で直列。`cancel-in-progress: false`)。
Worker が送る type は `oc-watchdog` と `oc-pm` の 2 つだけ。`oc-watchdog` は `DISPATCH_TYPES` (`src/github.ts`) を通り、payload は `{"event_type":"oc-watchdog"}` のみで `client_payload` を持たない。`oc-pm` は `dispatchPm` だけが送り、payload は `kind` と `ref` だけ。`oc-fix` (PR 番号・理由・素材名の `client_payload` を検証して送る) は Actions の `watchdog.sh` の仕事で、Worker は送らない。

1. 本 PR を merge する。
2. `wrangler.toml` の `LIVE_DISPATCH` を `"1"` にして (`LIVE_LAUNCH` は `"0"` のまま)、`npx wrangler deploy --dry-run` で bindings を確かめてから再デプロイする。切替の前に `GET /status` の `pm_detected` (kind ごとの検出数) を確認する。0 以外があれば、切替後すぐに対象の oc-pm が送られる (PM agent が起動する)。
   `GET /status` が `mode_dispatch: "live"`・`mode_launch: "dry-run"`・`mode: "partial"` になる。
3. Worker 由来の `repository_dispatch` の run が届くことを確認する (VM 由来の actor は `pycabbage`、Worker 由来は `oc-pm-for-signature-studio[bot]`):
   `gh api "repos/signature-studio/signature-studio-dev/actions/runs?event=repository_dispatch&per_page=10" --jq '.workflow_runs[]|"\(.created_at) \(.display_title) \(.triggering_actor.login)"'`
   併せて `GET /status` の `counters.dispatched` が増え、`last_watchdog` が 5 分ごとに進むこと。ここまでの間は VM の ping も動いている (どちらかが欠けても watchdog は途切れない)。
4. VM の `pm-watchdog.timer` を止める: `systemctl --user disable --now pm-watchdog.timer`。
5. 24 時間後にも watchdog の run が途切れないことを確認する (`display_title` が `watchdog` の run の間隔が 10 分以内であること。送信が重なる期間に、待機中の run が後続の run に置き換わって `cancelled` になるのは正常):
   ```
   S=$(date -u -d '24 hours ago' +%FT%TZ)
   gh api --paginate "repos/signature-studio/signature-studio-dev/actions/runs?event=repository_dispatch&per_page=100&created=%3E%3D$S" \
     --jq '.workflow_runs[]|select(.display_title=="watchdog")|.created_at' | sort | python3 -c 'import sys,datetime as d; t=[d.datetime.fromisoformat(l.strip().replace("Z","+00:00")) for l in sys.stdin if l.strip()]; g=[(b-a).total_seconds() for a,b in zip(t,t[1:])]; print(len(t),"runs, max gap",max(g),"s")'
   ```

戻す場合 (旧案。今は『切替の記録』の戻し方に従い、VM の timer は再開しない): `pm-watchdog.timer` を `enable --now` で再開し、`LIVE_DISPATCH` を `"0"` にして再デプロイする (oc-pm の送信も止まる)。

### B. launch を live にする

1. dry-run の出力 (`GET /status?detail=1` の `would_launch_now` と `log`) を、VM の `launch_issues.py plan` と数時間比較する。
2. 一致したら `LIVE_LAUNCH` を `"1"` にして再デプロイする (A の後なら `mode` が `live` になる)。同時に Actions 側の `vars.OC_PM_BOT_LOGIN` に `GET /status` の `pm_bot_login` (`oc-pm-for-signature-studio[bot]`) を設定する (別 issue)。
3. VM の `pm-launch.timer` を止める (A を済ませていなければ `pm-watchdog.timer` も)。
4. 戻す場合 (旧案。今は『切替の記録』の戻し方に従い、VM の timer は再開しない): `LIVE_LAUNCH` を `"0"` にして再デプロイし、VM の timer を再開する (VM 版は変更していない)。同期が壊れたら `/status` の `fresh` が false になり、Worker は投稿しない。

## 再デプロイ (PM。VM に残した wrangler の OAuth)

Worker のコード (`src/`・`wrangler.toml`) を変更して main に merge したら、PM が VM から再デプロイする。認証は初回デプロイで保存された OAuth を使う (wrangler が refresh token で access token を自動更新する)。
Workers Builds は接続しない (後述)。デプロイするのは **main に merge 済みの commit だけ**。以下のコマンドは wrangler 4.151.0 で、`--help` とソース、認証なしで実行できるものは実行して確認した。実 Worker への実行は未確認の項目として最後に列挙する。

1. 認証の確認 (token の値は表示しない・書かない)。

   ```
   cd infra/pm-worker
   wrangler whoami --json
   ```

   終了コード 0・`loggedIn` が `true`・`authType` が `OAuth Token` ならよい。`--json` を付けない `wrangler whoami` は、資格情報が無い環境でも終了コード 0 になる (`--json` は 1。認証なしの環境で確認)。判定には `--json` を使う。
   `authType` が `OAuth Token` でないときは、環境変数の token が OAuth より優先されている。止めて原因を調べる (この VM に token の環境変数を置かない。指示 4・9)。失敗したら後述の「OAuth が失効したとき」。
   OAuth の保存先 `~/.config/.wrangler/config/default.toml` は平文で token を含む。中身を表示・commit・コメントに貼らない。
2. 戻し先の記録。デプロイ前に `wrangler deployments status` を実行し、稼働中の version id を控える (ロールバックの戻し先)。あわせて `curl -fsS "$PM_WORKER_URL/status"` の `mode` `mode_launch` `mode_dispatch` `fresh` `last_tick` を控える (`PM_WORKER_URL` は `tools/pm/README.md` の `pm_gate.sh` と同じ)。
3. ビルドの確認: `wrangler deploy --dry-run --outdir <作業用の一時 dir>`。認証なしで通り、bindings の一覧 (`PM` と `[vars]`) が出る。migration の有無はここでは分からない。
4. デプロイ: `wrangler deploy --tag <commit の先頭 7 桁> --message "<commit hash> <issue または PR の番号>"`。`--tag` `--message` は version に付き、`wrangler deployments status` と `wrangler versions list` に出る (ロールバックで戻し先を選ぶ手がかり)。
   - **`[vars]` は deploy のたびに `wrangler.toml` の値で置き換わる。** `--keep-vars` なしの既定では、dashboard 等で変えた var は消える (`wrangler deploy --help` の説明)。特に `LIVE_LAUNCH` / `LIVE_DISPATCH`: dashboard 等で変えても、再デプロイすると `wrangler.toml` の値 (2026-10-14 以降は `"1"`) で置き換わる。切替の手順は「切替」節 (A・B) が正本で、値を変えるときも `wrangler.toml` を変えて merge してから deploy する (正本はリポジトリ)。デプロイ前に手順 2 の `mode` `mode_launch` `mode_dispatch` を見て、意図しない `live` → `dry-run` の変化が出ないことを確かめる。
   - secret (`STORE_KEY`) は deploy で消えない (ソースで `keepSecrets: true`、`--help` に『secrets are never deleted by deployments』)。`STORE_KEY` を作り直さない (App の鍵が復号できなくなる)。
   - Durable Object のコードを変えるだけなら migration は要らない (公式: <https://developers.cloudflare.com/durable-objects/reference/durable-object-class-migrations-legacy/>)。migration は適用済みの tag を飛ばして、新しい tag の分だけが deploy 時に適用される。現在の `wrangler.toml` は `v1` (`new_sqlite_classes = ["PmDO"]`) だけ。`[[migrations]]` を足す変更は、ロールバックできなくなる境界を作る (後述)。単独の PR・単独のデプロイにする。
5. 反映の確認。
   - `wrangler deployments status` に、手順 4 の `--tag` と `--message` を持つ version が 100% で出る。出力の項目 (version id・Created・Tag・Message) はソースで確認した。実 Worker での表示は未確認 (末尾のチェックリスト)。
   - `curl -fsS "$PM_WORKER_URL/status"` が応答し、`fresh` が `true`、`last_tick` が deploy 後の時刻に進む。
   - **現状の `/status` には、デプロイされた commit を識別する key が無い** (`src/engine.ts` の `status()`、main 0ca7f8c5)。そのため `/status` だけでは『新しい commit が反映された』と断定できない。上の `deployments status` の Tag / Message と、その commit で `/status` に足した・変えた key が応答に出ることを併せて見る。恒久策は [CI-84] #2416 (`/status` に `build` を載せる)。

## ロールバック

1. 戻し先を決める。`wrangler versions list` (直近 10 件) または `wrangler deployments status` で、手順 4 の Tag / Message から選ぶ。
2. `wrangler rollback <version-id> --message "<理由>"`。`--message` を付けると確認の prompt が省かれる。version id を省くと『最新の 1 つ前に upload された version』に戻る (公式: <https://developers.cloudflare.com/workers/wrangler/commands/workers/#rollback>)。戻すと新しい deployment ができ、全 route で即座に有効になる。
3. 「再デプロイ」の手順 5 と同じ確認をする。戻した理由と戻し先の version id を、起点の issue に書く。**main に問題の commit が残ったままだと、次の再デプロイで同じ版がまた出る。** revert の PR を出すか、修正を merge してから再デプロイする。

制約 (公式: <https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/>):

- 戻せるのは直近 100 version まで。
- **Durable Object のクラス lifecycle の変更 (`[[migrations]]` の追加) を跨いでは戻せない。** 現在の稼働中 version と戻し先の間に migration の追加があると、rollback は拒否される。本 Worker は `v1` 1 件だけなので、`v1` を含む version 同士の rollback は、公式の記述では可能と読める (実機では未実行: 後述 [未確認])。
- rollback で戻るのはコードだけで、binding の先 (DO の SQLite の保存内容) は戻らない。DO に保存する形式を変える変更は、旧コードが新しい形式を読める (後方互換) ようにしてから出す。公式にも『データの構造が変わると、旧 version のコードでエラーが起きうる』とある。
- OAuth が失効している間は、`wrangler rollback` も実行できない。dashboard の Workers & Pages → 対象 Worker → Deployments → Rollback でも戻せるが、dashboard へのログインは依頼者の操作になる。

## OAuth が失効したとき

**検知。**

- 再デプロイ・ロールバックの直前の `wrangler whoami --json` が、終了コード 1 で失敗する。OAuth の失効を自動で知らせる経路は無い。Worker は OAuth を使わない (デプロイ操作だけが使う) ので、失効しても Worker は止まらず、Worker 側の監視 (`/status`) にも出ない。
- Worker 自体の停止は別: `/status` の `fresh=false` または応答なしを watchdog が検知して `[CI] PM Worker 停止` の issue を起票する設計 ([CI-49] #2328)。**この文書の作成時点 (main 0ca7f8c5) で #2328 は open で、`.github/scripts/watchdog.sh` に該当の処理は無い** (`PM Worker 停止` の grep が 0 件)。実装されるまでは、停止も自動では検知されない。
- wrangler の挙動 (4.151.0 のソースで確認): access token は期限が切れたときだけ refresh token で更新される。refresh が拒否されたとき、TTY が無い・CI の環境では『`Not logged in. Your auth token has expired and could not be refreshed, and the environment is non-interactive.`』で失敗する。TTY のある端末では、ブラウザでの再ログインが自動で始まる。Cloudflare に届かないだけのときは別の理由 (`token-refresh-unreachable`) で、保存済みの資格情報は変更されない。
- 擬似的な再現: 隔離した設定 dir に、期限切れの access token と無効な refresh token を入れて `CI=1 wrangler whoami` (`--json` の有無を問わず) を実行すると、終了コード 1 で上のメッセージが出た。これは実機の失効 (Cloudflare 側で refresh token が失効した場合) の再現ではない。
- エラー文は、`CLOUDFLARE_API_TOKEN` を設定する方法も案内する。**この手順では従わない** (token を作らない・設定しない。指示 4・9)。

**失効している間の状態。** 稼働中の Worker は、最後にデプロイしたコードのまま動き続ける (webhook・Cron・alarm・DO は Cloudflare 側で動く)。遅れるのは『コード変更の反映』と『ロールバック』だけ。main に merge した修正は、再認証までデプロイされない。

**対処。** 再認証にはブラウザでの承認が要るので、依頼者の操作になる。

1. 依頼者が VM のシェルで `wrangler login --device --browser=false` を実行する。表示された URL を手元のブラウザで開き、コードを入力して **Allow** を押す (コードの有効期限は 5 分。切れたら再実行)。ログインするメンバーのロールは、既存 Worker の更新だけなら `Editor` で足りる (上の「必要な Cloudflare の権限」)。
2. 実行後に `wrangler whoami --json` が通ることを確認し、保留していた再デプロイをする。
3. 依頼者が不在のときは待たない。`needs-user-input` の issue に積む (既定案: 『再認証まで反映を遅らせる』。他の作業は止めない。`docs/WORKFLOW.md` §12)。

## Workers Builds を接続しない理由

Workers Builds (Cloudflare 側に repo を接続し、main への merge で自動ビルド・デプロイする機能) は、既定ではビルド用の API token を Cloudflare がアカウントに**自動で発行**する (公式: <https://developers.cloudflare.com/workers/ci-cd/builds/configuration/#api-token>)。依頼者の指示 4・9 (無断で token を作らない・secrets を平文で保存しない) の趣旨に反しうるため、PM 判断 (2026-10-14、#2357 [CI-78]) で接続しないと決めた。代わりに、上の手順で PM が VM の OAuth を使って再デプロイする。引き換えに、merge から反映までは PM の操作を待ち、OAuth が失効している間は反映できない (稼働中の Worker は止まらない)。依頼者が判断を変えたら、#2357 を再開して判断する。

## 確認できていない点 `[未確認]` のチェックリスト

公式 docs・wrangler のソース・認証なしで実行できるコマンドで確認できなかった点。推測では書かない。実 Worker で確かめたら、結果をここに移して `[未確認]` を外す。

- [ ] `[未確認]` refresh token の有効期間と失効の条件。公式 docs に記載を見つけられなかった (確認した範囲: `wrangler login` のページ、`wrangler auth token` の『automatically refreshed if expired』)。wrangler のソースでは、refresh の応答に新しい refresh token があればそれを保存し、無ければ従来のものを使い続ける。ただし有効期間が固定か、使うたびに延びるか、使わない期間が長いと失効するか、パスワード変更・ロール剥奪・ユーザーによる取り消しで失効するか、`--device` で得た token が通常の `wrangler login` と同じ寿命かは不明。確認の方法: 失効が起きたときの日時と、直前の `wrangler` 実行の日時を issue に記録して比べる。
- [ ] `[未確認]` 稼働中の script の `migration_tag` が `v1` か。wrangler は deploy 時にこの tag を取得して、`wrangler.toml` の最後の tag と同じなら migration を送らない (ソースで確認)。初回デプロイを REST (`scripts/metadata.mjs`) と `wrangler deploy` のどちらでしたかの記録が無く、tag が付いていなければ wrangler は `v1` を再送する。その場合に、既存の DO namespace に対して Cloudflare がどう応答するかは不明。確認の方法: 最初の再デプロイの出力に migration の適用が出ないこと。出たら止めて、依頼者に報告する。
- [ ] `[未確認]` `wrangler rollback` を本 Worker (migration は `v1` の 1 件のみ) で実行したときの成否。公式の制約は『lifecycle 変更を跨ぐと不可』で、本 Worker の `v1` 同士なら可と読めるが、実機では未実行。確認の方法: `LIVE_LAUNCH` / `LIVE_DISPATCH` を `"1"` にする前に、最初の再デプロイで 2 つ目の version ができた後、`wrangler rollback <旧 version> --message "rollback test"` で戻し、もう一度 deploy する。
- [ ] `[未確認]` rollback で `[vars]` (特に `LIVE_LAUNCH` / `LIVE_DISPATCH`) と Cron の schedule が戻し先の version の値に戻るか。公式は『binding の先は変わらない』とだけ書き、`[vars]` と schedule の扱いは書いていない。`LIVE_LAUNCH` または `LIVE_DISPATCH` が `"1"` の運用中に rollback すると、戻し先の値が `"0"` ならその経路が dry-run に戻る (投稿・dispatch が止まる) 恐れがある。確認の方法: 上のテストの後に `GET /status` の `mode_launch` / `mode_dispatch` (と `mode`)、dashboard の Triggers の cron が残っていることを見る。
- [ ] `[未確認]` `wrangler deployments status` と `wrangler versions list` の実際の出力 (Tag / Message の表示を含む)。項目名はソースで確認した。実 Worker での表示は未確認。
