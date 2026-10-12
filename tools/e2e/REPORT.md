# 検収・E2E REPORT — tools/e2e / deploy

> **デプロイ構成の正本は [`deploy/README.md`](../../deploy/README.md) の案 S** (Workers Static Assets +
> `_headers` で COOP/COEP/CORP 一括付与・Access `worker` 型)。旧 R2 バケット + ゾーン Transform Rules 前提の
> 記述は `deploy/legacy-r2/` に退避 (`docs/DECISIONS.md` D1)。
> **E2E ハーネス (`tools/e2e`) 自体は配信先に依存しない** (`--url` で任意の URL を検証)。

## 結論
1. **agent-browser (vercel-labs, v0.39.0) は導入可・採用済み**。`tools/e2e/package.json` にプロジェクトローカル導入
   (native binary は npm 同梱 = postinstall/外部ダウンロード不要、`npm ci --ignore-scripts` で成立)。既存 `/usr/bin/google-chrome 154` を
   `--executable-path` で使用。**フォールバック**として puppeteer-core ドライバも同梱し、同一スイートを両ドライバで実行できる (クロスチェック)。
2. **1 コマンド E2E**: `bash tools/e2e/run.sh` → ビルド → ローカルサーバ起動 → headless chrome で `crossOriginIsolated`・AudioWorklet・
   Canvas・wasm を検証 → スクリーンショットを `tools/e2e/work/shots/` に保存。**実測: 3 ターゲット × 2 ドライバ = PASS 44 / FAIL 0 / SKIP 10**。
3. **配信構成をコード化** (`deploy/`): **Worker コード無しの Workers Static Assets 1 本** (既定ホスト名 workers.dev)、
   `_headers` で COOP/COEP/CORP 一括付与、Access `worker` 型 + service token、>24MiB は 16MiB part に自動分割。
   旧 R2 バケット + zone Transform Rules 構成は `deploy/legacy-r2/` (自前ゾーン前提のため現在は未使用)。
   **実デプロイ実績あり** (CAB-35、`deploy/REPORT.md`)。
4. **重要な発見**: この環境の `cf` は**既に OAuth ログイン済み**で、Workers Scripts / Access の書込スコープを保有
   (`cf auth whoami` 実測)。zone / R2 / DNS 権限は不要。ブロッカーは認証ではなく**ユーザ決定** (公開ホスト名・Access 許可メール・実行承認) のみ。
   公開ホスト名は暫定=既定ホスト名 (workers.dev)。自前ドメインへの移行はユーザ指示後 (`deploy/README.md` §移行)。

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

> **注記 (2026-10-12 再編)**: 本節は旧 R2 + Transform Rules 前提で書かれた記録。
> 現行の正本は `deploy/README.md` の**案 S** (Workers Static Assets + `_headers`)。旧構成は `deploy/legacy-r2/` に退避。
> edge-sim は同一の `edge-policy.json` を解釈するので、配信先に依存しない形で両方のポリシーを検証できる。

- 正本 `deploy/config/edge-policy.json` → `lib/policy.mjs` がポリシーを解釈 (案 S では `_headers` 生成・旧 Rules 構成では Rulesets ペイロード生成。edge-sim も同一定義を解釈)。単体テスト 6/6 PASS。
- **旧 R2 構成の 4 phase** (現在は `legacy-r2/`): `http_request_transform` (`/`→index.html: **R2 カスタムドメインは index を解決しない**) / `http_response_headers_transform` /
  `http_request_cache_settings` (**CF 既定は wasm/html/json 非キャッシュ**) / `http_response_compression`。全 rule は host スコープ + `ref` 名前空間化、
  PUT 前に既存 rule を読んでマージ (entrypoint 全置換のため)。
- **案 S (現行) の実績**: `deploy/scripts/deploy.sh` の DRY-RUN 完走 + 実デプロイ (CAB-35、`deploy/REPORT.md`)。

