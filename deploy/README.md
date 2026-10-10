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
cp deploy/env.example deploy/.env && $EDITOR deploy/.env                  # WORKER_NAME / ACCESS_ALLOW_EMAILS
bash deploy/scripts/deploy.sh --src <dist> [--manifest tools/assets/manifest.json]            # DRY-RUN (書込なし)
APPLY=1 bash deploy/scripts/deploy.sh --src <dist> [--manifest ...]       # 実デプロイ = CAB-35 (ユーザ承認後のみ)
```
CAB-35 の具体手順・確認項目は `RUNBOOK.md`。

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
