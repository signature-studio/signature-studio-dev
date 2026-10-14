# PERF.md — wasm 性能・起動時間の設計提言 (tools/perf)

> **検収追記**: 以下の OTT 数値/LTO 17〜52× は M10 RetDec lift (junk 出力・`__asm_*` helper が別 C ファイル) 固有。bit-exact な自作 x64c lift (`tools/ott/REPORT.md` が正本) では **LTO は無害 (効果は 1.15× 程度)・O2 以上が必須**で、LTO の桁違い効果は RetDec chain 固有 (数値: `tools/perf/REPORT.md` §2.1)。

実測根拠はすべて `results/*.jsonl` / `results/TABLES.md` (自動生成表) / `REPORT.md`。推定は「(推定)」と明記。
測定環境: AMD Ryzen 9 9950X (16C, Zen5), node 26.10 (V8 14.6), Chrome 154.0.8037.97 (V8 15.4, headless=new, Dedicated Worker)。
**16 コアを他 subagent と共有 (loadavg 5〜25)**。p50 は最小値寄り・p99/max は負荷の影響を受ける (後述 §1)。

## 0. 結論 (先に)

1. **最大の性能問題はコンパイラ設定ではなく「SSE helper が別 TU の関数呼出」な現行構造**。OTT の `processReplacing` は
   -O2 でも 715 回の `__asm_*` call が残り、**LTO (helper の inline 化) だけで 17× (O2: 72.7→4.3 µs/128f)**、
   M10 現行 (-O0) 比 **47〜52×** (204.8→3.9 µs)。出力 bit は全変種で一致 (署名 `c2858a18`)。→ 最優先で標準ビルド化。
2. **-O 水準・wasm-opt・SIMD は二次的**: O0→O1 2.7×、O2→O3 1.45×。LTO 無しの `-msimd128` は OTT 中立 (±3%)、
   **LTO + `-msimd128` は逆に 6× 遅い** (helper が u128 経由で inline されず call が 489 残る)。純 SIMD 化できる M5 カーネル
   (waveshaper/distortion) は `-O2/-O3 -msimd128` で 3〜4× 速い → SIMD は C helper ではなく **IR lowering (`<4 x float>`)** で入れる。
3. **リアルタイム余裕は十分** (現状 OTT): 128f/2.90ms (44.1k) 予算に対し M10 現行 RTF **0.070** (14 インスタンス/コア)、
   LTO+O3 で **0.0013** (750 インスタンス/コア)。Liftoff-only でも定常は TurboFan の 1.25〜2.0× 遅いだけ。
   ただし OTT は M10 時点で出力 junk (実行経路が本来と違う可能性) → **絶対値は目安、相対比 (inline 化効果) は頑健**。
4. **Chrome 154 は wasm を既定で lazy compile** (関数は初回呼出時に Liftoff)。巨大 wasm でも compile は検証のみ:
   FLEngine 規模相当 (K=10: 32MiB/89,360 関数) で **96 ms (stream) / 43 ms (bytes)**、300MiB/893,600 関数でも 0.4〜0.6 s。
   eager (`--no-wasm-lazy-compilation`) は K=10 で 0.9 s・K=30 で 2.4〜4.1 s、**TurboFan 全量は K=10 で 10.7 s / 24 CPU 秒**。
5. **起動時間を支配するのは転送** (K=10 を 100 Mbps で 2.8 s; compile は stream で隠れる)。brotli-11 で実 wasm は **31%**。
6. **AudioWorklet への `WebAssembly.Module` の postMessage は Chrome 154 で受信できない** (`messageerror`)。版・ブラウザで異なり、Firefox 157 は受信 OK、Chrome 155 の再実行も受信 OK (`tools/perf/REPORT_P7.md` §7)。bytes を transfer して worklet 内で compile (採用方式)。
   同一プロセス内 NativeModule キャッシュが効き、main で eager compile 済みなら worklet の compile は **481→33 ms**。
