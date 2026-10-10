# M e2e-deploy — ブラウザ E2E ハーネス + R2/Transform Rules 配信スクリプト

> **前提 (検収で追記)**: `deploy/` の構成は**自前ゾーン (例: cabbagelettuce.com) のカスタムドメイン + Transform Rules 前提**。
> ユーザ決定は「ドメインは全作業完了後に指示、暫定は既定ホスト名」。r2.dev 既定ホストでは Rules/Access/WAF/キャッシュ機能が使えない
> (R2 公式 "Public buckets")。既定ホスト名 (workers.dev 等) 構成は `tools/hosting` の結論に従い別途適応する (Linear CAB-61 = H-1)。
> **E2E ハーネス (`tools/e2e`) 自体は配信先に依存しない** (`--url` で任意の URL を検証)。

## 結論
1. **agent-browser (vercel-labs, v0.39.0) は導入可・採用済み**。`tools/e2e/package.json` にプロジェクトローカル導入
   (native binary は npm 同梱 = postinstall/外部ダウンロード不要、`npm ci --ignore-scripts` で成立)。既存 `/usr/bin/google-chrome 154` を
   `--executable-path` で使用。**フォールバック**として puppeteer-core ドライバも同梱し、同一スイートを両ドライバで実行できる (クロスチェック)。
2. **1 コマンド E2E**: `bash tools/e2e/run.sh` → ビルド → ローカルサーバ起動 → headless chrome で `crossOriginIsolated`・AudioWorklet・
   Canvas・wasm を検証 → スクリーンショットを `tools/e2e/work/shots/` に保存。**実測: 3 ターゲット × 2 ドライバ = PASS 44 / FAIL 0 / SKIP 10**。
3. **配信構成をコード化** (`deploy/`): R2 バケット + カスタムドメイン、Transform Rules (COOP/COEP/CORP/Cache-Control/index rewrite)、
   Cache Rules、Compression Rules、Access Self-hosted App + service token を `cf` CLI で。**Rules 4 phase の JSON は Cloudflare API のサーバ側検証を通過済み**
   (`--validate-only`、非永続。不正式は確かに拒否されることも確認、検証後に entrypoint 未作成のままを確認)。実デプロイは未実行。
4. **重要な発見**: この環境の `cf` は**既に OAuth ログイン済み**で、R2/Transform/Cache/Compression/Access/DNS の書込スコープを全て保有
   (`cf auth whoami` 実測)。ブロッカーは認証ではなく**ユーザ決定** (公開ホスト名・Access 許可メール・実行承認) のみ。
   公開ホスト名は暫定=既定ホスト名のため、`deploy/` の自前ドメイン構成は `tools/hosting` の結論を受けて適応が必要 (冒頭の前提参照)。

## agent-browser 導入記録
| 項目 | 結果 |
|---|---|
| 導入 | `cd tools/e2e && npm ci --ignore-scripts` (6s)。bin は `node_modules/.bin/agent-browser`。npm の postinstall は node26 で既定ブロックだが**不要** (7 プラットフォームの binary が tarball に同梱) |
| 起動 | `agent-browser --executable-path /usr/bin/google-chrome --args "--no-sandbox,--autoplay-policy=no-user-gesture-required" open <url>` (初回 open 約 1.2〜1.7s) |
| 使った機能 | `open` / `eval --stdin` (async IIFE の Promise を await) / `click` / `screenshot` / `console` / `errors` / `--headers` (Access service token 用) / `--json` / `--session` (名前付きで他 agent と非共有) |
| 注意 | `wait --fn` のタイムアウトは固定 25s (CLI から変更不可) → ドライバ側 100ms polling で実装。呼出は **非同期 spawn 必須** (下記不具合) |

**E2E 基盤自身で見つけた不具合**: edge-sim (同一 node プロセス内 HTTP サーバ) に対し `spawnSync` で agent-browser を呼ぶとイベントループが
塞がり Chrome のリクエストが全滅 (`Page.navigate` が 30s タイムアウト)。非同期 spawn に修正し解消 (`suite/drivers/agent-browser.mjs` 冒頭コメント)。

## E2E スイート (`tools/e2e/suite/checks.mjs`)
| check | 内容 |
|---|---|
| headers-isolation | `/` と worklet が COOP `same-origin` / COEP `require-corp` |
| edge-policy | (edge-sim / 実 URL) CORP・Cache-Control・Content-Type・br 圧縮・index rewrite・R2 同様の素の 404 を `edge-policy.json` と突合 |
| page-load | ページ起動、title、ハーネスの起動表示 |
| cross-origin-isolated | `crossOriginIsolated===true`、`new SharedArrayBuffer()` 生成可、secure context |
| wasm-load | アプリ内 smoke (`add(40,2)=42`) + `WebAssembly.instantiateStreaming(fetch('/__e2e__/add.wasm'))` で MIME `application/wasm` を検査 |
| canvas-render | 全画面 canvas の putImageData 結果を getImageData で読み戻し (lit ピクセル > 0, 色数 ≥ 2) + スクリーンショット |
| audioworklet | クリック → `samplePos` が 128f 単位で増加 (SAB 経由の worklet clock) |
| console-clean | uncaught エラー 0、想定外 console error/warning 0 (意図的 fail-fast ログと favicon 404 のみ許容) |
| fl-boot | FL 統合後の契約チェック (下記)。既定 SKIP、`E2E_REQUIRE_FL=1` で必須化 |

