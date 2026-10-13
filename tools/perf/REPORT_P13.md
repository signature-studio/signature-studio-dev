# PERF-P13 (#952) 大物 (>24MiB) wasm の配信 — 実測

方式決定は `docs/DECISIONS.md` D9 (事前非圧縮 part + `chunked.mjs`)。本書は実測のみ。
検証起点: worktree `ws-952` (branch `952-chunked-fetch`、origin/main `70385178` 起点)。

## 1. 実施内容

- `src/runtime/loader_boot.ts` `fetchCompile`: URL が `*.parts/index.json` のとき `deploy/client/chunked.mjs` の `chunkedResponse` に分岐 (streaming / bytes 両対応)。それ以外は従来どおり。
- `deploy/client/chunked.d.mts`: `src/` (strict TS) から型付きで import するための宣言。
- 計測: `node tools/perf/delivery/chunked_bench.mjs --mib 32 --reps 3 --mbps 0,100` (結果 `tools/perf/results/chunked.json`)。
- 結線の確認: `bun tools/perf/delivery/fetch_compile_chunked_check.ts <site> <asset>` (src の `fetchCompile` をそのまま実 HTTP で通す)。

## 2. 素材と制約 (重要)

- **素材は合成 wasm 34,229,227 B (32.6 MiB)**。関数 ~360 B のコード様バイト列。**実 FLEngine wasm ではない**。
- 実 FLEngine (>24MiB 本体) は lift パイプラインが未完のため本 run では生成できず、実規模の計測は未実施。
- 分割: `deploy/scripts/05-stage.mjs --max-file 24MiB --part-size 16MiB` → 3 part (元ファイルは置かれず)。
- 環境: headless Chrome 154.0.8037.97 (Linux, 4 コア, node v22.23.3)、loadavg 0.55〜1.11。

## 3. 実測 (n=3, fetch→compile→instantiate, ms)

| 帯域 | 方式 | 中央値 | min–max |
|---|---|--:|--:|
| 無制限 (loopback) | streaming | 204.2 | 202.8–265.1 |
| 無制限 (loopback) | bytes | 221.0 | 211.7–258.2 |
| 100 Mbps/接続 | streaming | 1490.5 | 1486.0–1503.6 |
| 100 Mbps/接続 | bytes | 1514.9 | 1506.7–1516.6 |

- 結果: **12/12 PASS** (全件 `f0()==42`、`exports=1`)。
- 注意: 帯域制限は**接続ごと**に掛かる。part は並列 6 本で取るため、100 Mbps/接続 の実効は最大約 300 Mbps 相当。「100 Mbps 回線」の値ではない。
- 無制限では streaming が bytes より約 17 ms 速い (中央値)。100 Mbps では差は約 24 ms。どちらも誤差に近い。

## 4. 検証

- `pnpm typecheck` PASS (exit 0)。
- `bun .../fetch_compile_chunked_check.ts`: streaming 262.5 ms / bytes 254.6 ms、`f0=42`、progress 6 回、PASS。
- `node --test deploy/client/chunked.test.mjs`: **既存 8 件 FAIL** (fixture 側の `05-stage.mjs` が `release-guard` の deny-list 不在で fail-closed)。本変更とは無関係。`tools/legal/release-guard/work/denylist` が worktree に無いため。対処は release-guard:build (解析 dir が要る)。
- 上記 release-guard 環境要件は §6 (#1151) に起票。

## 5. 結論

- 受入条件 1 (方式比較と決定記録): **達成** (D9)。
- 受入条件 2 (chunked.mjs → fetchCompile 結線): **達成** (loader_boot.ts)。
- 受入条件 3 (>24MiB の実測 n≥3, min–max): **部分達成**。合成 32.6 MiB で実施。実 FLEngine 規模 (>24MiB 本体) の実測は未了。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 FLEngine 規模 (>24MiB) の download→compile→instantiate 実測 | 受入条件 3 の本体 | #1150 `[PERF-P16]` |
| `chunked.test.mjs` が release-guard deny-list 不在で既存 8 件 FAIL | テストが通らない (CI 環境) | #1151 `[PERF-P17]` |
