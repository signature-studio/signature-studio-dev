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

**Memory64 vs wasm32** (Worker 内, median/min): seq 1.21/1.06, rand RMW 1.11/1.16, pointer chase 1.08/0.95, hot loop 1.04/1.06, OTT lifted DSP **0.925/0.83**。非インライン呼出 microbench は 0.57–12× と方向が反転する外れ値 (V8 インライン判断の揺れ)。負荷 load 9–20 の共有 VM 実測ゆえ静かな機で再測推奨。**検収再測 (load 11–22)**: seq 0.97(med)/1.01(min)、rand RMW 1.22/1.11、pointer chase 0.93/0.96、hot loop 1.03/0.98、OTT lifted 0.85–0.95、hash 一致。すなわち個別比は ±20% で揺れ (seq は 0.97〜1.21)、結論「性能差は決定要因でない」のみ再現性あり。個別の倍率は目安として扱うこと。

**ポンプ 4 方式** (50,000 件バースト): ring(Atomics/native) 25.7–118 万 ev/s、postMessage(JSPI/Asyncify) 8.4–10.7 万 ev/s。RTT は二峰性 (5–15 / 80–110 µs) で方式差なし。**Asyncify**: M10 +7.1% (実行速度 0.998×) / M11 **+39.4〜40.0%** (4.47→6.23〜6.25 MB)。

**compile スケール** (M11×1–16 合成, 5.8→52 MiB): streaming 33→215 ms、bytes compile 10→83 ms、instantiate(301MiB) 10–17 ms、初回呼出 ~5 ms。再訪は `transferSize=0` (HTTP cache 命中)、コードキャッシュによる追加短縮は観測されず。

**pthread (emcc)**: 4×1M atomic add = 4,000,000 一致、spawn+join 31.8 ms、cond RTT 19 µs、`instantiateWasm` による Module 注入と worker 共有 OK。

