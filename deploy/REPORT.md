# CAB-61: deploy/ を Workers Static Assets (既定ホスト名) 構成へ改修 — 実測レポート

実施 2026-10-10 / Chrome 154 headless / wrangler 4.149.0 / 実リソースは `signature-studio-deploy-probe-{a,b,c,d,e}` (全て作成→検証→削除)。**本番名 `signature-studio` は作成していない (CAB-35 はユーザ承認待ち)。**

## 1. 結論

- deploy/ を案S (Worker コード無し Static Assets + `_headers` + Access `worker` 型 + `preview_urls:false`) に改修。**一時 probe で create -> deploy -> isolation/Access 検証 -> cleanup を 5 回再現**、毎回 cleanup 後にベースライン (Worker 19 / Access app 28 / service token 1 / R2 バケット 4 / zone 1) と**完全一致 (残存 0・既存無変更)**。
- 実エッジで `crossOriginIsolated` が main / module Worker / AudioWorklet(SAB) で成立。**314MB の wasm (19 part) を連結 ReadableStream -> compileStreaming**: main 3.9–4.1s (76–80 MB/s)、Worker 内 4.5–5.2s、part 検証付き、全 200。
- `tools/e2e/run.sh --url` (agent-browser / puppeteer の両 driver): **7 PASS + `edge-policy` 1 FAIL + `fl-boot` SKIP**。FAIL の原因は**実機が正しい挙動**: Static Assets は `/index.html` を **307 -> `/`** にし、checks.mjs がそれを Access ログインと誤判定 (EDGE-SIM.md §B)。307 を許容する同等検査 (`deploy/probe/policy-check.mjs`) は `/` `/assets/*.js` `/worklets/*.js` `/__e2e__/add.wasm` と 404 が**全て policy 一致**。
- 新規に分かった**設計上の要点 (T 調査に無かった)**: ① workers.dev 有効化直後、Access が効くまで**無認証 200** が返った回がある (1/5)。-> placeholder 公開 -> 302 確認 -> 本物の asset を release する 3 段デプロイにした。② release 直後は新 version がエッジに行き渡るまで 404/旧版が混ざる (verify が buildId 一致まで待つ)。③ `_headers` で `Content-Encoding: br` を付けても事前圧縮扱いにならず**二重エンコード**。④ `html_handling:none` は `/` が 404 になり使えない。

## 2. 変更内容 (コミット `feat(deploy): workers static assets backend (CAB-61)`)

| 区分 | ファイル |
|---|---|
| 新規 | `wrangler.jsonc` / `scripts/{00-preflight.sh,05-stage.mjs,20-worker.mjs,40-access.mjs,deploy.sh}` / `client/chunked.{mjs,test.mjs}` / `probe/*` / `RUNBOOK.md` `EDGE-SIM.md` `REPORT.md` |
| 改修 | `scripts/90-verify.sh`(buildId 待ち・302/preview 検査) `scripts/lib.sh`(pnpm PATH) `env.example` `README.md` `.gitignore` |
| 退避 (`git mv`, 内容は import 修正のみ) | R2 構成一式 -> `legacy-r2/` (10-bucket, 20-upload, 30-rulesets, 40-access(hostname型), 50-domain, 00-preflight, deploy-r2.sh, lifecycle.json, rendered/) |
| 不変 | `config/edge-policy.json` `lib/policy.mjs` `lib/cf.mjs` (tools/e2e が import) / tools/e2e 全体 / tools/hosting |

- `05-stage.mjs`: `_headers` を `tools/hosting/headers-from-policy.mjs --check` で生成・突合 + Static Assets 補正 (Content-Type を policy 値へ、mutable prefix の Cache-Control 明示、`/c/` `/m/` immutable、`/latest.json` no-cache は有効 policy のみに追加し正本は不変)。>24MiB を 16MiB part + `index.json` に分割。ファイル数 20,000 / 25MiB / immutable のハッシュ名 / ブロック数 100 を検査。314MB の stage は 0.65s (hardlink + 分割)。
- `40-access.mjs`: destination `{type:"worker",worker_id}`、人間 allow(メール) + service token `non_identity`、冪等 upsert。secret は `deploy/work/secrets/*.json` (0600, gitignore)。
- `client/chunked.mjs`: 連結 ReadableStream (順序保証・並列プリフェッチ・背圧)、part sha256 検証、429/5xx の Retry-After/指数バックオフ、Access 失効は `AccessExpiredError`。`node --test deploy/client/chunked.test.mjs` 7/7 + `deploy/lib/policy.test.mjs` 6/6 PASS (合計 13)。

