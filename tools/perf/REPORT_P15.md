# tools/perf REPORT_P15 — 実 OTT の Chrome Memory 本数上限 (124〜125) に対する instance 数の設計 (PERF-P15 / #990)

**結論**: 方式 (a) を採る。**1 instance (Memory 1 本) の中に plugin の処理オブジェクトを畳み込む**。
Chrome 154 の Memory 本数上限は 1 Worker あたり 124〜125 本。Worker を分けると合計が増えることもあるが、割り当ては再現せず不安定なため、(b) Worker 分割では N=130 を確実に通せない。
Chrome Dedicated Worker で M=130 のオブジェクトを 1 Memory に畳み、instantiate 失敗なし・全 130 obj の署名が既知値 `6b1696f0` と一致した (3 回)。

| 項目 | 結果 |
|---|---|
| **採る方式** | (a) 同一 Memory への畳み込み (1 instance 内の複数オブジェクト) |
| **退けた方式** | (b) Worker 分割: 同一 renderer 内で合計 124〜253 本で頭打ち。(c) 低位 base・小 Memory 化: #91 の完了が前提で本 issue 単独では成立しない |
| **N=130 の駆動** | Chrome 154 Dedicated Worker, Memory 1 本 (864 MiB), M=130 obj: 3 回とも `sig_ok=true` (130/130 一致)、instantiate 失敗なし |
| **定常コスト** | M=1: 138.41 / 139.71 / 138.50 µs/block (p50)。M=4: 140.58 / 139.09 / 139.12。M=130: 140.56 / 140.75 / 139.73。obj 当たり横ばい |
| **setup** | M=130 で 790〜999 ms (obj 当たり約 6〜8 ms)。起動時に一括で行う前提 |

## 0. 検証起点

- 検証起点: `origin/main` = `a5adb2fc` の worktree `ws-990` (branch `990-perf-p15-instance-cap`) で計測。素材 `work-m6-ott` を `tools/ott/work/` に展開 (gitignore)。
- 環境: Chrome 154.0.8037.97 (headless), CPU `AMD EPYC 7763 64-Core Processor` (4 vCPU), node v22.23.3。load average は計測ごとに記録 (表内 `loadavg` 参照)。
- 測定コードの最終変更 (実測を取った HEAD 再実行の起点): `862ef65b`。以後の差分 `git diff 862ef65b 638ae3fc -- tools/perf` は以下のとおり。`page.html` の `message` リスナー削除は、測定スクリプト (`probe_limit.mjs` / `probe_iso.mjs` / `chrome_shared.mjs`) が `p.eval` で `probeWorkers` を直接呼ぶため測定経路に入らず、数値に影響しない (再測定不要)。
  ```diff
  -// 親ページからの依頼 (iframe 経由 = 別 site = 別 renderer プロセス) に応答する。
  -window.addEventListener('message', (ev) => {
  -  if (!ev.data || ev.data.p15 !== 'probe') return;
  -  window.probeWorkers(ev.data.k, ev.data.max).then((r) => ev.source.postMessage({ p15: 'reply', r }, ev.origin));
  -});
  ```
  (REPORT の変更は §3 の表と生データ件数の記載のみ。)

## 1. 上限の所在 (renderer 単位か Worker 単位か)

`tools/perf/p15/probe_limit.mjs` (Worker を K 個に分け、各 Worker で instance を max=160 まで生成。instance は駆動しない)。
`tools/perf/p15/results/probe_limit.jsonl` の 6 行:

| K (Worker 数) | run | 各 Worker の成功数 | 合計成功 | 失敗 |
|---|---|---|---|---|
| 1 | 0 | 125 | 125 | `Out of memory: Cannot allocate Wasm memory for new instance` |
| 2 | 0 | 63, 61 | 124 | 同上 |
| 4 | 0 | 36, 125, 40, 42 | 243 | 同上 |
| 1 | 1 | 125 | 125 | 同上 |
| 2 | 1 | 125, 63 | 188 | 同上 |
| 4 | 1 | 64, 124, 40, 25 | 253 | 同上 |

