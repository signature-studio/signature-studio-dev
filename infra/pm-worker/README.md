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
4. 同期が 15 分以上止まっている間は投稿しない。

`/oc` コメントの本文は固定テンプレートで、可変なのは `oc_artifacts:` 行だけ。素材名は `.github/scripts/prepare-event-context.sh` の `ARTIFACT_RE` と同じ集合 (`ALLOW_ARTS`) を通ったものだけ。webhook の自由文 (タイトル・本文・コメント) は指示文に入らない。

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
2. 戻し先の記録。デプロイ前に `wrangler deployments status` を実行し、稼働中の version id を控える (ロールバックの戻し先)。あわせて `curl -fsS "$PM_WORKER_URL/status"` の `mode` `fresh` `last_tick` を控える (`PM_WORKER_URL` は `tools/pm/README.md` の `pm_gate.sh` と同じ)。
3. ビルドの確認: `wrangler deploy --dry-run --outdir <作業用の一時 dir>`。認証なしで通り、bindings の一覧 (`PM` と `[vars]`) が出る。migration の有無はここでは分からない。
4. デプロイ: `wrangler deploy --tag <commit の先頭 7 桁> --message "<commit hash> <issue または PR の番号>"`。`--tag` `--message` は version に付き、`wrangler deployments status` と `wrangler versions list` に出る (ロールバックで戻し先を選ぶ手がかり)。
   - **`[vars]` は deploy のたびに `wrangler.toml` の値で置き換わる。** `--keep-vars` なしの既定では、dashboard 等で変えた var は消える (`wrangler deploy --help` の説明)。特に `LIVE`: `wrangler.toml` は `"0"` (dry-run) なので、`LIVE=1` にした後に再デプロイすると dry-run に戻る。`LIVE` を変えるときは `wrangler.toml` を変えて merge してから deploy する (正本はリポジトリ)。デプロイ前に手順 2 の `mode` を見て、意図しない `live` → `dry-run` の変化が出ないことを確かめる。
   - secret (`STORE_KEY`) は deploy で消えない (ソースで `keepSecrets: true`、`--help` に『secrets are never deleted by deployments』)。`STORE_KEY` を作り直さない (App の鍵が復号できなくなる)。
   - Durable Object のコードを変えるだけなら migration は要らない (公式: <https://developers.cloudflare.com/durable-objects/reference/durable-object-class-migrations-legacy/>)。migration は適用済みの tag を飛ばして、新しい tag の分だけが deploy 時に適用される。現在の `wrangler.toml` は `v1` (`new_sqlite_classes = ["PmDO"]`) だけ。`[[migrations]]` を足す変更は、ロールバックできなくなる境界を作る (後述)。単独の PR・単独のデプロイにする。
5. 反映の確認。
   - `wrangler deployments status` に、手順 4 の `--tag` と `--message` を持つ version が 100% で出る。出力の項目 (version id・Created・Tag・Message) はソースで確認した。実 Worker での表示は未確認 (末尾のチェックリスト)。
   - `curl -fsS "$PM_WORKER_URL/status"` が応答し、`fresh` が `true`、`last_tick` が deploy 後の時刻に進む。
   - **現状の `/status` には、デプロイされた commit を識別する key が無い** (`src/engine.ts` の `status()`、main 3d011ecd)。そのため `/status` だけでは『新しい commit が反映された』と断定できない。上の `deployments status` の Tag / Message と、その commit で `/status` に足した・変えた key が応答に出ることを併せて見る。恒久策は [CI-84] #2416 (`/status` に `build` を載せる)。

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
- Worker 自体の停止は別: `/status` の `fresh=false` または応答なしを watchdog が検知して `[CI] PM Worker 停止` の issue を起票する設計 ([CI-49] #2328)。**この文書の作成時点 (main 3d011ecd) で #2328 は open で、`.github/scripts/watchdog.sh` に該当の処理は無い** (`PM Worker 停止` の grep が 0 件)。実装されるまでは、停止も自動では検知されない。
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
- [ ] `[未確認]` `wrangler rollback` を本 Worker (migration は `v1` の 1 件のみ) で実行したときの成否。公式の制約は『lifecycle 変更を跨ぐと不可』で、本 Worker の `v1` 同士なら可と読めるが、実機では未実行。確認の方法: `LIVE=1` にする前 (dry-run の間) に、最初の再デプロイで 2 つ目の version ができた後、`wrangler rollback <旧 version> --message "rollback test"` で戻し、もう一度 deploy する。
- [ ] `[未確認]` rollback で `[vars]` (特に `LIVE`) と Cron の schedule が戻し先の version の値に戻るか。公式は『binding の先は変わらない』とだけ書き、`[vars]` と schedule の扱いは書いていない。`LIVE=1` の運用中に rollback すると、投稿が止まる (dry-run に戻る) 恐れがある。確認の方法: 上のテストの後に `GET /status` の `mode` と、dashboard の Triggers の cron が残っていることを見る。
- [ ] `[未確認]` `wrangler deployments status` と `wrangler versions list` の実際の出力 (Tag / Message の表示を含む)。項目名はソースで確認した。実 Worker での表示は未確認。