## 3. probe 実測

| 項目 | 実測 |
|---|---|
| 所要 (k100.wasm 314MB 込み, probe e) | stage 5s / closed 5s / access 7s / open 6s / release 35s / verify 2s / browser 14s / e2e 4s / cleanup 9s |
| closed 状態の URL | 404 (到達不可) |
| open 直後の無認証応答推移 | a: 404 -> (後続 302) / b: **200** (placeholder 無しの旧フロー) / c: `[404@0.1s, 302@11.2s]` / d,e: `[302@0.1s]` |
| 無認証 `GET /` | 302 -> `<team>.cloudflareaccess.com` (全回)。`<ver>-<name>.<sub>.workers.dev` 形式は 404 (200 でない) |
| service token 認証 | `CF_Authorization` cookie 発行 (HttpOnly, Secure, SameSite=None)、以降 cookie のみで isolation/SAB/worklet が通る |
| release 後の buildId 反映 | 0s (d,e) / 初回 c は反映前に 404 (旧フローで verify が待たなかった) |
| 全ブラウザ検査 (e) | main/Worker `crossOriginIsolated=true`・SAB OK、AudioWorklet SAB OK (`typeof SharedArrayBuffer`=function、`crossOriginIsolated` は worklet に無い)、small wasm `content-type: application/wasm` で compileStreaming 20ms、console error は 404 1 件 (favicon 想定、測定対象外) |
| 314MB 連結 | 19 part、`partRequests=19`、statuses `[200]`、exports 8271 |
| edge facts | `/index.html` 307、404 は空本文+COEP、Range 無視で 200 全体 (16777216B)、HEAD 200、text/js は `content-encoding: zstd` + 弱 ETag、`If-None-Match` -> 304、descriptor/part は immutable |
| `_headers` Content-Type | 単一ブロック一致で既定を置換 (`text/javascript; charset=utf-8`)、重複ブロックは `a, a` 連結 |
| `_headers` `Content-Encoding: br` + `.br` | AE に br がある場合 21B -> 25B (二重エンコード)。ブラウザ fetch は 1 段復号後も br バイト列 (garbled) |
| 課金 | 静的アセット要求は無料。Access は Zero Trust Free |

## 4. 後処理・無影響の確認

- `deploy/probe/probe-cleanup.sh` は名前の厳密一致 (`^signature-studio-deploy-probe(-[a-z0-9]+)?$`、token は `…-e2e$`) のみを削除し REFUSE ガード付き。実行後 `snapshot.sh` を baseline と diff し **BASELINE MATCH** (5/5 回)。本番名 `signature-studio` は対象外。
- tools/e2e: ソース無改変 (git status 0)。`--url` 実行は `work/results|shots/url-*` を書くため、既存 `url-agent-browser*` を退避・復元 (cmp 同一確認)、自分の `url-puppeteer*` は削除。
- 機密: service token は `deploy/work/secrets` (gitignore)。コミット対象外。`deploy/work` に 314MB の hardlink/part あり (gitignore、20MB 超 blob コミット無し)。

## 5. 未解決・限界

1. edge-sim/`checks.mjs` の `/index.html` 307 対応は tools/e2e 側 (禁止範囲)。EDGE-SIM.md に 12 項目を文書化。
2. 実アプリ + 実 FL 資産での実デプロイは未実施 (CAB-35)。chunk 数が多い tools/assets pack (2,009 objects) の 1 version デプロイは T が 2.34GiB で実証済み。
3. open 直後の 200 は 1/5 回のみの観測 (再現性は n=5 で 20%)。対策は構造的 (placeholder) なので頻度に依存しない。
4. 反映遅延 (release 後 404 混在) は n=1 観測 (c)。verify はポーリングで吸収。
5. `.br/.zst` を透過復号させる経路は Static Assets では不可。E の pack が br/zstd 保存なら JS デコーダ必須 (または raw 配置)。
6. ブラウザは Chrome のみ (Firefox/Safari 未検証)。