- K=1 の上限は 125 本 (2 run とも)。K を増やすと合計は増えるが、同条件 (K=2 で 124 と 188、K=4 で 243 と 253) で値が大きくばらつき、各 Worker の本数も偏る (K=4 run 0 は 36・125・40・42)。
- 結果が再現しない配分では、「N 本の plugin を Worker k に決め打ちで置く」設計を保証できない。よって (b) は採らない。
- 6 行は n=2 で、ばらつきの原因は未切り分け (推定: Chrome の renderer/GC の配分)。

`tools/perf/p15/probe_iso.mjs` (同一 Chrome で origin を変えた 2 ページ = 別 site = 別 renderer。各 k=1, max=160。`renderers` は実測の renderer プロセス数):

| run | renderers | origin A (localhost) 成功 | origin B (127.0.0.1) 成功 |
|---|---|---|---|
| 0 | 7 | 124 | 124 |
| 1 | 7 | 124 | 125 |

- 別 renderer 側でも各 124〜125 本で止まる。renderer を分けると合計は増えるが、renderer 数は site isolation の挙動に依存して制御できないため、plugin 数の上限を renderer 数で稼ぐ設計は取れない。
- 補足: iframe 経由の別 origin 版は COEP (`require-corp`) で応答が返らず計測不能だった (試作は削除済み)。

## 2. 畳み込みの検証 (node)

`tools/perf/p15/shared_obj.mjs <ottl.cjs> <M> [BLK]`。1 instance の中に M 個の OTT 処理オブジェクト (`OBJ` を個別の VA に配置。stride 0x40000、入力・出力・buffer も個別) を置き、各 obj を 1000 block 駆動して署名を取る。

| M | load ms | setup ms | µs/block p50 (BLK=50) | 署名 (unique) | 判定 |
|---|---|---|---|---|---|
| 1 | 28.51 | 25.16 | 139.01 | `6b1696f0` (1) | OK |
| 4 | 22.71 | 41.14 | 138.83 | `6b1696f0` (1) | OK |
| 130 | 23.81 | 795.9 | 141.01 | `6b1696f0` (1) | OK (sig_n=130) |

- M=1 の署名 `6b1696f0` は `tools/perf/p8/real/bench_real.mjs` の既知値と同一。M=130 でも全 obj がこの値になり、obj 間の状態は汚染されない。
- 注: 定常の比較は §3 の Chrome 表を正とする (本表は署名確認が目的)。本表の node 行 (load・setup・署名) に対応する生データは `tools/perf/p15/results/` に無い。署名の根拠は §3 の Chrome 行 (`results/chrome_shared.jsonl` の `sig_ok`) とし、本表の node 行は参考値。

## 3. Chrome 実測 (受入条件: N=130 の駆動)

`tools/perf/p15/chrome_shared.mjs --m 1,4,130 --reps 7 --blk 1000 --runs 3`。1 Worker 内で instance 1 本 (Memory 864 MiB)、M obj を畳み込み。条件×反復ごとに Chrome を新規起動。
生データ: `tools/perf/p15/results/chrome_shared.jsonl` (10 行。下表の 9 行 + HEAD 再実行 1 行。HEAD 再実行は中央値の計算には含めていない)。

