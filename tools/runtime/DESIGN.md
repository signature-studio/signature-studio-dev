# tools/runtime/DESIGN.md — ブラウザ実行基盤 (runtime-arch) 設計・決定・実測

対象: Chrome 154.0.8037.97 (headless, `google-chrome`) / emcc 6.0.12 / node v26.10.0 / Linux 16 コア共有 VM。
すべての数値は `node tools/runtime/**` の再現スクリプトによる実測 (推定は「推定」と明記)。
実装: `src/runtime/{mem,worker*,boot*,loader_boot,imports_env}.ts`、e2e: `pnpm runtime:e2e`。

## 0. 決定一覧

| # | 論点 | 決定 | 主根拠 (実測) |
|---|---|---|---|
| D1 | メモリモデル | **wasm32 + LVA 敷設** (PE ImageBase を引いた線形アドレス)。Memory64 は退避路 (型・ビルド手順のみ整備) | FLEngine ImageBase=0x400000 / SizeOfImage=24.75MiB で 4GiB 内。Memory64 性能差は決定要因にならない (§1.3)。Memory 個数上限が wasm64 は半分 (§1.4) |
| D2 | 実行スレッド構成 | main(UI/入力) ⇄ **Worker "fl-runtime" (wasm 実行 = Win32 UI スレッド兼ポンプ)** ⇄ OffscreenCanvas(Worker 内描画) ⇄ AudioWorklet(ロックフリー消費のみ) ⇄ pthread プール | Worker 内 WebGL2/2D/rAF/OPFS sync handle/nested Worker すべて可。AudioWorklet は `Atomics.wait` が TypeError (§2.1) |
| D3 | ブロッキング GetMessage | **Atomics.wait + SAB ring (Vyukov MPSC)**。pthread ビルドでは同一 ABI を wasm 共有メモリに置き `memory.atomic.wait32` で直接ブロック。**Asyncify 不採用**、JSPI は async→sync 橋渡し専用の副次手段 | 4 方式すべてネスト(モーダル)ポンプ動作。ring 方式 25–118 万 ev/s vs postMessage 方式 8–11 万 ev/s。Asyncify は M11 で +40% サイズ (§2.3) |
| D4 | pthread | **emcc の pthread glue をそのまま使う** (`-pthread -sPROXY_TO_PTHREAD -sPTHREAD_POOL_SIZE=N`)。Module は `instantiateWasm` フックで自前 compile 済みを注入 | emcc pthread がヘッドレス Chrome で動作 (4 スレッド×1M atomic add = 4,000,000 一致、cond ping-pong 19µs)、Module 注入も動作 (§2.4) |
| D5 | ブート/キャッシュ | wasm は **Worker 内 `fetch → compileStreaming`**、ハッシュ名 + `immutable` の **HTTP キャッシュ**。**IndexedDB への Module 保存は不可** (実測 DataCloneError)。Cache API は opt-in | compile は lazy で安価 (1.5ms/MiB)。code cache による追加高速化は観測されず (§3) |
| D6 | COOP/COEP | `same-origin` + `require-corp`。wasm は **同一オリジン** 配信 (R2 カスタムドメイン同一ホスト) か、別オリジンなら `CORP: cross-origin` + CORS | `crossOriginIsolated=true` が SAB/Atomics.wait/共有メモリの前提 |

## 1. メモリモデル

### 1.1 事実 (M3/M5/M6/M11 実績 + PE 実測)
- FLEngine_x64.dll: **ImageBase 0x400000, SizeOfImage 0x18c0000 (24.75MiB)**, .text 0xfa34b0 / .data 0x240008 / .bss 0x388e9c (PE ヘッダ実測)。M11 は LVA = VA−0x400000 (= RVA) で敷設し GLOBAL_BASE=0x10000000、初期メモリ 301MiB (静的データ実測 294MiB)。
- プラグイン DLL (OTT 等) は ImageBase **0x180000000** (4GiB 超)。M6 で V-shift (0x180000000+RVA → 0x30000000+RVA, IR 内 38 箇所 remap) し GLOBAL_BASE=256MiB・メモリ 864MiB で実行済み。
- 本ランタイムの `mem.ts` に `LAYOUT` / `flengineVaToLinear` / `pluginVaToLinear` として固定。

