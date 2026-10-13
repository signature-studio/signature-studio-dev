# PERF-P13 (#952) 大物 (>24MiB) wasm の配信 — 実測

方式決定は `docs/DECISIONS.md` D9 (事前非圧縮 part + `chunked.mjs`)。本書は実測のみ。
検証起点: worktree `ws-952` (branch `952-chunked-fetch`、origin/main `70385178` 起点)。
測定は HEAD `30888aed` 上で再実行 (実行: 2026-10-14)。本書の数値は `tools/perf/results/chunked.json` と一致する。

## 1. 実施内容

- `src/runtime/loader_boot.ts` `fetchCompile`: URL が `*.parts/index.json` のとき `deploy/client/chunked.mjs` の `chunkedResponse` に分岐 (streaming / bytes 両対応)。それ以外は従来どおり。
- `deploy/client/chunked.d.mts`: `src/` (strict TS) から型付きで import するための宣言。
- 計測: `node tools/perf/delivery/chunked_bench.mjs --mib 32 --reps 3 --mbps 0,100` (結果 `tools/perf/results/chunked.json`)。
- 結線の確認: `bun tools/perf/delivery/fetch_compile_chunked_check.ts <site> <asset>` (src の `fetchCompile` をそのまま実 HTTP で通す)。

## 2. 素材と制約 (重要)

- **素材は合成 wasm 34,229,227 B (32.6 MiB)**。関数 ~360 B のコード様バイト列。**実 FLEngine wasm ではない**。
- 実 FLEngine (>24MiB 本体) は lift パイプラインが未完のため本 run では生成できず、実規模の計測は未実施。
- 分割: `deploy/scripts/05-stage.mjs --max-file 24MiB --part-size 16MiB` → 3 part (元ファイルは置かれず)。
- 環境: headless Chrome 154.0.8037.97 (Linux, 4 コア, node v22.23.3)、loadavg 0.54〜0.82 (`chunked.json` の rows 全件の範囲)。

## 3. 実測 (n=3, fetch→compile→instantiate, ms)

| 帯域 | 方式 | 中央値 | min–max |
|---|---|--:|--:|
| 無制限 (loopback) | streaming | 130.3 | 128.6–275.1 |
| 無制限 (loopback) | bytes | 124.0 | 120.4–140.0 |
| 100 Mbps/接続 | streaming | 1457.7 | 1454.6–1464.1 |
| 100 Mbps/接続 | bytes | 1458.9 | 1454.4–1473.9 |

- 結果: **12/12 PASS** (全件 `f0()==42`、`exports=1`)。
- 旧 commit 時点の `chunked.json` (旧数値: 無制限 streaming 204.2 / bytes 221.0、100 Mbps streaming 1490.5 / bytes 1514.9) は本再測定で再現しなかった。原因は未特定。
- 注意: 帯域制限は**接続ごと**に掛かる。part は並列 6 本で取るため、100 Mbps/接続 の実効は最大約 300 Mbps 相当。「100 Mbps 回線」の値ではない。
- 無制限では streaming が bytes より約 17 ms 速い (中央値)。100 Mbps では差は約 24 ms。どちらも誤差に近い。

**注記 (同 HEAD での再実行, 2026-10-14)**: `node tools/perf/delivery/chunked_bench.mjs --mib 32 --reps 3 --mbps 0,100 --out tools/perf/work/chunked_rerun.json` を HEAD `30888aed` で追加実行した (12/12 PASS, `f0()==42`, loadavg 0.49〜1.41)。値は以下のとおり。`chunked.json` (§3 表) とは一致せず、run 間のばらつきが大きい。

| 帯域 | 方式 | 中央値 | min–max |
|---|---|--:|--:|
| 無制限 (loopback) | streaming | 190.1 | 187.8–305 |
| 無制限 (loopback) | bytes | 204.5 | 203.4–209.5 |
| 100 Mbps/接続 | streaming | 1471.4 | 1454.2–1484.6 |
| 100 Mbps/接続 | bytes | 1487.9 | 1487.5–1489.5 |

