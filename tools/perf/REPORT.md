# tools/perf REPORT — wasm 実時間性能・compile 時間・巨大 wasm 実験

担当 P perf。設計提言は `PERF.md`、全表は `results/TABLES.md` (自動生成)、生データは `results/*.jsonl`。
環境: Ryzen 9 9950X 16C (**他 subagent と共有, loadavg 5〜25**)、node 26.10 (V8 14.6)、Chrome 154.0.8037.97 (V8 15.4, `--headless=new`)、
emsdk 6.0.12、binaryen 133 (`results/env.json`)。

## 0. 結論

| 論点 | 実測結果 |
|---|---|
| リアルタイム係数 (OTT `processReplacing` 128f) | **M10 現行相当 RTF 0.070 @44.1k (0.077 @48k)** = 204.8 µs/2902 µs、14 インスタンス/コア。**LTO+O3 で 0.0013 (3.9 µs, 745 インスタンス/コア)**。Chrome Worker ≈ node (O0/O2/O3 で ±5%; O1 のみ Chrome が 40% 遅い・原因未調査)、実 AudioWorklet スレッドも同値 (76〜103 µs @O2) |
| 最適化の支配要因 | **`__asm_*` helper の関数呼出** (O2 で 715 call/ブロック)。LTO で call 715→1・**17× (O2) / 47〜52× (対 M10 -O0)**。出力 bit は全 59 変種で一致 (署名 `c2858a18`) |
| 二次要因 | -O1 2.7×, O2→O3 1.45×, binaryen `-O3` 1.35× (LTO 無時のみ)。`-msimd128`: LTO 無で 0〜14%、**LTO 有で 6× 退行**。pthread/gc-sections/M1 定型 CFLAGS/Os/Oz/`--converge`: 性能差なし |
| tier | Liftoff-only は定常 1.25× (O2)〜2.0× (O0) 遅い。TurboFan 強制は O0 で 1.09× 速いのみ。起動コストは Liftoff 0 / TF 全量は巨大 wasm で致命的 |
| Chrome 154 compile | **既定は lazy** (検証のみ)。K=10 (32MiB, 89,360 関数) **96 ms**、K=100 (300MiB, 893,600 関数) **619 ms**。eager 915 ms / 8.0 s、**TurboFan 全量 10.7 s (K=10)** |
| 上限 | module **1 GiB ちょうどまで OK、+1 B で CompileError**。関数数 1,000,000 (1,000,832 で失敗)。同期 compile はメインスレッド 8MB 超不可 |
| キャッシュ | IDB へ `Module` 保存 **不可**。AudioWorklet へ `Module` postMessage **不可**。自動 code cache は headless で未観測 |
| 転送 | 実 wasm の brotli-11 = **31.0%** (gzip-9 42.1%)。K=10 を 100 Mbps で 2.8 s、stream で compile は隠れる |

**M10 の OTT は出力 junk (実行経路が本来と異なる可能性)** → RTF 絶対値は目安。相対比 (helper inline 化効果) は頑健。

## 1. 成果物

```
tools/perf/
  perf.sh                 1 コマンド E2E (PERF_QUICK=1 で縮小, PERF_STAGES で段選択)
  flags.sh  lib/inputs.sh 共通設定 / 既存成果物の読取専用コピー (→ work/inputs)
  build/ott_build.sh      OTT (M10 最終 IR + helper C) を任意 emcc 構成でビルド (ES6 glue, node/Chrome 共用)
  build/ott_matrix.sh     最適化マトリクス 29 変種 / build/wasmopt_matrix.sh  wasm-opt 10 構成 × 3 入力
  build/m5_build.sh       M5 純 SSE カーネル (waveshaper/distortion) 7 構成 / build/m11_build.sh  M11 closure 任意 -O
  harness/                bench_core(共通) node_one/node_bench, cdp(依存なし CDP クライアント)/server(COOP/COEP,帯域制限)/chrome_bench, ott_worklet
  huge/                   wasm_dup.py (実 wasm を K 倍に複製), huge_chrome.mjs (scale/cores/hints/limits/funcs/sync/idb/mem/bw/worklet/ottscale/cache)
  report/                 tables_*.mjs (表生成), compress.mjs, key.mjs, env.sh
  results/                *.jsonl (生データ 1.7MB), TABLES.md, env.json, compress.json, wasmopt_m11.tsv
```

