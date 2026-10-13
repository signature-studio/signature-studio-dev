# tools/perf REPORT_P8 — plugin 別 module/instance/memory vs 動的リンク (MAIN/SIDE_MODULE) (PERF-P8 / #166)

> **正本**: 本ファイル (`tools/perf/REPORT.md` §12 の付録。REPORT.md が 250 行上限のため分割)。全表は `p8/results/TABLES.md` (自動生成)、生データ `p8/results/*.jsonl`。

既知類型との関係: 該当なし (計測。lift・既存 wasm は未変更)。検証起点 commit: `8bf9b10` (クリーン detached worktree `p8/work/wt_verify` で `p8.sh` の build・node・Chrome 全段を実行、570 行 = `results/p8.jsonl`)。
後続 commit で `tables.mjs` (複数実行系対応)・`chrome_p8.mjs` (`P8_JSFLAGS`/`P8_OUT`/`--cfgs`) を直し、診断 2 本 (`p8_diag.jsonl`, `p8_limit.jsonl`) を追加した (ベンチ本体 `lib.mjs`/`bench.mjs` は 8bf9b10 から数値に影響する変更なし)。
実行系: node v22.23.3 (V8 12.4 相当; §2.1 の node 26 とは別) と headless Chrome 154.0.8037.97 の Dedicated Worker、4 コア runner (loadavg 開始時 node 1.22〜2.26 / Chrome 1.01〜8.53 = Chrome 自身の負荷を含む)。

**⚠ 範囲**: カーネルは実 OTT ではない合成 plugin (`work-m6-ott` 素材が本 run に無い)。AudioWorklet 内 (dlopen) ・実オーディオデバイス・Windows/Android は未測。結論は「構成差の構造的な大きさ」であり、実 lift での絶対値ではない。

## 0. 結論

| 論点 | 実測結果 (独立プロセス 3 回の p50 の中央値; 比は同 N の `static_based` 比) |
|---|---|
| **PIC 税 (定常 CPU)** | `-fvisibility=hidden` の SIDE_MODULE は **node ×1.002〜1.007 / Chrome ×1.004〜1.012** (標準カーネル) = 差は ≤1.2%。**既定 visibility の SIDE_MODULE は Chrome で ×1.241〜1.254 (標準) / ×1.221〜1.258 (軽量)**、node では標準 ×1.004〜1.014・軽量 ×1.000〜1.020。side module が `GOT.mem.{R,X,fCF,fZF,fSF,fOF,fPF,tab}` の 8 本を (可変) global として import するのが原因 (hidden は 0 本)。TurboFan のみ ×1.24〜1.27、Liftoff のみ ×1.72〜1.79 (hidden は ×1.15) |
| **plugin 別 module/instance/Memory** | 定常は静的リンクと同じ: node ×0.998〜1.002、Chrome ×0.989〜1.003 (標準, N=1〜16)。境界コスト (JS→wasm 呼出 + plugin 間 1 KiB コピー) は **コピー 14〜30 ns/plugin/ブロック**、JS→wasm 呼出は測定分解能 (±26 ns) 以下。N=64 軽量の chain 全体は `sep_based_light` 対 `dyn_hid_light` で node 104.3 vs 102.6 µs・Chrome 103.8 vs 103.5 µs (§2.2) |
| **VA 固定 (現行 lift) の可否** | ABS (VA=0x30000000) のコードは Memory 1 つに 1 plugin しか置けない = **plugin 別 Memory 以外の選択肢が無い**。動的リンク/静的 N 個同居には guest VA の相対化 (`based`) が要る。相対化自体の CPU コストは無い (`static_abs` vs `static_based` = ×0.994〜1.008) |
| **起動** | plugin あたり: 別 module (一意バイト列) node 1.40 / Chrome 1.55 ms、同一 Module を再 instantiate 0.47 / 0.34 ms、dlopen は node 2.19 (N=64 で 2 本目以降 p50 2.0 ms と増加) / Chrome 1.32 ms。**動的リンクは追加で main module の instantiate 11〜12 ms (node) / 15〜19 ms (Chrome) + glue 77 KB**。N=64 合計: 別 module 90/103 ms、dyn 152/114 ms、同一 Module 31/27 ms (node/Chrome) |
| **メモリ** | 別 Memory の **本数上限: Chrome 154 は 124 本 (16 MiB でも 769 MiB でも 124〜125 本; 125 本目で `Out of memory: Cannot allocate Wasm memory`)**、node は 128 本 × 769 MiB (98,440 MiB 予約) まで成功。dyn は Memory 1 本 (本数上限なし)。RSS は plugin あたり 2.0〜2.3 MiB (compile 済みコードが支配; 769 MiB 予約でも増えない) |
| **推奨 (本計測の範囲)** | 現行 lift (VA 固定) の plugin は **plugin 別 module/instance/Memory** (PERF.md §5.4(a) を支持)。動的リンクは CPU・起動・メモリのいずれでも優位が出ず、`-fvisibility=hidden` 必須・VA 相対化必須・main runtime 固定費・Chrome の同期 compile 上限という条件が付く。同一 Memory 共有 (ゼロコピー) の利得は 14〜30 ns/plugin/ブロックで無視できる。**ただし plugin 数が 124 を超え得る構成 (大量インスタンス) では別 Memory 方式は成立しない** → その場合のみ側 module / 共有 Memory を再検討 |

