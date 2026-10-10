# tools/runtime/REPORT.md — D runtime-arch (ブラウザ実行基盤)

## 結論 (先出し)
1. **メモリモデル = wasm32 + LVA 敷設**。Memory64 は退避路 (同一 lifted IR を `p:64` datalayout に書換えるだけで wasm64 ビルドが通り、**出力ハッシュが wasm32 と完全一致** `824c6c48` を実証)。Memory64 の実コード性能差は無し (OTT lifted: 0.925×)。ただし **Memory 個数上限が wasm32 124–125 / wasm64 61–62** と判明 → 「プラグイン DLL 1 本 = 1 Memory」は同時ロード <100 に抑える必要あり。
2. **ブロッキング GetMessage = `Atomics.wait` + SAB ring (Vyukov MPSC)**。pthread ビルドでは同一 ABI を共有 wasm メモリに置いて `memory.atomic.wait32` で直接ブロック。**Asyncify 不採用** (M11 lifted で +39〜40% サイズ)。JSPI は async→sync 橋渡し専用の副次手段。4 方式すべてネスト(モーダル)ポンプ動作確認済み。
3. **ブート = Worker 内 `fetch → compileStreaming` + ハッシュ名 immutable の HTTP キャッシュ**。**IndexedDB への `WebAssembly.Module` 保存は Chrome 154 で DataCloneError (不可)**。compile は lazy で ≈1.5 ms/MiB、100MiB 級でも compile は問題でなく**ダウンロードが支配** (brotli q11 実測 3.31×)。
4. 骨格を実装し **M1/M6/M10/M11 の既存 wasm を headless Chrome の Worker で実行 → 元 emcc glue(node) の参照値とビット一致**。1 コマンド: `pnpm runtime:e2e` (`--prod` で本番バンドル)。

詳細・根拠・全実測表は `DESIGN.md`。

## 成果物
| 区分 | パス |
|---|---|
| 設計 | `tools/runtime/DESIGN.md`, 本 `REPORT.md` |
| ランタイム実装 | `src/runtime/{mem,worker,worker_pump,worker_protocol,worker_drivers,boot,boot_ui,loader_boot,imports_env}.ts`、`loader.ts` に `instantiateCompiled` 追加 (既存 API 不変)、`src/index.ts` に `?runtime=` フック、`vite.config.ts` (`/wasm/*` 配信・Worker ES 形式・watch 除外)、`package.json` scripts |
| e2e | `tools/runtime/e2e.mjs` (`stage_wasm.mjs` が M1/M6/M10/M11 の wasm を hash 名で stage し `manifest.json` 生成) |
| 実機プローブ | `probe/run_features.mjs` (機能マトリクス), `probe/run_memcount.mjs` (Memory 個数上限) |
| ベンチ | `bench/build_ott_variants.sh` + `run_bench.mjs` (wasm32/64), `bench/asyncify_cost.mjs`, `bench/make_big_wasm.py` + `run_compile_bench.mjs` |
| spike | `spike/build_pump_spike.sh` + `run_pump_spike.mjs` (ポンプ 4 方式), `spike/run_pthread_test.mjs` (emcc pthread) |
| CDP クライアント | `lib/chrome.mjs` (依存ゼロ、puppeteer 不要), `lib/serve.mjs` |

## 実測サマリ (Chrome 154.0.8037.97 headless)
**e2e** (`pnpm runtime:e2e`, ALL OK, dev / `--prod` / `--cache=cacheapi --compile=bytes` の 3 経路):
| id | wasm | fetch+compile | run | 参照一致 |
|---|---|---|---|---|
| m1-hello | 14 KiB | 5 ms | 2 ms | stdout `hello from e2e, answer=42` |
| m6-ott | 0.80 MiB | 10 ms | 162 ms | hash `fb31ca9a` |
| m10-ott | 0.80 MiB | 8 ms | 69 ms | hash `824c6c48` / `cdd4ee04` (param 応答) |
| m11-boot | 5.77 MiB | 28 ms | 23 ms | `{m11_dllmain_done:1}` stage=1 (M11 担当が実装中の現状と一致) |
| pump 自己検証 | — | — | — | 2000 件欠落 0 / WM_TIMER 発火 / p50 **4.9–10 µs** p99 0.28 ms (静かな機; 高負荷時は p50 0.9–1.6 ms / p99 ~5 ms) |

**Memory64 vs wasm32** (Worker 内, median/min): seq 1.21/1.06, rand RMW 1.11/1.16, pointer chase 1.08/0.95, hot loop 1.04/1.06, OTT lifted DSP **0.925/0.83**。非インライン呼出 microbench は 0.57–12× と方向が反転する外れ値 (V8 インライン判断の揺れ)。負荷 load 9–20 の共有 VM 実測ゆえ静かな機で再測推奨。

**ポンプ 4 方式** (50,000 件バースト): ring(Atomics/native) 25.7–118 万 ev/s、postMessage(JSPI/Asyncify) 8.4–10.7 万 ev/s。RTT は二峰性 (5–15 / 80–110 µs) で方式差なし。**Asyncify**: M10 +7.1% (実行速度 0.998×) / M11 **+39.4〜40.0%** (4.47→6.23〜6.25 MB)。

**compile スケール** (M11×1–16 合成, 5.8→52 MiB): streaming 33→215 ms、bytes compile 10→83 ms、instantiate(301MiB) 10–17 ms、初回呼出 ~5 ms。再訪は `transferSize=0` (HTTP cache 命中)、コードキャッシュによる追加短縮は観測されず。

**pthread (emcc)**: 4×1M atomic add = 4,000,000 一致、spawn+join 31.8 ms、cond RTT 19 µs、`instantiateWasm` による Module 注入と worker 共有 OK。

