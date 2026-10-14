# tools/audio REPORT 付録 (#863 AU-15)

> **ナビゲーション**: 本ファイルは `tools/audio/REPORT.md` の分割移動節の付録。
> 正本の索引は `REPORT.md`。250 行上限 (`docs/DOC_MAP.md` §1) のため、§20 の全文をここへ移した。
> 内容は削除していない (Git 履歴にも残る)。

## 20. AU-15 (#863) 現 HEAD での再試行 (失敗 0 件)

測定 HEAD は `origin/main` `2f235a0a` (worktree `ws-863`・コード差分なし)。素材 `fl-win64` を `$RUNNER_TEMP/fl-win64/extracted`、`toolchain-emsdk` を `EMSDK_ENV` に指定。`bash tools/audio/integration/e2e.sh` を foreground で実行。

- 無負荷 9 run (load 1.64〜2.34): **9/9 exit 0・13/13 PASS** (11〜12 s)。
- CPU 負荷 (busy loop 6 本) 下 6 run (load 3.74〜9.52): **6/6 exit 0・13/13 PASS** (21〜23 s)。
- 計 15 run 全 PASS。dev:tone `max_err=1.49e-8` zero_runs 0・dev:underruns underruns 0・`first_err_frame=-1` (全 15 run のログで同値。rms の丸め差 1 件のみ)。
- 失敗が再現しなかったため、producer (wasm 出力遅延) と consumer (worklet rebuffer) の切り分けは未実施。旧 HEAD `bb912951` の失敗ログ (REPORT.md §19) が唯一の失敗例。
- 追跡 **#863** (AU-15) のまま。次回失敗時は REPORT.md §19 の位置情報 (`first_err_frame` 等) を取得して切り分ける。

## 21. AU-15 (#863) 再試行 (失敗 0 件・計 27 run)

測定 HEAD は `origin/main` `63ed695b` (worktree `ws-863`・コード差分なし)。素材 `fl-win64` を `$RUNNER_TEMP/fl` へ展開 (`FL_WIN64_DIR`)、`toolchain-emsdk` を `$RUNNER_TEMP/emsdk` へ展開 (`EMSDK_ENV`)。`pnpm install --frozen-lockfile` 後、`bash tools/audio/integration/e2e.sh` を foreground で実行。

| 区分 | run 数 | 結果 | wall | load (開始時) |
|---|---|---|---|---|
| 初回 | 1 | 13/13 PASS exit 0 | 37 s (初回 emsdk キャッシュ生成を含む) | 0.79 |
| 無負荷 | 6 | 6/6 exit 0・13/13 PASS | 11〜12 s | 1.66〜2.23 |
| CPU 負荷 (busy loop 6 本) | 4 | 4/4 exit 0・13/13 PASS | 20〜21 s | 6.06〜8.54 |
| 混合 (無負荷と負荷を交互) | 10 | 10/10 exit 0・13/13 PASS | 11〜21 s | — |
| 強負荷 (busy loop 12 本・論理 4 CPU) | 6 | 6/6 exit 0・13/13 PASS | 16〜31 s | 11.44〜16.25 |

- 計 27 run 全 PASS。全 run のログで dev/preview の tone 照合 `max_err=1.49e-8` (54 件すべて同値)・`zero_runs=0`・`underruns=0`・`first_err_frame=-1`。N1 (sr×1.01 のネガティブ制御) は全 run で `max_err=1.00e+0` となり検出できている。
- 失敗が 0 件のため、producer (wasm 出力遅延) と consumer (worklet rebuffer) の切り分けは未実施。
- 本 HEAD の負荷条件 (最大 busy loop 12 本・load 16) でも再現しない。旧失敗 (§19, 旧 HEAD `bb912951`・11 run 中 1 件) の条件は未特定のまま。
- 追跡 **#863** (AU-15) のまま。次回失敗時は REPORT.md §19 の位置情報を取得して切り分ける。

## 22. AU-15 (#863) 失敗ログの永続化 (e2e.sh 改修)

