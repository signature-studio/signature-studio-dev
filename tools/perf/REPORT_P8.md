# tools/perf REPORT_P8 — plugin 別 module/instance/memory vs 動的リンク (MAIN/SIDE_MODULE) (PERF-P8 / #166)

> **正本**: 本ファイル (`tools/perf/REPORT.md` §5 項目 7 の付録。REPORT.md が 250 行上限のため分割)。全表は `p8/results/TABLES.md` (自動生成)、生データ `p8/results/*.jsonl`。

既知類型との関係: 該当なし (計測。lift・既存 wasm は未変更)。検証起点 commit: `8bf9b10` (クリーン detached worktree `p8/work/wt_verify` で `p8.sh` の build・node・Chrome 全段を実行、570 行 = `results/p8.jsonl`)。
後続 commit で `tables.mjs` (複数実行系対応)・`chrome_p8.mjs` (`P8_JSFLAGS`/`P8_OUT`/`--cfgs`) を直し、診断 2 本 (`p8_diag.jsonl`, `p8_limit.jsonl`) を追加した (ベンチ本体 `lib.mjs`/`bench.mjs` は 8bf9b10 から数値に影響する変更なし)。
レビュー指摘対応の commit で `bench.mjs`/`chrome_p8.mjs` が jsonl の `info` に `cpu` (CPU 型番) を出し `tables.mjs` が `TABLES.md` ヘッダに出すようにし、§2.5 (別ホスト再測) を追加した (既存 jsonl の数値は未変更。`TABLES.md` は `tables.mjs` で再生成し、差分はヘッダ 2 行のみ)。
実行系: node v22.23.3 (V8 12.4 相当; §2.1 の node 26 とは別) と headless Chrome 154.0.8037.97 の Dedicated Worker、4 コア runner (loadavg 開始時 node 1.22〜2.26 / Chrome 1.01〜8.53 = Chrome 自身の負荷を含む)。
**CPU 型番: 不明** — 本結果 (`results/p8.jsonl`・`p8_diag.jsonl`・`p8_limit.jsonl`) を採取した元の run は `os.cpus()[0].model` を記録しておらず (jsonl の `cpus` は個数のみ)、事後に特定できない。ホスト識別の代用指標として Chrome `static_based` N=1 = 48.94 µs/block を書く (別ホスト EPYC 9V45 は 37.72, §2.5)。修正後の harness は jsonl の `cpu` 列と `TABLES.md` ヘッダに型番を出す (既存 jsonl は未記録のまま。型番は推定で補わない)。

**⚠ 範囲**: カーネルは実 OTT ではない合成 plugin (`work-m6-ott` 素材が本 run に無い)。AudioWorklet 内 (dlopen) ・実オーディオデバイス・Windows/Android は未測。結論は「構成差の構造的な大きさ」であり、実 lift での絶対値ではない。

## 0. 結論

| 論点 | 実測結果 (独立プロセス 3 回の p50 の中央値; 比は同 N の `static_based` 比) |
|---|---|
| **PIC 税 (定常 CPU)** | 以下の数値は**この runner での値** (CPU 型番不明; Chrome `static_based` N=1 48.94 µs/block)。`-fvisibility=hidden` の SIDE_MODULE は **node ×1.002〜1.007 / Chrome ×1.004〜1.012** (標準カーネル) = 差は ≤1.2% (別ホストの Chrome 再測でも ×1.000〜1.026, §2.5)。**既定 visibility の SIDE_MODULE は Chrome で ×1.241〜1.254 (標準) / ×1.221〜1.258 (軽量)**、node では標準 ×1.004〜1.014・軽量 ×1.000〜1.020。**別ホスト (AMD EPYC 9V45; 同 37.72 µs) の独立再測 (§2.5) では Chrome 標準 ×1.036〜1.077。大きさはホスト依存で、`dyn_def` ≥ `dyn_hid` ≈ 静的の向きは両ホストで再現**。**観測**: side module は `GOT.mem.{R,X,fCF,fZF,fSF,fOF,fPF,tab}` の 8 本を `(mut i32)` global として import (hidden は 0 本)。**機序は推定** (§2.1; 8 本 import が原因とは確定していない)。TurboFan のみ ×1.24〜1.27、Liftoff のみ ×1.72〜1.79 (hidden は ×1.15) は、この runner での各 1 回の診断 |
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
構成間の最大差 (標準カーネル): `static_abs`・`sep_*`・`dyn_hid` は node/Chrome とも ×0.989〜1.012 に収まる。`dyn_def` は Chrome のみ、**この runner では** N=1 60.76 / N=4 244.59 / N=16 981.63 µs (×1.241〜1.254。別ホストでは ×1.036〜1.077 = §2.5)。
`dyn_def` の切り分け診断 (`p8_diag.jsonl`, この runner, Chrome, 各 1 回): `--no-liftoff` で N=1 62.42 vs 49.22 (×1.268)、N=16 974.51 vs 787.15 (×1.238)。`--liftoff-only` で N=1 98.71 vs 55.07 (×1.792)、N=16 ×1.718。`dyn_hid` は ×0.990〜1.028 (TF) / ×1.148〜1.158 (Liftoff)。
→ **観測**: default visibility の side module だけが `GOT.mem.*` 8 本を `(mut i32)` global として import し (`wasm-dis side_def.wasm | grep -c 'import "GOT'` = 8、`side_hid.wasm` = 0)、`dyn_def` だけが遅く、両 tier で遅い。**機序は推定** (未検証): R[]/X[]/flag の各アクセスが可変 global 経由になり、可変 global は定数畳み込み・ループ外への巻き上げができない。V8 12.4 の node で差が ×1.004〜1.014 に縮むのは V8 版差、別ホストで ×1.036〜1.077 に縮むのは CPU 差と**推定**、いずれも未検証 (要因は分離していない)。
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