**RT-2 本番 pthread ビルドの boot e2e (#120)** — 既知類型との関係: 該当なし (lift 無し・shim C + emcc のみ)。検証起点 HEAD `bfd0ea0` (コミット済み内容で実行)、emcc 6.0.12 / Chrome 154.0.8037.97 / 4 コア runner。
- **確定フラグ** (`prod/flags.sh`): `-pthread -sPROXY_TO_PTHREAD -sPTHREAD_POOL_SIZE=12 -sALLOW_MEMORY_GROWTH=1 -sGROWABLE_ARRAYBUFFERS=2 -sMODULARIZE -sEXPORT_ES6 -sENVIRONMENT=web,worker -sEXIT_RUNTIME=1 -sERROR_ON_UNDEFINED_SYMBOLS=1`。`-O1`、shim は `tools/shim/src/*.c`。
- **ビルド**: `bash tools/runtime/prod/build_pthread.sh` (1.8 s、wasm 65,806 B / glue 156,753 B)。`/opt/emsdk` のキャッシュが読み取り専用の環境では `EM_CACHE` を `$RUNNER_TEMP/em_cache` へ複製して自動回避 (なければ `PermissionError: .../cache/js_output.lock`)。
- **経路**: Worker 内 `fetch → compileStreaming` で得た Module を glue の `instantiateWasm` フックへ注入 (`createEmscriptenPthreadModule`, `loader_boot.ts`)。glue は同じ Module を pthread Worker へ配る。`mt-boot` ドライバが 8 項目を検証: crossOriginIsolated / 注入が 1 回だけ使われた / メモリが shared+growable SAB / main が pthread 上で動作 (PROXY_TO_PTHREAD) / shim MT 自己テスト ALL PASS / 4 スレッド×1M atomic add = 4,000,000 / 192 MiB malloc(grow) を別 pthread から読めた / exit code 0。
- **配信**: `stage_wasm.mjs` が wasm と glue を `mt-boot.<sha256 先頭 12 桁>.{wasm,mjs}` で配置し、glue 内の自己名・wasm 名参照を hash 名へ置換 (pthread Worker 起動が hash 名 glue を指す)。`.br` (brotli q11) を隣に生成し、dev/preview サーバが `Accept-Encoding: br` に `Content-Encoding: br` で応答。wasm 65,806 → 22,040 B、glue 156,753 → 35,498 B。e2e は `decodedBodySize == manifest.bytes` かつ `transferSize(22,340) < 展開後` を検査。
- **e2e 実測** (`bfd0ea0` で `pnpm runtime:e2e` 系を各 3 回、各回ビルド込みの全体 3.22〜3.36 s、load average 1.09〜1.33、直列 1 本): dev / `--prod` / `--cache=cacheapi --compile=bytes` すべて **FAIL 0 / OK 10 / ALL OK** (9/9 回)。mt-boot の fetch+compile 5.0〜13.5 ms、run-to-exit 258.8〜308.8 ms、total 264.5〜314.2 ms。pump p50 0.0051 ms / p99 0.9802 ms (n=2000、dev、load 1.88)。OK 10 の内訳は mt-boot 関連 4 + crossOriginIsolated + state の計 6 + pump 4 (M1/M6/M10/M11 は素材無しで 0)。
- **ネガティブコントロール** (`node tools/runtime/e2e.mjs --neg` = カウンタを非 atomic にした版): counter=1,358,511 / 1,683,852 (2 回) で `4 thread x 1M` チェックが FAIL、exit 1。通常実行へ復帰して ALL OK (成果物が混入しない)。
- **踏んだ落とし穴**: glue (`.mjs`) は pthread Worker のスクリプトにもなる。`vite preview` では独自ミドルウェアが `preview.headers` より先に応答するため、`COEP: require-corp` を付けないと `--prod` だけ Worker がロード失敗 (`Uncaught [object Event]`)。`wasmAssets` が COOP/COEP/CORP を明示付与するよう修正。本番 R2 でも glue に COEP/CORP を付ける必要がある (RT-7 の入力)。
- **範囲外 (未検証)**: 実 FLEngine の lift 成果物ではなく **shim MT の自己テスト main** での boot。この run には `work-m11` / `work-liftdiff` が無く、既存 M1/M6/M10/M11 の e2e は **stage 時に skip** (回帰比較は未実施 = 下記未解決)。Firefox/Safari 未測定。

**RT-9 Firefox 機能マトリクス (#127)** — 検証起点 HEAD `5984d46` (コミット済み内容で実行)。Firefox 157.0 headless (geckodriver 0.37.1) と Chromium 154.0.8037.0 headless を同一 runner (4 コア、load average 0.95〜1.03) で `features.html` に流した実測。**Safari は未測定** (runner は Linux でプローブ可能な WebKit が無い: Playwright WebKit は gtk4/gstreamer 等のホスト依存ライブラリ欠落で導入不可)。再現: `node tools/runtime/probe/run_features_firefox.mjs` (→ `work/features_result_firefox.json`、1 回 59.7〜63.1 s、3 回実行)。
- **Firefox と Chromium で同値**: wasm 機能 validate は simd / relaxed_simd / threads_atomics / bulk_memory / reference_types / multivalue / tail_call / extended_const / **memory64** / multi_memory / eh_legacy / eh_exnref / gc / shared_everything がともに true。`WebAssembly.promising` / `Suspending` (JSPI) は function、`Memory({address:"i64"})` 生成可、`Memory.toResizableBuffer` あり、`JSTag` あり。crossOriginIsolated=true、SAB・`Atomics.waitAsync` あり、メインスレッド `Atomics.wait` は TypeError、Worker 内は timed-out (=許可)。nested Worker・OffscreenCanvas 2D・worker rAF・OPFS sync handle・Worker 内 IDB 可。4 worker×1M atomic add=4,000,000 一致 (Firefox 86.5〜96 ms / Chromium 146 ms)。`WebAssembly.Module` の IDB 保存は両者とも DataCloneError、`structuredClone` と Cache API は可。shared wasm32 4GiB・非 shared memory64 8GiB grow・shared memory64 max 16GiB 可。
- **差分**: Firefox は WebGPU・File System Access・WebHID が undefined。wide_arithmetic は Firefox のみ true。`ArrayBuffer(8GiB)` は Firefox 可・Chromium 失敗。cross-worker `memory.atomic.wait` の戻り値は Firefox 1 / Chromium 0 (テストが notify をポーリングする構造上、wait が先に入るか値不一致で即返るかの差と推測。原因は未検証。Chromium 側の `woken:0` も `woken:1` も `wait` からの復帰ではある)。
- **Firefox の注意**: 非 shared memory64 を 256MiB 刻みで 8GiB まで grow する処理が **35.0〜37.6 s** (Chromium 0.5 ms)。shared memory64 の同処理は 38〜166 ms (3 回でばらつきあり)。原因は未調査 (ページ commit/zero-fill 方式の差と推測するが未検証)。
- **headless では判定不能**: `AudioContext` 経路 (`resume()` と AudioWorklet) が Firefox headless で 20 s 内に完了せず (step timeout)、Worker 内 WebGL2 は null。runner に音声デバイス・GPU が無い影響の可能性が高く、**Firefox の AudioWorklet / WebGL2 可否は未確定** (実機が必要)。
- **変更**: `features.js` に各 step 20 s の hang ガードと `window.__partial/__step` を追加 (旧版は 1 step の hang で `__result` が出ず全体が止まる)。Chrome 結果への影響なし (`run_features.mjs` で Chromium 完走を確認)。

**その他の確定事実**: AudioWorklet 内で `Atomics.wait` は TypeError (消費専用)、Worker 内 OffscreenCanvas(WebGL2/2D/rAF)・OPFS sync handle・nested Worker すべて可、`Memory.toResizableBuffer` あり、JSPI あり、shared wasm32 4GiB / memory64 8GiB grow 可。

## 設計上の要点 (実装済み)
- **imports は introspection で組む** (`Module.imports()`): 実装 provider → 無ければ `createImportForwarder` (fail-fast)。Win32 / `function_xxxx` は呼ばれた瞬間に throw。
- **EM_JS / EM_ASM を glue 無しで解決** (`__em_js__NAME` export の文字列を遅延 `new Function`)。これにより emcc glue 非依存の自前ローダで M11 の `m11_throw_dllmain_done` が動く。
- 進捗は `Response.clone()` で並行消費し、`compileStreaming` には元 Response を渡す (code cache 連携を壊さない)。
- `MemoryView` は grow による buffer 差替えを自動追従。wasm64 は BigInt 引数 (`n()`) と iov 幅 (ptrSize) を吸収。

## 未解決・ブロッカー
1. **Safari 未測定** (Firefox 157 headless は #127 で測定済み)。Safari 実機で `window.__result` の共有が必要 (起票先: #127)。Firefox の AudioWorklet / Worker WebGL2 も headless では判定不能 (実機が必要)。
2. **実 FL サイズ wasm が未生成** → 合成 (≤52 MiB) からの外挿 (推定)。実測は FLEngine lift 完成後。
3. 本番 pthread ビルドの boot e2e は **shim MT 自己テスト main で実証済み (#120)**。残: 実 FLEngine lift を同フラグでビルドした boot (起票先: #227 ICALL-1 / RT-10)。
3b. この run は `work-m11` 無しで M1/M6/M10/M11 の既存 e2e が skip された。`oc_artifacts: fl-win64 work-m11` で再実行し、本変更後も 4 本が ALL OK のままか確認 (起票先: #120 に再検証コメント / PM 判断)。
3c. 本番 R2 配信では glue (.mjs) にも COOP/COEP/CORP を付ける必要 (起票先: RT-7)。
4. ヘッドレス WebGL2 は SwiftShader。実 GPU/OffscreenCanvas の fps は未測定。
5. Memory 個数上限 ~125 とプラグイン=1 Memory 方針の整合 (遅延ロード/統合が必要)。
6. Memory64 性能の定量は共有 VM 上でノイズ大。

## ユーザ依頼事項
- 必須の依頼なし (ブロッカーなし)。任意: **Safari** (と Firefox の音声/GPU あり実機) があれば、`lib/serve.mjs` (COOP/COEP 付き) で `tools/runtime/probe/` を配信し `features.html` を開いて `window.__result` を共有 (RT-9 の入力になる)。

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

## 他担当・既存 e2e との整合 (検収時点)
- `pnpm typecheck` / `pnpm build` 通過。B (`gui*.ts`) / C (`audio*.ts`) と import・設定の衝突なし。
- `bash tools/e2e/run.sh` 既定 (preview+edge-sim, agent-browser) は PASS 15 / FAIL 0 / SKIP 3。`--driver both --targets preview,edge-sim,dev` で **PASS 44 / FAIL 0 / SKIP 10** (D の `src/index.ts` / `vite.config.ts` 変更後も維持)。
- **`window.__webstudio` 契約 (CAB-64) は未実装**: `src/` に実装なし、e2e の `fl-boot` は SKIP (実 FL 未統合)。実装は実 FL 起動後 (RT 下流)。`?runtime=` パネルは別 UI で、契約とは独立。

## 再現手順
```sh
pnpm runtime:e2e                       # 1 コマンド e2e (stage → vite → headless Chrome → 参照突合 → pump 自己検証)
pnpm runtime:e2e:prod                  # 本番バンドル版
node tools/runtime/probe/run_features.mjs && node tools/runtime/probe/run_memcount.mjs
node tools/runtime/probe/run_features_firefox.mjs   # RT-9 (FIREFOX_BIN / GECKODRIVER_BIN で上書き可、CHROME_BIN=chromium で Chrome 側)
bash tools/runtime/bench/build_ott_variants.sh && bash tools/runtime/bench/build_membench.sh && node tools/runtime/bench/run_bench.mjs
bash tools/runtime/bench/build_asyncify.sh && node tools/runtime/bench/asyncify_cost.mjs
bash tools/runtime/spike/build_pump_spike.sh && node tools/runtime/spike/run_pump_spike.mjs
node tools/runtime/spike/run_pthread_test.mjs
bash tools/runtime/prod/build_pthread.sh && pnpm runtime:e2e      # RT-2 (e2e が毎回ビルド。--neg でネガティブコントロール、EMSDK_ENV で emsdk 指定)
python3 tools/runtime/bench/make_big_wasm.py <in.wasm> <out.wasm> <K> && node tools/runtime/bench/run_compile_bench.mjs
```
(PATH に node が必要: `export PATH=$HOME/.local/share/pnpm/bin:$PATH`)
