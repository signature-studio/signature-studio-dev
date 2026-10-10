# 既定ホスト名 (workers.dev / pages.dev / r2.dev) だけで COOP/COEP を成立させる配信構成

調査・実測日 2026-10-10 / Chrome 154 headless (/usr/bin/google-chrome) / 実リソースは `signature-studio-hosting-probe*` (検証後に全削除、§10)。

## 1. 結論 (推奨 1 案)

**推奨 = 案 S: Workers Static Assets (Worker コードなし) 1 本に全資産を載せ、`_headers` で COOP/COEP/CORP を付与、Access は `worker` 型で掛ける。**
`https://signature-studio.<account>.workers.dev` 1 ホストで完結し、SAB / AudioWorklet+SAB / OPFS / Worker 内 fetch が全て動く。R2 も Worker 実行も不要。

| 根拠 (実測) | 値 |
|---|---|
| crossOriginIsolated / SAB / Worker+AudioWorklet から SAB / OPFS SyncAccessHandle 書込 | 全て OK (main=true, worker=true, worklet は SAB 可・書込が main から見える) |
| 規模: 2,400 × 1MiB (2.34GiB, 2,402 ファイル) を 1 Worker version にデプロイ | 成功。アップロード 198.7s (12 MiB/s)、全体 209s。全 2,400 chunk を cold で取得し sha256 照合 **2400/2400 一致・エラー 0・62.6s (38 MB/s)**、warm 70 MB/s |
| 課金 | **$0**。静的アセットへのリクエストは無料・無制限 (公式)。R2/Worker 呼出なし。Access は Zero Trust Free (≤50 ユーザ) |
| E の chunk 取得 (1MiB×100, 並列 8, id=sha256 検証, OPFS 書込, Cache Storage) | 63–81 req/s (中央値 71 req/s, p50 111ms, p95 159ms), 429 ゼロ |
| Access 配下 (service token で認証→ `CF_Authorization` cookie のみで動作) | crossOriginIsolated=true のまま全テスト OK、スループット同等 (66 req/s, n=1) |

**制約 (必ず設計に織り込む)**: ① **Range 非対応** (Range を付けても 200 全体を返す。`rangePar` 検証で不一致を実測) ② 1 ファイル ≤ **25MiB** (26MiB は `Asset too large` でデプロイ拒否を実測) ③ Free で 20,000 ファイル/version (Paid 100,000) ④ `.raw/.br/.zst` は Content-Type 無し (fetch では無害) ⑤ `_headers` 更新の反映に **30–60 秒** (n=3)。
→ E の「content-addressed ≤1MiB chunk を丸ごと GET」設計と完全に整合 (現 full pack = 2,009 objects / 610MB で上限の 10%)。**25MiB 超の単一 wasm (tools/perf に 335MB 級あり) は chunk 分割必須** (§6)。

**フォールバック**: Range / >25MiB 単体 / >20k ファイルが必要になった資産だけ、同 Worker に `run_worker_first: ["/r/*"]` + R2 バインディング (案 A) を足す。

## 2. 案別の実測比較

| 案 | 構成 | isolated | Access 後付け | Range | 課金 | 評価 |
|---|---|---|---|---|---|---|
| **S** | Static Assets + `_headers` | ✅ (require-corp) | ✅ `worker` 型 (全ドメイン+preview を保護) | ❌ 200 全体 | $0 | **採用** |
| A | Worker + R2 バインディング全面 | ✅ | ✅ (S と同じ) | ✅ 206 バイト一致 | Worker req 課金 | 次点 (§3) |
| B | HTML=Static Assets, データ=r2.dev + CORS | ✅ credentialless / **require-corp でも ✅** | ❌ r2.dev に不可 | ✅ | $0 | **却下**: データが公開、429 |
| C | Pages `_headers` (+ r2.dev) | ✅ | △ (§5) | ❌ (Pages も 200 全体) | $0 | S と機能同等。レガシー (§3) |
| D | 自前ドメイン + Transform Rules | (未検証: ゾーン無し) | ✅ | R2 経由なら ✅ | R2 のみ | 後日移行 (§7) |

