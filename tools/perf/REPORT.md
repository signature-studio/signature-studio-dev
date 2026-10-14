# tools/perf REPORT — wasm 実時間性能・compile 時間・巨大 wasm 実験

担当 P perf。設計提言は `PERF.md`、全表は `results/TABLES.md` (自動生成)、生データは `results/*.jsonl`。
環境: Ryzen 9 9950X 16C (**他 subagent と共有, loadavg 5〜25**)、node 26.10 (V8 14.6)、Chrome 154.0.8037.97 (V8 15.4, `--headless=new`)、
emsdk 6.0.12、binaryen 133 (`results/env.json`)。

> **⚠ 重要な前提 (検収で追記)**: 本 REPORT の OTT RTF 表 (§0/§2) は **M10 の RetDec lift 出力 = junk を生成する wasm** の速度である
> (tools/ott f4e0514: 間接 call 54 箇所脱落等で実行経路が本来と異なり、処理量が過少)。**bit-exact な正しい lift (tools/ott 自作 x64c lifter) で再測した結果は §2.1**:
> RTF は O2/O3 で **0.017〜0.019** (junk 版 0.025/0.017 と同程度) だが、**LTO は 1.15× しか効かず (junk 版の 17× は `__asm_*` helper が別 C ファイルだった RetDec chain 固有)**。
> 「LTO が決定打」「0.0013 / 745 インスタンス/コア」は **bit-exact 版では成立しない**。下流の標準ビルド設定の根拠には §2.1 の数値を使うこと。 (組込済み: `tools/liftlib/data/std_build.json` + 署名ガード = PERF-P1 / #155、実測は `tools/liftlib/REPORT_APPENDIX_C.md` §19)

## 0. 結論

| 論点 | 実測結果 |
|---|---|
| リアルタイム係数 (OTT `processReplacing` 128f) | **M10 現行相当 RTF 0.070 @44.1k (0.077 @48k)** = 204.8 µs/2902 µs、14 インスタンス/コア。**LTO+O3 で 0.0013 (3.9 µs, 745 インスタンス/コア)**。Chrome Worker ≈ node (O0/O2/O3 で ±5%; O1 のみ Chrome が 40% 遅い・原因未調査)、実 AudioWorklet スレッドも同値 (76〜103 µs @O2) |
| 最適化の支配要因 (**junk 版 RetDec chain の場合**; bit-exact 版は §2.1) | **`__asm_*` helper の関数呼出** (O2 で 715 call/ブロック)。LTO で call 715→1・**17× (O2) / 47〜52× (対 M10 -O0)**。出力 bit は全 59 変種で一致 (署名 `c2858a18`) |
| 二次要因 | -O1 2.7×, O2→O3 1.45×, binaryen `-O3` 1.35× (LTO 無時のみ)。`-msimd128`: LTO 無で 0〜14%、**LTO 有で 6× 退行**。pthread/gc-sections/M1 定型 CFLAGS/Os/Oz/`--converge`: 性能差なし |
| tier | Liftoff-only は定常 1.25× (O2)〜2.0× (O0) 遅い。TurboFan 強制は O0 で 1.09× 速いのみ。起動コストは Liftoff 0 / TF 全量は巨大 wasm で致命的 |
| Chrome 154 compile | **既定は lazy** (検証のみ)。K=10 (32MiB, 89,360 関数) **96 ms**、K=100 (300MiB, 893,600 関数) **619 ms**。eager 915 ms / 8.0 s、**TurboFan 全量 10.7 s (K=10)** |
| 上限 | module **1 GiB ちょうどまで OK、+1 B で CompileError**。関数数 1,000,000 (1,000,832 で失敗)。同期 compile はメインスレッド 8MB 超不可 |
| キャッシュ | IDB へ `Module` 保存 **不可**。AudioWorklet へ `Module` postMessage **不可**。自動 code cache は headless で未観測 |
| 転送 | M11 lift wasm (-O0) の brotli-11 = **31.0%** (-O2 の OTT で 37%、M11 -O1/-O2 で 34〜35%) (gzip-9 42.1%)。K=10 を 100 Mbps で 2.8 s、stream で compile は隠れる |

**M10 の OTT は出力 junk** → 上の OTT RTF は junk 版の値。**bit-exact 版 (§2.1)**: -O0 0.12〜0.13 / -O1 0.031 / -O2 0.018〜0.019 / -O3 0.018 / -O3+LTO 0.015 (≈ 67 インスタンス/コア)。
最適化 -O0→-O2 の 7× は共通で頑健、LTO の桁違い効果は junk 版のみ。

## 1. 成果物

```
tools/perf/
  perf.sh                 1 コマンド E2E (PERF_QUICK=1 で縮小, PERF_STAGES で段選択)
  flags.sh  lib/inputs.sh 共通設定 / 既存成果物の読取専用コピー (→ work/inputs)
  build/ott_build.sh      OTT (M10 最終 IR + helper C) を任意 emcc 構成でビルド (ES6 glue, node/Chrome 共用)
  build/ott_matrix.sh     最適化マトリクス 29 変種 / build/wasmopt_matrix.sh  wasm-opt 10 構成 × 3 入力
  build/m5_build.sh       M5 純 SSE カーネル (waveshaper/distortion) 7 構成 / build/m11_build.sh  M11 closure 任意 -O
  harness/                bench_core(共通) node_one/node_bench, cdp(依存なし CDP クライアント)/server(COOP/COEP,帯域制限)/chrome_bench, ott_worklet; x64c_* (§12: bit-exact OTT を node/Worker/実 AudioWorklet で計測), x64c_suite.sh + native/native_bench.* (§12 の 1 コマンド再現)
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

### 2.1 bit-exact 版 (tools/ott x64c lift) での再測 — 検収追加

`build/ott_x64c_build.sh` + `harness/ott_x64c_bench.mjs` (tools/ott の `work/lift/ott_lifted.c` と `rt/*` を読取専用コピーしてビルド)。node 26, 3 反復 p50 の範囲, **loadavg 19〜20 (共有ホスト)**。
CPU 状態をグローバル (`R[]`/`X[]`/flag) に持つ 1:1 lift で、SSE helper は `ott_cpu.h` の static inline (= 別ファイル call 無し)。全変種で出力署名一致 (`6b1696f0`)。

| 変種 | wasm B | p50 µs | RTF@44.1k | 対 o0 |
|---|--:|--:|--:|--:|
| o0 | 905,274 | 358〜388 | 0.123〜0.134 | 1.0× |
| o1 | 736,946 | 90〜97 | 0.031〜0.033 | 4.1× |
| o2 / o3 | 666,061 / 670,594 | 52〜56 / 51〜54 | 0.018〜0.019 / 0.018〜0.019 | 7× |
| o2lto / o3lto | 650,185 / 655,595 | 44〜47 / 43〜44 | 0.015〜0.016 | 8.3〜8.6× (対 o2 **1.15×**) |
| o2 + wasm-opt -O3 / o3lto + wasm-opt -O3 | 663,917 / 655,285 | 51 / 43〜46 | 0.018 / 0.015 | 効果なし |
| o3lto + `-msimd128` | 706,103 | 62〜64 | 0.021〜0.022 | **1.4× 退行** |

→ bit-exact 版の O2 (52 µs) は junk 版 O2 (73 µs) と同程度だが、junk 版 LTO 後 (4 µs) の 1/10 以下の水準には届かない = junk 版 LTO の 4 µs は本来の処理量を実行していない値の可能性が高い。**定常 RTF 0.015〜0.019 (O2/O3)** が現実的な目安。
結論の差: LTO/`-O3`/wasm-opt の効果は小 (≤1.15×)、`-O2` 以上であれば十分、`-msimd128` は逆効果、O0 は 7× 遅い。LTO 自体は無害 (ビルド時間のみ) ゆえ標準に入れてよいが「決定打」ではない。
(別 loadavg 下の追加試行では o2 90 µs / o3lto 72 µs と絶対値が悪化し比は 1.25×; 絶対値は負荷依存。)

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

1. **junk 版の LTO 効果 (17×) は bit-exact 版に移らない** (§2.1 で 1.15×)。M5 カーネル (純 SSE) の SIMD 効果は別 (OTT x64c lift には SIMD 化余地なし)。bit-exact 版の Chrome Worker・実 AudioWorklet 実測は §12 で実施 (LTO 1.2×)。M11 級 closure での LTO 効果は未測 (§12 未解決)。
2. 共有ホスト (loadavg 5〜25/16C): **単発 max に 5〜6 ms の外れ値** (O3+LTO の 4 µs ブロックでも発生)=スケジューラ起因。実 underrun 評価は低負荷+実オーディオデバイスで要再測 (headless は null sink)。
3. Chrome 自動 wasm code cache は headless で未観測 (Xvfb headful でも未観測・実ウィンドウ/GPU 有の実機は未確認: `REPORT_P7.md`)。compilationHints は「無効果」までで機序未解明 (eager/bg/lazybase ヒントで global eager 時 CPU 9.3→5.7 s、wall 2.3→3.3〜4.1 s)。
4. FLEngine 実体の wasm は未存在: 規模は M11 closure の K 倍複製+x86 サイズ比の**外挿 (推定)**。`-O1/-O2` の M11 は到達可能関数のみ (619〜810 関数, code 44〜53KB) になり比較に使えない。
5. Chrome 154 (Linux, Zen5) が主。Firefox 157 の compile/上限/同期 compile は `REPORT_P7.md` で測定済み。Safari/モバイル CPU (3〜10× 低速想定)・実オーディオデバイスは未測 (PERF-P7 #165 に残置)。SIMD は AVX-512 機で有利な可能性。
6. wasm vs native 比 (M3 は crc で 1.3〜1.4×): OTT x64c 版は `tools/ott/native` の実機械語参照と同一手順で測定可能になり §12 で測定 (旧 RetDec 版 (junk) は未測)。
7. 動的リンク (MAIN/SIDE_MODULE, PIC 税) → **PERF-P8 (#166) で合成カーネルを測定済み: 全文・表は `REPORT_P8.md`** (`bash tools/perf/p8/p8.sh`)。結論: 現行 lift (VA 固定) の plugin は plugin 別 module/instance/Memory、動的リンクは `-fvisibility=hidden` 必須 (既定 visibility の PIC 税の大きさはホスト依存)。実 OTT (x64c) / FLEngine 実体での再測は未実施。

## 6. ユーザ依頼事項

なし (素材追加は不要)。headful 実機 (GPU/オーディオ有り) での追試が可能なら P7/P3 に有益。

## 7. 次タスク提案 (下流チケット; 詳細は `PERF.md` §6)

P1 lift ビルド標準を LTO+O3+最小 export に (署名ガード付き) / P2 `__asm_*` を LLVM vector IR へ lowering (SIMD+LTO 両立) /
P3 AudioWorklet ローダ (bytes transfer・worklet 内 compile・pre-warm・main 側 Module 保持) / P4 lifted VA の低位再配置 (initial 864MiB→数十MB) /
P5 perf 回帰ゲート (PERF_QUICK を CI) / P6 FLEngine 実 closure の起動〜初回 audio E2E / P7 headful・Firefox・Safari・Android 再測 /
P8 プラグイン別 module vs 動的リンクの比較 / P9 OTT 機能修復後の RTF 再測 (**node 版は §2.1、Chrome Worker・AudioWorklet・低負荷・native 比は §12 で実施済み**; M11 級 closure が残)。

## 8. 再現

```sh
bash tools/perf/perf.sh                  # 全段 (数十分)
PERF_QUICK=1 bash tools/perf/perf.sh     # 代表変種・反復 1 (数分)
# 個別: node tools/perf/harness/node_bench.mjs <tag> ott o2,o3lto --reps 5 ; node tools/perf/huge/huge_chrome.mjs scale --k 1,10,30
```
注: 巨大 wasm 実験の K 倍素材は M11 の 5,655,905B スナップショット (sha256 先頭 `af1599814c9898e2`; M11 側は以後更新され得る — 現在 6,008,101B)。
前提: `tools/m10/work/ott_m10.ll` 等 (`bash tools/m10/m10_build.sh` で生成)、`tools/m11/work/boot_final2.ll`。`work/` は gitignore (≈1.9GB)。

## 9. perf 回帰ゲート (PERF-P5 / #164) — bit-exact OTT (x64c) 対象

既知類型との関係: 該当なし (計測ゲートの追加。lift 自体は未変更)。検証起点 commit: `aa4306b` (クリーン detached worktree で実行。数値表は同内容の事前 commit 76fdcad (未 push) での 3 回実測、aa4306b では 1 回再実行し PASS 11/11・36 s・load 0.78〜0.98)。

`bash tools/perf/gate/perf_gate.sh` (1 コマンド。CI 用 workflow は `tools/perf/gate/perf-gate.workflow.yaml.txt`) = `tools/ott/ott_e2e.sh --quick` (native 実機械語との bit-exact; 22 シナリオ・9,620 cell・max_ulp 0) → `ott_x64c_build.sh o0 o2 o3lto` → `ott_x64c_bench.mjs` を 3 反復 (変種を反復内で交互) → `gate/judge.mjs` で判定。
判定は**相対指標のみ** (絶対 µs は参考表示): 署名 `6b1696f0` 一致・出力非ゼロ 256 cell・o0/o2 p50 比 ≥ 3.0・o2/o3lto p50 比 ∈ [0.9, 2.0]・wasm bytes 上限 (o0 1,200,000 / o2 810,000 / o3lto 780,000)。閾値は env (`GATE_*`) で上書き可。

実測 (GitHub-hosted 相当 runner, node v22.23.3, loadavg 0.45〜1.40, 3 回実行・各 3 反復の中央値。`perf_gate.sh` 全体の所要 36〜38 s, 実測 3 回):

| 指標 | 実測 (3 回の min–max) | 閾値 |
|---|---|---|
| 署名 (o0/o2/o3lto 全反復) | `6b1696f0` 一致 | 一致 |
| o0/o2 p50 比 | 5.68〜5.80 (別途 5 反復の単体測定 5.3〜5.9) | ≥ 3.0 |
| o2/o3lto p50 比 | 1.18〜1.20 (単体測定 1.15〜1.29) | 0.9〜2.0 |
| wasm bytes o0 / o2 / o3lto | 1,030,416 / 707,139 / 680,905 | 上記上限 |
| p50 µs (参考) o0 / o2 / o3lto | 328.65〜335.24 / 57.74〜57.88 / 48.39〜49.12 | 判定に使わない |
| 測定 commit `2d6c45fe` の全体 (素材は agent-setup 展開の `[EMSDK]`・`[ANALYSIS-PLUGINS]`) | 82 s・load 0.27→1.06・PASS 11/11 (o0/o2 7.59・o2/o3lto 1.18) | 上記 |

ネガティブコントロール (`judge.mjs` へ入力を壊して FAIL を確認; いずれも exit 1): 期待署名を `deadbeef` → 3 件 FAIL (8/11) / o2 bytes 上限 700,000 → FAIL (707,139) / o0/o2 比下限 8 → FAIL (5.52) / o2 の p50 を 3 倍 (o2 退行の模擬) → o0/o2 1.84・o2/o3lto 3.71 で 2 件 FAIL / 1 行だけ署名を `6b1696f1` に改ざん → FAIL。

パス修正 (ハードコード → `tools/shared/env.sh` / `paths.py`): `ott_e2e.sh`・`lift/lift_build.sh`・`native/ottnat.py`・`diff/count_icall.py`・`perf/flags.sh` (`EMSDK_DIR` 既定 `/opt/emsdk`)。

範囲外 / 未解決:

| 未解決 | 影響 | 起票先 |
|---|---|---|
| **CI workflow 未設置**: GitHub App に `workflows` 権限が無く `.github/workflows/` への push が拒否された (`refusing to allow a GitHub App to create or update workflow ... without workflows permission`)。テンプレートは `tools/perf/gate/perf-gate.workflow.yaml.txt` (2d6c45fe で pip 段を削除: agent-setup の venv と衝突し EXTERNALLY-MANAGED で失敗するため)。設置後の Actions 実行も未確認 | CI 化 (受入条件) が未達 | #164 (PM が `.github/workflows/perf-gate.yaml` へ移して設置) |
| 閾値は 1 台の低負荷 runner の実測 (反復 3〜5) から設定。高負荷時の誤検知率は未測 | flaky 化の可能性 | #164 |
| `perf.sh` (PERF_QUICK, junk 版 M10 RetDec) は本ゲートに含めない。Chrome・M5 カーネル・巨大 wasm は対象外 | 回帰検知範囲は x64c の node 実行のみ | #164 に分割提案 |
| ゲートは node のみ (Chrome 計測なし) | Chrome 側回帰は検知できない | PERF-P9 (§7) |
| runner の node は v22.23.3 (§2.1 は node 26) | 絶対値の比較は不可。比のみ判定 | — |

## 10. 配信形態 (PERF-P10 / #170) — br-11 × compileStreaming の実測と現状整理

既知類型との関係: 該当なし (配信計測。lift は未変更)。検証起点 commit: `e036886` (クリーン worktree・コミット済み HEAD で再実行)。

**現状 (main)**: ローダは結線済み。`src/runtime/loader_boot.ts` `fetchCompile` が `fetch → WebAssembly.compileStreaming` (既定。`compile=bytes` は比較用)、`tools/runtime/stage_wasm.mjs` が hash 名 + `.br` (q11) を生成、`vite.config.ts` が `Accept-Encoding: br` に `Content-Encoding: br` で応答 (dev/preview)。大物 (>24MiB) は `deploy/client/chunked.mjs` (連結 ReadableStream → compileStreaming; 314MB 実エッジ実証は `deploy/REPORT.md`)。lazy 既定は V8 既定のまま (追加設定なし)。配信先は DECISIONS D1 で R2 → Workers Static Assets に変更済み。

1 コマンド: `node tools/perf/delivery/delivery_bench.mjs [--mib 16] [--reps 3] [--mbps 100,0]` (結果 `results/delivery.json`)。ローカル HTTP サーバが `Content-Encoding: br` の有無と線上帯域 (10ms 刻み) を切替え、headless Chrome 154.0.8037.97 (Linux, 4 コア, node v22.23.3) で fetch → compileStreaming / compile(bytes) → instantiate → `f0()==42` を計測 (3 反復中央値, loadavg 0.5〜1.1, 全 24 件 PASS)。素材は合成 wasm 17,114,230B (関数 ~360B 単位のコード様バイト列; 実 lift wasm ではない) → br-11 6,214,503B (36.3%)。

| 帯域 | 配信 | streaming ms | bytes ms | 線上 B |
|---|---|--:|--:|--:|
| 100 Mbps | 非圧縮 | 1403.6 | 1435.2 | 17,114,230 |
| 100 Mbps | **br-11** | **516.8** | 553.8 | 6,214,503 |
| 無制限 (loopback) | 非圧縮 | 74.0 | 90.0 | 17,114,230 |
| 無制限 (loopback) | br-11 | 136.6 | 164.2 | 6,214,503 |

- 100 Mbps では br-11 で **2.7×** 短縮 (1403.6 → 516.8 ms)。streaming は bytes より 36〜38 ms 速い (compile が転送に隠れる分)。
- 帯域無制限では br の展開 (Chrome ネットワークスタック) が +40〜60 ms 乗る (br streaming 136.6 vs 非圧縮 74.0)。転送が支配的な回線 (≲ 数百 Mbps) で有利、ローカル/超高速回線では逆転する。
- 圧縮率は合成素材の値 (36.3%)。実 lift wasm の brotli-11 は §0 転送行 (31.0〜37%) と `tools/runtime/DESIGN.md` (M11 3.31×) を使うこと。

範囲外 / 未解決:

| 未解決 | 影響 | 起票先 |
|---|---|---|
| **案 S (Static Assets) で br-11 を使う経路が未確定**: `_headers` の `Content-Encoding: br` は二重エンコード (`deploy/EDGE-SIM.md` #9)、エッジ自動圧縮は zstd/br の level 不明。実エッジでの wire サイズ・`Content-Encoding` の実測が無い | 本 issue の「CDN 配信設定」が未達 | #170 に残置 (Closes しない)。実エッジ計測は Access 資格情報が必要 |
| R2 (`legacy-r2/20-upload.mjs --precompress br`) への実 PUT・ブラウザ透過復号は未実証 (S3 キー無し) | R2 へ戻す場合のみ | `deploy/REPORT.md` §7 の既存起票 (#8) |
| 大物 (>24MiB) は br でなく事前非圧縮 part で配信 (`fetchCompile` 関数レベルまで結線・runtime manifest 経路は未接続・決定は DECISIONS D9、合成 32.6MiB 実測は `REPORT_P13.md`)。実 FLEngine 規模の実測は未了 | 本番 runtime からは未到達 (manifest 経路)。>24MiB 実 FLEngine wasm の配信実測も未了 | manifest 経路 #1166 `[PERF-P18]`・実測 #1150 `[PERF-P16]` |
| 実 FLEngine 規模 (K=10〜100) での streaming 隠蔽効果は合成 17MB のみ。他ブラウザ/実回線は未測 | — | PERF-P9 (§7) |

## 11. AudioWorklet 向け wasm ローダ (PERF-P3 / #162)

既知類型との関係: 該当なし (lift 無し・ローダ + 合成 wasm の計測)。検証起点 commit: `c3cd3e8` (detached worktree で 3 回実行)。
実装: `src/runtime/worklet_loader.ts` (main 側 API `createWasmWorkletHost` → `host.load(bytes, {prewarmBlocks, keepModule, stubImports})`・`host.firstBlocks()`・`host.probeModulePost()`) と
`public/worklets/wasm-host-worklet.js` (processor `wasm-host`: bytes 受信 → `WebAssembly.compile` → `instantiate` → `ws_init` → pre-warm → `ws_reset` → `loaded` 通知、`process()` が最初の 16 ブロックの処理時間と先頭 4 ブロックの入出力を報告)。
wasm ABI `ws_v1`: export `memory` / `ws_buffers()->i32` (in[128] f32 直後に out[128] f32) / `ws_process(i32)`、任意 `ws_init` / `ws_reset`。違反は `loaded` ではなく `error` で reject (e2e で確認)。

e2e: `node tools/perf/loader/loader_e2e.mjs [--reps 5] [--quick]` (Chrome 起動は条件×反復ごとに新規 = NativeModule キャッシュを持ち越さない。`gen_wasm.mjs` が emcc 不要の合成 wasm を生成)。
対象 wasm: small = 4,778 B (1000 → 64 段 IIR)、big = 33,554,432 B (1000 段 + 各段 nops 200 + 呼ばれない filler 関数 90,000 + padding section; lazy compile 対象は約 1000 関数)。OTT/FLEngine 実 wasm ではない。
計測は 48 kHz AudioContext・headless Chrome 154 (null sink)・runner 4 コア。worklet 内は `Date.now()` のみ (**1 ms 分解能**)。

検査 (7 項目、3 回とも PASS 7 / FAIL 0。所要 34.7 / 33.9 / 34.5 s、終了時 loadavg 4.5 / 5.7 / 7.7): Module 直 postMessage が messageerror になる・transfer 後に main の buffer が detach・main Module 保持・先頭 4 ブロックの出力が参照モデル (JS, 全段 fround) と bit 一致 (4 ブロック×128 サンプル・非ゼロ 128)・ABI 違反 wasm の reject。
ネガティブコントロール: 参照への入力を 1 サンプル 0.001 ずらすと 4/4 ブロックが不一致 → FAIL 判定が効く。1000 段の初版 (係数でゲイン > 1 → Infinity) は bit 一致検査が `mism=3` で FAIL し、係数修正で解消した。

| 条件 (n=5 の中央値、3 回実行の範囲) | worklet compile ms | main compile ms | roundtrip (transfer→loaded) ms | block0 ms | 最初の 16 ブロックの最大 ms |
|---|--:|--:|--:|--:|--:|
| small / pre-warm 0 / keep 0 | 0〜1 | - | 1.4 前後 | 0〜1 | 0〜1 |
| big / pre-warm 0 / keep 0 | 21〜23 | - | 21.6〜29.6 | **6〜9** | **6〜11** |
| big / pre-warm 8 / keep 0 | 20〜22 | - | 32.8〜42.8 | **0〜1** | **1〜2** |
| big / pre-warm 0 / keep 1 | 21〜23 | 27.9〜33.2 | 21.4〜27.5 | 6〜10 | 6〜10 |
| big / pre-warm 8 / keep 1 | 20〜21 | 29.0〜31.8 | 32.4〜41.8 | 0〜1 | 1 |

- **pre-warm の効果**: 初回ブロックの処理 6〜11 ms (128f = 2.67 ms の予算の 2〜4 倍 = 初回で underrun) → 0〜2 ms。コストは load の roundtrip +11〜13 ms (pre-warm 8 ブロックの計 11〜12 ms を worklet 内で払う)。small (関数 ~65) では初回も 0〜1 ms で差は 1 ms 分解能以下。
- **main 側 Module 保持 (`keepModule`) は lazy compile では効果なし**: worklet compile は keep 0/1 とも 21 ms 前後で変わらず、main compile (27.9〜33.2 ms) が startup 〜 first16 に**加算** (66〜75 ms → 90〜118 ms)。§3 の「main で eager compile 済みなら worklet 33 ms」は **eager (`--no-wasm-lazy-compilation`) 時の NativeModule 共有**の話で、既定 lazy では当てはまらない (本実験の Chrome は既定 flag)。→ 既定では `keepModule` は使わず、eager 設定を採るときだけ要再測。
- load 完了から ctx.resume → 最初の 16 ブロック完了までは 25〜47 ms (small 28〜47 / big 25〜47, null sink の起動待ちが支配; wasm サイズ依存ではない)。startup→first16 (transfer 開始から計): small 32〜50 ms、big 61〜75 ms (keep 0)。
- 再現: 上のコマンド 1 本。生データ `tools/perf/loader/work/loader_e2e.jsonl` (gitignore)。

| 未解決・限界 | 影響 | 起票先 |
|---|---|---|
| 合成 wasm のみ。bit-exact OTT (x64c) / FLEngine 実 closure の worklet 計測は未実施 (REPORT §5.4: FLEngine wasm 未存在) | pre-warm 効果量 (6〜11 ms) は実 closure で変わる | PERF-P9 (#168: bit-exact OTT の Chrome Worker / AudioWorklet 再測) にコメント。FLEngine 実 closure の起動〜初回 audio E2E (旧 P6 案) は issue 未起票 → PM 判断で新規起票 |
| `Date.now()` 1 ms 分解能・null sink (headless)。実デバイスの underrun 計測なし | 初回ブロック < 1 ms は判別不能・実 underrun 未評価 | PERF-P7 (#165: 実機再測) |
| eager compile + keepModule の効果 (§3 の 481→33 ms) をローダ経由で未再測 | keepModule の採否判断 | 本 issue のコメントで PM 判断 (必要なら子チケット) |
| 本ローダ (perf 計測対象) は `src/index.ts` に未接続 (オーディオ本番経路は AU-9 #185 の `FlAudioShim`。旧 `audio.ts` は削除済み) | ローダは未接続の部品 | RT / AU 系 (FLEngine 結線時) |

## 12. bit-exact OTT の RTF 再測 — Chrome Worker / 実 AudioWorklet / 低負荷 / native 比 (PERF-P9 / #168)

全文・表・未解決は `REPORT_APPENDIX.md` §12 (検証起点 `1f98990`、再現 `bash tools/perf/x64c_suite.sh`)。結論: **node = Chrome Worker = 実 AudioWorklet (±4%)**、AudioWorklet で 128f 時間超過 0 / 15,000 block、LTO 1.2×、native 実機械語比 3.6〜4.4×。**M11 級 closure での LTO 効果は未測** (`fl-win64` + FLEngine x64c lift が必要 → 新規 `[PERF-P12]` 起票依頼)。