### 1.2 Chrome 154 の機能マトリクス (実機: `node tools/runtime/probe/run_features.mjs` → `work/features_result.json`)

| 項目 | 結果 | 項目 | 結果 |
|---|---|---|---|
| wasm SIMD / relaxed-SIMD | ✅ / ✅ | wasm threads+atomics | ✅ |
| memory64 | ✅ | shared memory64 (max 16GiB) | ✅ |
| multi-memory / tail-call / extended-const | ✅ ✅ ✅ | bulk-memory / reference-types / multivalue | ✅ ✅ ✅ |
| EH (legacy / exnref) / GC | ✅ ✅ / ✅ | wide-arithmetic / custom-page-sizes | ❌ ❌ |
| JSPI (`WebAssembly.Suspending/promising`) | ✅ | `Memory.toResizableBuffer` | ✅ |
| wasm32 Memory initial 4GiB | ✅ (0.5ms) | shared wasm32 initial 4GiB | ✅ (1.2ms) |
| memory64 grow → 8GiB | ✅ (0.4ms) | memory64 の 5GiB `Uint8Array` view | ✅ |
| `Atomics.wait` in Worker / main | ✅ / ❌ TypeError | `Atomics.waitAsync` | ✅ |
| nested Worker | ✅ | Worker 内 OffscreenCanvas 2D / WebGL2 / rAF | ✅ ✅ ✅ (WebGL2 は SwiftShader=ヘッドレスのソフトウェア描画) |
| OPFS `createSyncAccessHandle` (Worker) | ✅ | IndexedDB (main/Worker) | ✅ |
| AudioContext / AudioWorklet (ヘッドレス) | ✅ running, 48kHz, 128f ブロック 200 回/546ms (実時間) | Worklet 内 SAB / WebAssembly | ✅ / ✅ |
| Worklet 内 `Atomics.wait` | ❌ TypeError → **worklet はロックフリー消費のみ** | WebGPU / WebCodecs / WebMIDI | object / ✅ / ✅ |
| 共有 wasm memory で 4 Worker×1M `i32.atomic.rmw.add` | 4,000,000 一致 (72ms) | `memory.atomic.wait32/notify` Worker 間 | ✅ |
| **IndexedDB に `WebAssembly.Module` 保存** | ❌ **DataCloneError** ("can not be serialized for storage") | Cache API put/get / `structuredClone(Module)` | ✅ / ✅ |
| `navigator.storage.estimate().quota` (ヘッドレス profile) | 4GB | | |

### 1.3 Memory64 vs wasm32 性能 (`bench/*`, Chrome Worker 内, 同一ソース・同一 `-O2`)
共有 VM のため load average 9–20 の下での実測 (ノイズ大。min と median を併記)。再測は静かな機で推奨。

| ベンチ | wasm64/wasm32 (median) | (min) |
|---|---|---|
| seq_sum 64MiB | 1.21 | 1.06 |
| rand_rmw 64MiB (cache miss) | 1.11 | 1.16 |
| pointer chase (1M node) | 1.08 | 0.95 |
| hot_loop (L1, load/store 密) | 1.04 | 1.06 |
| call_mix (非インライン呼出 + store) | 12.1 | 4.8 ← 外れ値 |
| **OTT lifted DSP (M10 IR, 256 サンプル/ブロック)** | **0.925** (164.8 vs 178.1 µs/block) | 0.83 |

