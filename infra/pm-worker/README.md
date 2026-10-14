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
| `GET /status` | 集計のみ (実行中 run 数・ready/blocked 数・最終 reconcile 時刻・モード)。`?detail=1` は repo の push 権限を持つ GitHub token (Bearer) が必要 |

launch の規則は `tools/pm/launch_issues.py` の `classify` と同じ入出力 (固定 JSON を Python 版と TS 版の両方で読む突き合わせテスト: `test/classify.test.ts`)。差分は次の 4 点で、いずれも issue 本文を解析しない。

1. blocked_by の一覧が不明な issue は着手しない。
2. open な子 (`親: #N`) を持つ親 issue は着手対象から外す。
3. ラベル `oc:no-pr` は『PR を出さずに終わった』run の後。cooldown (既定 3 時間) の間は着手せず、過ぎたら再着手する (3 回まで。超えたら stopped)。`oc:stuck` は人の判断待ち。
4. 同期が 15 分以上止まっている間、または一覧を上限ページで打ち切った間 (下の「同期の窓と打ち切り」) は、投稿も `oc-watchdog` の dispatch もしない (`/status` の `fresh=false`)。

`/oc` コメントの本文は固定テンプレートで、可変なのは `oc_artifacts:` 行だけ。素材名は `.github/scripts/prepare-event-context.sh` の `ARTIFACT_RE` と同じ集合 (`ALLOW_ARTS`) を通ったものだけ。webhook の自由文 (タイトル・本文・コメント) は指示文に入らない。

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
- `src/app.ts` HTTP 面 (`/webhook` `/setup` `/setup/callback` `/status` `/tick`)。`src/engine.ts` 同期・分類・launch・watchdog・status。
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
