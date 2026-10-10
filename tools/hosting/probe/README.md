# probe — 既定ホスト名配信の使い捨て検証

結果と推奨は `../REPORT.md`。全リソース名は `signature-studio-hosting-probe*`。**`cleanup.sh` は名前の厳密一致だけを削除**する (他用途の Worker/R2/Access/zone には触れない)。

| ファイル | 役割 |
|---|---|
| `e2e.sh` | 作成→測定→削除の一括実行 (`KEEP=1` 残す / `ALLOW_EMAIL=` Access 検証 / `BIG=1 [BIG_N=]` 規模検証) |
| `gen-data.mjs` `build-site.mjs` | `/dev/urandom` のダミー (100MiB + 24MiB + 1MiB chunk×100 + 分割 wasm) と配備物 (`work/dist-s`, `work/r2`) を生成 |
| `site/lib/probe*.js` | ブラウザ側テスト (isolated・SAB・AudioWorklet・Worker 内 fetch/Range/OPFS/Cache Storage・分割 wasm compileStreaming) |
| `run-probe.mjs` `show.py` | headless Chrome (puppeteer-core) 実行と要約 (`CF_ACCESS_FILE=` で service token 認証) |
| `worker-a/` | 案 A: R2 バインディング Worker (Range/ETag/304/416 実装) |
| `worker-s/` `worker-big/` `worker-over/` `worker-pol/` | Static Assets 構成 (基本 / 2.34GiB / 26MiB 拒否 / policy→`_headers` 実エッジ突合) |
| `r2-upload.mjs` `r2-cors.json` | R2 へ `cf r2 objects put`、CORS 例 |
| `access-probe.sh` `access-expiry.mjs` | Access の掛かり方 (a/s/p/r2.dev) とセッション失効時の fetch 挙動 |
| `stress.mjs` `verify-big.mjs` | Node 並列負荷 (429 検出) / 全 chunk 取得+sha256 照合 |
| `pol-test.sh` | `../headers-from-policy.mjs` の出力を実エッジに載せ、M の edge-policy と突合 |
| `results/` | 本調査の実測 JSON と `summary.txt` |

前提: `cf auth login` / `wrangler login` 済み、google-chrome、node≥22、`npm i` (tools/hosting)。ルート package.json は不変。
