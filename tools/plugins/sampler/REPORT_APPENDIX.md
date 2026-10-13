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