## 1. 測定対象と方法

**カーネル** (`tools/perf/p8/src/p8_kernel.c`): 実 OTT ではなく **lift 風の合成 plugin** (`work-m6-ott` 素材が本 run に無いため)。
CPU 状態を別 TU のグローバル `R[16]`/`X[16]`/`fZF..fPF` に持ち (`tools/ott/rt/ott_cpu.h` と同形)、guest pointer を整数→ポインタで読み書きし、
guest 間接 call を関数 table (`tab[256]`, 非 const) 経由で行う。`plg_process` = 2ch × 128f を NST 段の biquad (1 段 = lift 1 関数 / 1 サンプル 16 文) で処理。
標準 NST=32 (定常 48 µs/block = 本 REPORT §2.1 の bit-exact OTT O2 52〜56 µs と同オーダ)、軽量 NST=1 (1.5 µs/block; 境界コストの検出用)。
関数 256 個・wasm 94,726〜101,314 B/plugin (`-O2`, 全 plugin 同一ソース。静的 N 個リンク時は plugin ごとに定数を変えて binaryen の関数重複排除で潰れないようにした)。

| 構成 (略称) | 何か | メモリ |
|---|---|---|
| `static_abs` / `static_based` | 1 module に N plugin を静的リンク (非 PIC)。`abs` = guest VA を固定 linear address (現行 lift)、`based` = module 内配列 (rebase 済み lift) | 1 本 (64 MiB) |
| `sep_abs_hi` | plugin 別 standalone module/instance/Memory。VA = 0x30000000 固定 (現行 OTT と同じ配置; initial 769 MiB) | N 本 |
| `sep_abs_lo` | 同上、VA を低位 (16 MiB) に rebase (initial 64 MiB) | N 本 |
| `sep_based` | 同上、guest image が module 内配列 (initial 16 MiB)。JS が plugin 毎に `plg_process` を呼び、plugin 間の 1 KiB (256 f32) を JS の `TypedArray.set` で複写。N 個とも**バイト列を一意化** (custom section 付加; V8 の NativeModule 共有を避ける) | N 本 |
| `sep_based_shared` | 同上だが `WebAssembly.Module` を 1 回 compile して N instance (同一 plugin を N 回使う場合) | N 本 |
| `sep_based_nocopy` | `sep_based` から plugin 間コピーを除去 (署名は連鎖しないので比較対象外) | N 本 |
| `dyn_def` / `dyn_hid` | MAIN_MODULE=2 (C ホスト `chain_block`; 20 KB + emscripten glue) + SIDE_MODULE=2 (`-fPIC`) を N 個 `dlopen` (MEMFS 経由, 一意化したバイト列)。`def` = 既定 visibility、`hid` = `-fvisibility=hidden`。単一 Memory 共有、chain は wasm 内 (`memcpy` 1 KiB) | 1 本 (64 MiB) |
| `dyn_hid_jsdrive` | `dyn_hid` を JS から plugin 毎に `call_one(i)` で駆動 (JS→wasm 境界のみ。署名比較対象外) | 1 本 |