**その他の確定事実**: AudioWorklet 内で `Atomics.wait` は TypeError (消費専用)、Worker 内 OffscreenCanvas(WebGL2/2D/rAF)・OPFS sync handle・nested Worker すべて可、`Memory.toResizableBuffer` あり、JSPI あり、shared wasm32 4GiB / memory64 8GiB grow 可。

## 設計上の要点 (実装済み)
- **imports は introspection で組む** (`Module.imports()`): 実装 provider → 無ければ `createImportForwarder` (fail-fast)。Win32 / `function_xxxx` は呼ばれた瞬間に throw。
- **EM_JS / EM_ASM を glue 無しで解決** (`__em_js__NAME` export の文字列を遅延 `new Function`)。これにより emcc glue 非依存の自前ローダで M11 の `m11_throw_dllmain_done` が動く。
- 進捗は `Response.clone()` で並行消費し、`compileStreaming` には元 Response を渡す (code cache 連携を壊さない)。
- `MemoryView` は grow による buffer 差替えを自動追従。wasm64 は BigInt 引数 (`n()`) と iov 幅 (ptrSize) を吸収。

## 未解決・ブロッカー
1. **Firefox / Safari 未測定** (環境に Chrome のみ): memory64・JSPI・threads・OffscreenCanvas の互換マトリクスは Chrome のみ。
2. **実 FL サイズ wasm が未生成** → 合成 (≤52 MiB) からの外挿 (推定)。実測は FLEngine lift 完成後。
3. 本番 pthread ビルド (shim MT + emcc glue + 本ローダ) の boot e2e は未実施 (spike で個別要素は実証)。
4. ヘッドレス WebGL2 は SwiftShader。実 GPU/OffscreenCanvas の fps は未測定。
5. Memory 個数上限 ~125 とプラグイン=1 Memory 方針の整合 (遅延ロード/統合が必要)。
6. Memory64 性能の定量は共有 VM 上でノイズ大。

## ユーザ依頼事項
- 必須の依頼なし (ブロッカーなし)。任意: Firefox / Safari の実機があれば、`lib/serve.mjs` (COOP/COEP 付き) で `tools/runtime/probe/` を配信し `features.html` を開いて `window.__result` を共有 (RT-9 の入力になる)。

## 下流チケット案
- **RT-1 (shim 担当)** user32 ポンプ shim (C): `GetMessageW/PeekMessageW/DispatchMessageW/TranslateMessage/PostMessageW/PostThreadMessageW/SetTimer/KillTimer/InvalidateRect/PostQuitMessage/MsgWaitForMultipleObjects` を `worker_pump.ts` の RING ABI で実装 (`spike/pump_spike.c` の NATIVE 版が雛形)。wParam/lParam は Win64 `MSG` (48B) レイアウトに変換。
- **RT-2 (FL 本番ビルド)** emcc フラグ確定: `-pthread -sPROXY_TO_PTHREAD -sPTHREAD_POOL_SIZE=N -sGROWABLE_ARRAYBUFFERS=2 -sMODULARIZE -sEXPORT_ES6 -sENVIRONMENT=web,worker`、`boot.ts` に `instantiateWasm` 注入経路、brotli 事前圧縮 + hash 名出力。
- **RT-3 (GUI)** `transferControlToOffscreen` → fl-runtime Worker 内描画、入力イベントを `PumpRing.push` へ (マウス移動 coalesce は producer 側)。`src/index.ts` の `?runtime=` フックと共存。
- **RT-4 (audio)** worklet は ring 消費専用 (Atomics.wait 不可)。sample clock マスターと underrun 無音ポリシー、ring ABI 共有。
- **RT-5 (VFS)** OPFS `createSyncAccessHandle` を第一候補、async 必須経路は JSPI または補助 Worker sync-RPC。
- **RT-6 (plugin loader)** 同時ロード DLL <100 の予算管理 (遅延ロード/アンロード時の参照解放/小プラグイン統合) と 100+ ロードの負荷試験。
- **RT-7 (deploy / M12)** R2: COOP/COEP/CORP 注入、wasm は同一オリジン、`Content-Encoding: br`、hash 名 immutable、`manifest.json` は no-cache。
- **RT-8 (CI)** lift 成果物ごとに wasm32/wasm64 両ビルドを回し 4GiB 超仮定を早期検出 (`bench/build_ott_variants.sh` が雛形)。
- **RT-9 (互換)** Firefox/Safari マトリクス取得と JSPI/memory64 の機能検出フォールバック設計。
- **RT-10 (soak)** 実 FLEngine lift で download→compile→instantiate→初回フレームの総時間と tier-up 影響を計測。

## 再現手順
```sh
pnpm runtime:e2e                       # 1 コマンド e2e (stage → vite → headless Chrome → 参照突合 → pump 自己検証)
pnpm runtime:e2e:prod                  # 本番バンドル版
node tools/runtime/probe/run_features.mjs && node tools/runtime/probe/run_memcount.mjs
bash tools/runtime/bench/build_ott_variants.sh && bash tools/runtime/bench/build_membench.sh && node tools/runtime/bench/run_bench.mjs
bash tools/runtime/bench/build_asyncify.sh && node tools/runtime/bench/asyncify_cost.mjs
bash tools/runtime/spike/build_pump_spike.sh && node tools/runtime/spike/run_pump_spike.mjs
node tools/runtime/spike/run_pthread_test.mjs
python3 tools/runtime/bench/make_big_wasm.py <in.wasm> <out.wasm> <K> && node tools/runtime/bench/run_compile_bench.mjs
```
(PATH に node が必要: `export PATH=$HOME/.local/share/pnpm/bin:$PATH`)