7. **IndexedDB に Module は保存不可** (`DataCloneError`)。bytes は IDB/Cache API に保存可。Chrome 自動 wasm code cache は
   headless では観測できず (4 ロード + 2.5s idle で `Code Cache/wasm` エントリ 0)。lazy 既定なので必須ではない。
8. 上限実測: モジュール **1 GiB (1,073,741,824) ちょうどまで OK / +1 で CompileError**、関数数 **1,000,000**、
   同期 `new WebAssembly.Module` は **メインスレッド 8MB 超不可** (Worker は可)。`WebAssembly.Memory` 4GiB まで確保 0.5 ms・RSS 0
   (仮想予約のみ)、864MiB を 124 個まで確保可。

## 1. リアルタイム係数 (OTT processReplacing, 128 フレーム, `results/TABLES.md` A〜E)

予算: 44.1kHz → 2.9025 ms、48kHz → 2.6667 ms。RTF = 1 ブロック処理時間 / 予算 (小さいほど良い)。node と Chrome は O0/O2/O3/LTO で ±5% 以内 (O1 のみ Chrome が 40% 遅い・原因未調査)。

| 構成 | node p50 µs | Chrome p50 µs | RTF@44.1k | RTF@48k | OTT/コア | 対 o0 |
|---|--:|--:|--:|--:|--:|--:|
| M10 現行相当 (-O0, no SIMD, 全 export, no-gc) | 204.8 | 200 | 0.0705 | 0.0768 | 14 | 1× |
| -O2 | 72.7 | 70 | 0.0251 | 0.0273 | 40 | 2.8× |
| -O3 | 49.7 | 50 | 0.0171 | 0.0186 | 58 | 4.1× |
| -O2 + LTO | 4.3 | 4.7 | 0.0015 | 0.0016 | 669 | 47× |
| **-O3 + LTO** | **3.9** | **4.1** | **0.0013** | **0.0015** | **745** | **52×** |
| Liftoff-only (-O2) | 91.0 | 90 | 0.0313 | 0.0341 | 32 | 2.3× |

- p99: o0 0.44 ms (RTF 0.15)、o3lto 0.010 ms。**単発 max は 5〜6 ms に達する回がある (o3lto でも)** → 計算量ではなく共有ホストの
  スケジューラ preemption (loadavg 20+/16C)。実機での underrun 判定は実デバイス + 低負荷で再測が必要 (下流チケット)。
- 本物の AudioWorklet スレッド (Chrome, 48kHz): 区間平均 76〜103 µs/128f (Worker と同値; o2)、2 秒実時間で process() 1048/1048 回
  (null sink のため機能確認止まり。underrun の実測ではない)。
- 純 SSE カーネル (M5): waveshaper 0.845 µs → `-O2 -msimd128` 0.207 µs (4.1×)、distortion 0.575 → 0.261 µs (O2), 0.573 → 0.159 µs (O3)。waveshaper O3 は 0.849 → 0.187 µs。RTF 1e-4 オーダ。

## 2. 最適化の効果と推奨設定

| 項目 | 実測効果 (OTT 128f) | サイズ | 推奨 |
|---|---|---|---|
| **LTO (`-flto` / thin)** | O2: 72.7→4.3 µs (17×)。call 数 715→1。thin も同等 (4.5 µs) | -6% (622→586KB) | **無害** (bit-exact 版では 1.15× 程度・RetDec chain では決定的)。OTT 規模でビルド 2〜12 s |
| -O3 vs -O2 | 1.45× (LTO 無し) / 1.1× (LTO 有) | +2% | O3 |
| -Os / -Oz | O2 比 1.05× / 0.89× | -1〜2% | 不要 |
| binaryen `wasm-opt -O3` (LTO 無し・O2 object 入力) | 1.35× (74→55 µs)。-O2/-Os/-Oz/-O1 は 0〜1.05×。`--converge`・`--flatten --rereloop` は上乗せ無し | -9% (-O2) | LTO 採用なら不要 (o3lto + `--lto-O3` も同値)。M11 規模 5.65MB で -O3 1.1 s / `--converge` 3.2 s |
| `-msimd128` (現 helper) | LTO 無: O0/O1 ±1%、node の O2/O3 で 11〜14% 改善 (Chrome は差なし)。**LTO 有: 6× 遅い** (O3: 3.9→23.7 µs) | ±0 | 現構造では付けない。IR lowering 後に有効化 |
| `-pthread` (shared memory + atomics) | 73.7 vs 72.7 µs (差なし) | +6% | スレッド化の性能ペナルティ無し |
| `--gc-sections` + 最小 export | 性能差なし | -5.7% (全 export 比) | 本番では export をエントリのみに |
| M1 定型 `-frounding-math -fno-strict-aliasing` | 差なし (69.6 vs 72.7 µs) | ±0 | 維持可 |