ベンチ対象 wasm: ① OTT M10 (`tools/m10/work/ott_m10.ll` + m6/m8/m9/m10 C 一式; 原本は読取のみ。`o0` が M10 build と同構成: 838,328B vs 844,118B(-g1))、
② M5 waveshaper `function_6a7540` / distortion `function_6a2fb0` (FLEngine 実機能の lift)、③ M11 boot closure 5.65MB (compile 実験の素材)。
M3 crc / M1 は < 40KB で compile・RTF とも自明のため対象外。

測定法: 1 変種 1 プロセス、warm-up 300 → 20,000 ブロックを個別計時 (Chrome は cross-origin isolated で 5 µs 精度 → 5 µs 未満の変種は 64 call バッチ平均 †)。
node 5 反復 / Chrome 3 反復の p50 中央値を採用 (最小値も併記)。各変種で **出力署名 (先頭 8 ブロック + 1000 ブロック目の FNV) を -O0 基準と照合**。

## 2. 最適化比較 (OTT 128f; node p50 µs, 5 反復中央値。Chrome は `results/TABLES.md`)

| 変種 | wasm B | p50 µs | p99 µs | RTF@44.1k | 対 o0 | 備考 |
|---|--:|--:|--:|--:|--:|---|
| o0 (M10 相当) | 838,328 | 204.8 | 440 | 0.0705 | 1.0× | 全 export・no-gc |
| o0min (min export+gc) | 791,476 | 207.8 | 383 | 0.0716 | 1.0× | サイズ -5.6% |
| o1 / o2 / o3 | 695,184 / 622,306 / 634,568 | 74.7 / 72.7 / 49.7 | 148 / 150 / 92 | 0.026 / 0.025 / 0.017 | 2.7 / 2.8 / 4.1× | |
| os / oz | 615,770 / 611,373 | 69.3 / 81.7 | 177 / 463 | 0.024 / 0.028 | 3.0 / 2.5× | |
| o2simd / o3simd | 622,164 / 638,852 | 65.1 / 43.7 | 142 / 115 | 0.022 / 0.015 | 3.1 / 4.7× | node のみ 11〜14% 改善 (Chrome 差なし) |
| **o2lto / o3lto** | 585,557 / 586,192 | **4.3 / 3.9** | 10.6 / 10.0 | **0.0015 / 0.0013** | **47 / 52×** | processReplacing: call 715→1, 命令 10,884→4,014 |
| o2thinlto / o3thinlto / oslto | 585,994 / 586,547 / 579,682 | 4.5 / 4.0 / 5.2 | 15.6 / 12.2 / 16.5 | 0.0015 | 46 / 51 / 40× | thin も同等 |
| o2ltosimd / o3ltosimd | 598,911 / 608,748 | 34.3 / 23.7 | 63 / 53 | 0.012 / 0.008 | 6.0 / 8.6× | SIMD+LTO は退行 (call 489 残存) |
| o3lto + M1 定型 CFLAGS / `--lto-O3` | 586,300 / 586,523 | 3.9 / 3.9 | 11 / 8 | 0.0013 | 53× | 差なし |
| o2m1flags (`-frounding-math` 等) | 622,379 | 69.6 | 178 | 0.024 | 2.9× | 差なし |
| o2fullnogc / o2fullgc | 659,854 / 649,052 | 69.1 / 72.3 | 166 / 232 | 0.024 / 0.025 | 3.0 / 2.8× | export 全部: +4〜6% サイズ |
| o2thr (`-pthread`) / o2thrsimd | 663,097 / 662,955 | 73.7 / 63.5 | 153 / 113 | 0.025 / 0.022 | 2.8 / 3.2× | 共有 memory/atomics の税なし |

