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
| 新規 | `wrangler.jsonc` / `scripts/{05-stage.mjs,20-worker.mjs}` / `client/chunked.{mjs,test.mjs}` / `probe/*` / `RUNBOOK.md` `EDGE-SIM.md` `REPORT.md` |
| 改修 | `scripts/00-preflight.sh`(Workers 用に全面書換) `scripts/deploy.sh`(3 段化) `scripts/40-access.mjs`(hostname 型 -> worker 型に全面書換) `scripts/90-verify.sh`(buildId 待ち・302/preview 検査) `scripts/lib.sh`(pnpm PATH) `env.example` `README.md` `.gitignore` |
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

---

# CAB-35: 実デプロイ実施 — 実測レポート

実施 2026-10-10 (ユーザ承認済み・同日決定) / wrangler 4.149.0 / node v26.10.0 / Chrome 154 headless。**本番 URL: https://signature-studio.pycabbage.workers.dev**

## 1. 結論

- 3 段デプロイ (closed → Access → open → release) 完走、全検証項目 PASS。**CAB-61 の受入条件「新構成 URL で 8 check PASS」を満たしたため CAB-61 は Done 移行** (証跡は Linear コメント)。
- デプロイ内容: **ランディング** (`vite build` の harness: index + assets 2 + worklets 2) + **E2E probe 資産** (`/__e2e__/add.wasm` 41B) + **ランタイム wasm 資産** (`/wasm/manifest.json` + m1-hello/m6-ott/m10-ott/m11-boot 計 7.4MB、ハッシュ名) の **12 ファイル 7,752,022B**。FL 本体 (314MB k100 等) は未統合ゆえ含まず。**chunk 化 (>24MiB) 対象は無し** (最大 6.0MB) — 連結 compileStreaming は CAB-61 probe (19 part / 314MB) で実証済み。
- ベースライン増分は本デプロイ分のみ (snapshot diff 実測): **Worker 19→20 / Access app 28→29 / service token 1→2 / R2 4・zone 1 不変**。一時リソースの残置無し (cleanup 対象 0)。

## 2. 実行手順と所要 (APPLY=1 実測)

`bash deploy/scripts/deploy.sh --src deploy/work/app-dist --manifest deploy/work/runtime-manifest.json` と同値を段別実行 (所要記録のため)。DRY-RUN 先行実施済み。

| 段 | 内容 | 所要 | 実測 |
|---|---|---|---|
| 00 preflight | 読取のみ (OAuth スコープ 4 種 OK / `signature-studio` 未作成確認) | 6.2s | — |
| 05 stage | hardlink + `_headers` 生成 + 制約検査 | 0.13s | buildId **146af7ccd3ca** / 12 files / headers ok (32 blocks) / warnings 0 |
| 20 closed | placeholder デプロイ (workers_dev=false, URL 無し) | 4.7s | version bc728c01 |
| 40 access | Access app + service token 作成 | 4.4s | app 6a08c044… / token 0858d57b… |
| 20 open | 公開 URL 発行 + 無認証 302 待ち | 5.8s | 推移 `[404@0.5s, 302@1.5s]` (無認証 200 の瞬間無し) |
| 20 release | 本物 12 assets (新規 4: `/assets/*.js` 2 + m11 wasm + 他) | 7.2s | version baf2d1e2 |
| 90 verify | 302 / preview 404 / buildId 待ち / ヘッダ検査 (読取のみ) | 1.2s | buildId 一致 **0s** |

- ビルド: `tsc --noEmit` OK + `vite build --outDir deploy/work/app-dist` (104ms) + `tools/e2e/fixtures/add.wasm` を `__e2e__/` へ複製。**tools/e2e は無改変** (成果物 `url-*` は退避→復元、cmp 一致)。asset ハッシュは CAB-61 検収時と同一 (`index-DhkVDjrK.js` / `worker-37S5mIMN.js`)。
- `--manifest deploy/work/runtime-manifest.json` (gitignore 済・再生成可): `tools/runtime/work/wasm/` (stage_wasm.mjs 生成) を `/wasm/` 配下へ配置。edge-policy は `/wasm/` を immutable prefix、`/wasm/manifest.json` を document として既に収載済み。

## 3. 検証結果