| M | run | µs/block p50 [min–max] | RTF@44.1k / obj | load ms | setup ms | 署名 | renderer RSS 増分 MiB |
|---|---|---|---|---|---|---|---|
| 1 | 0 | 138.41 [138.12–156.07] | 0.04769 | 15.59 | 36.87 | `6b1696f0` (1/1) | 63.2 |
| 1 | 1 | 139.71 [139.04–148.04] | 0.04813 | 7.43 | 23.53 | `6b1696f0` (1/1) | 107.5 |
| 1 | 2 | 138.50 [138.04–146.33] | 0.04772 | 13.88 | 33.54 | `6b1696f0` (1/1) | -13.2 |
| 4 | 0 | 140.58 [138.75–179.14] | 0.04843 | 12.97 | 66.66 | `6b1696f0` (4/4) | 336.5 |
| 4 | 1 | 139.09 [138.59–179.14] | 0.04792 | 13.33 | 65.76 | `6b1696f0` (4/4) | 318.7 |
| 4 | 2 | 139.12 [138.78–169.39] | 0.04793 | 16.07 | 61.94 | `6b1696f0` (4/4) | 360.3 |
| 130 | 0 | 140.56 [140.28–141.68] | 0.04843 | 14.24 | 998.8 | `6b1696f0` (130/130) | -150.5 |
| 130 | 1 | 140.75 [140.47–141.28] | 0.04849 | 18.15 | 807.46 | `6b1696f0` (130/130) | -123.1 |
| 130 | 2 | 139.73 [138.80–141.15] | 0.04814 | 11.17 | 789.91 | `6b1696f0` (130/130) | 368.5 |
| 130 | HEAD 再実行 (`862ef65b`) | 139.02 [138.56–139.62] | 0.04790 | 11.13 | 779.63 | `6b1696f0` (130/130) | -152.2 |

- M=130 の µs/block p50 の中央値は 140.56 µs (run 0〜2 の 3 回の中央値。4 行目の扱いは §6 参照)。M=1 の中央値は 138.50 µs。obj 数に依らず定常はほぼ平坦 (+1.5%)。
- RTF は 1 obj あたり 0.0477〜0.0485 (128 サンプル/44.1 kHz 換算)。
- renderer RSS の増分は負値を含み、原因は未切り分け。RSS は参考値で、受入判定には使わない。

## 4. 未解決・限界

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 異なる plugin (OTT + Fresh Air) を 1 Memory に畳む際の emcc 静的データ・heap の衝突と、node での署名一致 (本計測は同一 OTT の M 個 = 同一 binary の別 state)。Fresh Air は lift 時に画像窓を分けた (§8) | 畳み込みは未検証。異なる plugin を同居させる場合は未検証 | #3680 [PERF-P23] (#2963 から分割) |
| AudioWorklet 上の M=130 の instantiate・署名一致 | 解消 (本 PR): §7 で 130/130 一致・instantiate 失敗なし | なし (§7 で解消) |
| AudioWorklet 上の instantiate 上限 (M=130 を超える M) | 測定点の範囲で成功最大 M=145、失敗最小 M=146 (無応答、各 3 run)。147 以上と M=2〜129・131〜144 は未測で単調性は未確認。原因は未切り分け (§9) | #3959 [PERF-P25] (親 #2988) |
| setup 時間 (M=130 で 790〜999 ms、Dedicated Worker・§3) | 起動時の一括 instantiate/setup の遅延。pre-warm の設計が必要 | REPORT_P8 §11 (pre-warm) と同じ経路 |

## 5. 再現

```sh
export PERF_TMP=$RUNNER_TEMP/perf
node tools/perf/p15/probe_limit.mjs --k 1,2,4 --max 160 --runs 2   # §1
node tools/perf/p15/probe_iso.mjs --k1 1 --k2 1 --max 160 --runs 2  # §1 (別 renderer)
node tools/perf/p15/chrome_shared.mjs --m 1,4,130 --reps 7 --blk 1000 --runs 3  # §3
```

前提: `oc_artifacts: work-m6-ott` (`tools/ott/work/lift/ottl.wasm`・`ottl.cjs`)。

## 6. 再測定 (2026-10-14, 素材 work-m6-ott で 4 スクリプトを実行)