スループット (browser, 中央値 n=3, 本 VM の回線上限 ≈70 MB/s。Node 並列 16 × 1000 req でも S/A/P とも 62–72 MB/s で同等):

| 経路 | 全体 GET | chunk 100×1MiB req/s (p50/p95 ms) | 備考 |
|---|---:|---:|---|
| S Static Assets | 140 MB/s (24MiB) | 71 (111/159) | cold 1 発目 21 req/s (edge MISS) |
| A Worker+R2 | 64 MB/s (100MiB, ストリーム) | 47 (159/256) | Range 25 分割並列 70 MB/s、全て 206 |
| B r2.dev (cl / rc) | 48 / 46 MB/s | 69 / 89 | 100 req では 429 なし (§4 の負荷で発生) |
| C Pages | 127 MB/s (24MiB) | 79 (101/163) | 初回デプロイ直後に 522 を 1 回観測 (n=1, 再現未確認) |

## 3. 却下・次点の理由

- **B (r2.dev) 却下**: ① 公式に「非本番・レート制限・Access/WAF/キャッシュ不可」。実測: **Node 並列 16 で 1000 req 中 386 が 429** (317 req/s)、直後は並列 2 でも 600/600 が 429 (ペナルティ窓)、並列 4 で 2/600、並列 8 で 539/600。E の既定並列 8 + 再試行 50/100/200ms では破綻 ② Access 作成 API が `12130 domain does not belong to zone` で拒否、curl も無認証 200 → 限定公開できない ③ Cache-Control を OAuth の `cf r2 objects put` で付けられない (Content-Type のみ)。
- **C (Pages) 非推奨**: 機能は S と同等 (isolated ✅、chunk 79 req/s) だが、公式が「新規は Workers」と明記。`wrangler pages project create` は Workers へ委譲され失敗し **`--force` が必要**。Pages は `x-content-type-options`/`referrer-policy` を自動付与、`_headers` の**同一パターン重複ブロックは後勝ちで上書き** (Workers は合算) — 実測で `/s/*` の COOP/COEP が消えて isolated=false になった。Access は hostname 型だと `<hash>.<project>.pages.dev` のデプロイ URL が **200 のまま素通し**。
- **A (Worker+R2) 次点**: Range/ETag/304/HEAD/416 を R2 の `range`/`onlyIf` で正しく実装でき (probe/worker-a)、**CPU ≤1ms/req** (wrangler tail n=32, 100MiB ストリーム含む)、応答サイズ上限なし。欠点: ① 全 chunk が Worker 呼出 (Free 100k/日) ② 公式: Cache API が機能するのはカスタムドメイン (Access 配下の Worker では不可) → workers.dev では毎回 R2 Class B ③ R2 `get(range: headers)` は Range 無しでも `obj.range` を埋めるので `request.headers.has('range')` で分岐しないと **通常 GET が 206 になる**バグを実測で踏んだ。

## 4. 課金・制限の数値 (公式 docs を 2026-10-10 に取得)

| 項目 | Free | Paid ($5/月) |
|---|---|---|
| Workers リクエスト | 100,000/日 (超過 error 1027) | 10M/月込み、+$0.30/M |
| CPU | 10ms/req | 30M ms/月込み、+$0.02/M ms |
| Static Assets リクエスト | **無料・無制限** | 同左 |
| Static Assets | 20,000 files・25MiB/file | 100,000 files・25MiB/file |
| Worker 応答サイズ | 上限なし | 同左 |
| R2 | 10GB 保管・Class A 1M・Class B 10M/月 無料、egress 無料 | 超過: $0.015/GB-月, A $4.50/M, B $0.36/M |
| Zero Trust (Access) | 50 ユーザまで $0 | $7/ユーザ/月 (51 人目から全員課金) |
| `_headers` | 100 ブロック・2,000 字/行・splat 1 個/パターン | 同左 |