- 外れ値 call_mix は node 側の分解で A(呼出のみ)=2.7×, B(storeのみ)=1.16×, 間接呼出=1.21×, D(元)=0.57× と**方向が反転**する → V8 のインライン/tier-up 判断の揺れで、メモリモデル固有の定数倍ではない。結論: 「一様な X 倍」は無く、実コード (OTT) では差なし (むしろ −7.5%)。
- **同一 lifted IR を p:64 datalayout に書換えるだけで wasm64 ビルドが通り、出力ハッシュが wasm32 と完全一致** (`824c6c48`)。必要なのは `datalayout` の `f128:64` 付き p:64 と shim の `size_t` 引数幅の整合のみ (`HeapAlloc` 署名不一致 warning 1 件 = i32 vs i64 size)。→ 退避路は実証済み。常時ビルド検査は `ci/wasm64_check.sh` ([REPORT](REPORT.md) RT-8 実測)。

### 1.4 Memory 個数上限 (`probe/run_memcount.mjs`) — **新規に判明した制約**
1 レンダラ内で作れる WebAssembly.Memory は **wasm32: 124–125 個 / wasm64(max 16GiB): 61–62 個** (2 回測定) (max/initial/shared に依存せず一定。約 1TiB の VA 予約上限と整合する値だが、内部上限の正体は**推定**)。
→ 「プラグイン DLL 1 本 = 1 Memory」方針では **同時ロード DLL を ~100 未満に抑える** (遅延ロード・アンロード時に参照を確実に落とす・小プラグイン統合) 必要がある。Memory64 は個数がさらに半分になるため不利。

### 1.5 決定の理由と退避条件
1. FL 固有の Memory64 必然性が無い (FLEngine は 25MiB / 低位 ImageBase)。4GiB 超の絶対アドレスを持つのはプラグイン DLL だが V-shift 済み・別 Memory。
2. Memory64 は Firefox/Safari の対応が**未検証** (本環境は Chrome のみ)。wasm32 は全ブラウザ。
3. サンプル/ストリーム等の大容量データは wasm ヒープ外 (OPFS / 別 SAB) に置き、wasm ヒープは 4GiB 未満で運用。
4. **退避トリガ**: (a) 実プロジェクトで wasm ヒープ >3GiB が観測、(b) 4GiB 超アドレスが remap 不能な lifted コードが見つかる → `MemoryModel="wasm64"` ビルドに切替 (`mem.ts` は両モデル対応済み: `createMemory`/`describeMemory`/BigInt 引数対応の `imports_env`)。
5. pthread + memory growth は `-sGROWABLE_ARRAYBUFFERS=2` (Chrome 154 に `toResizableBuffer` あり) を推奨 (emcc が警告を出す点)。

## 2. 実行モデル

```
main thread (UI, 入力, Canvas 所有)
  │  PumpRing.push()  [ロックフリー MPSC, SAB]        postMessage (制御面/進捗/ログ)
  ▼                                                   ▲
Worker "fl-runtime" ── wasm インスタンス = Win32 UI スレッド ── MessagePump.getMessage() = Atomics.wait
  │   ├ OffscreenCanvas (transferControlToOffscreen → Worker 内 WebGL2/2D, rAF)
  │   ├ pthread プール (emcc glue; オーディオエンジン/Delphi TThread)  ── 共有 wasm Memory
  │   └ SAB ring ──► AudioWorklet (消費専用。Atomics.wait 不可なので underrun は無音で吸収)
```

### 2.1 制約 (実測)
- main では `Atomics.wait` 不可 → **wasm 実行は Worker**。AudioWorklet でも不可 → worklet は `Atomics.load` で ring を掃くのみ。
- Atomics.wait でブロック中の Worker は自身の JS イベントループを回せない → 制御面 (終了要求等) も ring 経由 (`WM.APP_RUNTIME_STOP`)。非同期 Web API (fetch/IDB) を同期的に呼ぶ必要がある箇所 (VFS 等) は JSPI か補助 Worker 経由 (§2.5)。

