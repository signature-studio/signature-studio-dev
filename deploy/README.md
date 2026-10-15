# deploy/ — Workers Static Assets (既定ホスト名 workers.dev) + Access `worker` 型

> 採用構成は **案 S** (`tools/hosting/REPORT.md` §1/§9): Worker コード無しの Workers Static Assets 1 本に全資産を載せ、
> `_headers` で COOP/COEP/CORP を `/*` 一括付与、Access は `worker` 型、`preview_urls:false`。
> R2 / zone / Transform Rules は不要 (静的アセットへのリクエストは無料・無制限)。Linear: CAB-61 (本改修) → CAB-35 (実デプロイ)。
> 自前ドメインは後日ユーザ指示。**同一 Worker に custom domain を足すだけで移行**できる (§移行)。
> 旧 R2 + Transform Rules 構成は `legacy-r2/` に退避 (25MiB 超・Range・2 万ファイル超が必要になった時の次点。§旧構成)。

## 構成

```
deploy/
  wrangler.jsonc            wrangler 設定の正本 (main 無し=Worker コード無し / assets.directory / preview_urls:false)
  config/edge-policy.json   配信ポリシーの正本 (tools/e2e の edge-sim も同一ファイルを直接解釈。**変更は検収後に**)
  lib/policy.mjs            policy 解釈 (edge-sim が import。移動禁止)
  client/chunked.mjs        大物の連結ローダ (ReadableStream -> compileStreaming)。*.test.mjs は node --test
  scripts/                  05-stage / 20-worker / 40-access / 90-verify / 00-preflight / deploy.sh
  probe/                    使い捨て probe (create->deploy->検証->cleanup の再現)
  legacy-r2/                旧: R2 + zone Transform Rules 構成 (未使用)
  RUNBOOK.md                CAB-35 実デプロイ手順 / EDGE-SIM.md  edge-sim 調整一覧 / REPORT.md  probe 実測
```

| script | 内容 | 書込? |
|---|---|---|
| `00-preflight.sh` | cf/wrangler 認証・スコープ・既存衝突の確認 | 読取のみ |
| `05-stage.mjs` | `--src` (+`--manifest`) -> `deploy/work/site`。>24MiB を 16MiB part に分割、`_headers` 生成+突合、制約検査、`release.json` | `deploy/work/` のみ |
| `20-worker.mjs` | `--phase closed\|open\|release` で `wrangler deploy` (設定は wrangler.jsonc を name/workers_dev/assets.directory だけ上書き)。closed/open は placeholder asset、`open` は無認証 302 になるまで待つ | Worker |
| `40-access.mjs` | service token + Access app (`destinations:[{type:"worker"}]`、人間 allow + token non_identity) の冪等 upsert | `--apply` |
| `90-verify.sh` | release.json の buildId 反映待ち / 無認証=302 / preview=非200 / token でヘッダ検査 / `tools/e2e/run.sh --url` | 読取のみ |
| `deploy.sh` | 上記を順序保証で一括。既定 DRY-RUN | `APPLY=1` |

**順序 (本物の asset は Access が効いてから公開)**: stage -> deploy `closed` (placeholder・workers.dev 無し=URL 無し) -> Access (worker_id が要るので Worker 作成後) -> deploy `open` (placeholder のまま workers.dev 有効化、無認証 302 を確認) -> deploy `release` (本物の asset) -> verify。
実測: workers.dev 有効化直後、Access が効くまで無認証 200 が返った回が 1/5 あった (他は 404 -> 302 または即 302)。そのため公開 URL ができる時点では placeholder しか載せない。

## 1 コマンド (既定 DRY-RUN)

```sh
export PATH=$HOME/.local/share/pnpm/bin:$HOME/.bun/bin:$PATH
cp deploy/env.example deploy/.env && $EDITOR deploy/.env                  # WORKER_NAME / ACCESS_ALLOW_EMAILS (未指定なら Everyone)
bash deploy/scripts/deploy.sh --src <dist> [--manifest tools/assets/manifest.json]            # DRY-RUN (書込なし)
APPLY=1 bash deploy/scripts/deploy.sh --src <dist> [--manifest ...]       # 実デプロイ = CAB-35 (ユーザ承認後のみ)
```
CAB-35 の具体手順・確認項目は `RUNBOOK.md`。

## release guard (LGL-2。upload 前ゲート)

`05-stage.mjs` (入力) と `20-worker.mjs --phase release` (配備物) は `tools/legal/release-guard` の deny-list と照合し、一致で exit 6 (deny-list 欠落は exit 4・fail-closed)。
バイパスは `--skip-release-guard` の明示のみ (`deploy.sh` は両方へ伝搬)。deny-list 生成・allow-list・実測は `tools/legal/release-guard/REPORT.md`。