wasm-opt (入力: clang -O2 のみ・binaryen 未通過 `o2raw` 692,389B): none 73.8 µs / -O1 73.8 / -O2 75.4 / **-O3 54.5** / -Os 69.8 / -Oz 70.2 /
-O4 55.0 / -O2 --converge 69.7 / **-O3 --converge 54.4** / --flatten --rereloop -O3 55.1 (サイズ 624〜635KB、gzip 285〜295KB で差小)。
`o2rawsimd` 入力でも同傾向 (-O3 48.6 vs none 78.8 µs)。wasm-opt 所要: OTT 0.7MB で 0.1〜1.5 s、M11 5.65MB で -O3 1.1 s / `--converge` 3.2 s (`results/wasmopt_m11.tsv`)。

M5 純 SSE カーネル (128 sample/call, µs): waveshaper O0 2.11 / O2 0.845 / **O2+simd 0.207** / O3+simd 0.187、distortion O0 1.72 / O2 0.575 / O2+simd 0.261 / O3+simd 0.159。
`-O1 -msimd128` は退行 (3.4 / 2.3)。Liftoff-only は O3+simd で 0.298/0.337。署名は 14 変種とも一致 (`fd5cb93` / `d5864b34`)。

## 3. 巨大 wasm / Chrome compile (詳細: `results/TABLES.md` H1〜H12, `PERF.md` §3〜§4)

素材 (M11 closure): x86 1,417,790B / 7,361 関数 → wasm code 3.11MB / 8,928 関数 (@-O0, 2.19 B/B)。FLEngine `__text` 17.66MB へ外挿 → code ≈ 38.7MB (推定, K≈12)。
`wasm_dup.py` は関数/型を K 倍 (call 先は原本)、`wasm-validate` 通過。1 GiB 級は padding custom section で生成 (関数数 1,000,000 上限のため K≤111 ≈ 348MB が実コードの最大)。

| K (MiB / 関数) | lazy stream ms | lazy bytes ms | eager ms (CPU 秒) | HWM MB (lazy / eager) |
|---|--:|--:|--:|--:|
| 1 (5.4 / 8,936) | 18 | 7 | 144 (0.24) | 143 / 165 |
| 4 (14.3 / 35,744) | 44 | 20 | 422 (1.28) | 144 / 245 |
| 10 (32.1 / 89,360) | 96 | 43 | 915 (3.15) | 233 / 408 |
| 30 (91.6 / 268,080) | 219 | 133 | 4050 (5.5) | 430 / 936 |
| 60 (181 / 536,160) | 493 | 213 | 5168 (16.3) | 727 / 1707 |
| 100 (300 / 893,600) | 619 | 362 | 8013 (27.4) | 1124 / 2751 |

- eager + TF のみ: K=1 632 ms, K=4 3.0 s, **K=10 10.7 s (24 CPU 秒)**。eager + 動的 tiering 無: K=10 3.0 s (8.9 CPU 秒)。eager + Liftoff のみ: K=10 1.2 s。
- コア数 (K=30 eager): 1c 5.7 s / 2c 4.2 / 4c 2.9 / 8c 2.6 / 16c 2.4 s。
- 実行可能 K 倍 OTT (関数 144K): K=800 (64.7MiB / 115,200 関数) lazy create **122 ms**、eager 966 ms、初回 128f 0.12 ms、定常 70 µs (K=1 と同値)。
- 上限: `size > maximum module size (1073741824)` — L-1 / L は成功 (2.1〜2.2 s, RSS 3.2GB)、L+1 / L+1MiB は失敗。関数数 111→OK / 112 (1,000,832) → `exceeds internal limit of 1000000`。
- メモリ: `WebAssembly.Memory` 16MB〜4GiB (shared 含む) 確保 0.07〜0.54 ms・RSS 増なし。864MiB × **124 個**で `could not allocate memory`。
- 帯域: 100 Mbps で K=10 は stream 2816 ms (≈転送時間)、bytes→eager 4051 ms。1 Gbps: eager stream 750 vs bytes 1131 ms。
- AudioWorklet: `Module` postMessage → `messageerror`。bytes transfer で compile+instantiate 1+4 ms (OTT)、K400 は 38+3 ms。main で eager compile (481 ms) 済みなら worklet 33 ms。2 秒実時間 1048/1048 ブロック処理 (null sink)。
- キャッシュ: IDB `put(Module)` → `DataCloneError`。bytes IDB (32MiB) put 174 / get 72 / 再 compile 54 ms。Cache API 経由 compileStreaming 71〜94 ms、`Code Cache/wasm` は 4 ロード後も index のみ。
- compilationHints: 既定で効果なし (§PERF 4)。