- 測定 commit: `2b2faf52` (origin/main の worktree `ws-990`)。`tools/perf/p15` の差分は `862ef65b` 以降 `page.html` の未使用リスナー削除のみ (測定経路外・§0)。
- 環境: Chrome 154.0.8037.97 (headless), CPU `AMD EPYC 9V45 96-Core Processor` (4 vCPU。§0 の 7763 とは別機), node v22.23.3。
- 生データ: `tools/perf/p15/results/rerun_20261014_*.jsonl` (`probe_limit` 6 行・`probe_iso` 2 行・`chrome_shared` 9 行。いずれも本再測定の行のみで、`2b2faf52` の既存 `results/*.jsonl` と完全一致する行は除外)。
- `shared_obj.mjs` (M=130 の `sig_unique` / setup 時間) は本節の根拠から外す。同じ実行の生データ (標準出力) が残っておらず、jsonl にも保存できなかったため。N=130 の署名一致は下表の `chrome_shared` M=130 の 3 行 (`sig_ok=true`、sig_n=130) で示す。

| 項目 | 前回 (`862ef65b`, EPYC 7763) | 再測定 (`2b2faf52`, EPYC 9V45) |
|---|---|---|
| probe_limit K=1 (Worker 1 個) | 125 | 125 / 125 (2 回) |
| probe_limit K=2 合計 | 124 / 188 | 125 / 124 |
| probe_limit K=4 合計 | 243 / 253 | 182 / 216 |
| probe_iso 別 origin 各 1 Worker | 124〜125 | 124〜125 (renderers=7, 2 回とも) |
| chrome_shared M=1 µs/block p50 (3 回) | 138.41 / 139.71 / 138.50 | 135.89 / 120.08 / 126.17 (中央値 126.17) |
| chrome_shared M=4 µs/block p50 (3 回) | 140.58 / 139.09 / 139.12 | 121.59 / 140.77 / 140.01 (中央値 140.01) |
| chrome_shared M=130 µs/block p50 (前回 4 値) | 140.56 / 140.75 / 139.73 / 139.02 (中央値 140.15) | 118.93 / 125.70 / 138.69 (中央値 125.70) |
| M=130 署名 | 130/130 一致 (4 行, `sig_ok=true` 全て) | 130/130 一致 (3 回, `sig_ok=true` 全て) |

- 前回 M=130 の 4 行の出自: `fcc0eb02` 時点では M=130 は 3 行 (run 0〜2)。4 行目 (p50 139.02, `run: 0`, loadavg `[1.00, 0.83, 0.65]`, setup 779.63 ms) は `862ef65b` で 1 行だけ追記された行で、他の 3 行とは別の呼び出しの行と見られる。追記時の commit message・ログから実行の対応は確定できないため、表には 4 値をそのまま載せた。中央値は 4 値で 140.15 (3 値なら 140.56)。
- 結論は変わらない。M=130 を 1 instance で instantiate 失敗なし・全 obj 署名一致で駆動できる。obj 数に対する定常コストは横ばい (M=1 と M=130 の中央値の差は前回 +1.2% (138.50→140.15)、再測定では -0.4% (126.17→125.70))。機差 (CPU 世代) が大きく、絶対値は機ごとに比較しない。
- Worker 分割 (K=2) の合計は再測定でも 124〜125 で、N=130 に届かない。K=4 の合計は 182〜253 で、回ごとのばらつきが大きい。(b) を退けた根拠 (割り当てが再現せず不安定) は再測定でも成立する。
- chrome_shared の µs/block は run 間で 118.93〜140.77 に散る (全 9 行の min/max)。定常の数値は 1 回の値ではなく 3 回の中央値で読む。

**測定 commit から HEAD までの tools/perf 差分**: 測定コード (スクリプト) の差分は空。HEAD で追加されたのは `results/rerun_20261014_*.jsonl` の 3 ファイル (17 行) のみ。`git diff --stat 2b2faf52 HEAD -- tools/perf/p15` の出力は PR 本文の「検証」節と一致する。

## 7. AudioWorklet 上での M 個駆動の実測 (PERF-P19 / #1259)