メカニズム: lift 後の x86 SSE 命令は `__asm_*` (別 TU の C) への i128 引数 call になり、wasm の shadow-stack 経由で
引数が往復する。LTO で helper を取り込むと SROA で i128 が消え、`processReplacing` は 10,884→4,014 命令・call 715→1 になる。
`-msimd128` + LTO では `u128`↔`v4f` の memcpy 変換が残り inline が阻害される (call 489 残存, 推定: helper 本体が大きくなり
inline 閾値超過)。**提言: lift pass で `__asm_*` を直接 LLVM vector IR に落とす** (下流 P2)。

## 3. 巨大 wasm: compile / メモリ (FLEngine 規模の見積り)

実 wasm (M11 boot closure: x86 1,417,790B・7,361 関数 → wasm code 3.11MB・8,928 関数 @-O0 = 2.19 B/B) を K 倍複製
(`huge/wasm_dup.py`; 関数/型を複製・call 先は原本)。**FLEngine 全体の外挿 (推定)**: `__text` 17.66MB・.pdata 57,816 関数
→ code ≈ 38.7MB (K≈12.4)、関数 ≈ 70k〜110k。以下 K=10 (32.1MiB, 89,360 関数) と K=30 (91.6MiB, 268,080 関数) を FLEngine 規模の括りとする。

| 構成 (Chrome, 16C 共有) | K=10 | K=30 | K=100 (300MiB, 893,600 関数) |
|---|--:|--:|--:|
| 既定 (lazy) compileStreaming ms / CPU 秒 / HWM MB | 96 / 0.10 / 233 | 219 / 0.50 / 430 | 619 / 1.98 / 1124 |
| 既定 (lazy) bytes→compile ms | 43 | 133 | 362 |
| eager (`--no-wasm-lazy-compilation`) ms / CPU 秒 / HWM | 915 / 3.15 / 408 | 4050 (2.4〜4.1 s) / 5.5〜8.9 / 936 | 8013 / 27.4 / 2751 |
| eager + Liftoff のみ | 1231 / 2.2 | - | - |
| eager + **TurboFan のみ (`--no-liftoff`)** | **10654 / 24.2** | - | - |
| eager + 動的 tiering 無 (全関数 TF 追従) | 2989 / 8.9 | - | - |

- Liftoff eager は 約 11MB/s/コア・30 µs/関数 (K=100 で 27.4 CPU 秒/893,600 関数)。**FLEngine 規模で全関数 TF は非現実的** (K=10 で 10.7 s)。
- コア数 (K=30 eager): 1 コア 5.7 s / 2: 4.2 / 4: 2.9 / 8: 2.6 / 16: 2.4 s → **4 コアで頭打ち寄り**。FLEngine 規模 (K≈12, 推定) eager でも 4 コア ≈ 1.2 s。
- instantiate 8〜16 ms (lazy), eager 時 24〜225 ms。初回 export 呼出 0.1 ms。
- 実行可能な K 倍 OTT (関数 144K 個): K=800 (64.7MiB, 115,200 関数) でも lazy create 122 ms・初回 128f 0.12 ms・定常 70 µs で K=1 と同値。
  eager は create 966 ms (CPU 5.6 s)。**定常性能は wasm サイズ・関数数に依存しない**。