計測 (`tools/perf/p8/lib.mjs`, node と Chrome Worker で同一コード): 定常 = 1 ブロックごとに JS から chain を 1 回呼ぶ (`sep_*` は JS が N 回呼ぶ)。
warm-up 500 ms → 1 rep = 150 ms 分のブロックを 9 rep → rep の p50 を 1 プロセスの値とし、**独立プロセス (Chrome は独立ブラウザ) 3 回の p50 の中央値 (min–max)** を表に載せる。
起動 = `compile + instantiate (+ plg_init / dlopen)` の合計と初回 chain 1 ブロック (lazy compile の stall) を **5 回** (毎回新規プロセス/新規 Chrome)。
メモリ = N 個 load + 1 ブロック後の RSS 増分 (node: `process.memoryUsage().rss`、Chrome: renderer の `/proc/<pid>/status` VmRSS 差)。

## 2. 結果

全表は `p8/results/TABLES.md` (node / Chrome 別、min–max 付き)。ここでは結論に使った数値と定義だけを置く。

**2.1 定常 (µs / 128f ブロック)**: 標準カーネル N=1 / 4 / 16 の `static_based` は node 48.44 / 194.49 / 787.14、Chrome 48.94 / 194.98 / 786.70 (min–max はいずれも ≤0.5%)。
構成間の最大差 (標準カーネル): `static_abs`・`sep_*`・`dyn_hid` は node/Chrome とも ×0.989〜1.012 に収まる。`dyn_def` は Chrome のみ N=1 60.76 / N=4 244.59 / N=16 981.63 µs (×1.241〜1.254)。
`dyn_def` の機序検証 (`p8_diag.jsonl`, Chrome, 各 1 回): `--no-liftoff` で N=1 62.42 vs 49.22 (×1.268)、N=16 974.51 vs 787.15 (×1.238)。`--liftoff-only` で N=1 98.71 vs 55.07 (×1.792)、N=16 ×1.718。`dyn_hid` は ×0.990〜1.028 (TF) / ×1.148〜1.158 (Liftoff)。
→ default visibility だと R[]/X[]/flag の各アクセスが可変 global `GOT.mem.*` 経由になり両 tier で遅い (**推定**: 可変 global は定数畳み込み・ループ外への巻き上げができない。V8 12.4 の node では差が ×1.004〜1.014 に縮むのも V8 版差と**推定**、未検証)。
署名: N=1 の chain 構成は全て b418cf81、N=4 e159b254、N=16 567f3617 (標準)、軽量 N=1 976c9c24 (`check.mjs`: node+Chrome 14 グループ全一致。nocopy/jsdrive は chain を組まないため署名比較対象外)。

**2.2 境界コスト (軽量カーネル NST=1, 1 ブロック 1.5 µs/plugin)**: 派生値は `TABLES.md` の「派生値」。plugin 間 1 KiB コピー = (sep_based − sep_based_nocopy)/N = node 14 ns (N=16)・24 ns (N=64)、Chrome 19 / 30 ns。
JS→wasm 呼出 1 回 = (sep_based_nocopy − dyn_hid)/N = node −24 / 3 ns、Chrome −26 / −25 ns (負 = wasm 内 chain の `memcpy` 込みの dyn_hid の方が遅い = 呼出コストは分解能以下)。
N=64 軽量の chain 全体: `sep_based_light` node 104.3 / Chrome 103.8 µs、`dyn_hid_light` 102.6 / 103.5 µs (差 ≤1.7%)。

**2.3 起動 (ms, 独立プロセス/新規 Chrome 5 回の中央値 (min–max))**: N=64 の load 合計 — `sep_based` node 89.7 (87.8–93.8) / Chrome 103.3 (93.4–113.1)、`sep_based_shared` 31.0 / 27.4、`dyn_hid` 152.3 (151.1–154.9) / 114.3 (108.3–119.1)、`dyn_def` 161.0 / 119.8。
dlopen の内訳 (dyn_hid): main instantiate node 11.0〜12.3 / Chrome 15.0〜18.6 ms、1 本目 2.1 / 3.3〜4.8 ms、2 本目以降 p50 は node 0.97 (N=4) → 1.25 (16) → 1.96 (64) と増加 (loaded library 数に対し超線形; **推定**: GOT 更新が既存 library 全体を走査)、Chrome は 0.96〜1.17 でほぼ一定。
初回 chain 1 ブロック (lazy compile の stall, N=64): `sep_based` 17.5 / 17.2 ms、`sep_based_shared` 3.9 / 6.1 ms (関数コードが instance 間で共有される)、`dyn_hid` 18.9 / 18.9 ms。N=64 の stall は 2.67 ms の予算 (48 kHz) の 6.5〜7.1 倍 (17.2〜18.9 ms) → **pre-warm 必須** (REPORT §11)。
wasm サイズ: plugin 1 本 `sep_abs_hi` 94,726 B / `sep_based` 101,093 B / `side_def` 96,107 B / `side_hid` 96,022 B (PIC は ABS 比 +1.4%)、`dyn_main.wasm` 20,274 B (+ glue 77,091 B)、静的 16 本 `static_based_16` 1,719,386 B。