**結論**: AudioWorklet (AudioWorkletGlobalScope) 上でも、1 instance (Memory 1 本) に OTT 処理オブジェクト M=130 を畳み込み、instantiate 失敗なし・全 130 obj の署名が既知値 `6b1696f0` と一致した (3 run。9 行すべて一致)。異なる plugin の畳み込みは本節の対象外で、子 issue #2963 [PERF-P20] に移した。

| 項目 | 結果 |
|---|---|
| 駆動方法 | `OfflineAudioContext` 上の `AudioWorkletProcessor`。1 render quantum (128 frame) ごとに全 obj を 1 block ずつ process する。音声デバイス不要 |
| 署名 | 9 行すべて `6b1696f0`。M 個全て一致 (M=1: 1/1, M=4: 4/4, M=130: 130/130)。instantiate 失敗・error 行なし。memory は各 864 MiB |
| 定常 (µs/block p50 の 3 run 中央値) | M=1: 134.00 / M=4: 145.75 / M=130: 139.80 |
| 読み方 | M=1 (134.00) に対し M=130 (139.80) は +4%。M=4 が M=130 より高く単調増加ではない。1 run 内の min〜max の幅は M=1 で 10〜39 µs、M=4 で 16〜30 µs、M=130 で 4〜12 µs (下表の [min–max] から算出)。M=1 と M=4 の幅が大きく、傾向は断定できない |
| Worker との比較 | §6 再測定の Dedicated Worker M=130 中央値 125.70 (同じ EPYC 9V45)。run 間の散らばり (worklet M=130: 115〜145) の中にあり、差の有無は n=3 では判定しない |

- 測定 commit: `80298b02` (`tools/perf/p15/chrome_worklet.mjs`・`web/shared_worklet.js`・`web/worklet_page.html`)。
- 環境: Chrome 154.0.8037.97 (headless), CPU `AMD EPYC 9V45 96-Core Processor` (4 vCPU), node v22.23.3。素材 `work-m6-ott` (`tools/ott/work/lift/ottl.wasm`)。
- 時刻の取り方: AudioWorkletGlobalScope には `performance` が無い (`ReferenceError` を確認)。rep ごとの時間は `Date.now()` (1 ms 分解能) で取る。M=1 の 1 rep は約 0.13 s で、1 ms は約 0.8%。M=130 の 1 rep は約 18 s で、分解能の影響は無視できる。
- 条件: 1 run = 署名区間 1000 quantum + warm 300 quantum + 計測 7 rep × 1000 quantum。Chrome は条件×反復ごとに新規起動。

| M | run | µs/block p50 [min–max] | loadavg (1 分) | 署名 |
|---|---|---|---|---|
| 1 | 0 | 134 [133–149] | 0.85 | `6b1696f0` (1/1) |
| 1 | 1 | 141 [140–150] | 1.25 | `6b1696f0` (1/1) |
| 1 | 2 | 120 [119–158] | 1.09 | `6b1696f0` (1/1) |
| 4 | 0 | 130.75 [129.75–160] | 0.87 | `6b1696f0` (4/4) |
| 4 | 1 | 161 [158.25–174.25] | 1.23 | `6b1696f0` (4/4) |
| 4 | 2 | 145.75 [141–161.5] | 1.08 | `6b1696f0` (4/4) |
| 130 | 0 | 139.8 [138.2–142.08] | 1.25 | `6b1696f0` (130/130) |
| 130 | 1 | 144.63 [137.21–149.02] | 1.09 | `6b1696f0` (130/130) |
| 130 | 2 | 115.08 [112.97–116.81] | 1.01 | `6b1696f0` (130/130) |

- node (`shared_obj.mjs`) による同じ署名の確認は、本節の根拠に含めない。その実行の生データが `results/` に無く、再実行には `work-m6-ott` の `ottl.cjs` が要るため。署名の根拠は上表の Chrome 行 (`sig_ok=true`、130/130)。
- 署名検査のネガティブコントロール (1 obj の入力を変えて FAIL することの確認) は本節では未実施。素材の再取得を伴うため、子 #2988 [PERF-P21] の受入に入れる。
- 未解決: worklet 上の setup 時間と instantiate 上限は未測 (`setup_ms` を出力していない。M=130 を超える M は試していない)。子 #2988 [PERF-P21] で測る。M=130 の setup は Dedicated Worker で 790〜999 ms (§3)。pre-warm の設計は §4 の経路で扱う。

