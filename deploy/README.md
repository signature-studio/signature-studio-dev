# deploy/ — R2 静的直配 + Cloudflare Rules (COOP/COEP) + Access

構成 (ユーザ確定): **R2 バケット + カスタムドメイン (CF プロキシ) の静的直配**。Worker 不使用。
COOP/COEP/CORP/Cache-Control は **ゾーンレベル Transform Rules** で注入、保護は **Access Self-hosted App**
(R2 カスタムドメインのホスト名)。GitHub Pages はヘッダ不可で不採用。Workers は動的エンドポイントが必要になった時のみ。

## 1 コマンド (既定 DRY-RUN)

```sh
cp deploy/env.example deploy/.env && $EDITOR deploy/.env       # CF_ZONE / CF_HOSTNAME / CF_R2_BUCKET / ACCESS_ALLOW_EMAILS
bash tools/e2e/run.sh --targets preview                         # dist を tools/e2e/work/dist に生成 (E2E_SKIP_BUILD=1 で省略)
bash deploy/scripts/deploy.sh --src tools/e2e/work/dist         # DRY-RUN: 読取 API のみ実呼出、書込は cf --dry-run
APPLY=1 bash deploy/scripts/deploy.sh --src tools/e2e/work/dist # 実デプロイ (Cloudflare 認証 + 上記 .env 必須)
```

| script | 内容 | 書込? |
|---|---|---|
| `00-preflight.sh` | cf/認証スコープ/zone/既存衝突の確認 | 読取のみ |
| `10-bucket.sh` | R2 バケット作成 (冪等), **r2.dev 公開 URL を無効化** (Access を素通りさせない), 任意で lifecycle | APPLY=1 |
| `20-upload.mjs` | 計画/圧縮見積り(`--stats`)/アップロード(`--execute`)/差分スキップ/purge | `--execute` |
| `40-access.mjs` | service token + 2 ポリシー + Self-hosted App (冪等 upsert) | `--apply` |
| `30-rulesets.mjs` | 4 phase の rules を生成→既存 rule とマージ→PUT。`--validate` はサーバ側検証のみ | `--apply` |
| `50-domain.sh` | R2 カスタムドメイン接続 (**最後**) | APPLY=1 |
| `90-verify.sh` | 実 URL に tools/e2e を agent-browser で実行 (service token 自動) | 読取のみ |

**順序が重要**: bucket → upload → **Access → rules → ドメイン接続**。先に接続すると、無保護 / COEP 無しで一時公開される。

## 配信ポリシー (唯一の正本: `config/edge-policy.json`)

`lib/policy.mjs` が Rulesets API ペイロードを生成し、tools/e2e の `edge-sim` も同じ定義を解釈する
(= rule JSON が本当に crossOriginIsolated を成立させることを CF 認証なしで E2E 検証できる)。
`node deploy/scripts/30-rulesets.mjs --host H` で生成 JSON を確認、`rendered/` に例。全 rule は `http.host eq "<HOST>"` で
スコープされ、`ref` は `webstudio_<host>_*` (同一ゾーンの他 rule・他ホストに触れない)。

| phase | 目的 |
|---|---|
| `http_request_transform` | `ends_with(path,"/")` → `concat(path,"index.html")`。**R2 カスタムドメインは / の index 解決をしない** |
| `http_response_headers_transform` | COOP `same-origin` / COEP `require-corp` / CORP `same-origin` / nosniff を全応答に。Cache-Control をクラス別に |
| `http_request_cache_settings` | **wasm/html/json は CF 既定ではキャッシュ対象外** (既定は拡張子限定)。bucket 全体を cache:true、immutable は edge TTL 1 年、他 5 分 |
| `http_response_compression` | wasm/js/css/html/json/svg/txt を br→zstd→gzip (Free 既定は zstd) |

注意 (公式ドキュメント記載): Transform Rules で Cache-Control を書いても **CF のキャッシュ挙動は変わらない** (評価はキャッシュ後)。
エッジ挙動は Cache Rules、ブラウザ向けは Transform、で役割分担している。

### キャッシュ戦略とレイアウト

```
/index.html, /release.json, /wasm/manifest.json  document : no-cache (ETag 再検証)、エッジ TTL 60s。デプロイ時に purge
/assets/<name>-<hash>.js|css   immutable: public, max-age=31536000, immutable   (vite のハッシュ名)
/wasm/<name>.<hash8+>.wasm     immutable: 同上 (内容アドレス。Content-Type: application/wasm)
/data/<hash>/...               immutable: FL 資源・プラグイン・サンプル等 (内容アドレス)
/worklets/*.js, その他         mutable  : public, max-age=300, must-revalidate (非ハッシュ名)
/__e2e__/add.wasm              E2E 用 fixture (instantiateStreaming + MIME 検査)
```
`20-upload.mjs` は **immutable 配下でファイル名にハッシュが無いと中止** (1 年 immutable の事故防止)。
最後に `release.json` (buildId, 全ファイル sha256/size) を生成して上げる。`tools/assets` の manifest 契約:
`{"version":1,"files":[{"path":"wasm/ott.1a2b3c4d.wasm","src":"<相対/絶対>","contentType":"任意"}]}`。