**2.5 別ホストでの独立再測 (PIC 税のホスト依存)**: 出典 = 本 PR の oc-reviewer レビュー (2026-10-13 02:48Z, CHANGES_REQUESTED) の再測。数値は reviewer の報告を転記したもので、実装側で再測したものではない (生 jsonl は reviewer の worktree にあり本 PR には未収録)。
条件: 別の clean worktree @ `04ad086`、**CPU = AMD EPYC 9V45 (4 vCPU)**、node v22.23.3、Chrome 154.0.8037.97、PR 本番と同じ `--reps 9 --runs 3` (独立 Chrome 3 回)。所要 74 s、署名は全構成一致 (b418cf81 / e159b254 / 567f3617)、error 行 0。
コマンド: `node tools/perf/p8/chrome_p8.mjs steady --n 1,4,16 --reps 9 --runs 3 --cfgs static_based,dyn_def,dyn_hid,sep_based` (既定の出力先は `results/p8.jsonl` への追記。本 PR の jsonl に混ぜないよう、再現時は `P8_OUT=<別ファイル>` を付ける)。

| Chrome 標準カーネル (p50 の中央値; 比 = 同 N の `static_based` 比) | EPYC 9V45 N=1 | N=4 | N=16 | この runner (CPU 型番不明) N=1 | N=4 | N=16 |
|---|--:|--:|--:|--:|--:|--:|
| `static_based` µs/block (min–max) | 37.72 (37.52–39.30) | 151.22 (150.73–151.67) | 607.92 (606.10–609.88) | 48.94 (48.66–48.94) | 194.98 (194.88–195.09) | 786.70 (786.28–789.01) |
| `sep_based` | ×1.003 | ×0.997 | ×0.996 | ×0.990 | ×1.000 | ×1.003 |
| `dyn_hid` | ×1.002 | ×1.026 | ×1.000 | ×1.004 | ×1.011 | ×1.012 |
| **`dyn_def`** | **×1.077** | **×1.068** | **×1.036** | **×1.241** | **×1.254** | **×1.248** |

- **再現した**: `sep_*` ≒ 静的 (EPYC で差 ≤0.4%)、`dyn_hid` ≒ 静的 (EPYC で差 ≤2.6%)、構成間の署名一致、`dyn_def` ≥ `dyn_hid` の向き。Chrome の Memory 本数上限も同じ (`sep_based` N=124 OK / 125 ERR、`sep_abs_hi` N=125 OK / 126 ERR; reviewer 実施でコマンドは本文に記載なし)。
- **再現しなかった**: `dyn_def` の大きさ (この runner +24〜25% に対し +3.6〜7.7%)。`static_based` N=1 が 37.72 / 48.94 = ×0.771 でホストは別物。原因 (CPU 世代・μarch の差か、runner の状態か) は**未特定**で、元の run の CPU 型番が不明のため CPU 同士の比較もできない。
- 別算法検算 (reviewer、`WebAssembly.Module.imports` で import を直接計数): `side_def.wasm` は `GOT.mem` 8 本 (R, X, fCF, fZF, fSF, fOF, fPF, tab; kind=global)、`side_hid.wasm`・`sep_based`・`sep_abs_hi` は 0 本。→ 「8 本 import (hidden は 0 本)」は観測。それが遅さの原因かは §2.1 のとおり推定。
- 言えること / 言えないこと: 確認済みの 2 ホスト・各 3 独立 Chrome の範囲で、PIC 税 (既定 visibility) の大きさは ×1.036〜1.254 でホスト依存、`-fvisibility=hidden` ならどちらでも ≤2.6%。「Chrome で ×1.24」を一般値として使わない。`-fvisibility=hidden` 必須の推奨は維持する。