- メモリ: lazy K=10 HWM 233MB、K=30 430MB、K=100 1.1GB。1 GiB wasm (padding) の streaming compile で renderer RSS 3.2GB (≈3×サイズ)。
- `-O1/-O2` の M11 ビルドは code 53/44KB (619〜810 関数) に縮む: closure の大半が現状エントリから到達不能 (VMT/間接呼の未結線)。
  サイズ見積りは -O0 比で行い、結線が進むと増える点に注意。OTT での -O2/-O0 code 比は 0.35 (推定上限 38.7MB→約 14MB)。

## 4. キャッシュ・分割・配信の実測事実

| 項目 | 結果 |
|---|---|
| IndexedDB に `WebAssembly.Module` | **不可** (`DataCloneError: A WebAssembly.Module can not be serialized for storage`) |
| `structuredClone` / postMessage → Worker | 可 (12.9〜14 ms) |
| postMessage → **AudioWorklet** | **Chrome 154 では不可** (`messageerror`)。Firefox 157 では受信 OK (版・ブラウザ別。`REPORT_P7.md` §7)。bytes transfer → worklet 内 `WebAssembly.compile` は可 (OTT 1 ms / K400 38 ms) |
| 同一プロセス NativeModule 共有 | main で eager compile (481 ms) → worklet の同一 bytes compile **33 ms**。main の Module を生存させる |
| bytes を IDB 保存 | 32MiB: put 174 ms / get 72 ms / 再 compile (lazy) 54 ms |
| Cache API (`Cache.put` → `match` → `compileStreaming`) | 可。32MiB で 71〜94 ms。エントリ = wasm bytes のみ (code 側ストリーム無し) |
| Chrome 自動 wasm code cache | **headless=new では未観測** (HTTP cache 保存は確認: 34,195,903B、`Code Cache/wasm` は index のみ)。headful 実機で別途確認要 |
| `compilationHints` custom section | 既定 Chrome では lazy/eager ヒントの効果なし (`--experimental-wasm-compilation-hints` 併用でも global eager 時 lazy ヒント無効果)。**当てにしない** (eager/bg/lazybase ヒント付き版では global eager 時の CPU 秒が 9.3→5.7 に下がるが wall は 2.3→3.3〜4.1 s に悪化。機序未解明) |
| 同期 `new WebAssembly.Module` | メインスレッド 8MB 超は RangeError、Worker は可 (15MB: 19.5 ms) |
| 帯域制限 (K=10 32MiB): 100 Mbps | stream 2816 ms vs bytes 2867 ms (lazy)。eager なら stream 3364 vs bytes 4051 ms (compile が転送に隠れる) |

## 5. 起動時間予算と対策

**予算案 (提案値)** (4 コア・100 Mbps のデスクトップ; TTI ≤ 3 s のうち wasm ロード段 ≤ 2 s を割当):

| 段 | 実測根拠 | 見積り (FLEngine 相当 38.7MB code, 推定) | 対策 |
|---|---|--:|---|
| 転送 | brotli-11 = 31.0% (M11 wasm 5.66MB→1.75MB; gzip-9 42.1%, zstd-19 34.7%) | 全体 ~50MB → ~15MB → 100 Mbps で 1.2 s | brotli-11 配信 + immutable 長期 cache、stream で compile を重畳 |
| compile | lazy 既定 ≈ 3 ms/MiB (K=10: 96 ms) | 0.1〜0.2 s | `compileStreaming`/`instantiateStreaming` 必須 (Content-Type: application/wasm)、**eager 強制 flag は使わない** |
| instantiate | 8〜16 ms | ≤ 50 ms | memory は 1 度確保 (§下記) |
| 初回呼出 stall | Liftoff 30 µs/関数、OTT 128f 初回 0.12 ms (K≥1 不変) | closure 1,000 関数で ≈ 30 ms (> 2.7ms 予算) | **audio 経路を silence で 1 周させてから接続 (worklet 内 pre-warm)** |
| データ像・CRT 初期化 | (M11 boot 側; 未計測) | - | 別チケット |

