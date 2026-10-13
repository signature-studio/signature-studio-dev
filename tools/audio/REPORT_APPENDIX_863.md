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
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` へ展開 (`FL_WIN64_DIR`)、`toolchain-emsdk` は `/opt/emsdk` (6.0.12) を使用。`TMPDIR=$RUNNER_TEMP`。
- 測定 commit: `7d275cb0` (改修後 HEAD)。改修前の基準は `origin/main` `f3ffd7ba` で 13/13 PASS (22.5 s)。
- 改修後 HEAD の実測 (foreground):

| 区分 | run 数 | 結果 | wall | load (開始時) |
|---|---|---|---|---|
| 改修前 HEAD `f3ffd7ba` | 1 | 13/13 PASS exit 0 | 22.5 s | 0.6 |
| 改修後 HEAD 直後 | 1 | 13/13 PASS exit 0・ログ生成 | 13.7 s | 0.5 |
| 負荷 (busy loop 6 本) | 6 | 6/6 exit 0・13/13 PASS・FAIL 0 | 20〜29 s | 9〜13 (前 run の busy loop 残存) |
| 改修後 HEAD・負荷残存下 | 3 | 3/3 exit 0・13/13 PASS | 20〜21 s | 9.4〜10.2 |
| 改修後 HEAD・負荷 (busy loop 6 本) | 3 | 3/3 exit 0・13/13 PASS・FAIL 0 | 20〜29 s | 12〜13 |

- 注: 上表の「無負荷」は前 run の busy loop が残っていたため無負荷ではない。純粋な無負荷の再測定は未実施。
- 失敗は 0 件。producer (wasm 出力遅延) / consumer (worklet rebuffer) の切り分けは未実施。旧失敗 (§19) の条件は引き続き未特定。
- 未解決: (a) CI に e2e を組み込んでいない (`.github` に参照なし) ため、失敗ログを CI artifact として残す経路は無い。(b) 失敗の再現条件の特定。追跡は **#863**。
