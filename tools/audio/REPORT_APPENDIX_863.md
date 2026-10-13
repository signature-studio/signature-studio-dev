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