**対策の優先順位**
1. **標準ビルドを LTO + O3 に** (§2)。起動と無関係だがリアルタイム余裕が 50× 変わる最大要因。
2. **Liftoff 優先は既定のまま** (lazy Liftoff + 動的 tier-up)。TF 全量/`--no-wasm-dynamic-tiering` は禁止。定常 Liftoff/TF 差は 1.25〜2.0×、起動コストは 0。
3. **pre-warm 手順**を worklet ローダに実装: bytes transfer → worklet 内 compile → init → silence で全プラグイン entry を 1〜N 回 → `connect`。
   main スレッドで先に `WebAssembly.compile` して Module を保持し、同一プロセス NativeModule 共有を利用 (eager 時 481→33 ms)。
4. **分割**: (a) プラグイン (OTT 等) は FL 本体と別 module・別 instance・別 memory (VA 前提の lift コードは PIC/side module に不向き)。
   (b) 本体は 1 module のまま lazy で十分 (compile はボトルネックでない)。(c) 配信は module 単位 brotli + 必要時 fetch (未使用プラグインは遅延)。
   動的リンク (MAIN/SIDE_MODULE) の PIC 性能は未測定 → 下流 P8。
5. **メモリ**: OTT は VA==offset のため initial 864MiB (13,824 pages)。仮想予約のみで確保 0.4 ms・RSS 増 0、Chrome は 864MiB を 124 個まで可。
   ただし Windows commit charge / モバイルは未検証 → VA を低位 base に再配置して initial を 数十 MB に (下流 P4)。FLEngine は M11 で 301MB→1.79GB。
6. **キャッシュ**: Module は保存不可。bytes を Cache API/IDB に置き SW で配信 (再訪の fetch 0)、compile は lazy ゆえ 50〜100 ms で許容。
   自動 code cache は期待せず、headful 実機で追検証。
7. **サイズ上限**: 1 GiB 上限・関数 1,000,000 上限・8MB 同期上限に十分余裕 (FLEngine 規模 40〜120MB, 70k〜110k 関数)。ただし 300MiB で HWM 1.1GB → 低メモリ端末は注意。

## 6. 下流チケット案

| ID | 内容 | 根拠 |
|---|---|---|
| P1 | lift ビルドの標準化: helper を同一 LTO 単位に (`-flto`/thin, `-O3`, 最小 export, `--gc-sections`)。m6/m10 build へ反映し bit 署名ガード付き | §2: 17〜52× |
| P2 | `__asm_*` → LLVM vector IR lowering pass (`<4 x float>` + `llvm.fma`) で SIMD を IR 側で表現し、LTO と両立 | §2: simd+LTO で退行 |
| P3 | AudioWorklet ローダ: bytes transfer + worklet 内 compile + pre-warm + main 側 Module 保持、実機 underrun 計測 (headful/実デバイス) | §4, §5 |
| P4 | lifted VA の低位再配置 (initial memory 864MiB→数十MB)、Windows/Android の commit 影響測定 | §3 |
| P5 | perf 回帰ゲート: `PERF_QUICK=1 perf.sh` を CI 化、RTF と署名を閾値判定 | 本ハーネス |
| P6 | FLEngine 実 closure (M11 完成版) で起動〜初回 audio までの E2E 計測 (データ像 fetch・CRT 初期化含む) | §5 未測定 |
| P7 | headful Chrome / Firefox / Safari / Android での compile・lazy 挙動・code cache の再測 (本測定は Chrome 154 headless のみ) | §4 |
| P8 | プラグイン別 module vs 動的リンクの性能/メモリ比較 (PIC 税、instance 数 × memory) | §5.4 |
| P9 | OTT の機能修復後に RTF を再測 (node 版は REPORT §2.1、Chrome Worker・実 AudioWorklet・低負荷・native 比は `REPORT_APPENDIX.md` §12 で実施済み; 残: M11 級 closure での LTO 効果) | §0.3 |