### 2.2 ポンプ ABI (`worker_pump.ts` `RING`; C 側 `spike/pump_spike.c` が同一レイアウトで動作確認済み)
- ヘッダ 16×i32 (64B): `enq, deq, wake(futex), quit, capacity, dropped`。スロット 64B × capacity(2 のべき乗): `seq, message, hwnd(lo,hi), wParam(lo,hi), lParam(lo,hi), time, pt.x, pt.y, tPost(f64@+48)`。
- push = Vyukov bounded MPSC (CAS で enq 予約 → payload → `seq` publish → `wake++` + `Atomics.notify`)。満杯は `false` (PostMessage 失敗相当) と `dropped++`。マウス移動の coalesce は producer(GUI) 側の責務。
- consumer `MessagePump`: Win32 の優先順 (投稿 → WM_QUIT → WM_PAINT → WM_TIMER) を再現。タイマー期限は `Atomics.wait` の timeout に畳み込み (GetMessage が次の WM_TIMER まで正確に寝る)。`peekMessage(remove=false)`、`sleep()`、`setTimer/killTimer/invalidateRect/postQuitMessage`。

### 2.3 方式比較 spike (`spike/*`, `node tools/runtime/spike/run_pump_spike.mjs`)
同一 C (`pump_spike.c`) から 4 方式を作り、producer Worker からの ping-pong RTT・50,000 件バースト・ネスト(モーダル)ポンプを測定。**全 4 方式でネストポンプ正常 (maxDepth=2 / handled=53,204 一致)**。

| 方式 | RTT p50 / p99 (µs, 深さ0) | バースト (ev/s) | 備考 |
|---|---|---|---|
| Atomics.wait (JS import) | 5–80 / 100–165 | 257,593 / 1,184,553 / 345,459 | 3 回測定 |
| native (wasm 内 `memory.atomic.wait32`, 共有メモリ) | 5–80 / 100–170 | 677,874 / 927,558 / 272,168 | 同一 ring を C が消費 |
| JSPI (`Suspending/promising`) | 10–110 / 105–340 | 95,017 / 90,804 / 87,427 | postMessage 経由 |
| Asyncify (`wasm-opt --asyncify`) | 15–105 / 170–245 | 107,334 / 87,925 / 84,213 | postMessage 経由 |
- RTT はスケジューラ起因で **二峰性** (5–15µs の「温かい」状態 / 80–110µs の「冷えた」状態) で、方式の優劣を判別できない (4 方式とも両モードを取った)。静かな機での e2e では pump p50=**4.9µs**, p99=0.28ms (2000 イベント)。
- スループットは SAB ring 方式 (25.7–118 万) が postMessage 方式 (8.4–10.7 万) より 3–14 倍。入力イベントは ring、重い構造化データは postMessage と使い分ける。
- スタック深さ 64 でも RTT に有意差なし。
- **Asyncify コスト (実 lifted wasm)**: M10 OTT: `-O2` 単体 704,923B → asyncify 754,886B (**+7.1%**, `ignore-indirect` なら +0.7%)、通常実行速度は `-O2` 比 **0.998 倍** (DSP は async import に到達しないため計装対象外)。**M11 (FLEngine boot closure)**: `-O2` 4,465,489B → asyncify 6,249,772B (**+40.0%**; M11 担当の再ビルド後スナップショットでは 4,467,060B → 6,227,702B = +39.4%)、wasm-opt 時間 1.85s→2.76s。GetMessage が UI コードの全呼出経路から到達しうる実 FL では更に増える見込み (推定)。
- **結論**: 主=Atomics.wait。pthread ビルドは wasm 内 wait (JS import 往復なし)。Asyncify はサイズ+40% 超・全呼出元の計装・unwind/rewind が必要で不採用。JSPI は (a) ブラウザ依存 (Chrome 系)、(b) JS フレームを跨いで suspend できない、(c) 同期 import から非同期 Web API を呼ぶ用途に限定して副次採用。