## notices ゲート (LGL-3。stage 前ゲート)

`05-stage.mjs` は入力に `THIRD_PARTY_NOTICES.{txt,html}` が無い/不完全/registry と不一致、または記録なしの同梱 OSS・同梱禁止 (GPL 系) の痕跡を検出したら exit 7。
NOTICES は `vite build` が出す (FL 素材 `FL_WIN64_DIR` が無いと不完全)。バイパスは `--skip-notices-gate` の明示のみ。仕様・実測は `tools/legal/notices/REPORT.md`。

## 大物 (>24MiB。tools/perf の 335MB 級 wasm など)

Static Assets は 1 ファイル 25MiB 上限 (26MiB は `Asset too large` で拒否: 実測)、Range 非対応。`05-stage.mjs` が自動で分割する:

```
wasm/ott.1a2b3c4d.wasm.parts/0000.<sha12>.part … (16MiB 単位)  +  index.json  (v, path, size, sha256, contentType, partSize, parts[{name,size,sha256}])
release.json.chunked[<key>] = { descriptor, size, sha256, parts, contentType }       (元ファイルは配備しない)
```
```js
import { compileChunkedWasm, instantiateChunkedWasm, chunkedResponse, AccessExpiredError } from '/…/chunked.mjs';
const mod = await compileChunkedWasm('/wasm/ott.1a2b3c4d.wasm.parts/index.json', { concurrency: 6 });   // main / Worker 両方可
```
連結 `ReadableStream` (順序保証・並列プリフェッチ・背圧: 先読みは `concurrency` part まで)、part 毎 sha256 検証、429/5xx は Retry-After/指数バックオフ、
Access 失効 (302/401/403) は `AccessExpiredError` (再ログイン誘導用。ネット断と区別)。`node --test deploy/client/chunked.test.mjs`。
immutable 配下の元ファイル名はハッシュ必須 (stage が検査)。tools/assets の `c/<id>.raw|br|zst` 配置は `/c/` `/m/` を immutable、`/latest.json` を no-cache として `_headers` に反映
(正本 edge-policy.json への取込みは tools/e2e 検収後。`STAGE_EXTRA_IMMUTABLE` / `STAGE_EXTRA_DOCUMENT` で制御)。

## 配信ポリシー

唯一の正本は `config/edge-policy.json`。Static Assets では `tools/hosting/headers-from-policy.mjs --check` が `_headers` に変換し、
`_headers` の累積セマンティクス (同名ヘッダは上書きでなく追加、`! H` は splat->splat のみ) と policy の「後勝ち」の差を検査する。
- 全応答: COOP `same-origin` / COEP `require-corp` / CORP `same-origin` / nosniff。**Worker スクリプトにも COEP が要る** (HTML だけだとネスト Worker が `ERR_BLOCKED_BY_RESPONSE`) ため `/*` 一括。
- Cache-Control: immutable prefix = 1 年 immutable、document (`/` `/index.html` `/release.json` `/wasm/manifest.json`) = no-cache、他は Static Assets 既定 `max-age=0, must-revalidate`+ETag (policy の max-age=300 より厳格)。status 条件は表現不可。
- 圧縮・キャッシュはエッジ既定 (text/wasm を zstd/br/gzip 自動圧縮)。Cache Rules / Compression Rules は使えない/不要。

## トークン権限 (API トークン運用の場合)

Account: Workers Scripts **Edit**、Access: Apps and Policies **Edit**、Access: Service Tokens **Edit**。現環境の `cf`/`wrangler` は OAuth ログイン済みで
`workers-scripts.write` `access-app.write` `access-service-token.write` を含む (00-preflight が検査)。zone / R2 / DNS 権限は不要。

## CI / E2E の秘密情報 (`.github/workflows/e2e.yaml`)

