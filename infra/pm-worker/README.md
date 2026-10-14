# signature-studio-pm (PM Worker)

PM の launch / watchdog を、VM のポーリング (systemd timer) から **webhook 駆動 + Cron / alarm** の Cloudflare Worker に移す (#1751)。
既定は **dry-run** (GitHub へは書き込まない)。書き込みの有効化と VM timer の停止は PM の判断 (後述)。
書き込みは経路ごとに独立したスイッチを持つ: launch の `/oc` コメント投稿 = `LIVE_LAUNCH`、`repository_dispatch` (`oc-watchdog`) の送信 = `LIVE_DISPATCH` (#2417)。

## 構成

| 要素 | 役割 |
|---|---|
| `POST /webhook` | GitHub App の webhook。`X-Hub-Signature-256` を HMAC-SHA256 (定数時間) で検証してから状態に反映する。対象: `issues` `issue_comment` `issue_dependencies` `pull_request` `pull_request_review` `workflow_run` |
| Durable Object `PmDO` (SQLite) | issue / PR / run / 最後の bot 報告 / blocked_by / launch 時刻を保持。App の鍵は AES-GCM で封じて保管 |
| alarm (webhook の 2 秒後 / 毎分) と Cron Trigger (毎分) | `tick`: 同期 (6 時間ごとに full、5 分ごとに reconcile)・`repository_dispatch` (`oc-watchdog`、前回の送信から 5 分未満は送らない。`LIVE_DISPATCH`)・launch (`LIVE_LAUNCH`) |
| `GET /setup` `GET /setup/callback` | GitHub App `oc-pm-for-signature-studio` の manifest flow (org 所有)。`/setup` は無認証だが、期限内 (1 時間) の state があれば上書きせず同じ state を返す。state は org 所有の App への変換に成功したときだけ消費する |
| `GET /status` | 集計のみ (実行中 run 数・ready/blocked 数・最終 reconcile 時刻・モード)。`mode_launch` / `mode_dispatch` が経路ごとのモード (`live` / `dry-run`)。`mode` は両方 `live` のときだけ `live` (片方だけなら `partial`、どちらもなら `dry-run`。`tools/pm/pm_gate.sh` は `mode=live` を『VM の command を止めてよい』と読む)。`?detail=1` は repo の push 権限を持つ GitHub token (Bearer) が必要 |

launch の規則は `tools/pm/launch_issues.py` の `classify` と同じ入出力 (固定 JSON を Python 版と TS 版の両方で読む突き合わせテスト: `test/classify.test.ts`)。差分は次の 4 点で、いずれも issue 本文を解析しない。

1. blocked_by の一覧が不明な issue は着手しない。
2. open な子 (`親: #N`) を持つ親 issue は着手対象から外す。
3. ラベル `oc:no-pr` は『PR を出さずに終わった』run の後。cooldown (既定 3 時間) の間は着手せず、過ぎたら再着手する (3 回まで。超えたら stopped)。`oc:stuck` は人の判断待ち。
4. 同期が 15 分以上止まっている間は投稿しない。

`/oc` コメントの本文は固定テンプレートで、可変なのは `oc_artifacts:` 行だけ。素材名は `.github/scripts/prepare-event-context.sh` の `ARTIFACT_RE` と同じ集合 (`ALLOW_ARTS`) を通ったものだけ。webhook の自由文 (タイトル・本文・コメント) は指示文に入らない。

## oc-pm: PM agent を起こす終端状態の検出と送信 (#2333)

PM の判断が要る終端状態を **決定的に** (ラベル・マーカー・正規表現だけ。LLM も本文の解析も使わない) 検出し、`repository_dispatch` の `oc-pm` を送る。入口側は `.github/scripts/prepare-event-context.sh` (#2327)。

| kind | 検出 (すべて open の対象。起票者は後述の絞り込みを通ったものだけ) |
|---|---|
| `stuck` | `oc:stuck` の PR で、最新の停止コメント (`<!-- oc-fix-limit -->`、bot 投稿) に `<!-- oc-pm-intent: stuck pr=N ... -->` がある (`pr=` が当該 PR の番号) |
| `no_pr` | `oc:no-pr` の issue で、最後の `<!-- oc-run-outcome: no-pr reason=... -->` が `split` / `stop`、または `unknown` で Worker が再投入済み (再投入の後の run でも `unknown`) |
| `needs_decision` | reviewer の最新の verdict が CHANGES_REQUESTED で、本文が `NEEDS_KEY` (`src/needs.ts`。`tools/pm/pm_needs.py` の `KEY` と同じ正規表現・同じ行分割) に一致し、その後に PM 応答が無い |
| `user_answered` | `needs-user-input` の issue に、ラベルが付いた後に非 bot のユーザーのコメントが付いた |

- マーカーは **bot (実装 App・reviewer App) の投稿だけ** を信じる (誰でもコメントできるため)。PM 応答は、PM のログイン (`PM_LOGINS` と PM App) のコメント、または bot の `oc-pm-decision` / `oc-pm-intent: relaunch` マーカー付きコメント。根拠より後にあれば、その対象は送らない。
- 状態は `sig` (issue / PR 番号ごとの時刻・列挙値・真偽。本文は持たない)。webhook の増分で更新し、webhook で埋まらない reviewer の verdict と `needs-user-input` の付与時刻は reconcile で REST から一度だけ補う (best effort)。
- 送信: payload は `{"event_type":"oc-pm","client_payload":{"kind":<列挙>,"ref":<数字>}}` だけ。値は検証済みの列挙・整数から組み立て、issue / PR の自由文は入らない。PM App の installation token で送る。
- 絞り込み: 起票者が `MEMBER` / `OWNER` / `COLLABORATOR`、または許可 bot (`opencode-for-signature-studio[bot]` `oc-reviewer-for-signature-studio[bot]`) の対象だけ。起票者が未取得の対象は送らない。
- 抑止 (DO の `meta/pmDispatch`): 同じ (kind, ref) は 60 分に 1 回・全体で 1 時間に 12 起動・同じ ref に 24 時間で 3 回まで。未送信の対象を先に、送信済みは古い順に選ぶ。失敗した試行も数える (403 / 429 はその tick を打ち切る)。同期が 15 分以上止まっている間は送らない。
- **dry-run (既定)**: 送らず、`/status` の `would_dispatch_pm` (`?detail=1` のみ) と `counters.wouldDispatchPm`、`pm_detected` (kind ごとの検出数) に記録する。履歴は live と分ける (`meta/pmWould`)。
- ラベル `pm-apply` / `needs-user-input` の issue (着手しても PR を出さない/出せない) は、`no_pr` の検出と `/oc` の再投入 (launch) の対象から除く (`user` 行に置く)。`user_answered` は `needs-user-input` が対象。
- 検出するのは上の 4 kind。`refs_orphan` は [CI-58]、`supply` / `digest` は [CI-71] / [CI-70] が担当する。

## ファイル構成

- `src/index.ts` Worker の入口 (対象外のイベントは DO を起こさず捨てる)。`src/do.ts` Durable Object `PmDO` (SQLite の `kv` 表 + alarm)。
- `src/app.ts` HTTP 面 (`/webhook` `/setup` `/setup/callback` `/status` `/tick`)。`src/engine.ts` 同期・分類・launch・watchdog・status。
- `src/webhook.ts` `src/classify.ts` `src/launch.ts` `src/hmac.ts` は純関数 (#1751 / #1795)。`src/pm.ts` (oc-pm の検出・抑止) と `src/needs.ts` (PM 判断を求める語彙) も純関数 (#2333)。
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
`LIVE_LAUNCH` / `LIVE_DISPATCH` はどちらも `"0"` (dry-run)。

## 依頼者の操作 (1 回、ブラウザ)

1. `https://signature-studio-pm.<subdomain>.workers.dev/setup` を開く。
2. **Create GitHub App** を押す (org `signature-studio` の owner。App 名は `oc-pm-for-signature-studio`)。
3. 次の画面で **Install** を押し、`signature-studio-dev` だけを選ぶ。

App の id・private key・webhook secret は Worker が受け取って暗号化保管する。依頼者には表示されない。
権限: issues write / pull_requests write / contents write (`repository_dispatch` のため) / actions read / metadata read。

## 切替 (PM の判断。この PR では行わない)

スイッチは `wrangler.toml` の `[vars]` にある 2 つ。値は秘密ではない (`wrangler secret` は使わない)。`"1"` だけが live で、それ以外 (`"0"`・`""`・`"true"`・未設定) は dry-run。

| 変数 | 経路 | `wrangler.toml` の既定 |
|---|---|---|
| `LIVE_LAUNCH` | launch の `/oc` コメント投稿 (`POST /repos/{o}/{r}/issues/{n}/comments`) | `"0"` |
| `LIVE_DISPATCH` | `repository_dispatch` の `oc-watchdog` の送信 (`POST /repos/{o}/{r}/dispatches`) | `"0"` |
| `LIVE` (旧) | 上の 2 つのうち、未設定のほうにだけ効く (両方の既定値) | (置かない) |

個別の設定があれば `LIVE` より優先する (`LIVE=1` かつ `LIVE_LAUNCH=0` なら launch だけ dry-run)。`LIVE=1` だけの旧デプロイは従来どおり両方 live。
切替は `[vars]` を書き換えて**再デプロイ**する (`cd infra/pm-worker && npx wrangler deploy`。`STORE_KEY` の secret は変わらない)。リポジトリと稼働中の値を一致させるため、書き換えは PR で merge してから、その main でデプロイする。

### A. dispatch (watchdog) だけを先に live にする

`oc-watchdog` の送信は Actions の watchdog job を起こすだけで、VM の `pm-launch.timer` と二重着手にならない (watchdog job は同じ concurrency group `opencode-watchdog` で直列。`cancel-in-progress: false`)。launch は dry-run のまま。
Worker が送る type は `oc-watchdog` だけ (`src/github.ts` の `DISPATCH_TYPES`)。payload は `{"event_type":"oc-watchdog"}` のみで、`client_payload` を持たない。`oc-fix` (PR 番号・理由・素材名の `client_payload` を検証して送る) は Actions の `watchdog.sh` の仕事で、Worker は送らない。

1. 本 PR を merge する。
2. `wrangler.toml` の `LIVE_DISPATCH` を `"1"` にして (`LIVE_LAUNCH` は `"0"` のまま)、`npx wrangler deploy --dry-run` で bindings を確かめてから再デプロイする。
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

戻す場合: `pm-watchdog.timer` を `enable --now` で再開し、`LIVE_DISPATCH` を `"0"` にして再デプロイする。

### B. launch を live にする

1. dry-run の出力 (`GET /status?detail=1` の `would_launch_now` と `log`) を、VM の `launch_issues.py plan` と数時間比較する。
2. 一致したら `LIVE_LAUNCH` を `"1"` にして再デプロイする (A の後なら `mode` が `live` になる)。同時に Actions 側の `vars.OC_PM_BOT_LOGIN` に `GET /status` の `pm_bot_login` (`oc-pm-for-signature-studio[bot]`) を設定する (別 issue)。
3. VM の `pm-launch.timer` を止める (A を済ませていなければ `pm-watchdog.timer` も)。
4. 戻す場合: `LIVE_LAUNCH` を `"0"` にして再デプロイし、VM の timer を再開する (VM 版は変更していない)。同期が壊れたら `/status` の `fresh` が false になり、Worker は投稿しない。