## 4. 検証

- 全変種で出力署名一致 (OTT 59 変種 `c2858a18`、M5 a1/a2 各 7 変種 `fd5cb93`/`d5864b34`; node+Chrome 全反復)。不一致は表に `MISMATCH` と出る設計 (出現なし)。
- node と Chrome の p50 は O0/O2/O3/LTO で ±5% 以内に一致 (O1 のみ Chrome 0.105 vs node 0.075 ms) → 計測系の相互妥当性。
- `wasm_dup.py -k 1` は原本とバイト一致、`-k 4` は `wasm-validate` 通過。`perf.sh` の `inputs build tables` 段を PERF_QUICK=1 で再実行し exit 0 (他段は個別実行済みの同コマンド)。
- `tools/m1..m11, tools/shim` は未改変 (読取のみ・`git status` で tools/perf/ 以外の変更なし)。

## 5. 未解決・制約

1. **OTT 出力が junk** のため実行命令の分布が本番と異なる可能性。LTO 効果の方向 (call 削減) は構造由来だが絶対 RTF は M10 修復後に再測。
2. 共有ホスト (loadavg 5〜25/16C): **単発 max に 5〜6 ms の外れ値** (O3+LTO の 4 µs ブロックでも発生)=スケジューラ起因。実 underrun 評価は低負荷+実オーディオデバイスで要再測 (headless は null sink)。
3. Chrome 自動 wasm code cache は headless で未観測 (headful 未確認)。compilationHints は「無効果」までで機序未解明 (eager/bg/lazybase ヒントで global eager 時 CPU 9.3→5.7 s、wall 2.3→3.3〜4.1 s)。
4. FLEngine 実体の wasm は未存在: 規模は M11 closure の K 倍複製+x86 サイズ比の**外挿 (推定)**。`-O1/-O2` の M11 は到達可能関数のみ (619〜810 関数, code 44〜53KB) になり比較に使えない。
5. Chrome 154 (Linux, Zen5) のみ。Firefox/Safari/モバイル CPU (3〜10× 低速想定) は未測。SIMD は AVX-512 機で有利な可能性。
6. wasm vs native 比 (M3 は crc で 1.3〜1.4×) は OTT では未測 (lift IR の VA 固定が native 側の障壁)。
7. 動的リンク (MAIN/SIDE_MODULE, PIC 税) 未測定。

## 6. ユーザ依頼事項

なし (素材追加は不要)。headful 実機 (GPU/オーディオ有り) での追試が可能なら P7/P3 に有益。

## 7. 次タスク提案 (下流チケット; 詳細は `PERF.md` §6)

P1 lift ビルド標準を LTO+O3+最小 export に (署名ガード付き) / P2 `__asm_*` を LLVM vector IR へ lowering (SIMD+LTO 両立) /
P3 AudioWorklet ローダ (bytes transfer・worklet 内 compile・pre-warm・main 側 Module 保持) / P4 lifted VA の低位再配置 (initial 864MiB→数十MB) /
P5 perf 回帰ゲート (PERF_QUICK を CI) / P6 FLEngine 実 closure の起動〜初回 audio E2E / P7 headful・Firefox・Safari・Android 再測 /
P8 プラグイン別 module vs 動的リンクの比較 / P9 OTT 機能修復後の RTF 再測。

## 8. 再現

```sh
bash tools/perf/perf.sh                  # 全段 (数十分)
PERF_QUICK=1 bash tools/perf/perf.sh     # 代表変種・反復 1 (数分)
# 個別: node tools/perf/harness/node_bench.mjs <tag> ott o2,o3lto --reps 5 ; node tools/perf/huge/huge_chrome.mjs scale --k 1,10,30
```
注: 巨大 wasm 実験の K 倍素材は M11 の 5,655,905B スナップショット (sha256 先頭 `af1599814c9898e2`; M11 側は以後更新され得る — 現在 6,008,101B)。
前提: `tools/m10/work/ott_m10.ll` 等 (`bash tools/m10/m10_build.sh` で生成)、`tools/m11/work/boot_final2.ll`。`work/` は gitignore (≈1.9GB)。
