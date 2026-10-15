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
| webstudio-contract | `window.__webstudio` の形状検査 (state ∈ booting/running/error、frames は非負 number、running なら frames>0、error 文字列は state=error 時のみ)。FL 未統合のハーネスは `booting`/`frames:0` で PASS |
| fl-boot | FL 統合後の契約チェック (下記)。既定 SKIP、`E2E_REQUIRE_FL=1` で必須化。`state==='running' && frames>0` (180s) + canvas 画素検査 (lit>0, colors≥2) |

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

## CI 化 (#66, `tools/e2e/ci/e2e.yaml.proposed` → `.github/workflows/e2e.yaml`)

2026-10-15 に PR #3292 で配置済み。以下は経緯。

**配置の制約**: Actions の GitHub App には `workflows` 権限が無く、`.github/workflows/` への push は拒否された
(`refusing to allow a GitHub App to create or update workflow ... without workflows permission`、実測 1 回)。
そのため workflow 本体は当初 `tools/e2e/ci/e2e.yaml.proposed` に置いた。`workflows` 権限のあるユーザ/PM が `.github/workflows/e2e.yaml` へ移し
(actionlint 1.7.7 で配置後の内容を検査済み = エラー 0)、`.proposed` は PR #3292 で削除した (Git 履歴に残る)。

既知類型との関係: 該当なし (lift/IR 系ではない)。検証起点: `origin/main` 2847625。

