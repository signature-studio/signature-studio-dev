# tools/plugins/sampler/REPORT_APPENDIX.md — sampler REPORT §6 の旧版 (分割移動)

> **正本**: `tools/plugins/sampler/REPORT.md`。 本書は REPORT §6 から分割移動した旧検証の全文 (250 行上限・削除ではなく移動)。
> 数値は各節の検証起点 commit の実測で、現行 HEAD の値は REPORT §6 を参照。

## A. 旧検証 (検証起点 53c2eb6、#208 段階)

検証起点 commit は **53c2eb6** (以降の commit は REPORT.md のみ)。 以下は全てコミット済み HEAD で実行した。

| 項目 | 実測 |
|---|---|
| `sampler_e2e.sh` 全体 (最終版、HEAD 53c2eb6、inventory 済みから) | exit 0、**211.95 s** (開始時 load average (1 分) 1.31)。 内訳: 7 閉包の lift 79 s、残りは `closure_facts.py` + `matrix_check.py` |
| 同 (HEAD aec2fac) | exit 0、276.46 s (開始時 load 1.97。 engine の後段 pass 2 プロセスと RetDec 1 本が同時に走っていた) |
| 初版 (engine 込み、HEAD 56aeefe) | **exit 1**、921.34 s。 RetDec の C 出力段が終わらず私が 2 本を停止したため engine 判定が FAIL (§5)。 現行版は engine を `sampler_engines.sh` に分離 |
| 7 閉包の lift 秒 (`status.csv` の seconds、3 回の合計) | 76 s / 109 s / 79 s (run 2 は並走プロセスがあり Slicex 15 → 23 s、Soundfont Player 33 → 57 s)。 プラグイン別の min–max は §1 の最右列 |
| 3 回の結果一致 | §1・§3・§4 の表 (判定列・閉包値・host・kernel) は run 2 と run 3 で完全一致 (`diff`)。 `declares_unimpl` と `unimpl_names` を含む 7 行の判定列は 3 回とも同一 |
| `sampler_engines.sh` (HEAD 53c2eb6、2 本並列) | exit 0、**287.04 s** (開始時 load 0.36)。 2 回目の実行 (1 回目は `lift_from_ll.sh` の sed が段付き行を拾えず lift_rc 1 → 判定が **exit 1** で止まった。 修正して再実行)。 結果は停止再開版と各列一致 (§5) |
| `matrix_check.py` | 54/54 項目一致 (閉包 6 項目 × 7 本 + `batch` 4 項目 × 3 本) |
| `ids_crosscheck.py` | exit 0、3.16 s。 7/7 本で取りこぼしなし (§3) |
| `unreached_unique.py` | exit 0、2.66 s。 正の対照 7/7 |
| 前提 inventory (初回のみ、`work/` 無しから) | 533 s (`win_scan`〜`kernel_table`。 `win_funcs.py` が並列 14 プロセス / 4 core で大半)。 `block_manifest.json` が tarball に無く `nsis_names.py` が動かないため、`mk_blockmap.py` が `PLUGIN_MATRIX.json` から代替の blockmap (182 record) を合成 |

## B. 旧検証 (検証起点 82a99ac / 7de96e0、#540 共有鎖修正・main 取り込み前)


検証起点 commit は **82a99ac** (共有鎖 3 pass + sampler スクリプト)。 REPORT のみ 7de96e0 で追加。

| 項目 | 実測 |
|---|---|
| クリーン HEAD (7de96e0、`git worktree add --detach`、`e.drc.ll` のみ持ち込み) の `sampler_engines.sh` | **exit 0**、269 s (開始時 load average 0.68 / 0.85 / 2.06)。 `judge engines: PASS 2/2`。 23664: define 5,993・`emcc_c_rc_after_f80` 0・lift 251 s / 23677: define 2,525・`emcc_c_rc_after_f80` 0・lift 140 s |
| 修正前 HEAD 190f1d8 の 2 本 (基準再現) | 23664 `emcc -c` rc 1 (`use of undefined value '%15'`)、23677 rc 1 (E1)。 `engine_fixcmp.py` 後 23664 は同エラー、23677 は `zext 0 to i64` → 修正を 1 件ずつ当てると `zext constexprs are no longer supported` → `fp_extend` (f80) の順に露見 |
| `sampler_e2e.sh` (Delphi 殻 7 本、修正後の共有鎖) | exit 0、7/7 `emcc_c=0`、`judge shells: PASS 7/7`。 7 閉包の define は 29 / 141 / 90 / 121 / 51 / 158 / 433 (§1 と同じ) |
| T0 `batch_lift.sh --tier T0` | 42 行すべて lift_rc 0・`emcc -c` rc 0・f80 関数 0。 104 s (開始時 load 0.11) |
| T1 `batch_lift.sh --tier T1` | 45 行中 lift_rc 0 は 45、`emcc -c` rc 0 は **44**。 失敗 1 は ReWired (f80 2 関数、`do not know how to soften fp_extend`)。 修正前 pass でも同一の失敗で `final.ll` は一致 (上記の既知の T1 失敗と同じ)。 205 s |
| 修正前後の `final.ll` 同一性 (`PLUGIN_MATRIX.json` の T0+T1 の `CreatePlugInstance` 持ち Delphi 86 ブロック、修正前 pass を `git show 190f1d8` から復元して `lift_ranges.sh` に差替。 `!insn.addr` と空行を除外して比較) | **84 ブロックが同一、2 ブロック (19148・19245) が差分**。 320 s |
| 差分 2 ブロックの内容 | 各 6 行、`%m11op_1 = add i64 %ce.., 4` / `%m11INTP_1 = inttoptr` / `select` が `%ce0n13_.. = add` / `%ce0n14_.. = inttoptr` に**変数名だけ**変わる (A9L の固定点反復が行書換だけの変更を採用するようになり、`m11_passes` が付ける名前の前に A9L が命令化したため)。 演算は同じ。 値の同一性は差分試験していない |
| NC (`sampler_nega.sh`、HEAD 82a99ac の作業ツリー) | exit 0。 NC7 / NC8 を含む全 NC が期待通り。 NC8: 最終 emcc rc=1 → 1、-1 → 1、`missing_ref`=1 → 1、旧 header → 2 |

