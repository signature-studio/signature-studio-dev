# REPORT_APPENDIX_960 — `REPORT_N27.md` §14 (#960) の全文。250 行上限のため分割移動 (内容は無変更)

## 14. #960: `--full` を同一 HEAD・同一 PE で 2 回実行し、IR の差の段を切り分け

- 条件: HEAD `29f63707` (origin/main)・PE `fl-win64` の `block00031_PE.bin` (sha256 `b2c64da4…`)・`toolchain-retdec`・`work-m11`・`work-liftdiff`。Ghidra 12.1.4 (`ghidra_12.1.4_PUBLIC_20260921.zip`・sha256 `ddac49f9…`) で `functions_dll.csv` を再生成 (8 分 8 秒・rc 0・59 010 行・JDK 21)。2 回目の前に `work/` の lift・IR 生成物を削除 (`ir_conditions.json` 含む) してから全再生成した。
- PATH は `[RETDEC]` の bin と agent-py を先頭に置き、`FL_WIN64_DIR`・`RETDEC_ROOT` を設定。

| 測定 | コマンド | rc | 所要秒 | load (開始→終了) | ir_sha256 | reached_stage | survey ok / trap / miss |
|---|---|---|---|---|---|---|---|
| N1 | `bash m11_e2e.sh --full` | 0 | 506 (8 分 26 秒) | 1.32 → 1.10 | `20d68876…` | 4 | 870 / 25 / 46 |
| N2 | 同 (生成物を削除してから) | 0 | 492 (8 分 12 秒) | 0.80 → 1.03 | `90c59e22…` | 4 | ok 870 (trap / miss は未抽出) |

- **結論**: 同一 HEAD・同一 PE・同一素材でも `ir_sha256` は一致しない (N1 ≠ N2)。N1 の survey は 870 / 25 / 46 (`M11_SUMMARY`)、N2 は survey_ok 870 を確認した。IR の bytes の差が survey 結果に出るかは N2 の trap / miss を抽出して未確認。
- **差の段 (N1 と N2 を比較・N1 の中間物は `$RUNNER_TEMP/run1` に保存)**:
  - RetDec 段 `boot0.drc.ll` が最初に変わる。`uselistorder` 行の並びと、`@global_var_*` 定義行の位置の計 2 行の差。この 2 種を除いた差は無い。`boot0.drc.c`・`*.drc.dsm`・`*.drc.config.json` の差は `time` / `Decompilation date` と変数宣言 1 行 (`0x52a738` 付近) に限られる。
  - `boot0.lift.ll` (ir5_patch 後) は `@global_var_13bd880` 定義の 1 行が移動するだけ (行集合は一致)。
  - `boot_final.ll` は末尾の空行を除くと行集合が一致し、行の並びだけが違う。sha256 の差はこの並び順から出る。
  - 段の切り分けの結論: 最初に変わるのは RetDec (drc.ll) の出力順。後段 (norm0・ir5・gen_ir2) が順序を保存するかは、各段の入出力を個別に比較していないため未確認。`m11_passes.py` の一部は `sorted(...)` を使うが、順序を完全に固定するものかは未確認。
- **既知との関係**: RetDec の lift 出力が同一入力で実行ごとに変わることは #668 (LIFTLIB-9・k80 の drc.ll) で既に記録されている。本件はその m11 側の再現 (`--full` の boot0〜boot5)。
- **扱いの提案 (受入 3・PM 判断待ち)**: `ir_sha256` は実行ごとの固定指紋として使えない。survey 基準の比較は件数 (ok / trap / miss / reached_stage) で行い、`ir_sha256` の一致を再現性の証拠にしない。`ir_sha256` は「その IR から build した」ことの gate としてのみ使う (`m11_build.sh` の照合は現状どおり)。
- **未解決**: RetDec 段の出力順を固定する修正 (drc.ll の正規化、または RetDec 側の順序固定) は未実施。起票先 #668。
- 再現: `FL_WIN64_DIR=<fl-win64>/ RETDEC_ROOT=<[RETDEC]>/retdec PATH=<[RETDEC]>/bin:$PATH bash tools/m11/m11_e2e.sh --full` を 2 回 (間に `work/` の boot*/ir_conditions を削除)。