| 項目 | 結果 |
|---|---|
| ① 無認証 | `GET /` → **302** → `cabbage916.cloudflareaccess.com/cdn-cgi/access/login/…`。version preview URL 形式 (`<ver>-<name>.…`) → **404** |
| ② service token (non_identity) | `CF-Access-Client-Id/Secret` ヘッダ → **200** (CF_Authorization cookie 発行、以降 cookie のみで通過) |
| ③ policy-check.mjs (307 許容) | **7/7 ok, exit 0** (`/` `/assets/*.js` `/worklets/dummy-worklet.js` `/__e2e__/add.wasm` の policy 一致 + `/index.html` 307→`/` + 404) |
| ④ 隔離 | main: `crossOriginIsolated=true` + SAB 生成 OK。module Worker: blob (同一 COI agent cluster) と**実配備 `assets/worker-*.js`** の両方で cOI=true + SAB OK。AudioWorklet: e2e `audioworklet` **PASS** (samplePos 4608→15872, **41109 frames/s**, 128f 単位) |
| ⑤ chunk 化 | **対象無し** (最大 6.0MB < 24MiB)。連結 compileStreaming の実機実証は CAB-61 probe 参照 |
| ⑥ 90-verify buildId | `release.json` buildId **146af7ccd3ca** が **0s** で一致 (エッジ反映待ち無し) / COOP+COEP+CORP 付き 200 |
| ⑦ Access 対話ログイン | **未検証** (§5-1) |

- **実配備 module Worker の実走行** (新規 `deploy/probe/verify-live.mjs`、`deploy/probe/run.mjs` の production 版): `/?runtime=all&pump=1&pumpN=2000` → m1-hello **25ms** / m6-ott **463.6ms** / m10-ott **514.2ms** / m11-boot **590.4ms** 全 checks ok、Worker 内ログ `cOI=true`、pump self-test (main⇔Worker SAB リング + Atomics.wait) blockedWaits>0 / dropped=0 / p99=0.14ms。結果 JSON: `deploy/work/verify-live{,-all}.json` (gitignore)。
- ブラウザ e2e (`tools/e2e/run.sh --url`, agent-browser): **7 PASS + edge-policy 1 FAIL + fl-boot SKIP**。FAIL は既知の `/index.html` 307 誤判定 (③の 307 許容検査で ok、CAB-6 修正待ち)。

## 4. Access 設定 (ユーザ決定どおり)

- app `signature-studio`: self_hosted / destination `{type:"worker", worker_id: 83c98fc7…}` / session 24h / `app_launcher_visible:false`
- 人間ポリシー `signature-studio-allow`: decision allow, **`include: [{everyone:{}}]`** — ログイン必須・この Zero Trust 組織のユーザならログイン可 (ACCESS_ALLOW_EMAILS 未指定の既定動作)
- CI/E2E ポリシー `signature-studio-e2e-token`: decision **non_identity**, service token `signature-studio-e2e` (secret は `deploy/work/secrets/signature-studio-e2e.json`、0600・gitignore)
- **メール許可リストへの絞り込み/追加手順**: `deploy/.env` に `ACCESS_ALLOW_EMAILS=a@x,b@y` (または `ACCESS_ALLOW_EMAIL_DOMAIN=…`、`ACCESS_ALLOW_EVERYONE=1` 併用で Everyone 残存) を設定し `node deploy/scripts/40-access.mjs --apply` を再実行 (冪等 upsert、Worker/asset/token 無変更)。詳細は RUNBOOK §4。

## 5. 制限・未検証

1. **Access 対話ログインは未検証** (IdP ログイン操作はユーザ権限が必要)。service token 経路 (②) と 302 リダイレクト先の正当性 (①) のみ確認。メール許可リスト設定時に実ログインで確認すること。
2. ブラウザは Chrome 154 headless のみ (Firefox/Safari 未検証。CAB-61 から変わらず)。
3. FL 本体 wasm は未統合のため、chunk 化 (>24MiB) 配備の本番実証は FL 起動後の再デプロイ時。
4. tools/e2e の `edge-policy` check の 307 誤判定は未修正 (CAB-6 管轄。本件では tools/e2e 編集禁止のため、`deploy/probe/policy-check.mjs` を正とした)。
5. `preview_urls:false` でも `cf workers scripts` の version URL 形式は 404 を返す (200 素通し無し) — 期待どおり。

## 6. 次タスク

- **CAB-63 運用**: 再デプロイは同一コマンド (冪等、差分 asset のみ upload)。Access セッションは 24h。_workers.dev URL の共有/認証はメール許可リスト (RUNBOOK §4) で制御。
- **FL 起動後の再デプロイ**: `/wasm/` 配下に FL 本体 wasm (314MB 級) を `--manifest` で追加。chunk 化 (16MiB part + index.json) が初めて本番で効く。E ローダの `chunked.mjs` 結線が前提。
- edge-sim の Static Assets 追従 (EDGE-SIM.md §B) → tools/e2e `edge-policy` の 307 修正 (CAB-6)。
- `/c/` `/m/` `/latest.json` の edge-policy 正本取込み (tools/assets pack 使用時)。