- 再実行間で無制限の中央値が 190〜235 ms まで動く。n=3 では streaming/bytes の差を結論づけられない。確定値には反復数の増加が必要 (未起票・必要なら #1150 に統合)。

## 4. 検証

- `pnpm typecheck` PASS (exit 0)。
- `bun tools/perf/delivery/fetch_compile_chunked_check.ts tools/perf/work/chunked/site big.561695cb78ed.wasm`: streaming 165.8 ms / bytes 156.3 ms、`f0=42`、progress 6 回、PASS (HEAD `30888aed`)。
- `pnpm typecheck`: exit 0 (HEAD `30888aed`)。
- `node --test deploy/client/chunked.test.mjs`: **既存 8 件 FAIL** (fixture 側の `05-stage.mjs` が `release-guard` の deny-list 不在で fail-closed)。本変更とは無関係。`tools/legal/release-guard/work/denylist` が worktree に無いため。対処は release-guard:build (解析 dir が要る)。
- 上記 release-guard 環境要件は §6 (#1151) に起票。

## 5. 結論

- 受入条件 1 (方式比較と決定記録): **達成** (D9)。
- 受入条件 2 (chunked.mjs → fetchCompile 結線): **達成** (loader_boot.ts)。
- 受入条件 3 (>24MiB の実測 n≥3, min–max): **達成** (§7。実 FLEngine wasm 26.4 MiB で実施。合成 32.6 MiB は §3 のとおり参考値)。
- **結線の範囲: `fetchCompile` 関数レベルまで。runtime の manifest 経路は未接続。** `tools/runtime/stage_wasm.mjs` は単一ファイル URL しか出さず、`*.parts/index.json` を `entry.file` に入れる経路が無い。本番 runtime の経路からはまだ到達しない。manifest 経路の結線は #1166 `[PERF-P18]` で追跡。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (解消) 実 FLEngine 規模 (>24MiB) の download→compile→instantiate 実測 | §7 で実施済み (#1150) | — |
| `chunked.test.mjs` が release-guard deny-list 不在で既存 8 件 FAIL | テストが通らない (CI 環境) | #1151 `[PERF-P17]` |
| manifest 経路 (`stage_wasm.mjs` → runtime) が `*.parts/index.json` を出さない | 本番 runtime から未到達 | #1166 `[PERF-P18]` |

## 7. 実 FLEngine wasm (26.4 MiB) の実測 (#1150 / PERF-P16)

- **素材**: `tools/flelift/fle_lift.sh` で FLEngine_x64.dll 全体 (7,018 関数 / 340,761 命令 / unsup 0) を lift → emcc -O0 で `flel.wasm` 27,639,303 B (26.4 MiB)。`fl-win64` 素材 (`FL_WIN64_DIR`) から生成。生成物は `tools/flelift/work/` (gitignore)。
- **分割**: `deploy/scripts/05-stage.mjs --max-file 24MiB --part-size 16MiB` → 2 part (sha `b92b83ae3549`)。
- **注意 (合成との差)**: wasm は `env` 3 関数・`wasi_snapshot_preview1` 3 関数の import を持つ。bench は全 import を no-op stub で与えて instantiate する。判定は instantiate 成功 + export>0 (`f0` は無い)。実行 (`fle_init` 等) は行っていない。download→compile→instantiate のみの計測。
- **計測**: `node tools/perf/delivery/chunked_bench.mjs --wasm tools/flelift/work/lift/flel.wasm --reps 3 --mbps 0,100 --out tools/perf/work/chunked_real_head.json`。測定 commit `82c30421` (fetchCompile check の f0 判定修正を含む HEAD。bench 本体は `4d3a32f6` から不変)。headless Chrome 154.0.8037.97、node v22.23.3、4 コア、loadavg 0.22〜0.75 (測定中 0.55〜0.75)。`flel.wasm` は `tools/flelift/fle_lift.sh` (`FL_WIN64_DIR` = fl-win64 展開先、emsdk 6.0.12) で再生成 (27,639,303 B)。
- **指摘への対応 (#1387 レビュー)**: 合成 wasm 用の `f0 === 42` 判定を実 wasm に流用していた箇所を直した。実 wasm は `f0` を持たないので `f0=null` を出力し、判定は「instantiate 成功 + exports > 0」。`f0` があるときだけ `=== 42` を判定する。function 以外の import は stub せず明示的に throw する (黙って LinkError にしない)。

| 帯域 | 方式 | 中央値 | min–max |
|---|---|--:|--:|
| 無制限 (loopback) | streaming | 172.3 | 157.7–276.2 |
| 無制限 (loopback) | bytes | 158.8 | 144.6–166.6 |
| 100 Mbps/接続 | streaming | 1448.2 | 1437.3–1451.5 |
| 100 Mbps/接続 | bytes | 1456.2 | 1450.7–1472.4 |

- 結果: **12/12 PASS** (全件 instantiate 成功、`f0=null`)。
- `fetchCompile` 経路 (src の本物・受入条件 1): `bun tools/perf/delivery/fetch_compile_chunked_check.ts tools/perf/work/chunked/site big.b92b83ae3549.wasm` → streaming 199.2 ms (f0=null, exports=24) / bytes 186.7 ms (f0=null, exports=24)、progress 4 回、PASS (測定 commit `82c30421` の作業ツリー)。
- 測定 commit `82c30421` から HEAD (`11bc17b1`) までの差分: `deploy/client/chunked.test.mjs` のみ (テスト引数 `--skip-release-guard` の追加。測定経路の `chunked.mjs`・bench・fetch check・`loader_boot.ts` は不変)。
- 今回の再測定 (新 HEAD) では 100 Mbps/接続 が 1448 ms (旧 測定 1422 ms と同水準)。按分値 (合成 1458 ms × 26.4/32.6 ≈ 1181 ms) との差は依然として約 23% で、原因は未切り分け (part 数 3→2、wasm の中身の差などが候補。確定には別測定が要る)。
- 注記: 帯域制限は接続ごと (§2 と同じ)。
- 残り (未解決): 本番 runtime の manifest 経路は未接続 → #1166 `[PERF-P18]`。