## 3. 設計への含意 (本計測の範囲での推奨)

1. **VA 固定 lift の plugin は plugin 別 Memory が唯一の選択肢**。動的リンクにするには lift 側で guest VA を module 相対 (`LD32(a)` を `base+a` 化) にする必要がある (`static_abs`→`static_based` の CPU コストは ×0.994〜1.008 で無い)。VA 低位化 (#91) と同じ作業で、lift に手を入れる。
2. **別 Memory 方式の制約は CPU でも RSS でもなく本数 (Chrome は 124〜125 本)**。FL 1 プロジェクトの plugin 数がこれに近づく場合は、同一 plugin の複数インスタンスを 1 module 内の複数 state に畳む (本計測の `static` 方式 = Memory 1 本) か、plugin 数に上限を設ける。
3. **動的リンクを採るなら `-fvisibility=hidden` を必須とし、PIC ビルドの CPU 回帰を perf gate (`tools/perf/gate`) に足す** (default visibility の Chrome での増分はホスト依存: この runner は +24〜27% で標準カーネル 1 plugin の RTF@44.1k が 0.0169 → 0.0209、別ホスト EPYC 9V45 は +3.6〜7.7% (§2.5); hidden は両ホストで ≤2.6%)。
4. 起動: plugin 別 module は N=64 で 90〜103 ms (5 回中央値)・初回 stall 17 ms → AudioWorklet pre-warm (REPORT §11) とセット。同一 plugin の複数インスタンスは Module を 1 回 compile して再利用 (0.34〜0.47 ms/instance)。
5. dlopen は Emscripten 既定で**同期** compile (`new WebAssembly.Module`)。Chrome のメインスレッドは 8 MB 超で不可 (REPORT §3)。本計測の side module は 96 KB で Worker 内のため未顕在化 → 大きい plugin (Serum2/Massive X 級) では `emscripten_dlopen` (async) が要る (**未測**)。

## 4. 検証と範囲

- 検証起点 `8bf9b10` (クリーン detached worktree)。`p8.sh` の build・node・Chrome 全段の実測 748 s (開始 epoch 1791857650 → 最終 jsonl 行 1791858398)。tables 段は 8bf9b10 の `tables.mjs` が複数実行系で例外終了したため、後続 commit の `tables.mjs`/`check.mjs` で同じ `p8.jsonl` から再生成した (数値は jsonl の集計のみで再測なし)。
- 署名検査: `check.mjs` PASS 14/14 グループ。**ネガティブコントロール**: 1 件の署名を `deadbeef` に改ざん → `check.mjs --negative` が 13 PASS / 1 FAIL を検出 (exit 0 = 期待どおり検出)。
  PIC 税の検出力: この runner では `dyn_hid` (対照) が ×1.00 のまま `dyn_def` だけ ×1.24 になる = 同一ソース・同一測定で差が検出できる (別ホストでは `dyn_def` ×1.04〜1.08, §2.5)。run 間ばらつき (static_based 標準の min–max / 中央値) は node ≤0.5%・Chrome ≤0.6% (標準 N=1〜16) = ×1.01 未満の差は分解能以下。
- 別アルゴリズム検算: 定常 µs は N 倍則で検算 (`static_based` Chrome 48.94 × 16 = 783.0 vs 実測 786.70 = +0.5%、軽量 N=64 は `sep_based_nocopy_light` 101.9 µs vs 1.506 × 64 = 96.4 µs (+5.7%。plugin 数に比例しない分は状態・コードの cache 占有増と**推定**、未検証))。
- 範囲外: 実 OTT/FLEngine・AudioWorklet・Windows/Android・Firefox/Safari・実オーディオデバイス・pre-warm 後の定常 (REPORT §11 参照)。確認済みホストは 2 つ (元 runner は CPU 型番不明 + EPYC 9V45; PIC 税の大きさは §2.5)。`WebAssembly.Memory` の Windows commit charge。
- `git status --porcelain -- tools/perf/p8 docs tools/perf/REPORT.md tools/perf/REPORT_P8.md` で取りこぼしなし。20 MiB 超 blob なし。`work/` は gitignore。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 OTT (bit-exact x64c lift) / FLEngine 実 closure での再測 (`oc_artifacts: toolchain-emsdk work-m6-ott` で本ハーネスの `src/` を OTT に差替) | 合成カーネルの結論が実 lift に当てはまるか未確認 (特に default visibility の増分 (この runner +24%、別ホスト +3.6〜7.7%) は R[]/X[] へのアクセス頻度に依存すると**推定**) | #166 に残置 (Closes しない)。PERF-P9 (#168) にコメント |
| lift の guest VA 相対化 pass (`LD32(a)` → `base+a`) の実装と、相対化後の bit-exact 確認 | 動的リンク/静的同居の前提 | 解決: #1200 (PR #1260 本体、PR #1494 で N=16 別 base の署名一致)。相対化の CPU コストと PIC 税は §9 |
| Chrome の Memory 本数上限 124〜125 に対する plugin 数の設計 (インスタンス畳み込み or 上限) | 大規模プロジェクトで instantiate 失敗 | 新規子チケット案 `[PERF-n] instance budget under 124-Memory cap`・PM 判断 |
| AudioWorklet 内での dlopen と >8 MB side module の async dlopen | dyn の実運用可否 | 新規子チケット案 `[PERF-n] dlopen in AudioWorklet`・PM 判断 (PERF-P3 #162 ローダ関連) |
| default visibility PIC の機序確定 (可変 global 仮説)・V8 版差 (node 22 は小) | 設計ルール化の根拠の強さ | #166 コメント |
| 元の run の CPU 型番が不明 (jsonl 未記録)、2 ホストで `dyn_def` の大きさが違う (×1.241〜1.254 と ×1.036〜1.077) 原因 (CPU 世代・μarch か runner 状態か) が未特定 | PIC 税の大きさを CPU 型番に紐付けられない。perf gate のしきい値設計に影響 | #166 コメント。型番記録つきの再測は PERF-P7 (#165) の低負荷再測と統合 |
| Windows / Android の commit charge (769 MiB × N 予約)・`sep_abs_lo` RSS 2 倍の原因 | ABS 高位 VA を残す場合のコスト | PERF-P7 (#165) にコメント |
| node 22 での測定 (計画は node 26)・Firefox/Safari・低負荷再測 | V8 版・ブラウザ差 | PERF-P7 (#165) |

## 6. 再現

```sh
bash tools/perf/p8/p8.sh                  # build → node → Chrome → tables → check (build+計測 748 s @4 コア)
P8_QUICK=1 bash tools/perf/p8/p8.sh       # 縮小 (N=1,4・reps 3・runs 1)
node tools/perf/p8/check.mjs --negative   # ネガティブコントロール (署名改ざんを検出)
# 診断: P8_JSFLAGS=--no-liftoff P8_OUT=tools/perf/p8/results/p8_diag.jsonl node tools/perf/p8/chrome_p8.mjs steady --n 1,16 --cfgs static_based,dyn_def,dyn_hid
```

次タスク提案: 実 OTT での再測 (上表 1 行目)、PIC 回帰ゲート (`dyn_def`/`dyn_hid` の比を perf gate に追加; しきい値は §2.5 のホスト差 ×1.036〜1.254 を踏まえて要設計)、VA 相対化 lift。

## 7. 実 OTT (bit-exact x64c lift) での再測 (PERF-P8 未達項目の解消)

既知類型との関係: 該当なし (計測のみ。lift・既存 wasm は未変更)。検証 HEAD: `72e1ae3e` (`bash tools/perf/p8/real/p8_real.sh`, `NS="1 2 4 8 16"`)。素材 `oc_artifacts: work-m6-ott` (`tools/ott/work/lift/ottl.cjs` = 既存 `tools/ott` の x64c lift 産物, 26 KB glue + 793 KB wasm, 署名 `6b1696f0`)。
生データ: `tools/perf/p8/results/real_ott.jsonl` (N=1,2,4,8,16 の各別プロセス, 計 5 行)。本節の全数値はこのファイルの各行から引く (実行は commit 72e1ae3e; 以降 `tools/perf/` は未変更)。node v22.23.3, 4 コア runner, loadavg 0.2〜0.6 (計測時)。CPU 型番は未記録 (本 run は `os.cpus()` の型番を取っていない)。

**方式**: 1 プロセスで `ottl.cjs` の `createModule` を N 回呼び、各 instance が独立の Memory を持つ状態で同一 OTT の `process` (128f = 1 block) を instance 順に round-robin 駆動。定常 = 1000 block × 7 rep の p50、instance 当たり µs/block。署名は `ott_x64c_bench.mjs` と同一手順 (全 instance で一致を確認)。

| N (instance) | load ms | setup ms | RSS 増分 MiB | µs/block (p50 [min–max]) | RTF@44.1k / instance | 署名 |
|---|---|---|---|---|---|---|
| 1 | 22.41 | 20.18 | 20.7 | 110.43 [109.82–113.14] | 0.03805 | 6b1696f0 ×1 |
| 2 | 30.62 | 22.94 | 28.7 | 112.49 [110.96–118.54] | 0.03876 | 6b1696f0 ×2 |
| 4 | 41.03 | 35.68 | 42.5 | 112.92 [111.77–114.46] | 0.03891 | 6b1696f0 ×4 |
| 8 | 59.51 | 59.55 | 66.6 | 113.32 [112.74–115.38] | 0.03904 | 6b1696f0 ×8 |
| 16 | 93.59 | 107.89 | 115.4 | 113.57 [113.34–113.79] | 0.03913 | 6b1696f0 ×16 |

表の値はすべて `real_ott.jsonl` の各行 (`load_ms` / `setup_ms` / `rss_load_mib` / `us_per_block_p50`・`_min`・`_max` / `rtf44_per_instance` / `sig_n`) から引いた。RSS 増分 = `rss_load_mib`。合計 RSS は同行の `rss_after_mib` (N=16 で 287.6 MiB)。

**読み取り**:
- 実 OTT でも **定常コストは instance 数にほぼ依らず平坦** (N=1→16 で 110.43 → 113.57 µs、+2.8% = 113.57/110.43)。先の合成カーネルの「plugin 別 Memory は静的リンクと同等」と整合。各 instance は 1 block あたり約 110〜114 µs で、44.1 kHz では RTF 約 0.038〜0.039 (1 instance の計算量の 3.8〜3.9%)。
- **1 instance の追加コスト** (N=16 の平均): load 約 5.8 ms (93.59/16 = 5.85) + setup 約 6.7 ms (107.89/16) + RSS 約 7.2 MiB (115.4/16)。N=16 で合計 RSS 約 288 MiB (287.6)。
- 合成カーネルと違い、実 OTT は **絶対 VA (0x30000000 台) 固定** のため、動的リンク / 静的同居の比較は本 lift のままでは組めない (guest VA の相対化 pass が前提; 下記未解決)。したがって実 OTT で測れたのは「plugin 別 instance」の構成のみ。
- 合成カーネルの PIC 税 (SIDE_MODULE) の実 OTT 版は §9 で測った (`-fvisibility=hidden` ×1.102、N=1、node)。

**範囲外 (未測)**: AudioWorklet での実 OTT 複数 instance (node と Chrome Worker は §8 で測定済み)。Chrome の Memory 本数上限 (124〜125) は実 OTT でも §8.2 で確認 (合成カーネルは §2.4 `p8_limit.jsonl`)。

## 8. 実 OTT の Chrome Worker 計測と Memory 本数上限 (PERF-P8 未達項目の解消 2)

既知類型との関係: 該当なし (計測のみ。lift・既存 wasm は未変更)。検証 HEAD: `f85ea3f4` (`node tools/perf/p8/real/chrome_real.mjs --n 1,4,16 --reps 7 --blk 1000 --runs 3` と `--limit 160 --runs 3`)。素材 `oc_artifacts: work-m6-ott` (`tools/ott/work/lift/ottl.wasm`, 864 MiB initial memory, import 5 関数)。
ブラウザ版は glue (`ottl.cjs`) が node 専用 (`node:fs`) のため使わず、wasm の import (`env` 2 + `wasi_snapshot_preview1` 3) を直接満たして `WebAssembly.instantiate` → `__wasm_call_ctors` → `ott_data_install` の順で初期化する (`tools/perf/p8/real/web/real_worker.mjs`)。処理手順・署名は node の `bench_real.mjs` と同一。
Chrome 154.0.8037.97 headless, Dedicated Worker, `AMD EPYC 9V45 96-Core Processor` (4 vCPU, `os.cpus()` 記録), loadavg[0] (1 分平均) は定常 9 行が 0.83〜2.00、上限 3 行が 1.40。条件×反復ごとに Chrome を新規起動。生データ: `tools/perf/p8/results/chrome_real.jsonl` (9 行) / `chrome_real_limit.jsonl` (3 行)。

### 8.1 定常・起動 (N = plugin 別 instance 数, 3 回の Chrome 起動 = 回ごとに値を併記。中央値は本文に明記)

| N | 回 | µs/block p50 | RTF@44.1k / instance | load ms | setup ms | renderer RSS 増分 MiB | 署名 |
|---|---|---|---|---|---|---|---|
| 1 | 1 / 2 / 3 | 129.27 / 119.83 / 120.44 | 0.04454 / 0.04129 / 0.04150 | 14.20 / 8.17 / 8.31 | 27.88 / 16.53 / 23.18 | 24.9 / 21.7 / 13.4 | 6b1696f0 ×1 (3/3) |
| 4 | 1 / 2 / 3 | 137.37 / 127.78 / 128.01 | 0.04733 / 0.04403 / 0.04410 | 15.40 / 28.11 / 22.23 | 37.32 / 28.35 / 35.85 | 62.6 / 73.6 / 59.7 | 6b1696f0 ×4 (3/3) |
| 16 | 1 / 2 / 3 | 131.80 / 129.07 / 149.66 | 0.04541 / 0.04447 / 0.05156 | 65.03 / 53.79 / 42.83 | 67.32 / 84.55 / 82.47 | 237.1 / 238.6 / 236.2 | 6b1696f0 ×16 (3/3) |

(RTF = µs/block ÷ (128/44100 s)。µs/block は 1000 block × 7 rep の p50 で、各 rep の値は全 instance の平均 (`elapsed / (blk·n)`)。各回は Chrome を新規起動。)

**読み取り**:
- 実 OTT の Chrome 定常コストは N に対して **ほぼ平坦** (+9%、run 間ばらつき内: N=1 の中央値 120.44 → N=16 の中央値 131.80 µs、run 間のばらつきは 119.8〜149.7 µs と重なる)。node (§7、N=1→16 で +2.8%) より増分は大きいが、合成カーネル (§2) の「静的リンクと同等」からの大きなずれではない。増分の正確な機序は未特定。
- 1 instance の追加コスト (N=16, 3 回の中央値): load 53.79/16 ≈ 3.4 ms + setup 82.47/16 ≈ 5.2 ms、RSS 増分 237.1/16 ≈ 14.8 MiB。N=16 の合計 renderer RSS 約 358 MiB (358.3〜358.9)。
- 起動時間は固定費 + 約 3 ms/instance (N=1→16 で load 中央値 8.31→53.79 ms、増分 45.5 ms ÷ 15 instance ≈ 3.0 ms/instance)。

### 8.2 Memory 本数上限 (実 OTT, 1 Worker 内で instance を 160 本まで生成を試行)

| 試行 | 成功 instance 数 | 失敗メッセージ | renderer RSS MiB |
|---|---|---|---|
| 1 | 125 | `WebAssembly.instantiate(): Out of memory: Cannot allocate Wasm memory for new instance` | 872.5 |
| 2 | 125 | 同上 | 874.7 |
| 3 | 124 | 同上 | 868.5 |

合成カーネル (§2.4) の 124〜125 本と同じ上限。実 OTT の initial 864 MiB でも Chrome 154 では 124〜125 本で `instantiate` が失敗する。**plugin 数が 124 を超える構成の対応は [REPORT_P15](REPORT_P15.md) と DECISIONS D10 (同一 Memory への畳み込み) を正とする**。

### 8.3 結論の更新 (実 OTT の範囲)
- plugin 別 instance の**定常**は実 OTT でも node / Chrome Worker で ほぼ平坦 (node +2.8%、Chrome +9%・run 間ばらつき内; §7, §8.1)。
- **Memory 本数上限 124〜125 は実 OTT でも同一** (§8.2)。方式の決定 (採る方式 = 同一 Memory への処理オブジェクト畳み込み、Chrome で M=130 駆動・署名一致) は [REPORT_P15](REPORT_P15.md) と DECISIONS D10 が正本。
- 相対化 lift の **PIC 税 (SIDE_MODULE, hidden, N=1)** は §9 で実 OTT の実測 (×1.102)。**静的同居** (N≥2) は未測。前提の guest VA 相対化は #1200 (PR #1260 / #1494) で完了。Memory 本数上限への設計は #990 (`[PERF-P15]`) で扱う。

## 9. 相対化 lift の CPU コストと SIDE_MODULE の PIC 税 (実 OTT, LIFTLIB-15 / #1201)

既知類型との関係: 該当なし (計測のみ。既定 lift・x64c は未変更。相対化モードは #1200 の `OTT_RELOC=1`)。
測定 commit: `3da6b009` (コードを変えた最後の commit。計測スクリプトと side ビルド定義を追加)。lift・side の全 artifact はこの commit の worktree で再ビルドして測った。
差分の証跡: `git diff 3da6b009 HEAD -- tools/ott tools/perf/p8/real` の差分は `tools/ott/lift/side_build.sh` の冒頭コメント (2 行を書き直し) だけ。コメント以外の変更は 0 (`git diff 3da6b009 HEAD -- tools/ott tools/perf/p8/real | grep '^[-+]' | grep -v '^+++\|^---' | grep -vE '^[-+]\s*#'` の出力が空)。測定 artifact の再ビルドは不要。
CPU: **AMD EPYC 7763 64-Core Processor (4 vCPU)**、node v22.23.3。計測時 loadavg 1 分値 1.05〜1.25 (reloc 1.05〜1.23・pic 1.23〜1.25。`loadavg_before` 列を `results/real_ott_{reloc,pic}.jsonl` に記録。5 分値は 1.03〜1.05)。
ビルド: 既定 = `LIFT_OUT=… bash tools/ott/lift/lift_build.sh`、相対化 = 同 + `OTT_RELOC=1` (std profile = `-O3 -flto`)。SIDE = 相対化 lift の C を `tools/ott/lift/side_build.sh` で `-fPIC -fvisibility=hidden -sSIDE_MODULE=2` にし、`side_host.c` (MAIN_MODULE=2、`-O2`) が dlopen して `ott_run` を呼ぶ。compile の最適化・FP フラグは既定と同じ (`stdbuild.py flags std`)。
素材: `oc_artifacts: fl-win64 toolchain-emsdk analysis-ott-binaries work-m6-ott`。artifact の `tools/ott/work/lift/ottl.wasm` (793 KB) は std 以外の profile の旧産物で、§7 の 110 µs はそれによる。本節の数値とは直接比較しない。

**(a) 相対化の CPU コスト** (`bash tools/perf/p8/real/reloc_cost.sh`、既定と相対化を交互に 3 独立プロセス、各 p50 の中央値 (min–max))

| N | 既定 lift µs/block | 相対化 lift µs/block | 比 (相対化/既定) | 署名 |
|--:|--:|--:|--:|---|
| 1 | 91.23 (91.19–91.64) | 94.29 (94.00–94.34) | ×1.034 | 6b1696f0 (6/6 プロセス) |
| 4 | 91.52 (91.43–91.90) | 94.26 (94.10–94.37) | ×1.030 | 6b1696f0 (6/6) |
| 16 | 91.91 (91.91–92.01) | 94.62 (94.56–94.71) | ×1.029 | 6b1696f0 (6/6) |

- 相対化の定常コストは既定比 **×1.03**。N=1→16 の増分は相対化 +0.4%・既定 +0.8% で、N によらず平坦。各構成の run 間の幅は PR 実測 (上表の min–max、jsonl) で ≤0.5%、検収側の独立再測 (同 head を再ビルド、記録は PR コメントで jsonl なし) で N=4 相対化の run 間幅 1.40% (94.08〜95.40)。+3% はどちらでも分解能の外。独立再測の比は ×1.031 / ×1.029 / ×1.029 で、上表 (N=1 のみ 0.3% 差) と同じ桁。

**(b) SIDE_MODULE の PIC 税** (`RUNS=5 bash tools/perf/p8/real/pic_tax.sh`、静的相対化と SIDE を交互に 5 独立プロセス、N=1)

| 構成 | µs/block p50 中央 (min–max) | 署名 |
|---|--:|---|
| 静的 (非 PIC) 相対化 `static_reloc` (`api.mjs` の `load()` 経由・JS から `ott_run` 直呼び) | 94.16 (94.03–94.80) | 6b1696f0 (5/5) |
| SIDE_MODULE 経由 `side_reloc_hidden` (`-fPIC -fvisibility=hidden`。dlopen・host 中継・link 条件の差を含む) | 103.79 (103.67–104.81) | 6b1696f0 (5/5) |

- **PIC 税 = ×1.102** (中央値の比。対ごとの比は ×1.094–×1.110)。署名は 10/10 プロセスで `6b1696f0` (side module の dlopen 経由でも一致)。
- ネガティブコントロール: `SIDE_NEG=skip_data_install node tools/perf/p8/real/side_bench.mjs tools/ott/work/side_reloc 1000 1` (`ott_data_install` を省く) は **rc=1**。stderr の先頭行は `[ott] call to UNLIFTED function 0 (shifted VA; RVA 0xffffffffd0000000) ret=0x301a03d5`、続けて `Aborted()`。stdout は空で、署名行は出ない。未敷設は fail-fast で検出される (HEAD `43eacb0f` で実測。同じ HEAD で通常実行は署名 `6b1696f0`)。
- 合成カーネル (§2.1) の `-fvisibility=hidden` の増分は runner で ≤1.2%、EPYC で ≤2.6%。実 OTT の hidden は ×1.10 で、合成より大きい。合成の結論 (hidden は小さい) を実 OTT に当てはめてはいけない。
- 機序は**未特定**。静的版と side 版の差は次のすべてで、PIC 税 ×1.10 はこの総和。内訳は分離していない:
  1. **compile**: side は `-fPIC -fvisibility=hidden -sSIDE_MODULE=2` と `-include side_compat.h` を足す。compile の最適化・FP フラグは同じ (`stdbuild.py flags std`)。候補 (a): globals が `__memory_base` 経由でアクセスされる。
  2. **link**: 静的版 (`lift_build.sh`) にあって side に無いもの = `-sGLOBAL_BASE=268435456`・`-Wl,--initial-memory/--max-memory=0x36000000`・`-sMODULARIZE`・`-sEXIT_RUNTIME=1`・`-sALLOW_MEMORY_GROWTH=1`・`-sSTACK_SIZE=2MB`・`-sENVIRONMENT=node`。静的版の data は GLOBAL_BASE 側。side 版は `host_set_gbase(0x30000000)` で base を与え、`host_data_install` で敷設する。候補 (b): データ配置の差。
  3. **呼出し経路**: 静的版は `api.mjs` の `load()` が `_ott_data_install` だけを呼び、JS → `ott_run` を直接呼ぶ。side 版は JS → `host_run` (host wasm、`-O2`、std ではない) → dlopen 先の `ott_run` (関数ポインタ経由) の 1 段の中継が入る。1 block あたりの寄与は**推定**で、§2.2 の呼出分解能 (±26 ns) の桁と見込むが未測定。
  4. **global の import**: side.wasm は `__stack_pointer` (mutable) と `__memory_base` (immutable、mut=0) を global として import し、`env.memory` も import する。静的版の `ottl.wasm` は global の import も memory の import も 0 件 (HEAD で再ビルドした import section を解析して確認)。候補 (c): `__stack_pointer` の可変 global 参照のコスト。**機序は未検証** (分離の測定は未実施)。

**範囲 / 検証**: node のみ (Chrome Worker・AudioWorklet は未測)。N=1 のみ (side module を 1 つ dlopen。同居させるには別バイト列の一意化が要る)。`-fvisibility=default` の実 OTT は未測。署名検査は `check` 系の別アルゴリズムではなく bench と同じ FNV (1000 block) の手順。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| side module の N≥2 (同居・静的同居・別バイト列の複数 dlopen) | 動的リンクの同居時の CPU・起動 (§2.3 の合成値は未確認) | 親 #989 (OPEN) への提案 (子 issue 化の要否は PM 判断) |
| `-fvisibility=default` の実 OTT 測定 (合成では大きい増分) | PIC 税の上限 | 親 #989 (OPEN) への提案 (PM 判断) |
| PIC 税の機序 (-fPIC の寄与・データ配置・呼出し経路・global import の分離) | perf gate のしきい値設計 | 親 #989 (OPEN) への提案 (PM 判断) |
| Chrome Worker・AudioWorklet 上の side module | 実運用の可否 | 親 #989 (OPEN) への提案 (PM 判断) |