推定 (E の bootset から): 起動 ≈ HTML/JS 10 + manifest 2 + chunk 45 = **約 57 req/セッション**、full pack 全取得 ≈ 2,019 req (wasm chunk 分は別途)。案 A なら Free で **約 1,750 起動/日 または 49 full ロード/日**。Paid で 100M req/月 ≈ $5+$27+CPU$1.4 ≈ $33。案 S は $0。

## 5. Access (Zero Trust) の掛かり方 (API で実作成・curl で確認)

| ホスト名 | 結果 |
|---|---|
| workers.dev `worker` 型 (destination `{type:"worker",worker_id}`) | ✅ 302 → `<team>.cloudflareaccess.com`。**version preview URL も 302** で保護される |
| workers.dev hostname 型 (`{type:"public",uri}`) | ✅ 本番 URL のみ。`<ver>-<name>.<sub>.workers.dev` は **200 素通し** (実測) → 非推奨 |
| `preview_urls: false` (wrangler.jsonc) | version URL が 404 になる (実測) |
| pages.dev hostname 型 | ✅ 本番のみ。`<hash>.<project>.pages.dev` は 200 素通し → ワイルドカード要 |
| r2.dev | ❌ 作成不可 (`12130`)、無認証 200 |

- **反映遅延**: 作成直後に叩くと `worker` 型は即 302、hostname 型 (s/p) は 200 のまま (e2e 再実行時 n=1)。公開物を置く**前**に Access を作り、302 を確認してから URL を共有する (`access-probe.sh test` は 302 までポーリング)。
- service token (`non_identity` ポリシー) で E2E 可: 1 回の token 認証で **`CF_Authorization` cookie (HttpOnly, Secure, SameSite=None, 24h)** が発行され、以降は cookie のみで isolated・SAB・worklet・OPFS が通る。
- **セッション失効時の fetch**: 既定 fetch は `TypeError: Failed to fetch` (ネット断と区別不能)、`redirect:'manual'` なら `opaqueredirect`、`X-Requested-With: XMLHttpRequest` を付けると **401** (同一オリジンのみ有効。cross-origin は preflight を誘発) → E のローダは失効を検知して再ログイン誘導すべき。
- `cf` OAuth のスコープに `access:write` 等が含まれていたため権限不足は発生せず (§10)。

## 6. E (tools/assets) との衝突点 (読取のみ) と M への引継ぎ