**2.4 メモリ**: Memory 本数 (memory モード): node は `sep_abs_hi` N=128 (769.1 MiB × 128 = 98,440 MiB 予約) まで成功、RSS 増分は N=128 で 289.9 MiB。
Chrome は `sep_based`・`sep_abs_hi`・`sep_abs_lo`・`sep_based_shared` すべて **N=128 で失敗**、`p8_limit.jsonl` で `sep_based` は N=124 まで OK / 125 から ERR、`sep_abs_hi` は 125 まで OK / 126 から ERR。
Memory サイズ (16 MiB と 769 MiB) に依存せず 124〜125 本 = 本数の上限 (REPORT §3 の「864 MiB × 124」と同値)。dyn_hid は Memory 1 本 (64 MiB) で N=128 まで成功 (Chrome RSS 増分 71.9 MiB・node 280.7 MiB)。
RSS/plugin (RSS 増分 (N=128) − (N=1)) / 127: node `sep_based` 2.20 / `sep_based_shared` 2.04 / `sep_abs_hi` 2.25 / `dyn_hid` 2.16 MiB。`sep_abs_lo` は 4.19 MiB で他の 2 倍 (node/Chrome とも再現; **原因未調査**、runner の THP が `always` であることが関与する可能性は**未検証の仮説**)。
Chrome は 1 回測定の RSS (±数 MiB) でノイズが大きく、RSS/plugin の比較には node の値を使う。

## 3. 設計への含意 (本計測の範囲での推奨)