## 運用 (アップロード対象 / Content-Type / 圧縮 / キャッシュ)
- 対象: vite `dist` 全体 + wasm (`wasm/<name>.<hash>.wasm`) + 資産 (`data/<hash>/…`) + `release.json` (自動生成: buildId・全 sha256)。
  順序は immutable → mutable → `index.html` → `release.json` (最後)。immutable 配下にハッシュ名が無いと**アップロード中止**。
- Content-Type: `wasm=application/wasm` (instantiateStreaming 必須)、js/css/html は charset 付き、未知は octet-stream。
- 圧縮 (実測、node zlib・元サイズ比 br q11 / zstd 19 / gzip 9): python.wasm 5.93MB → **25.9 / 27.6 / 36.5%**、m11_boot.wasm ≈6.05MB → 30.2 / 33.8 / 41.2%
  (M 初回計測 6.06MB: 30.0 / 33.7 / 41.1%。m11 は他担当が再ビルドするため ±0.2pt)、ott.wasm 0.84MB → 33.0 / 35.9 / 42.0%
  (対象: `tools/python/work/build-wasm/python.wasm`, `tools/m11/work/m11_boot.cjs.wasm`, `tools/ott/work/ott.cjs.wasm`)。
  既定はエッジ動的圧縮 (text/wasm を zstd/br/gzip 自動圧縮)。
- キャッシュ (正本 `deploy/config/edge-policy.json`): immutable 1 年 / document (`/`・`/index.html`・`release.json`・`wasm/manifest.json`) は no-cache /
  他は Static Assets 既定。旧 R2 構成での CF キャッシュ可能上限 512MB 等の制約は `legacy-r2/` 側の記録。

## FL 起動契約 (提案: runtime-arch へ)
FL 統合後に `fl-boot` を有効化するため、ページは `window.__webstudio = { state: 'booting'|'running'|'error', frames: <number>, error?: string }` を公開する。
`state==='running'` かつ `frames>0` (GUI フレーム転送済み) を `E2E_REQUIRE_FL=1` で必須化。タイムアウト 180s。

## ユーザ依頼事項
1. **公開ホスト名** (例: `studio.<既存ゾーン>`)。案 S の既定は workers.dev (`deploy/README.md` §移行で自前ドメインへ)。
2. **Access 許可メール** (`ACCESS_ALLOW_EMAILS`) または許可ドメイン。service token (E2E/CI 用) の新規作成可否。
3. **実デプロイ実行の承認** (`APPLY=1 bash deploy/scripts/deploy.sh --src …`)。`cf` は既にログイン済みのため追加の認証作業は不要。
   CI 化する場合のみ API トークン (権限グループは `deploy/README.md`)。R2 S3 キーは旧構成 (`legacy-r2/`) を使う場合のみ。

## 下流チケット案
GitHub issue 起票済 (検収時): T1→実デプロイ (**CAB-35 として完了**・`deploy/REPORT.md`)、
T2→tools/assets manifest、T3→事前圧縮 + 大容量、T4→`window.__webstudio` 契約実装、
T5→CI 化 (`feat/add-opencode`)、T6→配信後の自動注入対策、H-1→既定ホスト名構成への適応 (**CAB-61 として完了**)。
旧 `CAB-xxx` と GitHub issue `#N` の対応は `docs/REFERENCES.md` `[CAB_TO_GH]`。

## 再現
前提: `node` (実測 v26.10.0) と `npm` が PATH にあること、`/usr/bin/google-chrome` (または `E2E_CHROME`)。
```sh
bash tools/e2e/run.sh --driver both --targets preview,edge-sim,dev      # ローカル全部 (実測 19.5s)
bash tools/e2e/run.sh --url https://studio.example.com                   # デプロイ後 (Access: E2E_ACCESS_CLIENT_ID/SECRET)
node --test deploy/lib/policy.test.mjs                                    # ポリシー単体テスト
bash deploy/scripts/deploy.sh --src tools/e2e/work/dist                   # DRY-RUN (要 deploy/.env)
```
