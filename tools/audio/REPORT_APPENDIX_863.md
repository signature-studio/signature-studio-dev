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
- 通算: 旧 HEAD 含む同一 e2e で FAIL 3 件 / 計 90 run (§19〜§24 の 2 件 / 86 run に、本節の旧 HEAD 初回 FAIL 1 件 / 1 run と、本節の probe 後 44 run の全 PASS を加算。probe 後の 44 run は同一 HEAD で行った 1 セット)。
- 未解決 (追跡 **#863**): (a) fill 推移を含む失敗 log が未取得 (次回失敗時に `fill_trace` で判定)。(b) 同一フレーム 56576 が 3 回出る理由は未特定 (起動からの相対位置が固定なら、決定的な起動経路の問題の可能性)。(c) producer 側の到達時刻 (wasm 側の変更) は本 PR の範囲外。