### 2.4 pthread (`spike/pthread_test.c`, `run_pthread_test.mjs`)
`-pthread -sPROXY_TO_PTHREAD -sPTHREAD_POOL_SIZE=6 -sEXIT_RUNTIME -sMODULARIZE -sEXPORT_ES6` がヘッドレス Chrome で完走: 4 スレッド×1M `atomic_fetch_add` = **4,000,000 (一致)**、4 スレッド spawn+join 31.8ms (プール事前確保)、`pthread_cond` ping-pong RTT **19.0µs**、`emscripten_num_logical_cores`=16。`Module.instantiateWasm` で自前 compileStreaming した Module を注入し、worker 側にも共有された (`injectedModule: true`)。→ 本番 FL ビルド (`tools/shim` MT 経路) はこの glue を採用し、boot.ts の compile 経路を `instantiateWasm` から差し込む。
**RT-2 (#120) で確定**: フラグは `tools/runtime/prod/flags.sh` (`-sGROWABLE_ARRAYBUFFERS=2` を含む)、注入は `loader_boot.ts` `createEmscriptenPthreadModule`、配信は hash 名 + brotli 事前圧縮 (`stage_wasm.mjs`)。glue (.mjs) は pthread Worker スクリプトでもあるため hash 名へ書換え、COEP/CORP を付けて配信する。実測は REPORT.md。

### 2.5 同期/非同期の橋渡し方針 (下流)
OPFS は Worker 内 `createSyncAccessHandle` が同期で使える (実測) → VFS は OPFS 同期ハンドルを第一候補。ネットワーク/IDB を要する場合のみ JSPI または補助 Worker + `Atomics.wait` の sync-RPC。

### 2.6 GUI 結線 (RT-3 #121): OffscreenCanvas と入力イベント
- **入力 (producer)**: `gui_input.ts` `PumpInput` が canvas/window の DOM イベントを Win32 メッセージ (WM_MOUSEMOVE/L,M,R BUTTON/MOUSEWHEEL/KEYDOWN,UP/SYSKEY*/CHAR/SETFOCUS,KILLFOCUS) に変換し `PumpRing.push`。純関数 (`mouseMoveMsg` 等) は DOM 非依存。
  **マウス移動の coalesce は producer 側**: pointermove は最新 1 件だけを保持し rAF で push、他種イベント (down/up/key/wheel/focus) の直前に保留 move を吐いて順序を保つ。
- **描画 (OffscreenCanvas)**: `canvas.transferControlToOffscreen()` で渡した先で 2D 描画する。主は **yield 方式** (非ブロッキングで ring を掃く → `Atomics.waitAsync` でイベントループへ戻る → タスク終了で commit)。
  **blocking 方式** (`getMessage` = `Atomics.wait` に居座ったまま描く = 実 FL の UI スレッドの形) は、Worker のタスクが終わるまで OffscreenCanvas が画面へ commit されない (Chrome 154 は `OffscreenCanvas.commit()` 無し、e2e で実測)。
  → **GetMessage でブロックする wasm UI スレッドと描画スレッドは分離する**: 描画は GuiShared の out ring を `waitAsync` で消費する専用描画 Worker (`gui_worker.ts` = `gui_renderer.ts`) が担う (tools/gui PROTOCOL §1 の構成)。fl-runtime Worker が OffscreenCanvas を直接持つのは (A) ブロックしない駆動 (yield) か (B) 描画だけをブロックしない別タスクへ逃がす場合に限る。
- **2 つの入力経路の関係** (統合は未決): tools/gui の GuiShared 入力リング (`gui.ts`, shim が `translate_input` で消費) と、本節の PumpRing (`worker_pump.ts` ABI, startup/pump の C ポンプが消費)。GUI shim とポンプ shim は同時リンク不可 (duplicate strong symbol: tools/startup/pump REPORT §8)。どちらを正にするかは GUI-3 (#174) / GUI-11 (#32) で決める。
- **`?runtime=` 共存**: `/?gui=selftest[&present=yield|blocking]` と `/?gui=render-selftest` は `?runtime=` と独立に併用可 (index.ts でそれぞれ別に mount)。

## 3. ブート手順とキャッシュ (`bench/run_compile_bench.mjs`)
フロー: `main: loadManifest(/wasm/manifest.json)` → `spawnRuntimeWorker` → Worker: `fetch(hash名.wasm)` → `compileStreaming` (進捗は `Response.clone()` の並行消費、compileStreaming には**元の Response**を渡す = コードキャッシュ連携を壊さない) → `buildImports` (Module.imports() を introspection、未解決は fail-fast フォワーダ) → instantiate → `emscripten_stack_init` / `__wasm_call_ctors` → driver。

実測 (M11 の関数本体を K 倍複製した合成 wasm, localhost, Chrome Worker; 合成は到達しない関数を含むため「検証+Liftoff 遅延」コストの上限近似):
| サイズ | streaming fetch+compile | bytes→`compile` のみ | instantiate (301MiB mem) | 初回呼び出し |
|---|---|---|---|---|
| 5.8 MiB | 33 ms | 10 ms | 12–17 ms | 5 ms |
| 8.9 | 40 | 15 | 10–20 | 5 |
| 15.0 | 67 | 26 | 10–15 | 5 |
| 27.4 | 108 | 40 | 9–15 | 5 |
| 52.2 | 215 | 83 | 10–14 | 5 |
- compile は **ほぼ線形 ≈1.5 ms/MiB** (V8 は関数を lazy コンパイル。初回呼び出しで実行経路のみ Liftoff) → 100MiB 級でも compile は ~0.15–0.4 s (**推定**)。ボトルネックは**ダウンロード**。
- 同一 profile で 3 連続・ブラウザ再起動後とも `transferSize=0 / deliveryType=cache` (HTTP キャッシュ命中) で fetch は消えるが、compile 時間に有意な短縮は無い (コードキャッシュの追加効果は観測されず; compile 自体が安価なため)。
- 実 lifted wasm の圧縮率: M11 6,044,445B → **brotli q11: 1,823,721B (3.31×, 展開 31ms)**、gzip -9: 2.45×、zstd -19: 2.96×。→ R2 には brotli 事前圧縮 (`Content-Encoding: br`) を置く。
- IDB は Module を保存不可、postMessage/structuredClone は可 → 「1 回 compile して Worker/pthread に共有」のみ。

## 4. 実装メモ (`src/runtime/`)
| ファイル | 役割 |
|---|---|
| `mem.ts` | メモリモデル型・LVA 定数・`createMemory`/`growMemoryTo`/`MemoryView` (grow で buffer が替わる件に対応) |
| `worker_pump.ts` | `PumpRing` (SAB MPSC) / `MessagePump` (GetMessage 相当) |
| `worker_protocol.ts` | main⇄Worker メッセージ型・manifest 型 |
| `loader_boot.ts` | `fetchCompile` / `buildImports` / `initEmscripten` |
| `imports_env.ts` | emscripten env/wasi の JS 実装 + **EM_JS/EM_ASM 汎用実装** (`__em_js__NAME` export の `"(args)<::>{body}"` を遅延 `new Function`; M11 の `m11_throw_dllmain_done` を glue 無しで解決) |
| `worker.ts` / `worker_drivers.ts` | Worker エントリと検証ドライバ (m1-hello / ott-t1 / m11-boot) |
| `boot.ts` / `boot_ui.ts` | main 側ブート (`bootProgram`, `runPumpSelfTest`) と進捗パネル (`/?runtime=all&pump=1`) |
| `loader.ts` (既存) | `instantiateCompiled` を追加し `instantiateWasm` と後処理を共有 (既存 API・`tools/misc/loader_smoke.mjs` は無改変で PASS) |
| `imports.ts` (既存) | `createImportForwarder` をそのまま fail-fast に利用 |

e2e (`pnpm runtime:e2e`): stage → Vite dev (COOP/COEP) → headless Chrome → 4 wasm を Worker で実行し **元の emcc glue を node で実行した参照値とビット一致を確認** (M10 hash `824c6c48`/`cdd4ee04`, M6 `fb31ca9a`, M1 stdout, M11 `{m11_dllmain_done:1}`/stage=1) + pump 自己検証 (2000 件欠落 0, WM_TIMER ≥3, 実ブロッキング wait 発生)。`--prod` は `vite build` + preview の本番バンドルで、`--cache=cacheapi --compile=bytes` で別経路も検証可。

### 4.1 機能検出フォールバック (RT-9 設計案・**未実装**・Safari 入力待ち)
入力: Chrome 154 / Firefox 157 は memory64・JSPI・shared memory・Worker 内 Atomics.wait・OffscreenCanvas がすべて可 (実測は REPORT.md)。Safari は未測定のため、以下は検出順序と退避先の設計で、Safari の可否は仮定しない。
| 機能 | 検出 | 無い場合の退避 |
|---|---|---|
| 実行可否 (必須) | `crossOriginIsolated && typeof SharedArrayBuffer` と shared Memory 生成 | pthread/ring 経路が成立しないため起動せず、非対応メッセージを表示 (退避なし) |
| memory64 | `WebAssembly.validate` (features.json の `memory64`) と `new Memory({address:"i64"})` | §1 の決定どおり wasm32 が既定で、memory64 は退避トリガ時のみ使う。**検出結果で wasm32↔wasm64 を切替える実装は不要** (配信ビルドは wasm32 のみ) |
| JSPI | `typeof WebAssembly.promising` と `Suspending` | §2 の決定どおり JSPI は副次手段。無ければ ring (`Atomics.wait`) 経路のみ。async→sync 橋渡しが必要な VFS は補助 Worker sync-RPC へ |
| OffscreenCanvas | Worker 内 `getContext("webgl2")` 成功 | 失敗時はメインスレッド canvas + 描画コマンド転送 (RT-3 で設計)。headless では判定できない (Firefox の Worker 内 WebGL2 は Xvfb 非 headless で判定可、REPORT.md RT-9)。実機判定は Safari 等で必要 |
| AudioWorklet | `ctx.audioWorklet.addModule` の成否 | 無音で起動せず明示エラー (音声は sample clock マスター: RT-4) |
| Module 永続化 | IDB 保存は Chrome/Firefox とも不可 | HTTP キャッシュ + hash 名 immutable のみ (§3 の決定どおり) |
検出は起動時に 1 回、結果を `window.__webstudio` 契約側へ公開する想定 (契約は未実装)。Firefox 固有の注意: 非 shared memory64 の大域 grow が遅い (REPORT.md の RT-9 節) ため、memory64 を使う場合は shared かつ事前確保を優先する。

## 5. 未解決・要確認
1. **Safari は未測定**。Firefox 157 は headless で実測済み (REPORT.md)。Playwright WebKit 26.0 (Linux・Safari ではない参考値) は memory64・JSPI が無い (`REPORT_APPENDIX_127.md`)。Firefox の AudioWorklet は仮想音声 sink、Worker WebGL2 は Xvfb で判定済み (REPORT.md RT-9)。実音声デバイス・GPU での挙動は未測定。
2. 実 FL サイズ (22MiB PE × lift 膨張) の wasm は RT-10 (#128) で実測済み (x64c boot 連鎖。数値は [`rt10/REPORT.md`](rt10/REPORT.md))。合成からの外挿との差もそちら。
3. 本番 FL ビルドを pthread 化した boot e2e: shim MT 自己テストでは実証済み (RT-2 #120, 実測は REPORT.md)。実 FLEngine lift での確認は未実施。
4. ヘッドレス WebGL2 は SwiftShader。実 GPU での OffscreenCanvas 性能は未測定。
5. Memory 個数上限 (~125) と「プラグイン=1 Memory」方針の整合 (§1.4)。
6. 性能ベンチは共有 VM 上 (load 9–20)。メモリ64 の定量は静かな機で再測が必要。