ターゲット: `preview` (vite preview) / `dev` (vite dev) / `edge-sim` (**deploy の配信ポリシーをローカル再現**: R2 同様 `/` の暗黙 index なし +
Rules の rewrite/ヘッダ/br) / `url` (`run.sh --url https://…`、Access 時は `E2E_ACCESS_CLIENT_ID/SECRET`)。
既存 `tools/misc/loader_smoke.mjs` (Node ローダ smoke) も run.sh 内で実行 (ALL OK)。

### 実測結果 (Chrome 154.0.8037.97, headless)
| target × driver | PASS | FAIL | SKIP |
|---|---|---|---|
| preview × agent-browser / puppeteer-core | 7 / 7 | 0 / 0 | 2 / 2 (edge-policy, fl-boot) |
| edge-sim × agent-browser / puppeteer-core | 8 / 8 | 0 / 0 | 1 / 1 (fl-boot) |
| dev × agent-browser / puppeteer-core | 7 / 7 | 0 / 0 | 2 / 2 (edge-policy, fl-boot) |
| url (ローカル edge-sim を `--url` で指定) × agent-browser | 8 | 0 | 1 |
| **合計 (url 除く)** | **44** | **0** | **10** (fl-boot 6 + edge-policy 4) |

dev は `__e2e__/add.wasm` fixture が配信されないため wasm-load 内の instantiateStreaming 部分のみ省略 (check 自体は PASS で SKIP に数えない)。

- 代表値: `canvas 1280x633 lit=101120px` (agent-browser) / `1280x720 lit=115200px` (puppeteer、viewport 差)、
  `samplePos 18432→29696` を約 1.3s で進行 (粗い実測 29k〜52k frames/s; 48kHz 実時間相当。128f 単位を毎回検査)、`AudioContext` は headless でも running。
- **感度確認 (ネガティブテスト)**: edge-sim のポリシーから COEP を削ると 4 check が FAIL
  (`headers-isolation` / `cross-origin-isolated` (coi=false) / `audioworklet` (ボタン無効化) / `console-clean`) → ヘッダ欠落を確実に検出。
  再現: `Cross-Origin-Embedder-Policy` を除いた `edge-policy.json` のコピーを作り
  `EDGE_POLICY_FILE=<copy> E2E_SKIP_BUILD=1 bash tools/e2e/run.sh --driver both --targets edge-sim` (検収で再現済: 8 FAIL = 4 check × 2 driver)。
- 他担当の未コミット変更 (`src/index.ts` の runtime panel, Worker bundle 追加) が入った作業ツリーでも PASS (15/15 preview+edge-sim)。
  E2E は**作業ツリーをそのままビルド**する点に注意。スクリーンショット: `tools/e2e/work/shots/<target>-<driver>-{canvas,audio,final}.png` (18 枚)。

## 配信構成 (`deploy/`, 詳細は `deploy/README.md`)
- 正本 `deploy/config/edge-policy.json` → `lib/policy.mjs` が Rulesets ペイロードを生成 (edge-sim も同一定義を解釈)。単体テスト 6/6 PASS。
- 4 phase: `http_request_transform` (`/`→index.html: **R2 カスタムドメインは index を解決しない**) / `http_response_headers_transform` /
  `http_request_cache_settings` (**CF 既定は wasm/html/json 非キャッシュ**) / `http_response_compression`。全 rule は host スコープ + `ref` 名前空間化、
  PUT 前に既存 rule を読んでマージ (entrypoint 全置換のため)。
- dry-run の実績 (すべて実 API の読取のみ / 書込なし): `deploy.sh` 全工程 DRY-RUN 完走、`30-rulesets --validate` 4/4 OK、
  `40-access --dry-run`、`20-upload` 計画 + `cf r2 objects put --dry-run` / `aws s3 cp --dryrun` のコマンド構築検証。
- **未実行 (実機でのみ確認可)**: 実アップロード、R2 カスタムドメイン接続、Access App 実作成、実 URL での E2E、lifecycle 書式、
  Transform の `http.request.uri.path` が rewrite 後の値か (document を `/` と `/index.html` 両方列挙して吸収済み。
  公式 docs "Rules > Field values during rule evaluation" は「rewrite 後の phase では書換後の値、`raw.*` なら元の値」と記載。実機確認は残る)。

## 運用 (アップロード対象 / Content-Type / 圧縮 / キャッシュ)
- 対象: vite `dist` 全体 + wasm (`wasm/<name>.<hash>.wasm`) + 資産 (`data/<hash>/…`) + `release.json` (自動生成: buildId・全 sha256)。
  順序は immutable → mutable → `index.html` → `release.json` (最後)。immutable 配下にハッシュ名が無いと**アップロード中止**。