1. **Range 非依存**: E は Range 不使用 (`HttpChunkSource` は丸ごと GET) → S で問題なし。依頼文の「Range+OPFS」は S では成立しない (A/R2 のみ)。
2. **>25MiB 単一 wasm**: tools/perf に 335MB の wasm あり。Static Assets は不可 → E の pack で chunk 化し、クライアントで連結して **`new Response(ReadableStream, {headers:{'content-type':'application/wasm'}})` を `WebAssembly.compileStreaming` に渡す** (実測 OK: 30MiB を 10MiB 単位で 4 分割、S/A/B/C 全てで isolated 下 0.6–1.5s で compile、customSection 長一致)。
3. **リトライ**: `http-source.ts` の再試行 3 回・50/100/200ms は r2.dev の 429 窓に不足。429/503 は `Retry-After`/指数バックオフ、Access 失効 (opaqueredirect/401) は別系統で扱う。S では 429 は出ない。
4. **ネスト Worker (fetch-worker) と COEP**: Worker スクリプトにも COEP/CORP が要る。**HTML にだけ付けると Worker が `ERR_BLOCKED_BY_RESPONSE` で起動しない** (実測。AudioWorklet モジュールは無ヘッダでも読めた) → `_headers` は **`/*` 一括**。なお AudioWorkletGlobalScope には `crossOriginIsolated` が無い (`typeof SharedArrayBuffer` で判定すること。実測 undefined/function)。
5. **`_headers` の仕様差**: 同名ヘッダは上書きでなく追加 (Cache-Control が二重になる)、`! H` で除去できるのは splat→splat のみ。M の `edge-policy.json` の「後勝ち」は再現不可 → **`node tools/hosting/headers-from-policy.mjs --check [--out dist/_headers]`** が変換・制約検査・オフライン突合する (実エッジ突合 `probe/pol-test.sh`: 8/8 ok)。blanket の cache-default (max-age=300) は出力せず Static Assets 既定の `max-age=0, must-revalidate`+ETag になる (より厳格)。`/wasm/manifest.json` は immutable prefix 配下だと `…immutable, no-cache` と連結される (no-cache が支配して意図通りだが、`/release.json` 配下に置く方が明快)。status 条件は表現不可。
6. **edge-sim の差**: Static Assets は Range 無視 (200)、`.raw/.br/.zst` は Content-Type 無し、text/wasm は zstd/br/gzip を自動圧縮、`/index.html` は 307→`/`、`_headers` 反映に 30–60s。edge-sim (tools/e2e) もこれに合わせると実機との乖離が減る。
7. **deploy/ の R2 前提**: S では R2・zone・Transform Rules・`50-domain.sh` 不要。`wrangler deploy` (assets.directory=dist) + `_headers` + Access `worker` 型 + `preview_urls:false`。`20-upload.mjs` の `cf r2 objects put` (300MB 上限・Cache-Control 不可) も不要になる。
8. **OPFS 書込と空き容量**: Chrome のプロファイルを tmpfs (この VM の /tmp は 3.7GB・空き 1.1GB) に置くと、約 300MB の OPFS 書込中に **`InvalidStateError: Failed to write to the access handle`** が 100 書込中 6–21 回発生 (8/8 回再現)。プロファイルを実ディスクに移すと 5/5 回ゼロ。QuotaExceededError ではなく InvalidStateError で出るので、E の `SlotCache` は書込失敗を「キャッシュ満杯」として扱い退避/メモリ継続すること。M の E2E (agent-browser 含む) は **プロファイルを実ディスク (OPFS 2.3GB 以上の空き) に置く**こと (`run-probe.mjs` は work/ 配下を既定にした)。
9. **OPFS はオリジン単位**: ホスト名変更で `fl-vfs` キャッシュ・Cache Storage・IndexedDB・cookie が全て別オリジン (§7)。E のキャッシュは chunk id キーなので再取得のみで整合は保たれるが、ユーザ書込データ (プロジェクト等) があれば要エクスポート。

## 7. 自前ドメイン移行 (案 D)

- **最小移行 (推奨)**: 同じ Static Assets Worker に `"routes":[{"pattern":"studio.<domain>","custom_domain":true}]` を足して再デプロイ。`_headers`・Access `worker` 型 (公式: 全ドメイン/preview を自動保護)・chunk は無変更。Transform Rules 不要。旧 workers.dev は `"workers_dev": false` で閉じる (※ wrangler の再デプロイで復活しないよう設定値で管理)。
- **R2 方式 (当初案) へ**: 25MiB 超・Range・2 万ファイル超が必要になった時だけ。R2 に同じ content-addressed chunk を `cf r2 objects put`、カスタムドメイン + Transform Rules (M の `deploy/`)。Range/Cache Rules/br 圧縮が使える。
- **オリジン変更の影響**: OPFS `fl-vfs`・Cache Storage・IndexedDB・localStorage・Access cookie (`CF_Authorization` はホスト単位、`aud` もアプリ毎に別) が新ホストでは空 → 初回は再ダウンロード (全量 2.3GB は不要、遅延取得分のみ)。旧ホストを 308 でリダイレクトする前に、ユーザデータのエクスポート導線を用意。COOP/COEP/SAB の挙動はホスト名に依存しない (どちらも HTTPS)。データ別ホスト構成 (B) を使っていた場合は R2 CORS の `allowed.origins` を更新。
- **cross-origin 資産を使う場合の注意**: `require-corp` 下で CORS モード fetch (`ACAO` あり) は CORP 不要で通る (実測)。no-cors の `<img>` 等は CORP 無しで遮断 (`NotSameOriginAfterDefaultedToSameOriginByCoep`)、`credentialless` なら通る。

