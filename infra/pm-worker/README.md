# signature-studio-pm (PM Worker)

PM の launch / watchdog を、VM のポーリング (systemd timer) から **webhook 駆動 + Cron / alarm** の Cloudflare Worker に移す (#1751)。
この PR の範囲は **dry-run まで** (GitHub へは書き込まない)。投稿の有効化と VM timer の停止は PM の判断 (後述)。

## 構成

| 要素 | 役割 |
|---|---|
| `POST /webhook` | GitHub App の webhook。`X-Hub-Signature-256` を HMAC-SHA256 (定数時間) で検証してから状態に反映する。対象: `issues` `issue_comment` `issue_dependencies` `pull_request` `pull_request_review` `workflow_run` |
| Durable Object `PmDO` (SQLite) | issue / PR / run / 最後の bot 報告 / blocked_by / launch 時刻を保持。App の鍵は AES-GCM で封じて保管 |
| alarm (webhook の 2 秒後 / 毎分) と Cron Trigger (毎分) | `tick`: 同期 (6 時間ごとに full、5 分ごとに reconcile)・`repository_dispatch` (`oc-watchdog`、5 分周期)・launch |
| `GET /setup` `GET /setup/callback` | GitHub App `oc-pm-for-signature-studio` の manifest flow (org 所有)。`/setup` は無認証だが、期限内 (1 時間) の state があれば上書きせず同じ state を返す。state は org 所有の App への変換に成功したときだけ消費する |
| `GET /status` | 集計のみ (実行中 run 数・ready/blocked 数・最終 reconcile 時刻・モード・健全性の観測。下の『/status の観測』)。`?detail=1` は repo の push 権限を持つ GitHub token (Bearer) が必要 |

launch の規則は `tools/pm/launch_issues.py` の `classify` と同じ入出力 (固定 JSON を Python 版と TS 版の両方で読む突き合わせテスト: `test/classify.test.ts`)。差分は次の 4 点で、いずれも issue 本文を解析しない。

1. blocked_by の一覧が不明な issue は着手しない。
2. open な子 (`親: #N`) を持つ親 issue は着手対象から外す。
3. ラベル `oc:no-pr` は『PR を出さずに終わった』run の後。cooldown (既定 3 時間) の間は着手せず、過ぎたら再着手する (3 回まで。超えたら stopped)。`oc:stuck` は人の判断待ち。
4. 同期が 15 分以上止まっている間は投稿しない。

`/oc` コメントの本文は固定テンプレートで、可変なのは `oc_artifacts:` 行だけ。素材名は `.github/scripts/prepare-event-context.sh` の `ARTIFACT_RE` と同じ集合 (`ALLOW_ARTS`) を通ったものだけ。webhook の自由文 (タイトル・本文・コメント) は指示文に入らない。

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

**rate-guard**: `rest_remaining` が 1,500 未満の間は launch を止める (`launch_stop: "rate-guard"`)。1,499 で止まり、1,500 で継続する。未観測 (`null`) は止めない。
reconcile の読み取りと watchdog の dispatch は続く。launch の途中でも、投稿の応答で残量が下がれば残りを投稿しない。遷移 (on/off) のときだけログに 1 行残す。
`stuck-ceiling` (既存) が立っているときは `launch_stop` はそちらを返す。dry-run でも計画 (`would_launch_now`) は止まる (投稿はもともとしない)。

**secrets を出さない**: `/status` は集計だけで、issue のタイトル・本文・コメントは載せない。自由文は `last_error.what` とログの `note` だけ (どちらも `?detail=1` のみ)。
これらと `console.log` は `src/redact.ts` を通し、PEM・`gh*_` / `github_pat_` の token・JWT・`Bearer …`・`sha256=…` と、実行時に分かっている secret (webhook secret・PEM・STORE_KEY・直近の installation token) を `[redacted]` にする。

## ファイル構成

- `src/index.ts` Worker の入口 (対象外のイベントは DO を起こさず捨てる)。`src/do.ts` Durable Object `PmDO` (SQLite の `kv` 表 + alarm)。
- `src/app.ts` HTTP 面 (`/webhook` `/setup` `/setup/callback` `/status` `/tick`)。`src/engine.ts` 同期・分類・launch・watchdog・status。`src/ratelimit.ts` `src/redact.ts` は #2338 の rate limit の解釈と自由文の redact (純関数)。
- `src/webhook.ts` `src/classify.ts` `src/launch.ts` `src/hmac.ts` は純関数 (#1751 / #1795)。
- `src/store.ts` `src/route.ts` は #1882 の entity 単位の SQLite 増分保存 (`receiveWebhook`)。`src/kvstore.ts` は Engine が使う汎用の保管 (bucket/key)。
  Worker の本番経路は `index.ts` → `do.ts` → `app.ts` → `engine.ts` (kvstore)。`store.ts` / `route.ts` は #1882 のテスト (`test/route.test.ts`) で検証される増分保存の実装で、
  PmState の全 entity (pmArt / blockedBy / launchedAt を含む) を保存・読み出せる。経路の一本化は #1882 側の判断 (本 PR では両方を残す)。

## テスト

```
cd infra/pm-worker && npm test      # Node >= 22.6 (--experimental-strip-types)。依存パッケージなし。Python 3 が要る (突き合わせ)
```

`npm run build` は bun、デプロイは wrangler を使う。wrangler は `login --device` がある版 (公式 docs の例は 4.119.0 の出力。VM は 4.151.0 で `--device` の存在を `wrangler login --help` で確認済み)。VM では root 不要で `$HOME/.local/bin` に置く
(`npm install --prefix $HOME/.local/wrangler wrangler@<版>`、bun は npm の `bun` パッケージ)。

## デプロイ (dry-run)

### 依頼者の操作 (デプロイ前に 1 回)

VM のシェルで `wrangler login` を行う。VM にブラウザが無く localhost の callback (8976) に届かないため `--device` を使う。

```
wrangler login --device --browser=false
```

表示された URL (`https://dash.cloudflare.com/oauth2/device`) を手元のブラウザで開き、表示されたコードを入力して **Allow** を押す (コードの有効期限は 5 分。切れたら再実行)。
ログインする Cloudflare のメンバーには、後述の **Workers の Admin** (Workers product スコープ) が要る。デプロイ後に PM が `wrangler logout` する (OAuth token の失効と保存済み資格情報の削除)。新規 API token は作らない。

### 必要な Cloudflare の権限

- **新規 Worker の作成 (初回の `wrangler deploy`) には、Workers の `Admin` (Workers product スコープ) が要る。`Workers Scripts: Edit` (= Workers の `Editor`) では足りない。**
  公式: 「Creating new Workers requires product-level `Admin` access」「per-Worker permissions can only apply to Workers that already exist」。
  根拠: <https://developers.cloudflare.com/workers/authorization/workers/> (Wrangler の表に『Create a new Worker: product-level Admin』)、<https://developers.cloudflare.com/workers/authorization/> (Common access patterns: 『Create or delete Workers: Workers product / Admin』)。
- `Editor` で足りるのは**既存 Worker** の更新: script・settings・schedules (cron)・versions・deployments・`wrangler secret put` まで。作成と削除はできない。2 回目以降の deploy と `STORE_KEY` の更新は `Editor` でよい。
- Durable Object には別の権限は無い。DO を実装する Worker への Workers ロールで決まる (<https://developers.cloudflare.com/workers/authorization/durable-objects/>)。
- 旧名との対応: `Workers Scripts: Edit` = `Editor`、旧 `Workers Admin` (改名後 `Workers Platform Admin`) = `Admin` (Developer Platform スコープ)。旧名の対応表は上の Workers ページの『Legacy Workers permissions』、改名は <https://developers.cloudflare.com/changelog/post/2025-06-16-workers-platform-admin-role/>。
- 補足: `wrangler login` の OAuth は、粒度の細かい権限 (granular authorization) に未対応と公式にある (<https://developers.cloudflare.com/workers/authorization/>)。OAuth で Worker を作れるかどうかは、ログインしたメンバー自身のロール (Workers の Admin か、アカウントの Administrator 等) で決まる。API token は『platform-level の権限を持てない』ので使う場合は Workers product スコープで付ける。この手順は新規 token を作らず OAuth を使う。
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
`LIVE` は `"0"` (dry-run)。

## 依頼者の操作 (1 回、ブラウザ)

1. `https://signature-studio-pm.<subdomain>.workers.dev/setup` を開く。
2. **Create GitHub App** を押す (org `signature-studio` の owner。App 名は `oc-pm-for-signature-studio`)。
3. 次の画面で **Install** を押し、`signature-studio-dev` だけを選ぶ。

App の id・private key・webhook secret は Worker が受け取って暗号化保管する。依頼者には表示されない。
権限: issues write / pull_requests write / contents write (`repository_dispatch` のため) / actions read / metadata read。

## 切替 (PM の判断。この PR では行わない)

1. dry-run の出力 (`GET /status?detail=1` の `would_launch_now` と `log`) を、VM の `launch_issues.py plan` と数時間比較する。
2. 一致したら `LIVE=1` にする。同時に Actions 側の `vars.OC_PM_BOT_LOGIN` に `GET /status` の `pm_bot_login` (`oc-pm-for-signature-studio[bot]`) を設定する (別 issue)。
3. VM の `pm-launch.timer` と `pm-watchdog.timer` を止める。
4. 戻す場合: `LIVE=0` にして VM の timer を再開する (VM 版は変更していない)。同期が壊れたら `/status` の `fresh` が false になり、Worker は投稿しない。