- `local` ジョブ: PR / main push (src・vite 設定・tools/e2e・deploy/config 等の path のみ。tools/audio・tools/legal/notices・tools/m1/flags.sh は未登録 = #3335) / 手動で
  `run.sh --driver both --targets preview,edge-sim`。結果 JSON・スクリーンショット・ログを artifact (14 日)、表を job summary に出す
  (`tools/e2e/suite/summary.mjs`)。
- `remote` ジョブ: 週次 (月曜 03:17 UTC) / 手動 (`remote=true`) で `run.sh --url "$E2E_URL" --driver both`。
  `E2E_URL` (repo variable) 未設定なら skip。service token は secrets `E2E_ACCESS_CLIENT_ID/SECRET`。
  運用・ローテーションは `deploy/README.md` §CI / E2E の秘密情報。
- 実測 (Actions runner 上、Chrome 154.0.8037.97、load average 0.43 → 0.66):
  `run.sh --driver both --targets preview,edge-sim` = **PASS 30 / FAIL 0 / SKIP 6**、所要 10.7–12.8s (build 込み、n=2: 作業ツリー 1 回 + コミット済み HEAD 0f60391 のクリーン worktree 1 回、load average 0.05–0.66)。
  `run.sh --url <ローカル edge-sim> --driver both` = **PASS 16 / FAIL 0 / SKIP 2**、所要 3.9s (1 回)。
- ネガティブコントロール: edge-policy の COEP キーを除いたコピーを `EDGE_POLICY_FILE` で与えると
  edge-sim × 2 driver で **FAIL 8** (4 check × 2)・exit 1 (CI ジョブが赤になる条件)。
  workflow の step と同じ `bash -eo pipefail -c 'bash tools/e2e/run.sh ... 2>&1 | tee <log>'` で再現 (コミット済み HEAD 6456cbc、Node v22.23.3、
  `--driver both --targets preview,edge-sim`、`E2E_SKIP_BUILD=1`): 所要 6.0s、load average 1.43 → 2.27、`PASS=22 FAIL=8 SKIP=6`、**パイプライン exit 1** (n=1)。
  同条件の正常系は `PASS=30 FAIL=0 SKIP=6`・exit 0・18.6s (build 込み、n=1)。
  `shell: bash` 明示の根拠: `bash -e -c 'false 2>&1 | tee /dev/null'` は exit 0、`bash -eo pipefail -c` は exit 1。同じ COEP 除去 run (edge-sim のみ) を
  `-e` のみ (pipefail 無し) で流すと exit 0 (= step が緑のまま FAIL を握り潰す) ことも確認。`shell:` 無指定の `run` は
  `bash -e {0}` で実行されるため、両 E2E step に `shell: bash` (= `bash --noprofile --norc -eo pipefail {0}`) を明示した。
- 範囲外: 実 URL への `--url` (Access 保護下の実 token での実行は未実施 = `E2E_URL` と secrets の登録はユーザ操作。残件は #3303 [E2E-9])。Actions 上の local ジョブは下の適用節で確認済み。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| repo variable `E2E_URL` と secrets `E2E_ACCESS_CLIENT_ID/SECRET` の登録 | 週次 remote ジョブは登録まで skip | #3302 [E2E-8] (PM/ユーザ作業。token secret は `deploy/work/secrets/` にしか無い) |
| 実 URL に対する週次ジョブの初回実績 | remote の PASS 未確認 | #3303 [E2E-9] (登録後に `gh workflow run e2e.yaml -f remote=true`) |
| path filter (`on.pull_request.paths`・`on.push.paths`) に `tools/audio/**`・`tools/legal/notices/**`・`tools/m1/flags.sh` が無い | これだけを変えた PR では workflow が起動せず、merge 前に E2E で検証されない | #3335 [E2E-10] (PM / 依頼者が依頼コメントの diff を適用。#3292 の merge 後) |

### 適用 (#66。PM が PAT で `.github/workflows/e2e.yaml` へ配置。検証起点 `origin/main` `7c85004e` に本 PR を載せたクリーン worktree・node v24.19.0・Chrome 154.0.8037.97・emsdk 6.0.12 (`[EMSDK]`))

- Actions 結果 (PR #3292 head `4c89a7b0`): run 38659352731 (`E2E / local` success・job 70 s (00:19:24 → 00:20:34Z)、`E2E / remote` skipped = `vars.E2E_URL` 未登録)。
- Actions 結果 (PR #3292 head `75131c60`): Actions run 38658202074 (head 75131c60・job local success・SUMMARY PASS=34 FAIL=0 SKIP=6・emsdk install 26 s・job 所要 72 s・n=1)。`E2E / local` (job 116172905176、00:07:39 → 00:08:51Z)。runner は Ubuntu 24.04.5・Chrome 154.0.8037.97・node v26.10.0・pnpm 12.10.1。remote ジョブは `vars.E2E_URL` 未登録のため skip。
- 測定 commit = `75131c60`。`git diff 75131c60 HEAD -- src public tools/e2e tools/audio tools/m1 deploy/config deploy/lib ':(exclude)tools/e2e/REPORT.md' ':(exclude)tools/e2e/ci'` は 0 行 (実行パスに差分なし。以後の差分は本 REPORT・`deploy/README.md`・`.proposed` の削除のみ)。
- 停止報告 (2026-10-14 17:24Z) の diff を `git apply` で適用した (140 行・新規 1 ファイル)。`.proposed` は PR #3292 の fix で削除した (適用後は `.github/workflows/e2e.yaml` が正)。
- 差分からの変更 2 点: (1) remote ジョブの `if` に `&& vars.E2E_URL != ''` を足した (PM 判断。実デプロイ #36 の後に `E2E_URL` と secrets を登録するまで、週次でも skip)。(2) local ジョブに emsdk の install step を足した (下記)。
- local ジョブと同じ `bash tools/e2e/run.sh --driver both --targets preview,edge-sim`: exit 0・**PASS=34 FAIL=0 SKIP=6**・12.2 s (build 込み・n=1)。SKIP 6 = `fl-boot` (FL 未統合) 4 + `edge-policy` の preview 側 (strict 限定) 2。
- emcc が無い環境の再現: 同じコマンドを `EMSDK_ENV=/nonexistent/emsdk_env.sh` で実行すると exit 1・`[audio] emcc not found` (`run.sh` → `tools/audio/integration/stage_app.sh` → `tools/audio/build.sh`)。`ubuntu-latest` (Ubuntu 24.04 image 20261004.327.1) の Readme に Emscripten の記載は無いため、(2) の step (`tools/m1/flags.sh` の `EMCC_VERSION_PIN` を `emsdk install`、`EMSDK_ENV` で `build.sh` に渡す) を足した。同じ方式の `emsdk install 6.0.12` は「FL 起動契約 (#65)」節の #2744 の再測定で 28 s だった。
- (2) の step は Actions run 38658202074 で成功 (上記)。この sandbox では実行できなかった (python の `urlopen` が `CERTIFICATE_VERIFY_FAILED`。環境固有)。remote ジョブは未実行 (`E2E_URL` と secrets が無い)。

## 839 E2E-5: dummy-worklet 参照の差し替え後の再測定 (#839・#1010)
`/worklets/dummy-worklet.js` の参照を `/worklets/fl-audio-worklet.js` へ差し替えた後 (commit `8e27b776` → 修正 commit は PR head を参照)、
edge-sim の `audioworklet`・`console-clean` が `/wasm/audio/manifest.json` の 404 で FAIL していた。原因は edge-sim が `work/dist` を
静的配信し `/wasm/*` の vite middleware を通らないため、テスト音 wasm が配信元に無かったこと。`run.sh` が build 後に
`tools/audio/integration/stage_app.sh` を実行し、`work/dist/wasm/audio/` へコピーするよう修正した (#1010 の対応)。

| 条件 (同一マシン・同一 Chrome 154.0.8037.97・`bash tools/e2e/run.sh --driver both --targets preview,edge-sim`) | 結果 | 所要 (wall) | load (開始 → 終了) |
|---|---|---|---|
| 修正前 `8e27b776` (ベース) | **PASS=26 FAIL=8 SKIP=6**, exit 1 | 92 s (1791912565 → 1791912657) | 0.34 → 0.42 |
| 修正後 (本 PR head) | **PASS=34 FAIL=0 SKIP=6**, exit 0 | 15 s (1791912689 → 1791912704) | 0.23 → 2.07 |

- コミット済み HEAD `22419ef4` で再実行 (同条件・Node v22.23.3): **PASS=34 FAIL=0 SKIP=6**, exit 0, 所要 13 s (1791912812 → 1791912825)、load 0.60 → 0.81 (ログ `head-22419ef4.log`)。
- 修正前の FAIL 8 = `audioworklet` ×4 (preview/edge-sim × 2 driver) + `console-clean` ×4。全件 `/wasm/audio/manifest.json HTTP 404`。
  preview 側も同じ 404 で落ちていた (修正前は preview の `audioworklet` も FAIL)。
- 修正後の `audioworklet` 実測 (samplePos 進行): preview agent-browser 40495 frames/s、preview puppeteer 47059、edge-sim agent-browser 39035、edge-sim puppeteer 51451 (いずれも 128f 単位)。
- 残る SKIP 6 は `fl-boot` (FL 未統合) と `edge-policy` の preview 側 (strict 限定) で、従来どおり。
- ログ: `tools/e2e/work/logs/base-8e27b776.log` (修正前)・`fix1.log` (修正後)。gitignore 配下のため正本はこの表。

## FL 起動契約 (#65)
ページは `window.__webstudio = { state: 'booting'|'running'|'error', frames: <number>, error?: string }` を公開する。
実装は `src/runtime/webstudio_state.ts` (`src/index.ts` が `installWebstudioContract()` を読込時に呼ぶ)。
- 遷移: `booting` → `running` (GUI フレーム 1 枚以上) / `error` (window `error`・`unhandledrejection`・`fail()`)。`error` は終端で最初のエラーを保持、`frames` は単調増加。
- frames の供給: `GuiHost.attach({ onFrame })` の累計フレーム数を `controller.setFrames()` に渡す (`src/runtime/gui.ts`)。
  **実 FL の GuiHost 接続は未実装** (FL 本体がページに統合されていないため。ハーネスのテストフレームは計上しない)。
- `guest: 'fl' | 'test'` (#3461): 載せたゲストの種別。`setGuest` まで契約に現れない。`/?gui=wasm` のテストゲストは `test` で、`fl-boot` は `guest === 'fl'` を要求する (テストゲストで PASS させない: D5)。
- e2e: `webstudio-contract` は常時 (形状)、`fl-boot` は `E2E_REQUIRE_FL=1` で `state==='running' && frames>0` を 180s 待ち、canvas の画素を検査 (#32 の受入に接続)。
  FL 未統合の現状では `E2E_REQUIRE_FL=1` は FAIL する (意図通り)。
- 実測 (HEAD 8bf83d9、Chrome 154、node v22.23.3): `--driver both --targets preview,edge-sim,dev` = **PASS 50 / FAIL 0 / SKIP 10** (28.1s、`webstudio-contract` 6/6 PASS = `{"state":"booting","frames":0}`、fl-boot 6 SKIP + edge-policy 4 SKIP)。
  `E2E_REQUIRE_FL=1 --targets preview` (agent-browser) = PASS 8 / **FAIL 1 (fl-boot: 180146ms 待って `{"state":"booting","frames":0}`)** / SKIP 1、合計 3m2.9s。
- 再測定 (HEAD `e2e15aec` = `origin/main` (`5bbeea0a`) を取り込んだ PR #2744 head、Chrome 154、node v22.23.3、emsdk 6.0.12): `E2E_REQUIRE_FL=1 bash tools/e2e/run.sh --driver agent-browser --targets preview` = **PASS 8 / FAIL 1 (fl-boot: 180185ms 待って `{"state":"booting","frames":0}`) / SKIP 1**、rc 1、所要 197 s (1791999621 → 1791999818)、load 0.38 → 0.63。`webstudio-contract` は `{"state":"booting","frames":0}` で PASS (41ms)。ログ `tools/e2e/work/logs/fl-boot-head-e2e15aec.log` (gitignore 配下)。
  - 測定 commit = `e2e15aec`。`git diff e2e15aec HEAD -- src tools/e2e ':(exclude)tools/e2e/REPORT.md'` は 0 行 (測定後の差分は本 REPORT と docs のみ)。
  - 環境: `toolchain-emsdk` 素材は本 run の `$ARTIFACTS_DIR` に無い。最初の run は `tools/audio/build.sh` の `[audio] emcc not found` で停止 (5 s・rc 1・fl-boot 未到達)。上流 emsdk 6.0.12 を `$RUNNER_TEMP/emsdk` へ `emsdk install 6.0.12` (28 s) で入れ、`EMSDK_ENV` で指定して再実行した。
- 単体テスト: `node --test tools/e2e/webstudio_state.test.mjs` (遷移 6 ケース)。
- 未実施: `agent-browser diff screenshot` による FL 画面のスクリーンショット差分 (基準画像となる FL 起動画面が無いため。#32 後)。

## gui=wasm: 製品ページへのテストゲスト結線 (WIN-24 #3461)
`/?gui=wasm&glue=<app.js>&app=<descriptor>` で、FL ではない検証用ゲスト (`tools/gui/test/text_wasm_app.c`・`GUI_NO_FT=1` = 内蔵 8x8) を chunked descriptor (64 KiB part × 2、sha256 検証) から読み、GuiHost 経由で専用 canvas `#gui-canvas` に描く。`window.__webstudio` は `running` / `frames=1` / `guest='test'`。1 byte 改竄した part は `state=error`・`frames=0` で止まる。実装は `src/runtime/gui_guest.ts`、ゲストのビルドは `tools/gui/e2e/build_guest.sh`。
- 経路: `fetchCompile` (chunked・sha256) → glue `createGuiApp` (`instantiateWasm` で compile 済み Module を注入。`loader_boot.ts` の `createEmscriptenPthreadModule` と同じ方式) → `GuiHost.attach` (専用 canvas・`onFrame` → `webstudio.setFrames`) → `window.__guiGuest` (e2e が `readback()` で画素を読む)。
- 設計: 起動はメインスレッド (`text_main.js` の経路を踏襲)。fl-runtime Worker への移管は未了 (#2717 受入 2)。入力経路 (PumpInput ↔ GuiShared 入力リング) は未結線 (#174・#32 の決定待ち)。`gui=wasm` では `#screen` に縞を描かない。契約 `guest` は `setGuest` まで現れない (既存の `webstudio-contract` の形状を変えない)、`fl-boot` は `guest === 'fl'` を要求する (D5)。

**測定** (測定 commit `0d614c059` = `origin/main` (`cf9dce6f`) を取り込んだ後の HEAD。Chrome 154.0.8037.97、node v22.23.3、emsdk 6.0.12、mingw-w64 11.0.1、開始時 load average 0.38 / 1 分)
| 検査 (ms。`drv.open` を含む検査全体) | preview / agent-browser | preview / puppeteer-core | edge-sim / agent-browser | edge-sim / puppeteer-core |
|---|---|---|---|---|
| `gui-guest-boot` (`state==='running'`, `frames=1`, lit 38400 px, 色 ≥7) | 384 | 198 | 410 | 198 |
| `gui-guest-tamper` (`state==='error'`, `frames=0`) | 142 | 151 | 149 | 50 |

- `EMSDK_ENV=/opt/emsdk/emsdk_env.sh bash tools/e2e/run.sh --driver both --targets preview,edge-sim`: **PASS 42 / FAIL 0 / SKIP 6**、wall 14 s、rc 0。前の基準 (`75131c60`) は PASS 34 / FAIL 0 / SKIP 6。増分 8 = 新検査 2 件 × 4 組 (取り込み前の `c56c734d0` も同じ 42/0/6)。
- 同系列の別 run (`3b1370f0f`・`9a3e4f520`・`c56c734d0`) でも PASS 42 / 0 / 6、`gui-guest-boot` は 197〜424 ms。`open → running` は検査の所要が上限値 (`drv.open` を含む)。180 s の予算に対して十分小さい。FL の wasm での値は未計測。
- 単体テスト `node --test tools/e2e/webstudio_state.test.mjs`: 7 PASS (新規 1 件: `setGuest` 前は契約に guest が無い・設定後は保持)。`pnpm typecheck` rc 0。

**ネガコン (d) の原因同定**: ブラウザの `error` は `WebAssembly compilation aborted: Network error: Failed to read from a ReadableStream.` (Chrome が stream 内の例外を包む)。同じ改竄 descriptor を node で `chunkedStream` に通すと `ChunkIntegrityError: part の sha256 不一致` (正常版は 120669 B を読み切る)。page 側に原因文言を出すのは #3497。

**素材・環境**: `toolchain-emsdk` (`[EMSDK]`) を使用。`gen_api.py` は `x86_64-w64-mingw32-gcc` を要する。`build_guest.sh` は mingw が無ければ apt で導入する (`gcc-mingw-w64-x86-64 mingw-w64-x86-64-dev`)。CI の `E2E / local` ジョブは mingw を入れていないため、この導入に依存する。`fl-win64` は使わない。

**未実施 (子 issue)**: オラクル画素の完全一致とネガコン (a)(b)(c)・`text_wasm_e2e.sh` 回帰 → #3495 (WIN-27)。GUI-REACH trace → #3496 (WIN-28)。D5 のネガコン (テストゲストで `E2E_REQUIRE_FL=1` が FAIL) と原因文言 → #3497 (WIN-29)。`text_wasm_e2e.sh` は FreeType の wasm32 ビルドと font 取得が要るため本 run では未実行 (`tools/gui/lift/gui_wasm.sh`・`text_wasm_app.c` は未変更)。

## ユーザ依頼事項
1. **公開ホスト名** (例: `studio.<既存ゾーン>`)。案 S の既定は workers.dev (`deploy/README.md` §移行で自前ドメインへ)。
2. **Access 許可メール** (`ACCESS_ALLOW_EMAILS`) または許可ドメイン。service token (E2E/CI 用) の新規作成可否。
3. **実デプロイ実行の承認** (`APPLY=1 bash deploy/scripts/deploy.sh --src …`)。`cf` は既にログイン済みのため追加の認証作業は不要。
   CI 化する場合のみ API トークン (権限グループは `deploy/README.md`)。R2 S3 キーは旧構成 (`legacy-r2/`) を使う場合のみ。

## 下流チケット案
GitHub issue 起票済 (検収時): T1→実デプロイ (**CAB-35 として完了**・`deploy/REPORT.md`)、
T2→tools/assets manifest、T3→事前圧縮 + 大容量、T4→`window.__webstudio` 契約実装 (#65、契約本体は実装済・実 FL 接続は #32 側)、
T5→CI 化 (#66、`.github/workflows/e2e.yaml`)、T6→配信後の自動注入対策、H-1→既定ホスト名構成への適応 (**CAB-61 として完了**)。
旧 `CAB-xxx` と GitHub issue `#N` の対応は `docs/REFERENCES.md` `[CAB_TO_GH]`。

## 再現
前提: `node` (実測 v26.10.0) と `npm` が PATH にあること、`/usr/bin/google-chrome` (または `E2E_CHROME`)。
```sh
bash tools/e2e/run.sh --driver both --targets preview,edge-sim,dev      # ローカル全部 (実測 19.5s)
bash tools/e2e/run.sh --url https://studio.example.com                   # デプロイ後 (Access: E2E_ACCESS_CLIENT_ID/SECRET)
node --test deploy/lib/policy.test.mjs                                    # ポリシー単体テスト
bash deploy/scripts/deploy.sh --src tools/e2e/work/dist                   # DRY-RUN (要 deploy/.env)
```
