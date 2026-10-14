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
| ベンチ | `bench/build_ott_variants.sh` + `run_bench.mjs` (wasm32/64。※ emcc 6.0.12 では `--max-memory` と `ALLOW_MEMORY_GROWTH=0` が衝突し wasm-ld エラー。ビルドは `ci/wasm64_check.sh` が代替), `bench/asyncify_cost.mjs`, `bench/make_big_wasm.py` + `run_compile_bench.mjs` |
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

**RT-3 GUI 結線 (#121)** — 既知類型との関係: 該当なし (lift 無し・TS のみ)。検証起点 HEAD `07fd3e2` (コミット済み内容)、Chrome 154.0.8037.97 / 4 コア runner / 素材なし (`fl-win64` 未展開・emsdk なし)。
- **実装**: `gui_input.ts` (`PumpInput`: DOM → WM_* → `PumpRing.push`、**pointermove coalesce は producer 側** = rAF で最新 1 件のみ、他イベント直前に保留 move を吐いて順序保存)、`gui_selftest.ts` (fl-runtime Worker: OffscreenCanvas + ring consumer)、`gui_boot.ts` (main 側: `transferControlToOffscreen` + `/?gui=selftest[&present=yield|blocking]` / `/?gui=render-selftest`)、`gui_renderer.ts` (`gui_worker.ts` から描画本体を切り出し = 専用描画 Worker と共用)。`?runtime=` とは独立 (`index.ts` で別 mount)。
- **e2e** `pnpm runtime:gui-e2e` (`--prod` / `--neg` / `--present=`): CDP 実入力 → DOM → PumpInput → ring → Worker → OffscreenCanvas → `Page.captureScreenshot` の画素で検証 (条件待ち、固定 sleep なし)。dev 3 回 + prod 1 回、各 **FAIL 0 / OK 22 / ALL OK** (全体 4.13 / 3.49 / 3.59 / 3.60 s、load average 0.13〜1.71)。入力→画素反映 28〜81 ms (yield)。500 pointermove → ring へ 1 件 (coalesce 499)。ring dropped 0 / rejected 0。
- **ネガティブコントロール** (`--neg` = 入力リスナーを外す): 画素・Worker 受信チェック 7 件が FAIL、exit 1。
- **発見 (設計に影響)**: Worker が `getMessage` (`Atomics.wait`) に居座ったまま描くと OffscreenCanvas は画面へ commit されない (Chrome 154 は `OffscreenCanvas.commit()` 無し; 1500 ms 待っても画素不変、ループを抜けて 1 タスク終了後 30 ms で出現)。→ **ブロッキング UI スレッドと描画は分離**する (DESIGN §2.6)。e2e が「commit されない」制約自体を固定する。
- **回帰**: `pnpm typecheck` OK、`tools/gui` の tsc (`gui_worker` 分割後) OK、`gui_worker` 経由の描画は合成 GuiShared で BGRA→RGBA 画素一致 (e2e `[render]` 3 件)、既存 `pnpm runtime:e2e` の pump 4 項目 OK (1.62 s、M1/M6/M10/M11/mt-boot は素材・emsdk 無しで skip)。

**RT-9 Firefox 機能マトリクス (#127)** — 検証起点 HEAD `5984d46` (コミット済み内容で実行)。Firefox 157.0 headless (geckodriver 0.37.1) と Chromium 154.0.8037.0 headless を同一 runner (4 コア、load average 0.95〜1.03) で `features.html` に流した実測。**Safari は未測定** (runner は Linux でプローブ可能な WebKit が無い: Playwright WebKit は gtk4/gstreamer 等のホスト依存ライブラリ欠落で導入不可)。再現: `node tools/runtime/probe/run_features_firefox.mjs` (→ `work/features_result_firefox.json`、1 回 59.7〜63.1 s、3 回実行)。
- **Firefox と Chromium で同値**: wasm 機能 validate は simd / relaxed_simd / threads_atomics / bulk_memory / reference_types / multivalue / tail_call / extended_const / **memory64** / multi_memory / eh_legacy / eh_exnref / gc / shared_everything がともに true。`WebAssembly.promising` / `Suspending` (JSPI) は function、`Memory({address:"i64"})` 生成可、`Memory.toResizableBuffer` あり、`JSTag` あり。crossOriginIsolated=true、SAB・`Atomics.waitAsync` あり、メインスレッド `Atomics.wait` は TypeError、Worker 内は timed-out (=許可)。nested Worker・OffscreenCanvas 2D・worker rAF・OPFS sync handle・Worker 内 IDB 可。4 worker×1M atomic add=4,000,000 一致 (Firefox 86.5〜96 ms / Chromium 146 ms)。`WebAssembly.Module` の IDB 保存は両者とも DataCloneError、`structuredClone` と Cache API は可。shared wasm32 4GiB・非 shared memory64 8GiB grow・shared memory64 max 16GiB 可。
- **差分**: Firefox は WebGPU・File System Access・WebHID が undefined。wide_arithmetic は Firefox のみ true。`ArrayBuffer(8GiB)` は Firefox 可・Chromium 失敗。cross-worker `memory.atomic.wait` の戻り値は Firefox 1 / Chromium 0 (テストが notify をポーリングする構造上、wait が先に入るか値不一致で即返るかの差と推測。原因は未検証。Chromium 側の `woken:0` も `woken:1` も `wait` からの復帰ではある)。
- **Firefox の注意**: 非 shared memory64 を 256MiB 刻みで 8GiB まで grow する処理が **35.0〜37.6 s** (Chromium 0.5 ms)。shared memory64 の同処理は 38〜166 ms (3 回でばらつきあり)。原因は未調査 (ページ commit/zero-fill 方式の差と推測するが未検証)。
- **headless では判定不能**: `AudioContext` 経路 (`resume()` と AudioWorklet) が Firefox headless で 20 s 内に完了せず (step timeout)、Worker 内 WebGL2 は null。runner に音声デバイス・GPU が無い影響の可能性が高く、**Firefox の AudioWorklet / WebGL2 可否は未確定** (実機が必要)。
- **変更**: `features.js` に各 step 20 s の hang ガードと `window.__partial/__step` を追加 (旧版は 1 step の hang で `__result` が出ず全体が止まる)。Chrome 結果への影響なし (`run_features.mjs` で Chromium 完走を確認)。

**RT-10 実 FLEngine lift の起動時間・tier-up・soak (#128)** — 実 x64c lift (boot 連鎖) の wasm を Chrome Worker で計測 (サイズ・圧縮・起動・帯域・tier-up・boot ループ soak)。**初回フレームと実 FL の soak は未測** (boot が unit 209/942 で停止)。数値・再現: [`rt10/REPORT.md`](rt10/REPORT.md)。

**その他の確定事実**: AudioWorklet 内で `Atomics.wait` は TypeError (消費専用)、Worker 内 OffscreenCanvas(WebGL2/2D/rAF)・OPFS sync handle・nested Worker すべて可、`Memory.toResizableBuffer` あり、JSPI あり、shared wasm32 4GiB / memory64 8GiB grow 可。

## 設計上の要点 (実装済み)
- **imports は introspection で組む** (`Module.imports()`): 実装 provider → 無ければ `createImportForwarder` (fail-fast)。Win32 / `function_xxxx` は呼ばれた瞬間に throw。
- **EM_JS / EM_ASM を glue 無しで解決** (`__em_js__NAME` export の文字列を遅延 `new Function`)。これにより emcc glue 非依存の自前ローダで M11 の `m11_throw_dllmain_done` が動く。
- 進捗は `Response.clone()` で並行消費し、`compileStreaming` には元 Response を渡す (code cache 連携を壊さない)。
- `MemoryView` は grow による buffer 差替えを自動追従。wasm64 は BigInt 引数 (`n()`) と iov 幅 (ptrSize) を吸収。

## 未解決・ブロッカー
0. **RT-3 (#121)**: (a) 実 FLEngine / `tools/gui/e2e.sh` (emsdk+RetDec 要) 経由の実 shim での入力往復は未実施 (本 run は素材・emsdk 無し)。(b) **入力経路が 2 本** (GuiShared 入力リング `gui.ts` と PumpRing): どちらを正とするかは GUI-3 #174 / GUI-11 #32 で決定 (DESIGN §2.6)。(c) index.html の `#screen` は `setupCanvas` が 2d context 取得済みで `transferControlToOffscreen` 不可 → FL 結合時に寄せる。(d) Firefox/Safari の OffscreenCanvas commit 挙動は未測定 (RT-9)。
1. **Safari 未測定** (Firefox 157 headless は #127 で測定済み)。Safari 実機で `window.__result` の共有が必要 (起票先: #127)。Firefox の AudioWorklet / Worker WebGL2 も headless では判定不能 (実機が必要)。
2. **実 FL サイズ wasm**: x64c boot 連鎖で実測済み (RT-10 #128, 数値は `rt10/REPORT.md`)。残: boot が初回フレームに届いた後の総時間と実 FL の soak (起票先: #541 [RT-12])。
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
- **RT-6 (plugin loader)** 同時ロード DLL <100 の予算管理 (遅延ロード/アンロード時の参照解放/小プラグイン統合) と 100+ ロードの負荷試験。**予算 + LRU プール + 負荷試験は実装済み** (下記「RT-6 実測」)。実プラグイン loader への接続は完了 (「RT-6 実 loader 接続」節)。未了: SAB 共有カウンタの既定経路への配線・小プラグイン同居 (Refs #125)。
- **RT-7 (deploy / M12)** R2: COOP/COEP/CORP 注入、wasm は同一オリジン、`Content-Encoding: br`、hash 名 immutable、`manifest.json` は no-cache。
- **RT-8 (CI)** lift 成果物ごとに wasm32/wasm64 両ビルドを回し 4GiB 超仮定を早期検出。**OTT 分は実装済み** (`ci/wasm64_check.sh`、下記「RT-8 実測」)。未了: (a) M11 boot closure 等 OTT 以外の target (`ci/targets/<name>.sh` を足す方式)、(b) GitHub Actions への常設 (素材が R2 の work-* のため workflow 化には素材取得の設計が要る)。
- **RT-9 (互換)** Firefox/Safari マトリクス取得と JSPI/memory64 の機能検出フォールバック設計。
- **RT-10 (soak)** 実 FLEngine lift で download→compile→instantiate→boot の総時間と tier-up 影響を計測 (**実施済み・初回フレームは未達**: `rt10/REPORT.md`)。

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

## RT-8 実測 (CI: wasm32/wasm64 同一 IR 両ビルド照合)
`bash tools/runtime/ci/wasm64_check.sh [--neg] [target ...]` (既定 target `ott`)。`ci/targets/<name>.sh` が入力 IR・ソース・フラグ・ドライバを定義。wasm64 側は IR の `target datalayout` を `p:64` (`f128:64` 付き) に sed 書換え、両者を並列に同一フラグ (-O2) でビルドし、node (`EMSDK_NODE`, v24。Memory64 は v22 では compile 不可) で同一入力を駆動して FNV-1a 出力ハッシュを比較。判定: wasm32/wasm64 不一致・期待ハッシュ (`824c6c48,cdd4ee04`) 不一致・memory section の memory64 flag が期待と逆、のいずれかで exit 1。emsdk は `EMSDK_ENV` (既定 `/opt/emsdk/emsdk_env.sh`)、repo パスは `tools/shared/env.sh` の `REPO_ROOT`。
- 入力 IR は `bash tools/m10/m10_build.sh` で再生成 (work-m6-ott 素材のみ。`ott_shift3b.ll` 在中のため retdec 不要)。再生成 `ott_m10.ll` の sha256 は素材スナップショットと一致 (`989cf685…`)、`m10_build.sh` 4.1 s。
- 実測 (GitHub runner 4 vCPU, emcc 6.0.12, load average 0.3–0.7): ビルド 2–3 s (32/64 並列)、`ott32.wasm` 659854 B / `ott64.wasm` 659327 B、全体 2.8 s。**PASS: wasm32/wasm64 とも `824c6c48,cdd4ee04`**。
- ネガティブコントロール `--neg` (wasm64 側 IR の `fadd float`→`fsub float`): wasm64 が `4d7705c5,4d7705c5` となり不一致を検出 (`NEG-CONTROL OK`)。期待ハッシュを故意に変えると exit 1、未知 target は exit 2。
- 既存ドライバ `bench/ott_driver.mjs` の `is64` は `memory.type()` (node 24 でも非対応) 依存で常に false → 検査では wasm バイナリの memory section を直接読む。

## RT-6 実測 (Memory 個数予算 + LRU プール + 100+ ロード負荷試験, #125)
既知類型との関係 (DEFECTS.md): 該当なし (lift 欠陥ではなくランタイム資源管理)。検証起点 commit `16b9005` (初版 `71b93a0` からの変更は下記「pin 競合の修正」「wasm64 追い出しの枠リーク修正」)。
- 実装: `src/runtime/memory_budget.ts` (`MemoryBudget` = SharedArrayBuffer 共有可の CAS 個数カウンタ、wasm64 は 1 Memory = 2 slot / `createBudgetedMemory` = 予約→生成、失敗で返却 / `PluginPool` = pin・unpin・LRU 追い出し・同一 id 同時 pin の dedup。ロード完了時に待機中 pin 数をそのまま pins として登録)。既定 capacity 96 (`DEFAULT_PLUGIN_CAPACITY`)。`pnpm typecheck` OK。
- 再現: `pnpm runtime:memload` = `node tools/runtime/memload/run_memload.mjs [--pos-only|--neg-only]` (1 ケース = 新規 headless Chrome 154.0.8037.97 = 新規レンダラ。判定 NG または **ネガコンが検出されない** と exit 1)。
- 実測 (GitHub runner 4 vCPU、コミット済み HEAD `16b9005` を作業ツリー clean の状態で 2 回、total 9.9 / 10.1 s、loadavg 2.01→3.39 / 3.39→3.48、exit 0): **ALL PASS 2/2** (PASS 9 + NEG-OK 7)。直前の `e82e685` の 3 回実測 (8.1 s × 3、PASS 7 + NEG-OK 6) は pin 競合の修正時点の記録として残す。
  | ケース | 実測 (1 回分の代表値) |
  |---|---|
  | naive: 無予算で 300 instance | 125 個目で `RangeError: Out of memory: Cannot allocate Wasm memory` (instance 経由では 125、Memory 直生成は 124。許容 124±4) |
  | churn_drop: 保持なし 1000 個 → 上限まで保持 → 全解放 → 再び上限まで保持 (明示 GC なし) | churn 1000 個とも例外なし。保持は first 123〜124 / second 123〜124 個で OOM (2 回実測)。全解放後の再作成が効く = 参照を落とした Memory は回収される |
  | pool_churn: 300 種・1500 pin (80% は 60 種に集中)・cap 96 | 例外 0・状態不一致 0・累計ロード 252 (>124)・追い出し 156・peakInUse 96 |
  | pool_concurrent: 120 本 `Promise.all` 同時 pin (cap 120) | 全員の linear memory 内容が一致。121 本目は `MemoryBudgetExceeded` (RangeError でない)・枠リークなし。1 本 unpin 後は LRU 追い出しで 121 本目がロード可。同一 id 10 同時 pin は 1 ロード |
  | pool_race: pin 復帰前の追い出し | (a) cap=1 で pin(A) の k=0〜8 マイクロタスク後に pin(B): 9 通りとも A は破棄されず、B は `MemoryBudgetExceeded`、inUse=size=1。(b) cap 8・24 種・並行 24 本×60 波 = 1440 pin: 受理 890 / 予算拒否 550 / 破棄済みハンドル 0 / 追い出し 423 / peakInUse 8。静止時 生存 value=size=inUse=8、全 unpin 後に追い出し切って 0 |
  | create_fail_releases | 不正 descriptor で RangeError → 予約は返却 (inUse 1→0)、`release()` 二重呼びで負数にならない |
  | dispose_throw: cap=2 で a (wasm32, unpin 済み) を載せておく → wasm64 `w` のロードが a を追い出す (a の dispose が throw) | 例外は `dispose-boom` のまま伝播。失敗後 inUse=0・size=0 (確保枠を残さない)、後続 `b` の pin は成功 |
  | cross_thread: main 60 + Worker | 共有カウンタ cap 120 で Worker は 60 個目で拒否 (deniedAt=60)、RangeError なし |
  | wasm64: cap 120 | 60 本許可・10 本拒否、実 Memory 生成成功 |
- **ネガティブコントロール** (全て FAIL を検出して NEG-OK。(6) は pin 競合): (1) `neg=leak` 追い出し後も instance 参照を保持 → 累計 125 ロードで OOM RangeError (pins 469/1500)。(2) pool_churn cap=130 (ネイティブ上限超) → OOM (pins 507/1500)。(3) pool_concurrent cap=130 → 121 本目が拒否されず `no-error`・inUse 121。(4) wasm64 cap=140 → 61 本許可後 RangeError (granted 61)。(5) cross_thread `budget=0` (Worker が予算を無視) → Worker が 65 本成功した後の 66 本目で RangeError (main 60 と合算 125 本)。(2) の pins と (4) の granted は実行ごとに揺れる (初版 507 / 61、再実行 483 / 62。いずれも FAIL を検出)。(6) `pool_race?neg=legacy` 修正前の pin (await 後に pins++) に戻す → k=1〜4 で A が破棄済みのまま pin 成功・B のロードも成功、並行 1440 pin 中 900 件が破棄済みハンドル。(7) `churn_drop?neg=keep` churn 中も参照を保持 → 125 本目で OOM (churn ok 124〜125、first / second は 0 本)。
- **pin 競合の修正** (oc-reviewer 指摘, PR #575): 旧 `pin()` はロード完了の `await` の後で `pins++` していたため、エントリ登録 (pins=0) から復帰までの間に別 id のロードが枠不足で LRU 追い出しに来ると、dispose・枠返却・Map 除去済みの value を pin 済みハンドルとして返した。`loadOne` がエントリ登録時に待機中の pin 数を pins として引き継ぐよう変更 (登録と pin 確保が同期)。旧実装 (`ec2a79b` の `memory_budget.ts`) に戻して `--pos-only` を実行すると `pool_race` だけが FAIL (k=1,2,3,4 で破棄済みハンドル、並行 1440 pin 中 900 件、exit 1)。旧版は `pool_churn` が直列、`pool_concurrent` が cap ちょうどで、この窓を踏まなかった。
- **wasm64 追い出しの枠リーク修正** (oc-reviewer 軽微指摘): `loadOne` の wasm64 経路で、追加枠の確保中に victim の `dispose` が throw すると、先に確保した base 枠 (wasm32 1 slot) が返らなかった。追い出しを try で囲み、失敗時は base を返して `dispose` を呼ぶよう変更 (`16b9005`)。旧版 (`4633168` の `memory_budget.ts`) に戻して `--pos-only` を実行すると `dispose_throw` だけが FAIL (`inUse=1`、`size=0`、exit 1)。修正版は `inUse=0`、後続 pin 成功。
- **実測で確定した事実**: (a) 参照を落とした Memory は回収される。`churn_drop`: 保持なしで 1000 個作成 (例外 0) → 上限まで保持 (123〜124 本で OOM) → 全解放後に再び上限まで保持 (123〜124 本)。明示 GC は使っていない (`--expose-gc` 相当の比較は未実施)。(b) 上限は main と Worker の合算で数える (`cross_thread?budget=0`: main 60 + 無予算 Worker 65 本)。→ 個数予算は SharedArrayBuffer カウンタでスレッド間共有する必要がある。
- 範囲外 / 検証範囲: Chrome 154 のみ (Firefox/Safari の上限は未測定)。Memory は 1 page (max 64MiB) の最小 wasm で、実 lifted DLL (OTT 等) のロードではない。pthread 共有 Memory・AudioWorklet 内の生成は未検証。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `PluginPool` を実プラグイン loader (hostbridge) へ接続し、実 DLL 100+ をロードする負荷試験 | 本試験は最小 wasm の代用。実 DLL 固有の初期化コスト・Memory 以外の資源 (Worker/Table) は未測 | #125 へコメント。親 #25 配下に新規子 issue `[RT-13]` を PM が起票 (`[RT-11]` は #25 が使用中) |
| `MemoryBudget` の共有カウンタ (SharedArrayBuffer) を `PluginPool` の既定経路 (実 loader・Worker) に配線していない。既定は per-thread カウンタ。受入の「予算で強制 ✅」は pool 単体の結果で、Worker を含む実運用の上限は未検証 (`cross_thread` は共有カウンタを直接渡して検証) | 実 loader 接続時に配線が必要 | #125 へコメント (実 loader 接続と同時に PM 判断) |
| Kilohearts 47 stub 等の 1 wasm 同居 (prefix + base 割当 + CPU 状態分離。#91 REPORT §7) | pool で追い出せない常駐が 124 を超える場合の最終回避策。未実装 | #96 (HB-H7) に連携コメント |
| Firefox / Safari の Memory 上限測定 | 予算値 96 は Chrome 実測のみに基づく | RT-9 (#127 系) へコメント |
| 追い出し時の `dispose` で呼ぶプラグイン終了処理 (FL 側 state 保存) の仕様 | pool は dispose フックだけ提供 | #125 へコメント |

## RT-6 実 loader 接続 (#125 2 回目): PluginPool → hostbridge 実 loader → lowbase 版 OTT
既知類型との関係 (DEFECTS.md): 該当なし (ランタイム資源管理)。測定 commit `80b69fa2` (コード変更の最終 commit)。`git diff 80b69fa2 HEAD -- tools/runtime/memload/real src/runtime` (測定後の文書のみ commit で差分 0 を確認する行を末尾に付す)。
- 実装: `tools/runtime/memload/real/real_worker.mjs` (Worker) と `run_real.mjs` (Chrome ドライバ、`pnpm runtime:memload:real`)。`PluginPool` (`src/runtime/memory_budget.ts` を transpile) の loader を hostbridge の `LoadLibraryW` (`prewarm` した EmscriptenGuest を sync 取得) に、dispose を `FreeLibrary` に接続。OTT は `tools/hostbridge/lowbase/retdec/build_m10_lb.sh` の lowbase 版 (LB_BASE 0x10000, initial 24 MiB / max 64 MiB, `ott_hb.wasm` 848,256 B)。host は `retdec/build_host_lb.sh` (`host_vst2.wasm` 3,734 B)。
- 入力素材 (展開確認済み): `work-m6-ott` (`tools/m10/work/ott_m10.ll` 955,899 B を lowbase 再ビルドに使用)。`plugins-ott` は NSIS インストーラ。`7z x` で取り出した `OTT_x64.dll` (PE32+, ImageBase 0x180000000, SizeOfImage 0x308000, 3,146,752 B) を `$HOME/analysis/plugins/ott/binaries/OTT_vst2_win64.dll` として配置。`toolchain-emsdk` は runner 既存の [EMSDK] (emcc 6.0.12) を使用 (artifact は展開していない)。`toolchain-retdec` は ott_m10.ll があるため不使用。
- 試験内容: 150 種の alias (同一 OTT ファイル、各々独立の Memory) を sweep で 1 回ずつ pin、続けて 170 回の偏った pin (70% が先頭 40 種、同時 pin 最大 3)。cap は `DEFAULT_PLUGIN_CAPACITY` 96。cold ロード直後の初回 block (128 frame) の出力 sha256 を基準 (同ページ内の最初の cold ロード) と照合。warm pin はパラメータ読み戻し (param 0 = 0.5) で instance の取り違えを見る。最後に全 unpin → 全 unload。
- 実測 (コミット済み `80b69fa2` を clean worktree で 3 回, Chrome 154.0.8037.97, 4 vCPU, 1 分 loadavg 0.58→1.70 (各回開始時)):
  | 項目 | run1 | run2 | run3 |
  |---|---|---|---|
  | pool 試験 PASS (pins 320 / loads 165 / evictions 69 / 生存 96 / peakSize 96 / peakInUse 96) | PASS | PASS | PASS |
  | cold 照合 (165 件) 全て基準と bit 一致 / warm pin param 不一致 | 0 / 0 | 0 / 0 | 0 / 0 |
  | 全 unload 後 size / inUse / bridge 登録 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
  | 試験本体 run (Chrome 内) | 1.85 s | 1.86 s | 1.81 s |
  | ネガコン neg_cap130 (cap を実測上限超) | OOM at load 124 | OOM at load 124 | OOM at load 125 |
  | ネガコン neg_nofree (dispose で FreeLibrary しない) | OOM at load 124 | OOM at load 124 | OOM at load 124 |
  | ALL PASS / exit / wall | ALL PASS / 0 / 7.05 s | ALL PASS / 0 / 6.92 s | ALL PASS / 0 / 7.09 s |
- 判定: 累計ロード 165 (> 124)、追い出し 69 で生存は 96 以下。実 OTT lowbase で、Memory 個数上限 (124) を超えるロードを pool 経由で通した。
- 実測で確定した事項: (a) `FreeLibrary` が Memory 参照を落とす唯一の経路 (dispose で呼ばないと bridge が握り続け、pool の追い出しに関係なく 124 で OOM)。(b) `host_close` は単一の `g_info.hmodule` (最後に load した plugin) を解放するため、任意の plugin の解放には使えない。pool は `bridge.FreeLibrary(handle)` を直接呼ぶ。(c) 採番の衝突 (コードから導出、再現試験は未実施): `hb_bridge.mjs` の `LoadLibraryW` は `handle = HMODULE_BASE + (loaded.size + 1) * 0x10000` で採番するため、解放後の再ロードが既存 handle と一致し得る。本試験は `PoolBridge` (LoadLibraryW を単調採番に置換した派生クラス) で回避し、共有 poc 側は未修正。
- 範囲外 / 検証範囲: Chrome 154 のみ (Firefox/Safari 未測定)。Worker 1 本のみ (per-thread カウンタ、SAB 共有カウンタは未配線)。異なる DLL の同時ロードは未実施 (plugins-ott は OTT のみ)。cold 照合の基準は node 参照ではなく同ページの最初の cold ロード (node との bit 突合は lowbase e2e 側で 500 block 実施済み)。warm pin は OTT が block 間で DSP 状態を持つため出力を照合しない。
- 再現: `bash tools/hostbridge/lowbase/retdec/build_m10_lb.sh` (前提: `$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll`、`tools/m10/work/ott_m10.ll`) → `bash tools/hostbridge/lowbase/retdec/build_host_lb.sh` → `pnpm runtime:memload:real` (`--pos-only` / `--neg-only` 可)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `MemoryBudget` の SharedArrayBuffer カウンタを `PluginPool` の既定経路 (Worker) に配線し、main+Worker 合算の 124 を pool 経路で試験 | 本試験は per-thread カウンタ。実運用の上限は未検証 | #125 (次 run) |
| `hb_bridge.mjs` `LoadLibraryW` の handle 採番 (`loaded.size + 1`) の解放後衝突を再現し、共有 poc 側を修正 | 本試験は派生クラスで回避。共有 poc は未修正 | #125 (次 run) |
| dispose 時の FL 側 state 保存仕様 | pool は dispose フックだけ提供 | #125 へコメント |
| 常駐が 124 超の 1 wasm 同居 | 既存 | #96 (HB-H7) |
| Firefox / Safari の Memory 上限 | 既存 | #127 (RT-9) |
| OTT 以外の DLL (freshair / serum2 / massivex) の同時ロード | 異なる lift 系統の実 DLL は未試験 | PM 判断 (素材追加依頼) |