- Content-Type: `wasm=application/wasm` (instantiateStreaming 必須)、js/css/html は charset 付き、未知は octet-stream。`cf r2 objects put` は Content-Type のみ設定可。
- 圧縮 (実測、node zlib・元サイズ比 br q11 / zstd 19 / gzip 9): python.wasm 5.93MB → **25.9 / 27.6 / 36.5%**、m11_boot.wasm ≈6.05MB → 30.2 / 33.8 / 41.2%
  (M 初回計測 6.06MB: 30.0 / 33.7 / 41.1%。m11 は他担当が再ビルドするため ±0.2pt)、ott.wasm 0.84MB → 33.0 / 35.9 / 42.0%
  (対象: `tools/python/work/build-wasm/python.wasm`, `tools/m11/work/m11_boot.cjs.wasm`, `tools/ott/work/ott.cjs.wasm`)。
  既定はエッジ動的圧縮 (br→zstd→gzip)。事前圧縮は `--backend aws` 拡張が必要 (未実装)。
- キャッシュ: immutable 1 年 (edge も 1 年) / document `no-cache` + edge 60s + デプロイ時 purge / 他 5 分。CF のキャッシュ可能上限 512MB (公式 Cache > Default cache behavior > Cacheable size limits: Free/Pro/Business)・
  `cf r2 objects put` の上限 300MB (cf の REST エンドポイント仕様 = `cf r2 objects put --help`。R2 本体の単一 PUT 上限は 4.995 GiB で別、公式 R2 Limits)
  → 大物は分割 (≤256MB は M の安全側の目安であり公式値ではない) か aws backend。

## FL 起動契約 (提案: runtime-arch へ)
FL 統合後に `fl-boot` を有効化するため、ページは `window.__webstudio = { state: 'booting'|'running'|'error', frames: <number>, error?: string }` を公開する。
`state==='running'` かつ `frames>0` (GUI フレーム転送済み) を `E2E_REQUIRE_FL=1` で必須化。タイムアウト 180s。

## ユーザ依頼事項
1. **公開ホスト名** (例: `studio.<既存ゾーン>`)。現アカウントには active ゾーンが 1 件 (Free プラン, `cf zones list` 実測) → そのゾーン配下のサブドメインを推奨 (ゾーン名は最終報告に記載)。
2. **Access 許可メール** (`ACCESS_ALLOW_EMAILS`) または許可ドメイン。service token (E2E/CI 用) の新規作成可否。
3. **実デプロイ実行の承認** (`APPLY=1 bash deploy/scripts/deploy.sh --src …`)。`cf` は既にログイン済みのため追加の認証作業は不要。
   CI 化する場合のみ API トークン (権限グループは `deploy/README.md`) と、aws backend 用に R2 S3 キーが別途必要。
4. バケット名 (`CF_R2_BUCKET`、既定案 `webstudio-prod`)。

## 下流チケット案
Linear 起票済 (検収時): T1→CAB-35 (既存)、T2→CAB-62、T3→CAB-63、T4→CAB-64、T5→CAB-65、T6→CAB-66、追加 H-1 (既定ホスト名構成への適応)→CAB-61。

- **T1 実デプロイ初回**: 上記承認後 `deploy.sh` APPLY → `90-verify.sh` で実 URL E2E (edge-policy が CORP/Cache-Control/br を実機検証)。
- **T2 tools/assets manifest**: `{version, files:[{path,src,contentType}]}` 契約の生産側実装 (wasm/data の内容アドレス名付与) と release.json 連携 (ローダが manifest 経由で解決)。
- **T3 事前圧縮 + 大容量**: `--backend aws` で `Content-Encoding: br` 保存・multipart・256MB 分割 (FL 本体 wasm が 100MB 級になった場合)。
- **T4 `window.__webstudio` 契約実装** (runtime-arch) と `fl-boot` check の必須化、FL GUI フレームの canvas 画素検査 (スクリーンショット差分 `agent-browser diff screenshot`)。
- **T5 CI 化**: GitHub Actions 等で `tools/e2e/run.sh` (headless chrome) + 週次で実 URL 検証。API トークン/ service token 運用。
- **T6 配信後の自動注入対策**: Web Analytics ビーコン等が COEP で console error になるか実機確認 → 必要なら Configuration Rule で無効化。

## 再現
前提: `node` (実測 v26.10.0) と `npm` が PATH にあること、`/usr/bin/google-chrome` (または `E2E_CHROME`)。
```sh
bash tools/e2e/run.sh --driver both --targets preview,edge-sim,dev      # ローカル全部 (実測 19.5s)
bash tools/e2e/run.sh --url https://studio.example.com                   # デプロイ後 (Access: E2E_ACCESS_CLIENT_ID/SECRET)
node --test deploy/lib/policy.test.mjs                                    # ポリシー単体テスト
bash deploy/scripts/deploy.sh --src tools/e2e/work/dist                   # DRY-RUN (要 deploy/.env)
```
