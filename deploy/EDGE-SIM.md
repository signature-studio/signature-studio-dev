# edge-sim (tools/e2e) を Workers Static Assets の実挙動に合わせるための調整一覧

§B の `/index.html` 検査は #3526 で `tools/e2e/suite/checks.mjs` に適用済み (§A の他項目は未適用)。根拠はすべて実エッジ実測
(`deploy/probe/edge-facts.sh` の出力 = `deploy/REPORT.md`、および `tools/hosting/REPORT.md` §6)。対象は `tools/e2e/suite/servers.mjs` の `startEdgeSim()` と `checks.mjs` の `edge-policy`。

## A. 配信挙動の差 (edge-sim -> 実機)

| # | 項目 | 現 edge-sim (R2 想定) | Static Assets 実機 | 調整 |
|---|---|---|---|---|
| 1 | `/` の index 解決 | `applyRequestRewrite` で `/`+`index.html` に書換え | Static Assets が `/` -> index.html を自前で解決 (200) | 結果は同じ。policy の `requestRewrite` は実機では使わない (R2 用) |
| 2 | `/index.html` | 200 | **307 -> `/`** (既定 `html_handling: auto-trailing-slash`)。`/x/a.html` も 307 -> `/x/a`。`html_handling: none` にすると `/` が 404 になり使えない (実測) | `.html` 要求は 307 + 拡張子無し `Location` に。**checks.mjs の `edge-policy` の probes に `/index.html` があり 307 を Access ログインと誤判定して FAIL する** -> 下記 B |
| 3 | 404 | `Not Found (...)` text/plain | `content-length: 0` の 404。`/*` の COEP 等は 404 にも付く | 本文空に |
| 4 | Range | 未対応 (200) | **Range を無視して 200 全体** (`Accept-Ranges` 無し)、HEAD は 200 | 206 を返す実装にしない (現状 200 で一致) |
| 5 | Content-Type | `policy.contentTypes` の値 | 既定は拡張子由来で **charset 無し** (`text/html`, `text/javascript`)。`.raw/.br/.zst/.part` は **Content-Type 無し** | 実機は `05-stage.mjs` が `_headers` で policy の値に上書き (単一ブロックのみ一致する path では既定を置換。複数ブロックが重なるとカンマ連結 `a, a` になるので stage は ext 別の単一ブロックにしている)。`.raw/.br/.zst/.part` は無しのまま (fetch で無害) |
| 6 | 圧縮 | br/gzip を policy の ext のみ | **text/wasm 系 (js, css, json, wasm, svg, txt, html) をエッジが zstd/br/gzip で自動圧縮** (curl `Accept-Encoding: br, zstd, gzip` で `zstd`)。octet-stream・Content-Type 無しは非圧縮。圧縮応答は弱 ETag `W/"…"` | zstd を追加し ext 判定を Content-Type 基準に。Cache Rules / Compression Rules は不要 |
| 7 | 条件付き | mtime+size の強 ETag | 強 ETag (内容 MD5)、`If-None-Match` -> 304 (COEP 等も付く) | 現状と同形で可 |
| 8 | Cache-Control 既定 | policy `cache-default` (`max-age=300, must-revalidate`) を全パスに | `_headers` 未指定は `public, max-age=0, must-revalidate`。`_headers` で指定した値はその既定を置換。ただし `_headers` ブロック同士が重なると**カンマ連結** (tools/hosting §6-5) | stage が mutable prefix (`/worklets/` `/__e2e__/`) に policy 値を明示。それ以外の非ハッシュ資産は `max-age=0, must-revalidate` (より厳格) |
| 9 | `Content-Encoding` の事前付与 | (n/a) | `_headers` で `.br` に `Content-Encoding: br` を付けても**事前圧縮扱いにならない**。Accept-Encoding に br があるとエッジがさらに圧縮し二重エンコード (実測: 21B -> 25B。ブラウザが 1 段復号しても br バイト列が残る) | tools/assets の `c/*.br|.zst` は JS デコーダ (`registerDecoders`) か raw 配置前提。ヘッダ依存の透過復号は不可 |
| 10 | 反映遅延 | 即時 | `_headers` / asset の反映に 30–60 秒 (n=3) | `--url` 検証前に COEP が付くまでポーリング (90-verify は実施) |
| 11 | 25MiB 上限 | 無制限 | 1 ファイル 25MiB 超は**デプロイ拒否** | edge-sim で 25MiB 超ファイルを検出すると実機との差を早期に拾える。大物は stage で part 化 (README) |
| 12 | workers.dev 有効化直後 | (n/a) | Access が効くまで**無認証 200 が出ることがある** (probe b で 1 回観測。他は 404 -> 302 / 即 302) | edge-sim 対象外。deploy は placeholder で公開 -> 302 確認後に release (20-worker.mjs) |

## B. `checks.mjs` の `edge-policy` (remote / strict ターゲット)

- **`/index.html` (唯一の実 FAIL)**: 実機は 307 -> `/`。`http()` が 3xx を Access ログインとみなして例外にするため、`--url` の `edge-policy` が FAIL する (実測: agent-browser/puppeteer とも 7 PASS + この 1 FAIL)。修正案: remote(strict) では probes から `/index.html` を外し `/` で代替するか、`/index.html` だけ `redirect:'manual'` で 307 + `Location: /` を assert する。**#3526 で後者を適用** (`assertIndexHtmlRedirect`。edge-sim は 200 のまま)。`deploy/probe/policy-check.mjs` は同等の検査を 307 許容で実装済みで、`/` `/assets/*.js` `/worklets/*.js` `/__e2e__/add.wasm` と 404 が全て policy 一致 (REPORT.md)。
- `content-type`: policy は `text/html; charset=utf-8` 等。stage が `_headers` で上書きするため実機でも一致 (上記 policy-check で実測)。stage を通さない素の dist を `--url` で検査すると不一致になる。
- `Cache-Control`: `/`・`/index.html` は no-cache、`/assets/*`・`/wasm/*`・`/data/*`(+ `/c/` `/m/`) は immutable、mutable prefix は stage が明示。prefix 外の非ハッシュ資産は `max-age=0, must-revalidate` なので、policy を直接比較するテストを足す場合は `tools/hosting/headers-from-policy.mjs` の `equivalent()` (より厳格な既定は可) を使う。
- 圧縮: remote では `content-encoding` は記録のみ (現行どおり)。実機は zstd が来るので `br` 固定の assert を remote に足さないこと。
- `/__no_such_object__` は 404 で一致。

## C. 根拠の再現

```sh
bash deploy/probe/probe.sh                           # create -> deploy -> 検証 -> cleanup (deploy/work/probe-<suffix>/edge-facts.txt に採取)
bash deploy/probe/edge-facts.sh <url> [token.json]   # 既存 URL に対する採取のみ
```