再現:

```sh
export PERF_TMP=$RUNNER_TEMP/perf
node tools/perf/p15/chrome_worklet.mjs --m 1,4,130 --reps 7 --blk 1000 --runs 3   # §7 の表
```

前提: `oc_artifacts: work-m6-ott` (`tools/ott/work/lift/ottl.wasm`)。

**測定 commit から HEAD までの tools/perf/p15 差分**: 測定コードの差分は空。`git diff --stat 80298b02 HEAD -- tools/perf/p15` は、測定結果 `results/chrome_worklet.jsonl` (9 行) の追加だけを示す。

## 8. 第 2 plugin (Fresh Air GainDsp) の x64c lift と単独 instance の署名 (PERF-P20 / #2963)

**結論**: Fresh Air の `gain::GainDsp::process` (SlateCore `0x180afe090`) を x64c で lift し emcc で wasm 化した。単独 instance の署名は node で `5e5287b5` (400 シナリオ・3 回一致)。同じシナリオで実機機械語 (ms_abi 直接実行) と突き合わせ、**400/400 シナリオ一致**。異なる plugin 2 種の **1 Memory への畳み込みは未実施** で、残りは子 issue #3680 [PERF-P23] に移した。impbase 分離と fa_ 改名の再 lift は §8 の付録 `tools/perf/REPORT_APPENDIX_4732.md` (#4732)。

