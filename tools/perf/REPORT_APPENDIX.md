# tools/perf REPORT 付録 — §12 PERF-P9 (#168): bit-exact OTT の RTF 再測

> 正本: `tools/perf/REPORT.md` (§12 に要約)。行数上限 (250 行, `docs/DOC_MAP.md` §1) のため全文をここに置く。

既知類型との関係: 該当なし (lift 無変更・計測のみ)。検証起点 commit: `1f98990` (コミット済み HEAD で `TAG=run2 REPS=5 bash tools/perf/x64c_suite.sh`、所要 7 分 42 秒)。
対象: tools/ott の x64c lift (75 関数 / 5,790 命令) を emcc 6.0.12 でビルドした wasm の `processReplacing` 128 フレーム。

## 12.0 結論

| 論点 | 実測 (中央値、範囲は n=5 反復の p50) |
|---|---|
| Chrome Worker / 実 AudioWorklet は node と同値か | **同値 (±4%)**: o2 p50 = node 61.5 / Worker 60.0 / AudioWorklet 60.7–64.2 µs、o3lto = 50.7 / 50.0 / 50.3–52.9 µs。RTF@48k (AudioWorklet p50) = o2 0.0238 / o3lto 0.0193 |
| AudioWorklet で 128f 時間 (2667 µs @48k) を超えるか | **0 / 15000 block** (o0・o2・o3lto・o3ltosimd 各変種)。最悪 max は o0 1574 µs・o2 404 µs・o3lto 432 µs |
| LTO の効果 (o2 → o3lto) | node **1.21×** / Worker 1.20× / AudioWorklet 1.23× (§2.1 は 1.15×、gate は 1.18〜1.20×)。M5 や junk 版のような桁違いは無い |
| `-msimd128` (o3lto 比) | **退行** node 1.52× / Worker 1.50× / AudioWorklet 1.47× (§2.1 の 1.4× 退行を再確認) |
| native 実機械語との比 | native p50 = **14.00–14.17 µs** (RTF@44.1k 0.00485)。wasm は o2 4.4× / o3lto 3.6× / o0 24.8× 遅い (node ÷ native) |
| 負荷依存 (busy loop 4 本で 4 vCPU 飽和、loadavg 3.2〜7.8) | p50 は node・Worker・native で **1.4〜1.5×** (native も同率; node ÷ native は o2 4.64× / o3lto 3.74× で不変)、AudioWorklet の 500 block 平均は 1.5〜2.4×。支配的リスクは p50 でなく**尾**: AudioWorklet で 128f 時間超過 1 / 9000 block (o2, 3324 µs)。詳細は §12.2 末尾 |

## 12.1 測定系

`bash tools/perf/x64c_suite.sh` 1 本 (`TAG`・`REPS`・`BUSY`・`VARIANTS` で調整)。`tools/ott/ott_e2e.sh --quick` (native 実機械語と bit-exact: 22 シナリオ・9,620 cell・max_ulp 0) → `ott_x64c_build.sh` (7 変種) → 下の 4 環境。
全環境が**同一の wasm と同一の core** (`harness/x64c_core.mjs`: emscripten glue 無しで `ott_run` を直接叩く) を使い、出力署名 (1000 block 処理、先頭 8 + 1000 block 目の FNV) を毎回照合する。