> workflow 本体は `.github/workflows/e2e.yaml` (2026-10-15 に PR #3292 で配置済み)。当初は App に `workflows` 権限が無く push できなかったため
> `tools/e2e/ci/e2e.yaml.proposed` に置いていたが、配置後に削除した (経緯は `tools/e2e/REPORT.md` §CI 化)。

| ジョブ | トリガ | 内容 | 必要な設定 |
|---|---|---|---|
| `local` | PR / main push (対象 path のみ) / 手動 | `tools/e2e/run.sh --driver both --targets preview,edge-sim` | なし |
| `remote` | 週次 (月曜 03:17 UTC) / 手動 (`remote=true`) | `tools/e2e/run.sh --url "$E2E_URL" --driver both` | repo variable `E2E_URL`、secrets `E2E_ACCESS_CLIENT_ID` / `E2E_ACCESS_CLIENT_SECRET` |

- `E2E_URL` (repo variable) が空なら、job の `if` (`vars.E2E_URL != ''`) で remote ジョブ自体が起動しない (notice も出ない)。
  手動実行で `remote=true` と `url` を入れても、`E2E_URL` が空なら起動しない。`E2E_URL` が設定済みのときだけ、`url` 入力が値を上書きする (`inputs.url || vars.E2E_URL`)。
- 成果物 (`results/*.json`・`shots/*.png`・ログ) は artifact `e2e-{local,remote}-<run_id>` に 14 日保存、表は job summary に出る。
- **fork PR / 秘密情報**: `local` は secrets を使わない。`remote` は schedule / 手動のみで PR からは起動しない。

**secrets の運用**
- service token (`signature-studio-e2e`、`40-access.mjs` が作成) の client id/secret を GitHub **repository secrets** に登録する。
  secret は作成時 1 回しか表示されない (`deploy/work/secrets/<name>.json`、0600・gitignore 済み)。登録後はローカルの控えを削除する。
- token の有効期間は `ACCESS_SERVICE_TOKEN_DURATION` (既定 8760h = 1 年)。**ローテーションは 11 か月ごと (失効 1 か月前)** に行う。
  1. `ACCESS_SERVICE_TOKEN_NAME=signature-studio-e2e-<YYYYMM> node deploy/scripts/40-access.mjs --apply` (新 token を作成し Access app のポリシーを新 token に更新。冪等)
  2. 新 client id/secret を repository secrets に上書き
  3. `gh workflow run e2e.yaml -f remote=true` で remote ジョブが PASS することを確認
  4. 旧 token を `cf zero-trust access service-tokens delete` で削除
- 失効・誤設定時は Access がログインへ 302 するため remote ジョブは FAIL する見込み (推定・実 URL では未検証)。FAIL 時はまず token 期限と secrets を確認する。
- CI から **デプロイは行わない**。API トークン (Workers Scripts Edit 等、上記「トークン権限」) を GitHub secrets に置く運用は、CI デプロイを導入する時に別 issue で決める
  (現状 E2E に必要なのは service token のみ。API トークンは不要)。

## 運用上の注意

- `_headers` の反映には **30–60 秒** (n=3)。90-verify は COEP が付くまでポーリング。再デプロイ直後に古いヘッダを見ても異常ではない。
- Access 反映: worker 型でも workers.dev 有効化直後は数秒〜十数秒 404/200 が混ざりうる (上記)。release 後は新 version の asset が行き渡るまで 404/旧版が混ざる (verify が buildId 一致までポーリング)。
- セッション失効 (24h) 時の fetch は `TypeError: Failed to fetch` (opaqueredirect)。`chunked.mjs` は `redirect:'manual'` で検知する。E のローダも同様に扱うこと。
- OPFS/Cache Storage/IndexedDB/cookie は**オリジン単位**。ホスト名を変えると全て空 (移行時はユーザデータのエクスポート導線を先に)。
- COEP `require-corp` 下では CF の自動注入 (Web Analytics 等) がブロックされる。Static Assets では注入されない (probe の console clean で確認)。
- Free: 20,000 files/version、Worker 呼出 100k/日 (静的アセット要求は対象外)。stage が 20,000 超で中止 (Paid は `STATIC_ASSETS_MAX_FILES=100000`)。

## 自前ドメインへの移行 (ユーザ指示後)

`wrangler.jsonc` に `"routes":[{"pattern":"studio.<domain>","custom_domain":true}]` を足して再デプロイ (zone が同アカウントに必要)。
`_headers`・Access `worker` 型 (全ドメイン/preview を自動保護)・part は無変更。旧 workers.dev は `"workers_dev": false` で閉じる。
オリジン変更の影響は上記「運用上の注意」。R2 方式 (`legacy-r2/`) へ戻すのは 25MiB 超 Range / 2 万ファイル超が必要になった時だけ。

## 旧構成 (legacy-r2/)

R2 バケット + カスタムドメイン + ゾーン Transform/Cache/Compression Rules + hostname 型 Access。ゾーン (cabbagelettuce.com 等) 前提のため現在は未使用。
パスは移動のみで内容は不変 (`deploy-r2.sh` が旧 `deploy.sh`)。`lib/policy.mjs` の `build*Rules` はこの構成用。
事前圧縮保存 (`20-upload.mjs --backend aws --precompress br [--no-transform]`) の仕様と判断は `REPORT.md` §7。