## C. 旧検証 (検証起点 7ffab50、main 取り込み (1ffb204) と fold 修正 (5bc59f1) の後、main 取り込み 4c3ae00 の前)

REPORT §6 の旧版を移動した (250 行上限)。 入力は 7ffab50 の sampler / lift。 4 core / 15 GiB、逐次。

| 項目 | 実測 (7ffab50) |
|---|---|
| `sampler_e2e.sh` | exit 0、873 s (開始時 load 0.63)。 judge shells PASS 7/7、matrix 54/54 |
| `unreached_unique.py` / `ids_crosscheck.py` / `report_tables.py 2` | exit 0 / exit 0 / exit 0 |
| `sampler_engines.sh` | exit 0、317 s (開始時 load 1.03)。 `judge engines` PASS 2/2。 23664 lift 295 s / 23677 lift 142 s |
| `sampler_nega.sh` | exit 0、11 s。 NC1–NC8 が期待どおり |
| `passes/test_fold_const_ops.py` | 4 件 OK (旧 `ir5_patch` 8a74e95 では 3 件 FAIL: 255 / 65535 / 2^64-1) |
| T0 `batch_lift.sh --tier T0` | 42 行: lift_rc 0 = 42、`emcc -c` rc 0 = 42。 214 s |
| T1 `batch_lift.sh --tier T1` | 45 行: lift_rc 0 = 45、`emcc -c` rc 0 = 44。 失敗 1 = ReWired (f80 2、既知)。 479 s |

- 無効 run (記録のみ): 初回の T0/T1 は `batch_lift.sh` が `pefile` の venv を見ずに全行 rc=1 で落ちた (driver の rc=0 は偽陽性)。 `sampler/env.sh` を source して再実行した値のみ掲載。

## D. RetDec の C 出力段の経緯 (REPORT §5 から分割移動、検証起点 53c2eb6 / 初版 e2e)

- `lift_ranges.sh` 直行 (`sampler_e2e.sh` 初版、engine 2 本を並列) では、`LLVM IR -> HLL` 段の開始 (= `.ll` 出力後) は RetDec 開始後 23664 で 114.24 s・23677 で 69.49 s (スクリプト一本版の run では 93.05 s / 46.51 s) だったが、その後の C 出力段が終わらなかった。
- 23664 は 614.57 s 時点 (`variable renaming`) で RSS 8.15 GiB、"out of memory; trying to recover" を 3 回出した (RetDec の既定メモリ上限は搭載 RAM の半分 = 約 8 GiB、`--no-memory-limit` で解除可)。 23677 は 758.98 s 時点 (`emission of the target code [c]`) で RSS 6.85 GiB。
- 同時使用は 14.4 GiB / 15.6 GiB (空き 1.6 GiB) まで逼迫したため、621 s / 838 s で RetDec を停止した (この初版 e2e は engine 判定で exit 1。 未完の run を成功と報告しない)。
- C は使わないので、`lift_from_ll.sh` で `.ll` 出力後に RetDec を止めて後段 pass 鎖だけ走らせる方式に変えた (`lift_ranges.sh` 本体から後段を切り出す。 共有鎖は変更していない)。 `.ll` の出力から `emcc -c` までの結果は、停止して再開した版とスクリプト一本の版で同一だった (23664: define 5,993 / 欠落 3 / 未実装 215 / f80 2、23677: define 2,525 / 欠落 1 / 未実装 151 / f80 1。 `.ll` は 23664 で 333 B 異なるが各列は一致)。