- node: `x64c_node.mjs` 1 変種 1 プロセス、warm-up 後 20,000 block 個別計時 (`performance.now`)。
- Chrome Worker: `x64c_chrome.mjs <tag> worker`。反復ごとに Chrome を新規起動 (headless=new, cross-origin isolated → timer 分解能 5 µs。表の p50 が 5 µs 刻みなのはこのため。`batch64` = 64 call 平均で補う)。
- 実 AudioWorklet: `x64c_chrome.mjs <tag> worklet`。`AudioContext` 48 kHz の本物の worklet スレッドで wasm を compile・instantiate し、(1) 連続実行 500 block × 20 chunk の `Date.now` 平均、(2) **AudioContext が `process()` を駆動する状態で 3,000 block の `process()` 内 wasm 1 block 所要を個別計測**。worklet には `performance` が無いため、`x64c_clock.js` (Dedicated Worker が `Atomics.store` を回し続ける SAB カウンタ時計、分解能 1 tick = 9.2 ns (1 ÷ 109 ticks/µs) の差分を使う。ticks→µs は (カウンタ総進行 / `Date.now` 総経過) で較正 (worklet 側較正 106.0–116.6 ticks/µs と時計 worker 側 106.0–115.9 ticks/µs が一致)。`--noclock` は時計 worker 無しの対照 (bench 平均のみ)。
- native: `native/native_bench.sh` (`libottnative.so` が OTT_vst2_win64.dll を VA 通りに敷設し MS x64 ABI で実機械語を実行; `ott_call` 1 回を `clock_gettime` で個別計時、20,000 回 × 7 反復)。署名も wasm と一致 (`6b1696f0`)。

環境: GitHub Actions runner、AMD EPYC 9V45 (4 vCPU = 2 core × 2 SMT)、node v22.23.3、Chrome 154.0.8037.97 (V8 15.4)、emsdk 6.0.12。loadavg(1 分) は node 1.09〜1.25、Worker 1.02〜2.40 (Chrome 自身を含む)、AudioWorklet 1.37〜1.99 (時計 worker が 1 vCPU を使う分を含む)、native 1.21〜1.23。**§2.1 (Ryzen 9 9950X 16C・node 26・loadavg 19〜20) とは CPU・node が違う**ので絶対値の差は負荷だけに帰せない。比で比較すること。

## 12.2 結果 (全表は `results/x64c/summary_run2.md`、生データ `results/x64c/*_run2.jsonl`)

| 変種 | wasm B | node p50 µs | Worker p50 µs (batch64) | AudioWorklet p50 / p99 / max µs | RTF@44.1k (node) | node ÷ native |
|---|--:|--:|--:|--:|--:|--:|
| o0 | 1,030,416 | 348.7 (332.6–366.6) | 400.0 (393.0) | 401.7–464.7 / 451.1 / 1574 | 0.1201 | 24.8× |
| o1 | 793,117 | 82.3 (79.0–86.3) | 135.0 (134.3) | (未測) | 0.0284 | 5.8× |
| o2 | 707,139 | 61.5 (59.4–63.6) | 60.0 (61.7) | 60.7–64.2 / 87.8 / 404 | 0.0212 | 4.4× |
| o3 | 711,842 | 59.3 (58.1–60.8) | 60.0 (61.3) | (未測) | 0.0204 | 4.2× |
| o2lto | 675,568 | 50.3 (48.9–51.4) | 50.0 (51.8) | (未測) | 0.0173 | 3.6× |
| o3lto | 680,905 | 50.7 (49.1–52.0) | 50.0 (51.3) | 50.3–52.9 / 65.0 / 432 | 0.0175 | 3.6× |
| o3ltosimd | 675,854 | 76.9 (74.9–77.5) | 75.0 (74.3) | 74.5–77.3 / 86.1 / 293 | 0.0265 | 5.5× |

- AudioWorklet 列: p50 は 5 反復の範囲、p99 は反復の中央値、max は 5 反復 × 3,000 block 中の最大。時計 worker 無しの対照 (Date.now 平均, 5 反復): o2 60.6–62.2 / o3lto 50.9–52.8 µs で、時計 worker の有無は結果に影響しない。
- Chrome Worker の **o1 だけ node の 1.6× 遅い** (135.0 vs 82.3 µs)。junk 版でも観測済みの現象 (§0)。production は O2 以上なので影響は小さいが原因未調査。
- インスタンス数/コアの目安 (**推定**): 1 ÷ RTF = o3lto で 57 (node, 他負荷無し・1 instance 定常 p50 から)。ただし 1 instance が linear memory 864 MiB (905,969,664 B) を確保するため、多 instance ではメモリが先に律速する (P4 低位再配置, §7)。
- 構造的な理由 (**推定**): x64c lift は CPU 状態 (`R[]`/`X[]`/flags) を linear memory 上に置く 1:1 変換で、native のレジスタ割付が失われるため wasm/native 比が 3.6〜4.4× になる。LTO で縮むのは関数境界の分 (1.2×) まで。
- AudioWorklet の駆動 (headless Chrome, null sink): `process()` はハードウェア buffer 単位のバーストで呼ばれ、入口間隔の最大は 10.1〜12.6 ms (`baseLatency` 10.02 ms = 481 frame 相当のバースト)、平均間隔は 1.73〜2.48 ms (128f = 2.667 ms 未満)。1 バースト 4 quanta の合計は o2 の p50 から 4 × 63.4 = 253.6 µs (10 ms 周期の 2.5%)。実デバイスの underrun は評価できない (PERF-P7 #165)。
- 時計の限界: 時計 worker が OS に止められると process() 中の tick が進まず所要を過小評価する (0 tick の呼出: o0 0 / o2 20 / o3lto 4 / o3ltosimd 2 件 / 各 15,000)。max は下限値として読むこと。p50 は Date.now 平均と一致 (o2: 60.7–64.2 vs 61.3–65.4 µs) するので影響しない。

### 負荷対照 (`BUSY=4 TAG=busy4 REPS=3 VARIANTS="o2 o3lto" WL_VARIANTS="o2 o3lto"`)

BUSY=4 (4 本の busy loop を並走; loadavg(1 分) node 3.20〜4.04・Worker 4.04〜4.75・AudioWorklet 4.93〜6.70・native 7.71〜7.78)、REPS=3、変種 o2・o3lto。右端は idle (run2) の値。

| 環境 | 変種 | busy p50 µs | busy p99 / max µs | idle p50 µs | idle p99 / max µs |
|---|---|--:|--:|--:|--:|
| node | o2 | 91.5 (91.3–92.0) | 3100.1 / 8105 | 61.5 | 74.0 / 436 |
| node | o3lto | 73.8 (73.7–75.3) | 89.1 / 6645 | 50.7 | 80.2 / 515 |
| Chrome Worker | o2 | 90.0 | 740 / 11135 | 60.0 | 85 / 720 |
| Chrome Worker | o3lto | 75.0 | 185 / 6095 | 50.0 | 75 / 845 |
| AudioWorklet (Date.now 平均, 時計 worker 無し) | o2 | 111.3–135.2 | (個別計測は下記) | 60.6–62.2 | 87.8 / 404 |
| AudioWorklet (同上) | o3lto | 76.9–127.0 | (同上) | 50.9–52.8 | 65.0 / 432 |
| native 実機械語 | — | 19.60–19.86 | 28.0 / 6038 | 14.00–14.17 | 19.7 / 85 |

- AudioWorklet の個別計測 (SAB 時計): 128f 時間 (2667 µs) 超過は **o2 で 1 / 9000 (最大 3324 µs)**、o3lto で 0 / 9000 (最大 2312 µs、1 ms 超は 4 件)。ただし busy 下では時計 worker が飢餓し 0 tick の呼出が o2 2421 件・o3lto 3158 件 / 各 9,000 (idle は 0〜20 件) なので、超過数・max は**下限値**であり p50・p99 は信用しない。
- 4 vCPU は 2 core × 2 SMT で、busy loop は SMT 兄弟スレッドと同一 core を奪い合う。node・Worker・native の p50 が 1.4〜1.5× 悪化するのはそのため (wasm 固有の劣化ではない)。§2.1 の「別 loadavg 下で o2 90 µs / o3lto 72 µs、比 1.25×」と同水準 (本 run の busy は 91.5 / 73.8 µs、比 1.24×)。
- busy でも AudioWorklet の 500 block 平均は最悪 180.6 µs/block (RTF@48k 0.068、時計 worker 有りの bench)。リアルタイム性を損なうのは計算量でなく、スケジューラ preempt による ms 級の尾 (max 2.3〜11 ms)。ホスト負荷が高い環境では 128f (2.67 ms) 単位の駆動に余裕が無い (**推定**: 実デバイスの buffer 長・優先度は未評価)。

## 12.3 検証

- 署名: run2 の全 117 実行 (node 35・Worker 35・AudioWorklet 20+20・native 7) が `6b1696f0` 一致、失敗実行 0。native 実機械語の署名も同一 = wasm と native の出力が 1000 block 目まで bit 一致。
- 別アルゴリズム検算: (a) AudioWorklet の独立 2 時計 (SAB カウンタ vs `Date.now` 区間平均) が ±3% で一致、(b) glue 版 `ott_x64c_bench.mjs` (別 harness) と x64c_core の p50 が一致: o2 p50 60.78–61.92 µs (x64c_core は 59.4–63.6)・o3lto 51.44–54.04 µs (同 49.1–52.0)、署名同一 (3 反復, `results/x64c/glue_xcheck_run2.jsonl`)。
- ネガティブコントロール: `x64c_summary.mjs run2 deadbeef` → 署名検査 FAIL。`x64c_negctl.mjs` で入力 1 sample を +1 ulp → 署名 `66977194` (≠ `6b1696f0`) で検出。wasm 1 byte (bit0) 反転 20 箇所 → o2 で 1 箇所・o3lto で 3 箇所が例外 (他は未到達の lift 関数内で無害 = 署名不変)。時間側: 意図的に遅い o0 は o2 比 node 5.7× / Worker 6.7× / AudioWorklet 6.8× で全環境が検出。
- 範囲: OTT 1 instance・128 フレーム・44.1/48 kHz・Chrome 154 / node 22 / Linux x86-64 (Zen 5) のみ。範囲外: 複数 instance 同時、実オーディオデバイス、Firefox/Safari/モバイル。

## 12.4 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| **M11 級 closure での LTO 効果が未測** (bit-exact な M11 級 = `tools/flelift` の FLEngine x64c lift。`fl-win64` 素材と長時間 lift/link が必要で本 run の素材 (toolchain-emsdk / analysis-ott-binaries / plugins-ott) と 60 分では不足) | #168 の 4 点中 1 点が未達 (Closes しない) | 新規 `[PERF-P12]` の起票依頼 (#168 コメントに本文案、必要素材 `oc_artifacts: fl-win64 toolchain-emsdk`) |
| 実オーディオデバイス (headful) での underrun、他ブラウザ/モバイル CPU (3〜10× 低速想定) | 実時間余裕は null sink の値 (RTF 0.02 級) | PERF-P7 (#165) にコメント |
| 1 instance = 864 MiB の linear memory | 多 instance・多プラグインの実用上限をメモリが決める | §7 P4 (低位再配置) |
| Chrome Worker の o1 が node の 1.6× 遅い原因 | production(O2+) では影響小 | #168 に残置 (必要なら PM が新規) |
| Chrome 用の perf 回帰ゲート (gate は node のみ) | Chrome 側回帰を検知できない | PERF-P5 (#164) にコメント (`x64c_suite.sh` の Worker 比 o2/o3lto ∈ [0.9, 2.0] 等を判定化できる) |