- 問題: `e2e.sh` の出力は stdout only で、失敗時の位置情報 (`first_err_frame` 等) が run 終了後に残らなかった。位置情報自体は `e2e.mjs` が FAIL 行の detail に出しており、コードは既にある。
- 改修: `e2e.sh` の node 実行を `tee` で `tools/audio/work/e2e_last.log` (gitignore) に保存し、終了コードは node の値をそのまま返す。コミット `7d275cb0` (`tools/audio/integration/e2e.sh` のみ)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` へ展開 (`FL_WIN64_DIR`)、`toolchain-emsdk` は [EMSDK] (6.0.12) を `EMSDK_ENV` で使用。`TMPDIR=$RUNNER_TEMP`。
- 測定 commit: `7d275cb0` (改修後 HEAD)。改修前の基準は `origin/main` `f3ffd7ba` で 13/13 PASS (22.5 s)。
- 改修後 HEAD の実測 (foreground):

| 区分 | run 数 | 結果 | wall | load (開始時) |
|---|---|---|---|---|
| 改修前 HEAD `f3ffd7ba` | 1 | 13/13 PASS exit 0 | 22.5 s | 0.6 |
| 改修後 HEAD 直後 (busy loop なし) | 1 | 13/13 PASS exit 0・ログ生成 | 13.7 s | 0.5 |
| 改修後 HEAD・busy loop 6 本 (前 run の残存を含む) | 12 | 12/12 exit 0・13/13 PASS・FAIL 0 | 20〜29 s | 9.4〜13 |

- 改修後 HEAD (`7d275cb0`) の run は 1 + 12 = 13 run で全 PASS exit 0 (改修前基準 1 run を含む総計 14 run)。`busy loop 6 本` の 12 run は旧表の 3 行 (負荷 6 run / 残存下 3 run / 負荷 3 run) を統合したもの。条件はいずれも busy loop 6 本で、開始時 load だけが違う。
- 注: 「直後」の 1 run は開始時 load 0.5 だが、純粋な無負荷の再測定は未実施。
- 鮮度: 測定 commit `7d275cb0` → HEAD (`5ca86ce0`・本 fix 時点) の `git diff 7d275cb0 HEAD -- tools/audio/integration` は出力 0 行 (差分 0)。HEAD 側の差分は `tools/audio/REPORT_APPENDIX_863.md` のみで、実行されるコードは変わらないため再測定は不要。
- ログ出力先 `tools/audio/work/e2e_last.log` は gitignore 対象の生成物で、運用ルールでは生成物を `work/` に置く。よって e2e.sh は変えていない。
- 失敗は 0 件。producer (wasm 出力遅延) / consumer (worklet rebuffer) の切り分けは未実施。旧失敗 (§19) の条件は引き続き未特定。
- 未解決: (a) CI に e2e を組み込んでいない (`.github` に参照なし) ため、失敗ログを CI artifact として残す経路は無い。(b) 失敗の再現条件の特定。追跡は **#863**。

## 23. AU-15 (#863) 再現試行と位置情報の読み (測定 commit 1e3ee7af = origin/main、コード差分 0)

- 測定: `bash tools/audio/integration/e2e.sh` (素材 fl-win64 + toolchain-emsdk 展開、`TMPDIR=$RUNNER_TEMP`、foreground)。
- 結果 (計 12 run・失敗 1):

| 区分 | run 数 | 結果 | wall | load (開始時) |
|---|---|---|---|---|
| 無負荷 (1 回目) | 1 | **FAIL** (dev:tone / dev:underruns。exit 1) | 10.5 s | 1.35 |
| 無負荷 (2〜6 回目) | 5 | 5/5 PASS (13/13) | 12 s | 1.35〜2.03 |
| busy loop 6 本 | 6 | 6/6 PASS (13/13) | 21〜22 s | 3.38〜9.79 |

- 失敗 run の位置情報 (`tools/audio/work/e2e_last.log`・dev のみ、preview は PASS):
  `dev:tone max_err=6.53e-1 rms=0.3510 zero_runs=1 first_err_frame=56576 first_zero_run_frame=56607 underrun_cap=1 first_underrun_frame=56576 last_underrun_frame=56576`。
- 旧失敗 (§19) と同じ `first_err_frame` / `first_underrun_frame` = 56576 (quantum 442)。zero run は 31 frame 後の 56607 から始まる。
- 切り分けの読み: underrun 計数は worklet 側 (`capture hdr[6]`) で取られ、その時点で出力が既に誤っている。よって「consumer (worklet 側のリング枯渇) で観測された」ことまでは言える。producer (wasm の出力到達時刻) 側の時刻は取っていないため、producer 遅延が原因かは**未確定**。
- 再現条件 (本節の 12 run 内の内訳): 無負荷 1/6・busy loop 6 本 0/6。負荷との相関は見えていない。
- 節ごとの FAIL 件数 (HEAD が節によって異なるため、合計は参考値): §19 (旧 HEAD `bb912951`) 1/11、§20 0/15、§21 0/27、§22 0/14 (改修前 1 + 改修後 13)、§23 1/12。計 **2 件 / 79 run** (11 + 15 + 27 + 14 + 12)。
- `shim_port.not_implemented_yet` の console.error は全 12 run (PASS 含む) に出ている。失敗とは無関係。
- 未解決 (追跡 **#863**): (a) producer 側の到達時刻 (fla_test の出力 quantum ごとの時刻) を capture に追加しないと切り分けられない。(b) 再現頻度は本節の個別 run 数で書く (無負荷 1/6・busy loop 6 本 0/6)。母数が少なく条件は未特定。

## §24 照合に充填量・audio callback 間隔を追加 (測定 commit 529ab8e8、Refs #863)

- 目的: 失敗時に producer / consumer を切り分ける材料として、worklet が既に capture へ書いている値を照合 (`verifyToneCapture`) で読むようにした。wasm 再ビルドは不要。
  - `fill_at_first_underrun`: 最初の underrun の quantum で consume 前に記録された出力リング充填量 (frames)。0 付近なら producer 側の供給不足。
  - `fill_min_before_first_underrun`: 最初の underrun 直前 32 quantum 内の充填量の最小値。段階的に低下していれば producer 遅延が先行。
  - `cb_gap_max_ms` / `cb_gap_over20`: audio callback 間隔の最大値と 20 ms 超の回数。大きければ consumer (音声スレッド) 側の停止。
- コード差分: `src/runtime/audio_app.ts` +21 行 / `tools/audio/integration/e2e.mjs` 1 行 (commit 529ab8e8)。
- 測定: 素材 fl-win64 + toolchain-emsdk 展開、`bash tools/audio/integration/e2e.sh` を foreground で実行 (`TMPDIR=$RUNNER_TEMP`)。

| run | load (開始時) | 結果 | dev:tone max_err | zero_runs | underrun | cb_gap_max_ms | cb_gap_over20 |
|---|---|---|---|---|---|---|---|
| 初回 (新フィールド確認) | 1.14 | 13/13 PASS exit 0 | 1.49e-8 | 0 | 0 | 11 | 0 |
| b1 | 1.69 | 13/13 PASS exit 0 | 1.49e-8 | 0 | 0 | 11 | 0 |
| b2 | 2.46 | 13/13 PASS exit 0 | 1.49e-8 | 0 | 0 | 11 | 0 |
| b3 | 3.56 | 13/13 PASS exit 0 | 1.49e-8 | 0 | 0 | 11 | 0 |
| b4 | 3.08 | 13/13 PASS exit 0 | 1.49e-8 | 0 | 0 | 11 | 0 |
| b5 | 2.68 | 13/13 PASS exit 0 | 1.49e-8 | 0 | 0 | 11 | 0 |
| b6 | 2.42 | 13/13 PASS exit 0 | 1.49e-8 | 0 | 0 | 11 | 0 |

- 計 7 run 全 PASS。全 run で `fill_at_first_underrun=-1` / `fill_min_before_first_underrun=-1` (underrun 0)。
- 初回の 13/13 PASS の所要は 10.2 s (`real`)。
- 検証の注意: 最初の試行は未コミットの編集を含まない `git archive HEAD` を検証したため、新フィールドが `undefined` と出た。コミット後に再実行して値が出ることを確認したので、上の 7 run はコミット済み HEAD での結果。
- 読み: 今回は underrun が 0 件のため、producer / consumer の切り分けは**未実施**。新フィールドは次回失敗時の判定材料になるが、現 HEAD では実測値は得られていない。
- 再現頻度 (通算、§19〜§23 の既存集計に今回の 7 run を加算): FAIL 2 件 / 86 run (§19 1/11、§20 0/15、§21 0/27、§22 0/14、§23 1/12、§24 0/7)。母数が少なく条件は未特定。
- 未解決 (追跡 **#863**): (a) producer 側の出力到達時刻 (fla_test の quantum ごとの時刻) は wasm 側の変更が必要で本 PR の範囲外。(b) 再現条件の特定。

## §25 AU-15 (#863) 再現試行 (32 quantum の充填推移を追加・計 45 run)

- 測定 commit: `4dc3df47` (`src/runtime/audio_app.ts` の `fill_trace_before_first_underrun` と `e2e.mjs` の FAIL 行出力を追加したもの。`origin/main` `b6361886` の上に 1 commit)。コード差分の範囲は `src/runtime` と `tools/audio/integration`。
- 失敗時の出力に `fill_trace=[...]` (最初の underrun までの 32 quantum の充填量・古い順) を追加した。`fill_min` のみでは、充填が徐々に減った (producer 遅延) か一度に落ちた (consumer 停止) かを区別できないため。
- 測定: 素材 fl-win64 + toolchain-emsdk 展開、`bash tools/audio/integration/e2e.sh`、foreground、`TMPDIR=$RUNNER_TEMP`。

| 区分 | run 数 | 結果 | wall | load (開始時) |
|---|---|---|---|---|
| 旧 HEAD `b6361886` (probe 追加前)・初回 | 1 | **FAIL** (dev:tone / dev:underruns。exit 1) | 36.6 s | 初回 (未計測) |
| 無負荷 (probe 後) | 8 | 8/8 exit 0・13/13 PASS | 11〜12 s | 1.15〜1.64 |
| busy loop 6 本 | 6 | 6/6 exit 0・13/13 PASS | 20〜22 s | 4.25〜9.03 |
| busy loop 4 本 (連続 30 run・負荷下) | 30 | 30/30 exit 0・13/13 PASS | — | 7.14〜10.24 |

- 失敗 run の位置情報 (旧 HEAD・probe 前のため fill 推移は無し): `dev:tone max_err=6.85e-1 zero_runs=1 first_err_frame=56576 first_zero_run_frame=56607 first_underrun_frame=56576 fill_at_first_underrun=0 fill_min_before_first_underrun=0 cb_gap_max_ms=11 cb_gap_over20=0`。dev のみで preview は PASS。
- 同一フレームの再出現: `first_err_frame = first_underrun_frame = 56576` (quantum 442) は §19 / §23 / 本節の 3 件すべてで一致。負荷量はばらばらで、相関は見えていない。
- 読み: 失敗 run では `fill_at_first_underrun=0` (underrun の時点でリングは空)。`cb_gap_max_ms=11` / `cb_gap_over20=0` で、audio callback 間隔は 20 ms を超えていない。ただし fill 推移は取れていないため、producer 遅延か consumer 停止かは**未確定**。
- 通算 (§19〜§25 の同一 e2e): FAIL 3 件 / 計 131 run (§19〜§24 の 2 件 / 86 run に、本節の 45 run・FAIL 1 件を加算)。本節の FAIL は旧 HEAD `b6361886` の初回 1 run のみで、probe 後の 44 run は全 PASS。
- 未解決 (追跡 **#863**): (a) fill 推移を含む失敗 log が未取得 (次回失敗時に `fill_trace` で判定)。(b) 同一フレーム 56576 が 3 回出る理由は未特定 (起動からの相対位置が固定なら、決定的な起動経路の問題の可能性)。(c) producer 側の到達時刻 (wasm 側の変更) は本 PR の範囲外。

## 26 AU-15 (#863) 断続失敗の捕獲試行 (hunt.sh・連続 131 run 全 PASS)

- 測定 commit: `c604805c` (`tools/audio/integration/hunt.sh` を追加。検証対象のコード (`e2e.sh`・`e2e.mjs`・`src/runtime`) は変更なし)。`origin/main` `8d632b57` の上に 1 commit。
- 方法: `EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk/emsdk_env.sh TMPDIR=$RUNNER_TEMP bash tools/audio/integration/hunt.sh 300 1380` を foreground で実行。`hunt.sh` は `e2e.sh` を繰り返し、最初の FAIL で止めて全出力を `tools/audio/work/hunt/fail_<n>.log` に残す (gitignore)。時間上限 1380 s。素材は `toolchain-emsdk` のみ展開 (e2e の経路は `fl-win64` を参照しない)。
- 結果: **131 run 全 PASS** (exit 0)。各 run の 13/13 は当時の summary に残っていない (exit 0 と e2e.mjs の check 数 13 (6 × 2 モード + N2) から導く。summary に check 欄を入れたのは §27)。FAIL 0 のため捕獲ログは無し。1 run の wall は 10〜11 s (build 込み)。load は**実行直後の 1 分 load** (`bash e2e.sh` の後に `/proc/loadavg` を読んだ値で、run 自身の負荷を含む) で 0.54〜2.68。「無負荷」は busy loop を足していない意味で、開始時の load は測っていない。
- 通算 (§19〜§26 の同一 e2e): FAIL 3 件 / 計 262 run。失敗 3 件はいずれも HEAD が異なる (`bb912951`・`1e3ee7af`・`b6361886`)。失敗後の 44 run (§25 の probe 後) と本節の 131 run、計 175 run は全 PASS。
- 統計の読み: 通算率は約 1.1% (3/262)。その率なら 131 run で 0 件となる確率は約 0.23 (0.989^131)。0 件は「率が下がった」の根拠にはならない。
- 既存の位置情報からの読み (§25 の失敗 1 件・probe 前の旧 HEAD のため fill 推移 `fill_trace` は無し): `fill_at_first_underrun=0` (underrun の時点でリングは空)、`fill_min_before_first_underrun=0`、`cb_gap_max_ms=11`・`cb_gap_over20=0` (audio callback の 20 ms 超は無い)。よって **consumer (音声スレッドの停止) で説明できる証拠は無い**。リングの供給不足 (producer 側の遅れ) に寄る読みだが、fill 推移つきの失敗は 0 件で、producer 側の到達時刻も取っていないため、producer 遅延と断定はできない。
- 未解決 (追跡 **#863**): (a) 失敗の捕獲は `hunt.sh` を長く回す run が必要 (1 run ≈ 10 s、時間上限内で約 130 run)。(b) producer 側の到達時刻は wasm 側の変更が要る (本 PR の範囲外)。(c) 再現条件 (負荷・タイミング) は未特定。(d) §25(b) の反証を残す: 3 件の FAIL はいずれも `first_err_frame = 56576` (quantum 442) で、HEAD と負荷量が違っても一致する。「producer 側の遅れに寄る読み」だけでは説明できず、「起動からの相対位置が固定 (決定的な起動経路)」の可能性が消えていない。本節の 131 run は FAIL 0 のため判定材料にならない。

## 27 AU-15 (#863) hunt.sh の失敗経路の修正と実測 (測定 commit `c37dd517`)

- 修正前の不具合 (`hunt.sh` の §26 版): run の出力を捨て、失敗時に `tools/audio/work/e2e_last.log` を `cp` していた。`e2e_last.log` を書くのは `e2e.sh` の `tee` (検査段に入ってから) だけなので、ビルド段 (patch・stage_app・tsc・vite build) で落ちた run では前回 run の PASS ログがそのまま捕獲された。`cp` の失敗も無言だった。
- 修正: `bash e2e.sh > <出力>/last.log 2>&1` で run ごとの stdout / stderr 全体 (ビルド段を含む) を受け、FAIL 時だけ `mv` で `fail_<n>.log` へ移す (`mv` 失敗は exit 1 で報告)。PASS 行には e2e.mjs の `[au9] N/M PASS` 行を載せ、`check=13/13 PASS` を run ごとの根拠として残す。
- 変更範囲: `git diff c604805c c37dd517 -- tools/audio/integration` は `hunt.sh` の 9 行追加・4 行削除のみ。`e2e.sh`・`e2e.mjs`・`src/runtime` は変更なし。

### 負例 (NC): FAIL 経路の実測

| NC | 条件 (EMSDK_ENV) | 結果 |
|---|---|---|
| NC-1 (§26 の不具合の再現形) | 1 回目だけ本物の emsdk を source し、2 回目は source しない (emcc が PATH に無い状態で、ビルド段が落ちる)。`hunt.sh 3 600` (HEAD `c37dd517`) | run 1 PASS `check=13/13 PASS` → run 2 FAIL `exit=1` → hunt exit 1 (run 3 へ進まず)。`fail_2.log` は 2 行 (`[au9] index.ts は適用済み` と `[audio] emcc not found`)。PASS 行 0 件 |
| NC-1' (旧 hunt.sh) | NC-1 と同じ条件で `c604805c` の hunt.sh を実行 | `fail_2.log` に run 1 の PASS 行が 14 件残り、`emcc not found` は 0 件。レビューの指摘どおり不具合を再現 |
| NC-2 | 存在しないパス (emcc が PATH に無い)。`hunt.sh 3 600` (HEAD `c37dd517`) | run 1 FAIL `exit=1` → hunt exit 1。`fail_1.log` に `emcc not found` が入る (1 件) |

- NC の wrapper は `$RUNNER_TEMP` に置いた一時ファイルで、リポジトリには含めない。
- NC-1' は旧 hunt.sh を一時的に `tools/audio/integration/` へ置いて実行し、直後に削除した (未コミット)。

### PASS 側の再測定 (変更後 HEAD)

- 測定: `c37dd517` (コードを変えた最後の commit)。`EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk/emsdk_env.sh TMPDIR=$RUNNER_TEMP bash tools/audio/integration/hunt.sh 40 300` を foreground・時間上限 300 s で実行。
- emsdk: 素材 `toolchain-emsdk` は本 run の `$ARTIFACTS_DIR` に無かったため、上流 tag `6.0.12` (`tools/m1/flags.sh` の pin と同版) を `emsdk install 6.0.12` / `activate` で取得した。`emcc --version` は 6.0.12。R2 の toolchain-emsdk との同一性は未確認。
- 結果: **27 run 全 PASS** (exit 0・各 run `check=13/13 PASS`)、FAIL 0。hunt は時間上限で停止 (`[hunt] 時間上限 300s 到達: PASS 27 run / FAIL 0`)。
- 1 run の wall は 11〜12 s。実行直後の 1 分 load は 0.28〜3.05 (run 自身の負荷を含む。busy loop なし)。

### 注 (鮮度・範囲)

- 測定 base `8d632b57` は現 `origin/main` `b7df55e6` より古い。main では `src/runtime/audio-layout.ts` (+1 行) と `src/runtime/audio-shim.ts` (2 行変更) が変わっており、本測定には入っていない (未測定)。PR head の鮮度は保たれている (`git diff c604805c HEAD -- src/runtime` は 0 行)。
- 通算 (§19〜§27 の同一 e2e): FAIL 3 件 / 計 289 run。§26 の未解決 (a)(b)(c)(d) は残る。捕獲の仕組みは NC で検証済みだが、失敗の再現は未達 (追跡 **#863**)。

## 28 AU-15 (#863) producer 起床統計 (wake_hist) を判定行へ追加 (測定 commit `f370c4ed`)

- 目的: 失敗時に producer 側の遅延の有無を見る材料を、wasm を再ビルドせずに取る。`fla_out_wait_fill_le` (`tools/audio/src/flasio.c`・`flaudio.c`) は ctl の `wake_hist[6]` (worklet の `notify_ms` から producer の起床までの遅延 ms。区間は <1 / <2 / <4 / <8 / <16 / ≥16) と `wake_count`・`wait_timeouts` を既に書いていたが、判定行に出していなかった。
- 変更 (`f370c4ed`): `src/runtime/audio-shim.ts` の `producerStats()`、`src/runtime/audio_app.ts` の `FlAudioSession.producer()`、`src/index.ts` の `window.__audio.verify` に `producer` を追加、`tools/audio/integration/e2e.mjs` の判定行 (tone / underruns) に `prod_wake_hist=a/b/c/d/e/f prod_wake_count=N prod_wait_timeouts=N` を出力。`tools/audio/integration/index.ts.diff` も同じ変更 (現 tree では `startFlAudio` が既に入っているため適用はスキップされる)。
- 注意: `wake_hist` は run 全体の累積で、起床の時刻は残らない。失敗位置との突き合わせは §25 の `fill_trace` と併用する。

| 区分 | run 数 | 結果 | dev の prod_wake_hist (<1/<2/<4/<8/<16/≥16) | prod_wait_timeouts |
|---|---|---|---|---|
| 初回 (`f370c4ed`) | 1 | 13/13 PASS | 301/13/0/0/0/0 (count 314) | 0 |
| 無負荷 | 4 | 4/4 PASS exit 0 | 303/12/0/0/0/0・313/8/0/0/0/0・299/9/0/0/0/0・301/7/0/0/0/0 (count 308〜321) | 0 (全 4 run) |
| busy loop `yes` ×12 (`timeout 60`・開始時 load 7.9 / 13.4) | 2 | 2/2 PASS exit 0 | 293/12/21/0/0/0 (count 326)・315/7/9/0/0/0 (count 331) | 0 (全 2 run) |
| `hunt.sh 400 1080` (foreground・時間上限 1080 s) | 91 | **91/91 PASS exit 0・FAIL 0** | hunt は run ごとの統計を残さない (最終 run のみログに残る) | — |

- 計 98 run (初回 1・無負荷 4・負荷 2・hunt 91) 全 PASS。dev:tone の `max_err=1.49e-8`・`zero_runs=0`・`underruns=0`・`first_err_frame=-1` は、判定行を確認した run の**代表値**であり、全 run の値ではない。hunt の 91 run は PASS 判定と check 件数 (`check=13/13 PASS`) だけを `summary.txt` に残し、dev:tone の値は残していない (`last.log` は最終 run のみ)。preview も全 PASS。
- 読み (観測事実のみ): 無負荷の 4 run では全 wake が 2 ms 未満 (<1 ms と <2 ms の 2 区間のみ)。`yes` ×12 の 2 run では 2〜4 ms の区間に 21 / 9 回入り、≥8 ms は 0 回、underrun は 0 だった。負荷は `yes` ×12 の 1 段階だけで、負荷量と起床遅延の関係 (用量反応) は測っていない。`wake_hist` は PASS/FAIL の判定条件 (`rec` の条件式) に入っておらず、負例も作っていないため、判定指標としての感度は未検証。判定への組み込みも未検証。
- 失敗の記録 (通算): §19・§23・§25 の FAIL 3 件はいずれも、その節で最初に走らせた e2e run (§19 は初回 1 run・§23 は無負荷の 1 回目・§25 は旧 HEAD の初回)。同じく節内の初回 run でも §21・§22 (改修前)・§24・本節は PASS。母数が少ないため「初回 run で起きやすい」は**仮説**に留める。FAIL の位置は 3 件とも `first_err_frame = first_underrun_frame = 56576` (quantum 442)。
- 未解決 (追跡 **#863**): (a) 失敗時刻と照合できる producer 側の時系列 (quantum ごとの起床時刻) は wasm (`flasio.c`) の変更が必要で、本節の範囲外。(b) 再現条件の特定。(c) 初回 run の仮説の検証 (再起動直後・キャッシュ状態を分けた実測)。

## 29 AU-15 (#863) 失敗 1 件の位置情報と producer 起床の照合 (測定 commit `6ca613d2`)

- 変更 (`6ca613d2`): `producerStats()` に `cb_count`・`cb_max_us`・`cb_max_q` を追加し、e2e の判定行に `prod_cb_count=` `prod_cb_max_us=` `prod_cb_max_q=` を出す。コード差分は `src/runtime/audio-shim.ts` と `tools/audio/integration/e2e.mjs` のみ (`ws-863` worktree、`origin/main` `198be2e6` の上の 1 commit)。
- 測定: 素材 `toolchain-emsdk` のみ展開 (`EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk/emsdk_env.sh`)、`TMPDIR=$RUNNER_TEMP`、foreground。

| 区分 | run 数 | 結果 | 備考 |
|---|---|---|---|
| 単発 1 (`198be2e6`・emsdk 展開直後) | 1 | **FAIL** (dev:tone / dev:underruns。exit 1) | emcc の sysroot キャッシュ生成を含む初回。VM 起動から約 4 分 |
| 単発 2 (`6ca613d2`) | 1 | 13/13 PASS | dev `prod_cb_max_us=489 prod_cb_max_q=797`・preview `489 / 436` |
| hunt 1 (時間上限 420 s) | 35 | 35/35 PASS | summary は hunt 2 で上書きされた (結果行のみ記録) |
| hunt 2 (時間上限 1140 s) | 96 | 96/96 PASS | load 0.85〜2.75・wall 11〜13 s |

### 失敗 run の位置情報 (単発 1・dev のみ。preview は PASS)

`dev:tone max_err=8.44e-1 rms=0.3525 zero_runs=1 first_err_frame=56320 first_zero_run_frame=56351 underrun_cap=1 first_underrun_frame=56320 last_underrun_frame=56320 fill_at_first_underrun=0 fill_min_before_first_underrun=0 cb_gap_max_ms=11 cb_gap_over20=0 prod_wake_hist=303/7/0/0/0/0 prod_wake_count=310 prod_wait_timeouts=0`

`fill_trace` (最初の underrun までの 32 quantum・古い順): `896,768,640,768,896,768,640,768,896,768,640,1024,896,768,640,1024,896,768,640,1024,896,768,640,1024,896,768,640,512,384,256,128,0`

- 充填は 4 quantum ごとに 1 回、`640 → 1024` の跳ね (producer の書き込み) を繰り返していた。最後の周期だけ `640 → 512` の後に跳ねが無く、`512 → 384 → 256 → 128 → 0` と 4 quantum 続けて減って underrun になった。
- 充填の低下が段階的であるため、producer 側の書き込み不足の形と読める。
- ただし起床は速い: `prod_wake_hist` (run 全体の累計) は 8 ms 以上が 0 件で、notify から起床までの遅れは観測されていない。起床後〜書き込みまでの区間 (OS の preemption・JS の GC を含む) は未計測。
- この run には `cb_max_us` が出ていない (項目の追加は後)。PASS の 2 run では producer のコールバック最大が 489 µs (約 0.5 ms) で、コールバック自体が長い証拠は今回の失敗 run には無い。
- §25 で「3 件とも `first_err_frame = first_underrun_frame = 56576`」と書いたが、本件は 56320 (quantum 440) で同一フレームは崩れた。
- 初回 run の仮説 (§28 (c)): 失敗 4 件中 3 件 (§19・§23・§25) と本件は、いずれも節の初回 run または検証 VM 起動直後の run。反例 (初回 PASS の節) も複数あるため仮説のまま。

### 通算

- 失敗は §19・§23・§25 の 3 件と本節の 1 件で計 4 件。§19〜§28 の 387 run に本節 133 run (単発 2 + hunt 131) を加えて **4 件 / 520 run** (率約 0.8%)。
- 次回失敗時は `prod_cb_max_us` / `prod_cb_max_q` の判定行と `fill_trace` を取得する。起床後〜書き込みの区間は wasm (`flasio.c` の `thread_fn`) に時刻を残さないと計れない。

### 未解決 (追跡 **#863**)

(a) 起床後〜書き込みの区間の計測 (wasm の変更が要る。新規 issue は起票していない)。(b) 再現条件の特定 (負荷・タイミングとも相関は見えていない)。(c) 初回 run 仮説の検証 (キャッシュ状態を分けた実測)。

## 30 AU-15 (#863) producer の write 単位の記録を ctl に追加 (測定 commit `287655cf`)

- 変更 (`287655cf`): wasm `tools/audio/src/flasio.c` の `thread_fn` が write ごとに `[w (書き込み開始 frame), fill (起床時の充填), 起床時刻 µs, 完了時刻 µs]` を `fla_ctl_t.pw_trace` (256 件リング、通算 `pw_n`) へ記録する。`FLA_CTL_SIZE` を 384 → 4488 (`pw_n`@384・`pw_trace`@388)。TS は `audio-layout.ts` と `audio-shim.ts` (`producerStats().writes`、ctl ビュー長を `FLA_CTL_SIZE` に)。
- e2e の判定行に `pw_n` `pw_w_step` `pw_lat_max_us` (起床→完了の最大) `pw_gap_max_us` (連続起床の間隔の最大) を追加。FAIL 時は `pw_at_underrun` (underrun 直前の write と次の write を `w/fill/起床µs/完了µs` で出す)。
- 合成データで `pwInfo` の FAIL 経路 (`pw_at_underrun` あり) を確認 (node で関数を抜き出して実行)。実 FAIL は未捕獲。
- 測定: 素材 `toolchain-emsdk` (`$ARTIFACTS_DIR`) を使用、`TMPDIR=$RUNNER_TEMP`、foreground、worktree `ws-863` (`origin/main` `7622290b` 起点)。

| 区分 | run 数 | 結果 | 備考 |
|---|---|---|---|
| 初回 (`287655cf`) | 1 | 13/13 PASS・exit 0 (11.1 s) | dev `pw_w_step=256` `pw_lat_max_us=35` `pw_gap_max_us=10070`・preview `25` / `10066` |
| 連続 (300 s 上限、FAIL で停止) | 30 | 30/30 PASS・exit 0 | load 0.02〜1.90 |

- 連続 30 run の判定行 (dev:tone): `first_err_frame=-1` が全件。`pw_lat_max_us` 16〜180 µs。`pw_gap_max_us` 10050〜12025 µs。`prod_cb_max_us` 20〜385 µs (§28・§29 と同程度)。
- 読み (事実のみ): 起床から書き込み完了までは最大 180 µs で、producer の書き込み処理自体は遅くない。一方、連続起床の間隔は PASS の中でも最大 10〜12 ms に達する。B=256 (5.33 ms) の 2 周期分に相当する。目標充填 T の値は判定行に出していないため、この間隔が underrun の余裕とどう対応するかは断定できない。
- 次の失敗が出たときは `pw_at_underrun` で、underrun を起こした write が (a) 起床していたか (起床の `fill` が閾値より低い、または `pw_at_underrun` に次の write が無い)、(b) 書き込み完了まで時間がかかったか、を読む。consumer 側の同時刻は未計測のため、突き合わせは (a)(b) の範囲に限られる。

### 通算

- §19〜§29 の 4 件 / 520 run に本節 31 run (全 PASS) を加えて **4 件 / 551 run** (0.73%)。
- 失敗 4 件はいずれも `first_err_frame = first_underrun_frame` (§19・§23・§25 は 56576、§29 は 56320)。本節では 0 件のため、この一致が今後も出るかは次の捕獲で確認する。

### 未解決 (追跡 **#863**)

(a) consumer (worklet) の quantum 時刻との突き合わせ (worklet 側に時刻を残す変更が要る。新規 issue は起票していない)。(b) 再現条件の特定 (負荷・タイミングとも相関は見えていない)。(c) 目標充填 T を判定行へ出す (連続起床の間隔との比較のため)。(d) 初回 run 仮説の検証 (キャッシュ状態を分けた実測)。