制約: CF のキャッシュ可能サイズ上限は Free/Pro/Business **512MB** (超過はキャッシュされず毎回 R2 = Class B op)。
`cf r2 objects put` は **1 件 300MB** 上限 → 大物は 256MB 以下に分割するか `--backend aws` (S3 multipart)。

### 圧縮 (実測: node zlib, 実 wasm)
br(q11) / zstd(19) / gzip(9) の元サイズ比: python.wasm 5.93MB → **25.9% / 27.6% / 36.5%**,
m11_boot.wasm 6.06MB → 30.0% / 33.7% / 41.1%, ott.wasm 0.84MB → 33.0% / 35.9% / 42.0%。
既定は **エッジ動的圧縮** (オブジェクトは非圧縮で保管)。事前圧縮 (`Content-Encoding: br` をオブジェクトに保存) は
`cf r2 objects put` では設定不可 (Content-Type のみ) → 必要になったら `--backend aws` を拡張。
進捗バー用に Content-Length を保つなら origin 側 `Cache-Control: no-transform` が必要 (圧縮無効化とのトレードオフ)。

## 必要な権限 (ユーザ依頼事項)

**現環境の `cf` は既に OAuth ログイン済み**で、`cf auth whoami` のスコープに下記すべてが含まれる (00-preflight が検査):
`workers-r2.write` `workers-r2-bucket-item.write` `zone-transform-rules.write` `cache-settings.write`
`response-compression.write` `cache.purge` `access-app.write` `access-policy.write` `access-service-token.write`
`dns.write` `zone.read`。→ **技術的ブロッカーは無く、ユーザ決定待ち**: 公開ホスト名 / Access 許可メール / 実行承認。

API トークン運用 (CI) にする場合の権限グループ (OAuth スコープ名からの対応づけ。ダッシュボード表記は要確認):
Account: Workers R2 Storage **Edit**, Access: Apps and Policies **Edit**, Access: Service Tokens **Edit** /
Zone: Transform Rules **Edit**, Cache Rules **Edit**, Response Compression **Edit**, Cache Purge **Purge**, DNS **Edit**, Zone **Read**。
`--backend aws` を使う場合のみ追加で R2 S3 互換キー (R2 > API トークン > Object Read & Write, 対象バケット限定)。

## 運用上の注意 (実機デプロイ時に確認する未実測事項)
- Free プラン: Transform/Cache/Compression rule は各 phase 10 本まで (本構成は 1/4/2/1 本)。purge は 1 リクエスト 30 URL。
- CF の自動注入 (Web Analytics ビーコン, JS detections) は COEP `require-corp` 下で **ブロックされ console error** になり得る
  → 対象ホストで無効化 (E2E の console-clean が検出する)。Rocket Loader/Email Obfuscation も OFF のまま。
- Access セッション失効中のサブリソース fetch は 302 でログインに飛び COEP/CORS エラーになる → session 24h、失効時はリロード。
- CORP は `same-origin`。別ホストへ資産を分離する場合は該当資産だけ `cross-origin` に変えること。
- `http.request.uri.path` が URL rewrite 後の値か否かで Cache-Control rule のマッチが変わり得るため、
  document 判定は `/` と `/index.html` の両方を列挙済み。**実機で `curl -I /` を確認** (90-verify が表示+検査)。
- `config/lifecycle.json` の書式 (R2 REST) は未検証。`APPLY_LIFECYCLE=1` 時にエラーなら wrangler の lifecycle 書式を参照。
- 本番は E2E の `edge-policy` チェック (CORP/Cache-Control/Content-Type) が実 URL に対しても走る。

## 手動手順 (スクリプトを使わない場合)
```sh
cf r2 buckets create-by-name $B && cf r2 buckets domains managed update $B --enabled false
cf r2 objects put <key> --bucket-name $B --file <f> --content-type <ct>
cf zero-trust access applications create --body @app.json         # 先に Access
cf rulesets account-rulesets phases update http_response_headers_transform -z $ZONE --rules @rules.json
cf r2 buckets domains custom create $B --domain $H --zone-id $ZID --enabled true --min-tls 1.2   # 最後
```
全コマンドに `--dry-run` (クライアント側) があり、rulesets は加えて `--validate-only true` (サーバ側検証・非永続) を持つ。