## 7. R2 次点構成の事前圧縮保存・大容量方針 (#64 [E2E-2], 検証起点 2847625)

既知類型との関係 (DEFECTS.md): 該当なし (lift 対象外)。現行配信は案 S (DECISIONS D1)。本節は `legacy-r2/` へ戻る場合の準備。

**実装**: `deploy/legacy-r2/20-upload.mjs` に `--precompress br` / `--no-transform` を追加 (`--backend aws` 専用。`cf r2 objects put` は Content-Type しか保存できないため `--backend cf` との併用は起動時に中止)。
- `--precompress br`: immutable かつ policy の compression 対象拡張子のファイルを brotli (q11、>64MB は q9、lgwin 24) で `deploy/work/precompressed/<key>.br` に生成し、`aws s3 cp --content-encoding br` で元キーへ保存。圧縮後が元より小さい時だけ採用。`release.json` の `files[key]` に `encoding` / `encodedSize` を追記し、`size` / `sha256` は元バイト列のまま (展開後の値)。
- `--no-transform`: immutable の Cache-Control に `no-transform` を追加。
- aws backend の multipart (aws cli 自動) と `--cache-control` は既存。

**検証 (dry-run、ネットワーク無し、合成入力 3 ファイル: 13.00MB wasm 反復データ / 1.00MB 乱数 wasm / 800KB js)**:

| 項目 | 実測 |
|---|---|
| 圧縮採用 | 反復 wasm・js の 2 件のみ。乱数 wasm は圧縮後が元以上のため非採用 (encoding なし) |
| 復号照合 | 採用 2 件とも `brotliDecompressSync` 後の長さ・sha256 が `release.json` の size/sha256 と一致 (2/2) |
| dry-run コマンド | 採用ファイルは `aws s3 cp <.br> s3://<bucket>/<元キー> ... --content-encoding br` を構築 (OK)。非採用は `--content-encoding` なし |
| ガード | `--backend cf` + `--precompress br` → 中止、`--precompress gz` → 中止 (各 1/1) |
| 所要 | `--precompress br --no-transform` 2.008s / 無し 1.668s (load average 0.52、n=1、合成データのため圧縮率・時間は実 wasm の代表値ではない) |

実 R2 への PUT・実 wasm の圧縮率は未実施 (R2 S3 キー無し・FL 本体 wasm 未統合)。実 wasm の既測値は `tools/runtime/DESIGN.md` (M11 6,044,445B → br q11 1,823,721B)。

**判断 (事実は #64 本文の公式 docs 引用に依拠。未再検証)**:
1. **分割**: R2 単一 PUT は 4.995 GiB、CF キャッシュ可能上限は 512MB (Free/Pro/Business)。FL 本体 wasm が 100MB 級なら R2 では**分割不要** (単一オブジェクトで aws multipart PUT)。512MB 超またはキャッシュ不可になる場合のみ Range 並列取得 (R2 方式は Range 対応: tools/hosting/REPORT.md の案 A は 25 分割並列 70 MB/s・全て 206)。案 S (現行) では Range 非対応のため既存の 16MiB part + `chunked.mjs` を使う (314MB・19 part 実測済み、§3)。
2. **事前圧縮 vs 動的圧縮**: 事前圧縮は Content-Encoding 付きオブジェクトの Range がエンコード後バイト列になる (tools/assets/MANIFEST.md) ため、Range 取得する資産には使わない。丸ごと GET の wasm/js には `--precompress br` で q11 を使える (エッジ動的圧縮より高圧縮が可能)。
3. **進捗バー (Content-Length) とのトレードオフ**: 圧縮配信では転送バイト数 ≠ 展開後サイズになるため Content-Length を分母にできない。分母は `release.json` の `size` (展開後) を使い、進捗は展開後バイト数で数える。`no-transform` は「エッジが再圧縮しない」だけで、事前圧縮オブジェクトの Content-Encoding は維持される。エッジ動的圧縮を使う場合 `no-transform` を付けると圧縮されなくなるため、**事前圧縮と no-transform は併用、動的圧縮に任せる資産には付けない**。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 R2 への `--precompress br --execute` 実証 (S3 キー要) | 事前圧縮オブジェクトのブラウザ透過復号・Content-Length 挙動が未実測 | #8 (H-2) にコメント / 実 R2 構成へ戻す時に新規子 issue |
| クライアントが `release.json` の `size` を進捗分母に使う結線 | 進捗バー | #12 (FL 起動) 側 |