## 8. ブラウザ対応 (MDN BCD 取得値 / 実測は Chrome 154 のみ)

| 機能 | Chrome/Edge | Firefox | Safari |
|---|---|---|---|
| COEP `require-corp` (crossOriginIsolated, SAB 再有効化) | 83 (SAB 68) | 79 | 15.2 |
| COEP `credentialless` | 96 | 119 (Android 非対応) | **非対応** |
| OPFS `createSyncAccessHandle` | 102 | 111 | 15.2 |
| AudioWorklet | 66 | 76 | 14.1 |

→ **`credentialless` は不要**: cross-origin 資産を CORS 経由に限れば `require-corp` で足り、Safari も含められる。`credentialless` を使うのは「CORP/CORS を付けられない第三者 no-cors 資産」を載せる場合のみ。Firefox/Safari の実機検証は本環境では未実施。

## 9. 手順書

```sh
export PATH=$HOME/.local/share/pnpm/bin:$HOME/.bun/bin:$PATH
# 1) 配信物: dist/ に HTML/JS/chunk を置き、_headers を生成
node tools/hosting/headers-from-policy.mjs --check --out dist/_headers     # (M の edge-policy.json から)
# 2) wrangler.jsonc  (main なし = Worker コードなし)
#    { "name":"signature-studio", "compatibility_date":"2026-10-01",
#      "workers_dev":true, "preview_urls":false, "assets":{"directory":"./dist"} }
bunx wrangler deploy                                  # 2.34GiB で 209s。再デプロイは差分 hash のみアップロード
# 3) Access (worker 型)
cf zero-trust access applications create --body '{"type":"self_hosted","name":"signature-studio",
  "destinations":[{"type":"worker","worker_id":"<cf workers scripts search --name signature-studio の id>"}],
  "session_duration":"24h","policies":[{"name":"allow","decision":"allow","include":[{"email":{"email":"you@example.com"}}]}]}'
# E2E 用 service token: cf zero-trust access service-tokens create --name signature-studio-e2e --duration 720h
#   + policies に {"decision":"non_identity","include":[{"service_token":{"token_id":"<id>"}}]}
# 4) 検証 (_headers 反映まで 30–60s ポーリング)
curl -sI https://signature-studio.<sub>.workers.dev/ | grep -i cross-origin   # 無認証は 302 になる (token ヘッダ付きで確認)
# 再現: bash tools/hosting/probe/e2e.sh   (KEEP=1 で残す / ALLOW_EMAIL=… で Access / BIG=1 で 2.34GiB)
```

## 10. 作成・削除したリソース (名前はすべて `signature-studio-hosting-probe*`)

Workers: `-a` `-s` `-big` `-over`(デプロイ拒否のため未作成) `-pol` / Pages: `-p` / R2: `signature-studio-hosting-probe` (r2.dev 有効・CORS 設定) / Access app ×3 (a,s,p; r は作成拒否) / service token ×1。**全て検証後に `probe/cleanup.sh` で削除し、残存ゼロを確認** (結果は最終回答)。既存の R2 4 バケット・zone・Access 28 アプリは非変更。権限エラーなし (`cf` OAuth に r2/access/rulesets 系スコープあり。`wrangler` OAuth 単体は r2 スコープ無しだが R2 は `cf r2 …` と Worker バインディングで代替でき不要)。

## 11. 未検証・限界

Firefox/Safari 実機 / Access のブラウザ対話ログイン (service token cookie で代替) / 案 A の `run_worker_first` ハイブリッド結合 (要素は個別に実測) / Pages 初回 522 の再現性 / 本 VM 回線 (≈70MB/s) 以上の edge 性能 / 実 FL 資産 (ダミー乱数のみ使用)。