1. **VA 固定 lift の plugin は plugin 別 Memory が唯一の選択肢**。動的リンクにするには lift 側で guest VA を module 相対 (`LD32(a)` を `base+a` 化) にする必要がある (`static_abs`→`static_based` の CPU コストは ×0.994〜1.008 で無い)。VA 低位化 (#91) と同じ作業で、lift に手を入れる。
2. **別 Memory 方式の制約は CPU でも RSS でもなく本数 (Chrome は 124〜125 本)**。FL 1 プロジェクトの plugin 数がこれに近づく場合は、同一 plugin の複数インスタンスを 1 module 内の複数 state に畳む (本計測の `static` 方式 = Memory 1 本) か、plugin 数に上限を設ける。
3. **動的リンクを採るなら `-fvisibility=hidden` を必須とし、PIC ビルドの CPU 回帰を perf gate (`tools/perf/gate`) に足す** (default visibility は Chrome で +24〜27%: 標準カーネル 1 plugin の RTF@44.1k が 0.0169 → 0.0209)。
4. 起動: plugin 別 module は N=64 で 90〜103 ms (5 回中央値)・初回 stall 17 ms → AudioWorklet pre-warm (REPORT §11) とセット。同一 plugin の複数インスタンスは Module を 1 回 compile して再利用 (0.34〜0.47 ms/instance)。
5. dlopen は Emscripten 既定で**同期** compile (`new WebAssembly.Module`)。Chrome のメインスレッドは 8 MB 超で不可 (REPORT §3)。本計測の side module は 96 KB で Worker 内のため未顕在化 → 大きい plugin (Serum2/Massive X 級) では `emscripten_dlopen` (async) が要る (**未測**)。

## 4. 検証と範囲

- 検証起点 `8bf9b10` (クリーン detached worktree)。`p8.sh` の build・node・Chrome 全段の実測 748 s (開始 epoch 1791857650 → 最終 jsonl 行 1791858398)。tables 段は 8bf9b10 の `tables.mjs` が複数実行系で例外終了したため、後続 commit の `tables.mjs`/`check.mjs` で同じ `p8.jsonl` から再生成した (数値は jsonl の集計のみで再測なし)。
- 署名検査: `check.mjs` PASS 14/14 グループ。**ネガティブコントロール**: 1 件の署名を `deadbeef` に改ざん → `check.mjs --negative` が 13 PASS / 1 FAIL を検出 (exit 0 = 期待どおり検出)。
  PIC 税の検出力: `dyn_hid` (対照) が ×1.00 のまま `dyn_def` だけ ×1.24 になる = 同一ソース・同一測定で差が検出できる。run 間ばらつき (static_based 標準の min–max / 中央値) は node ≤0.5%・Chrome ≤0.6% (標準 N=1〜16) = ×1.01 未満の差は分解能以下。
- 別アルゴリズム検算: 定常 µs は N 倍則で検算 (`static_based` Chrome 48.94 × 16 = 783.0 vs 実測 786.70 = +0.5%、軽量 N=64 は `sep_based_nocopy_light` 101.9 µs vs 1.506 × 64 = 96.4 µs (+5.7%。plugin 数に比例しない分は状態・コードの cache 占有増と**推定**、未検証))。
- 範囲外: 実 OTT/FLEngine・AudioWorklet・Windows/Android・Firefox/Safari・実オーディオデバイス・pre-warm 後の定常 (REPORT §11 参照)。`WebAssembly.Memory` の Windows commit charge。
- `git status --porcelain -- tools/perf/p8 docs tools/perf/REPORT.md tools/perf/REPORT_P8.md` で取りこぼしなし。20 MiB 超 blob なし。`work/` は gitignore。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 OTT (bit-exact x64c lift) / FLEngine 実 closure での再測 (`oc_artifacts: toolchain-emsdk work-m6-ott` で本ハーネスの `src/` を OTT に差替) | 合成カーネルの結論が実 lift に当てはまるか未確認 (特に default visibility の +24% は R[]/X[] へのアクセス頻度依存) | #166 に残置 (Closes しない)。PERF-P9 (#168) にコメント |
| lift の guest VA 相対化 pass (`LD32(a)` → `base+a`) の実装と、相対化後の bit-exact 確認 | 動的リンク/静的同居の前提 | 新規子チケット案 `[LIFTLIB-n] relocatable guest VA mode` (#91 低位 base 化と統合検討)・PM 判断 |
| Chrome の Memory 本数上限 124〜125 に対する plugin 数の設計 (インスタンス畳み込み or 上限) | 大規模プロジェクトで instantiate 失敗 | 新規子チケット案 `[PERF-n] instance budget under 124-Memory cap`・PM 判断 |
| AudioWorklet 内での dlopen と >8 MB side module の async dlopen | dyn の実運用可否 | 新規子チケット案 `[PERF-n] dlopen in AudioWorklet`・PM 判断 (PERF-P3 #162 ローダ関連) |
| default visibility PIC の +24% の機序確定 (可変 global 仮説)・V8 版差 (node 22 は小) | 設計ルール化の根拠の強さ | #166 コメント |
| Windows / Android の commit charge (769 MiB × N 予約)・`sep_abs_lo` RSS 2 倍の原因 | ABS 高位 VA を残す場合のコスト | PERF-P7 (#165) にコメント |
| node 22 での測定 (計画は node 26)・Firefox/Safari・低負荷再測 | V8 版・ブラウザ差 | PERF-P7 (#165) |

## 6. 再現

```sh
bash tools/perf/p8/p8.sh                  # build → node → Chrome → tables → check (build+計測 748 s @4 コア)
P8_QUICK=1 bash tools/perf/p8/p8.sh       # 縮小 (N=1,4・reps 3・runs 1)
node tools/perf/p8/check.mjs --negative   # ネガティブコントロール (署名改ざんを検出)
# 診断: P8_JSFLAGS=--no-liftoff P8_OUT=tools/perf/p8/results/p8_diag.jsonl node tools/perf/p8/chrome_p8.mjs steady --n 1,16 --cfgs static_based,dyn_def,dyn_hid
```

次タスク提案: 実 OTT での再測 (上表 1 行目)、PIC 回帰ゲート (`dyn_def`/`dyn_hid` の比 ≤1.05 を perf gate に追加)、VA 相対化 lift。