| 項目 | 結果 (実測) |
|---|---|
| 第 2 plugin | Fresh Air。`SlateCore.core_64` (PE32+ DLL、ImageBase `0x180000000`、SizeOfImage `0x2319000`)。素材 `plugins-freshair` の `Fresh Air.Win.zip` を `tools/targets/freshair/fetch.sh` で展開 |
| lift | `x64c.py --closure 60 --img 0x180000000 --shift 0x17E000000 --img-size 0x2319000`。functions 57、insns 2102、unsup `{}`、traps 0、imports 22、unlifted callees 0 |
| wasm | `fa.wasm` 2,148,176 B。`emcc -O0 -ffp-contract=off`、compile の warnings 0 / errors 0 |
| 窓 (lift 時の再配置) | wasm アドレス = VA − `0x17E000000`。画像は wasm `0x02000000`〜`0x04319000`。OTT の画像窓 `0x30000000` (§0 の `shared_worker.mjs`) と重ならない。emcc の静的データ・heap の衝突は未検証 (#3680) |
| 単独署名 | `fa_gain_sig.mjs` 400 シナリオ・seed 64030: `5e5287b5` (3 回とも一致)。出力が変わったシナリオ 371/400 |
| 差分 (native) | `fa_native_diff.py` seed 64030: 400/400 一致、比較バッファ 2,800、差分 0、native crash 0、wasm trap 0。seed 7 も 400/400 一致 |
| NC-1 (入力) | wasm 側だけ seed 64031 のシナリオを流す: 0/400 一致 (400 mismatch) |
| NC-2 (wasm の 1 命令) | lift C の 1 命令 (`0x180afe195` `addss`→減算、`fle_lifted.c` 行 550) を壊す: 214/400 一致、**186 mismatch**、署名 `5e5287b5`→`5cb40d4b` |
| 所要 | build 7.40 s (real)、差分 1 本 9.2 s (native 実行 + node) |

- 測定 commit: `e0d62359c` (コードを最後に変えた commit。`git diff e0d62359c HEAD -- tools/perf/p20` の出力は空。本節の追記は `tools/perf/REPORT_P15.md` だけ)。測定時の load average 0.08 (1 分)、CPU は runner の 4 vCPU。
- 環境: node v22.23.3、emcc は `[EMSDK]` (`toolchain-emsdk`。`EMSDK` に設定して読ませる。`docs/REFERENCES.md` §4)、素材 `plugins-freshair`。
- 既知類型との関係: 本 lift は x64c (RetDec 非依存)。RetDec 由来の修復 (P1・F7・F2) は適用していない。silent miscompile は差分 harness で検出する。NC-2 で検出力を確認した。
- 差分 harness の入力: 仕様は `tools/liftlib/specs/fa_gain.json` (vars・buffers) をそのまま使う (`liftlib.harness.spec.build`)。署名 harness (`fa_gain_sig.mjs`) は同じ分布の値を再現し、L/R は一様 [-1, 1] (仕様の sample 定義は使っていない)。署名値は回帰用の ID であり、正しさは差分 harness が担う。

再現 (素材 `plugins-freshair` の展開後。`FA_DL` は zip の置き場):

```sh
FA_DL=$RUNNER_TEMP/fa bash tools/targets/freshair/fetch.sh
bash tools/perf/p20/build_fa_gain.sh                                   # §8 の lift・wasm
node tools/perf/p20/fa_gain_sig.mjs tools/perf/p20/work/fa/fa.cjs 400 64030   # 単独署名
python3 tools/perf/p20/fa_native_diff.py --n 400 --seed 64030          # native 差分
python3 tools/perf/p20/fa_native_diff.py --n 400 --seed 64030 --neg-wasm-seed 64031 --out tools/perf/p20/work/fa/diff_neg   # NC-1
bash tools/perf/p20/fa_negctl.sh                                       # NC-2
```

| 未解決 | 影響 | 起票先 |
|---|---|---|
| OTT と Fresh Air を 1 Memory に畳む | 解決済み (#3680)。畳み込み後の署名は両者とも単独基準と一致 (付録 `tools/perf/REPORT_APPENDIX_3680.md`) | - |

## 9. AudioWorklet 上の instantiate 上限・setup 時間・ネガティブコントロール (PERF-P21 / #2988)

受入条件の「§7 に追記」は、main の §8 が PERF-P20 に使われたため本節 (§9) に置いた。

**結論** (PERF-P25 追補。受入の正本は `tools/perf/REPORT_APPENDIX_3959.md`): AudioWorklet 上で 1 instance (Memory 1 本) に畳んだ OTT obj は、Chrome 154 の測定点の範囲で **M=145 が成功・M=146 が失敗** (初期化・署名とも M=145 は 3 run 全て成功、署名 145/145 一致)。**M=146 は 3 run 全て無応答** (`Error: eval timeout`、30 s。1 run は 150 s でも戻らない)。M=148・152・160 も 3 run 全て無応答。単調性は未確認 (Chrome の M=147・149〜151・153〜159 と M=2〜129・131〜144 は、コミット済みのデータが無い)。Node 掃引の 159 点は生データが無く、本 run では再現していない。原因は未特定 (子 #4392 [PERF-P26])。

| 項目 | 結果 (Chrome 154.0.8037.97・EPYC 7763) |
|---|---|
| 成功最大 M / 失敗最小 M | 145 (3/3 成功) / 146 (3/3 無応答)。定義: 測定点 M ∈ {1, 130, 145, 146, 148, 152, 160} の中で成功した最大 M・失敗した最小 M (測定点外は含まない) |
| 二分探索 (各点 3 run) | 145 成功 → 152・148・146 失敗。M=160 も 3/3 失敗。147・149〜151・153〜159 は未測 |
| 署名 | M=145: 145/145 一致 (`6b1696f0`、3 run)。M=130: 130/130 一致 (3 run) |
| setup_ms | M=130: 756〜802 ms (6 値。署名の run 774・781・797 と、同じ setup ループのネガティブ制御の run 756・789・802)。M=145: 799〜868 ms (6 値。初期化 3 + 署名 3) |
| ネガティブコントロール | obj 0 の入力振幅を 0.5→0.25。M=1: 0/1 一致、M=130: 129/130 一致 (3 run とも `sig_ok=false`) |
| 旧測定 (Chrome 155.0.8059.39・EPYC 9V45) | 成功 M=1 (setup 17〜22 ms)・M=130 (3 run、setup 446〜465 ms)、署名 130/130、ネガ M=130 129/130。M=160・176・192・256・288・320・352 は 3 run とも無応答 (timeout 値は未記録)。生データ: `results/worklet_init_limit.jsonl`・`worklet_sig.jsonl`・`worklet_negctl.jsonl` (測定 `e4d2d1799`)、HEAD 再現 `rerun_20261015_worklet_{init,negctl,sig}.jsonl` (検証 HEAD `d064d219d`。`git diff --stat e4d2d1799 d064d219d -- tools/perf/p15` は 3 ファイル 5 行の追加のみ) |

- **測定 commit**: `c412b8937` (`chrome_worklet.mjs` に `timeout_ms` を行へ記録。測定コードの変更はこの commit だけ)。生データ: `results/worklet_range_{init,sig,negctl,long}.jsonl` (初期化 15 行・署名 6 行・ネガ 6 行・M=146 の 150 s 試行 1 行)。測定 commit から検証 HEAD までの差分 (`git diff --stat c412b8937 HEAD -- tools/perf/p15 tools/perf/harness tools/ott`) は `results/` の 4 ファイル・28 行の追加のみ。
- **環境**: Chrome 154.0.8037.97 (headless=new)、CPU AMD EPYC 7763 (4 vCPU)、素材 `work-m6-ott` (`tools/ott/work/lift/ottl.{wasm,cjs}`、gitignore)。旧測定と版・CPU が違うため、setup 値は直接比べない。
- **setup_ms の定義**: `shared_worklet.js` の `t0` (instantiate・`__wasm_call_ctors`・`ott_data_install` の後) から、全 obj の ctor・setParam 19 個・resume・入力設定までの所要 (`Date.now()`、1 ms 分解能)。
- **無応答**: 処理が戻らず例外も届かない。150 s でも戻らない (M=146) ので、遅いだけの失敗ではない。obj 基底 `0x31000000 + i×0x40000` が IN0 (`0x34000000`) に届くのは M≈192 で、146 の境界は配置の境界ではない。原因は未確認 (#3959)。
- **obj 0 の根拠**: 個別 index は記録していない。`sig` は `new Set(sigs)` の挿入順 (obj 番号順) なので、先頭の `d39696f0` が obj 0 (`sig_match_n`=129 と合う)。
- **旧 sweep の timeout 値**: 旧行に記録が無く回収できない。本節の 146・160 は 30 s で記録済み。

```sh
node tools/perf/p15/chrome_worklet.mjs --init-only --m 145,152,148,146,160 --runs 3 --timeout 30000 --out $RUNNER_TEMP/perf/worklet_range_init.jsonl
node tools/perf/p15/chrome_worklet.mjs --m 130,145 --reps 0 --runs 3 --timeout 120000 --out $RUNNER_TEMP/perf/worklet_range_sig.jsonl
node tools/perf/p15/chrome_worklet.mjs --m 1,130 --reps 0 --neg 0 --runs 3 --timeout 120000 --out $RUNNER_TEMP/perf/worklet_range_negctl.jsonl
node tools/perf/p15/chrome_worklet.mjs --init-only --m 146 --runs 1 --timeout 150000 --out $RUNNER_TEMP/perf/worklet_range_long.jsonl
```

| 未解決 | 影響 | 起票先 |
|---|---|---|
| M=146 以上の無応答の原因 (例外・ループ・メモリ破壊のどれか。止まる obj と呼び出し) | 上限の意味 (メモリの限界か状態の破壊か) が未確定 | #3959 [PERF-P25] |
| 147・149〜151・153〜159 の成否 (単調性) | 成功最大 M は 146 より大きい全点を測るまで一意に言えない | #3959 [PERF-P25] |
