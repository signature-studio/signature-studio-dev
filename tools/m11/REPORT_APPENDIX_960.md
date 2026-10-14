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

## 18. #1664 受入 1 の残り: RetDec 単体の `--print-after-all` で段を切り分け (`--passes` 相当)

- 測定 commit: `c2f67568` (origin/main 起点の `1664-retdec-passes-split`)。測定時点のコード差分 0。
- 条件: PE `fl-win64` の `block00031_PE.bin` (sha256 `b2c64da4…`)・`toolchain-retdec` (v5.0・`retdec-decompiler`)・`work-m11` の `boot_ranges.txt` 先頭 150 range (`--select-decode-only`・timeout 250〜500)。RetDec の `--print-after-all` (stderr) で LLVM pass ごとの IR を取った。
- RetDec の CLI に `--passes` は無い。pass 単位の切り分けは `--print-after-all` を使った。

| 測定 | rc | drc.ll md5 | A7 後 lift.ll md5 | pass dump (stderr) md5 | 差分行 |
|---|---|---|---|---|---|
| P1 (`--print-after-all`) | 0 | `cc6dac6c` | `23c8ea5b` | `340d476b` | — |
| P2 (同) | 0 | `fbd7af02` | `23c8ea5b` | `340d476b` | drc.ll 1 行 (`uselistorder @WriteFile`) |
| N1〜N3 (dump なし) | 0 | `ee485e91` / `cbee7ce0` / `cbee7ce0` | `23c8ea5b` ×3 | — | 同上 |
| Z1・Z2 (`setarch x86_64 -R`・ASLR 無効) | 0 | `7eae26d1` / `7eae26d1` | 未計測 | — | — |

- **結論 (pass 単位)**: `--print-after-all` の stderr (約 17,954 件の IR dump・81 MB) は P1 と P2 で md5 が完全一致した。`uselistorder` は pass dump に 1 行も現れない (0 件)。最終 `drc.ll` の差は `@WriteFile` の `uselistorder` 1 行の並び (`{ 0, 1, 2, 4, 3 }` と `{ 2, 0, 1, 4, 3 }`) だけ。つまり並びは LLVM の最終 writer 段で生じ、pass の中身の差では無い。
- **結論 (ASLR)**: ASLR を無効にすると 2 回とも `7eae26d1` で一致した。並びの揺れは実行ごとのアドレス (ポインタ) の割り当てに由来する可能性が高い。ただし ASLR を無効にしたときの `lift.ll` 段は未計測で、この結論は「可能性が高い」止まり。
- **受入 2 (固定化)**: A7 (`tools/m5/ir5_patch.py` の `uselistorder` 行除去) を通した `lift.ll` は、上記の 5 本の drc.ll (md5 4 種類) すべてで `23c8ea5b` に収束した。`tools/liftlib/liftlib/passes/base.py` の `normalize()` (A7) も同じ正規表現で除去し、P1・N1・N2 の 3 本の出力が `94a8363c` で一致 (Z1 は lift 段が未計測のため対象外)した。新しい正規化は不要と判断する。
- **未解決**: (a) `--passes` 相当の段の切り分けは `--print-after-all` で代替した。LLVM writer 段で並びが変わる仕組みそのものは未確認。(b) ASLR 無効時の `lift.ll` 段は未計測。(c) `@global_var_*` 行位置差 (§14) は今回の 150 range では再現せず、未切り分け (`--full` 全 range で要確認)。
- 再現: `RETDEC=<[RETDEC]>/bin/retdec-decompiler`・PE `block00031_PE.bin` で `retdec-decompiler <PE> -o x.drc.c --select-ranges "$(cat r150.txt)" --select-decode-only --print-after-all 2> x.pass.log` を 2 回。`drc.ll` の md5 と `uselistorder` 行を比較。ASLR 無効は `setarch x86_64 -R` を前置。

## 15. #960 追補: HEAD `58b7e990` (origin/main) で `--full` を 2 回実行 (N3・N4)

- 条件: HEAD `58b7e990`・PE `fl-win64` の `block00031_PE.bin` (sha256 `b2c64da4…`)・`toolchain-retdec`・`work-m11`・`work-liftdiff`。Ghidra 12.1.4 (sha256 `ddac49f9…` 一致) で `functions_dll.csv` を再生成 (8 分 3 秒・rc 0・59 010 行・JDK 21)。N4 の前に `work/` の lift・IR 生成物と `ir_conditions.json` を削除。

| 測定 | rc | 所要秒 | ir_sha256 | reached_stage | survey ok / trap / miss |
|---|---|---|---|---|---|
| N3 `m11_e2e.sh --full` | 0 | 525 (8 分 45 秒) | `ad73a2cd…` | 4 | 872 / 23 / 46 |
| N4 同 (生成物削除後に再生成) | 0 | 512 (8 分 32 秒) | `7e66d79d…` | 4 | 872 / 23 / 46 |

- **結論**: 同一 HEAD・同一 PE で `ir_sha256` は再び一致しない (N3 ≠ N4)。一方、survey の結果は一致した: `M11_SUMMARY` の survey 系フィールド全て一致、標準出力は時間・負荷の行を除くと差分 0 行。
- **差の段**: `boot0.drc.ll`・`boot0.lift.ll`・`boot2`/`boot4` の lift/drc は N3 と N4 で一致。`boot1.drc.ll`・`boot3.drc.ll` は `uselistorder` 行の並びに差がある (前回 §14 の `boot0` とは別の段)。`boot1.lift.ll` は空行 1 行だけ差がある。`boot_final.ll` は空行 1 行だけ差 (N3 48683 → N4 48684 個の空行)。空行を除いた sha256 は両者一致。
- **前回 §14 との関係**: §14 は HEAD `29f63707` で 870/25/46 (N1)、N2 は ok 870 のみ。HEAD が違うため件数は直接比較できない。差の起点が段ごとに変わるため、差は実行ごとに揺れると判断する。
- **扱いの提案 (受入 3・PM 判断待ち)**: `ir_sha256` は実行ごとの固定指紋として使えない。survey 基準は件数 (ok / trap / miss / reached_stage) で比較する方針を、今回 2 回の一致で支持する。ただし 2 回だけの一致であり、trap / miss の unit 単位の一致は未確認。
- 再現: §14 と同じ (`FL_WIN64_DIR=<fl-win64>` / `RETDEC_ROOT=<[RETDEC]>/retdec` / `PATH=<[RETDEC]>/bin:$PATH` で `bash tools/m11/m11_e2e.sh --full` を 2 回)。

## 16. #1664: RetDec 段 (drc.ll) の非決定の原因特定 (部分達成・`--full` 2 回は未実施)

- 測定 commit: `0eaf2989` (origin/main 起点の `1664-retdec-uselistorder`)。測定時点のコード差分 0 (本 PR はこの節だけを追加)。
- 条件: PE `fl-win64` の `block00031_PE.bin`・RetDec `[RETDEC]/bin/retdec-decompiler` (v5.0)・`work-m11` の `boot_ranges.txt` (先頭 N 個の range)。`m2/ir_normalize.py` と `m5/ir5_patch.py` (A7) はリポジトリ版を使用。
- 測定 (RetDec 単体・同一 range・同一 PE):

| 測定 | range 数 | 所要秒 | load | drc.ll の md5 | 差分行 (drc.ll) | A7 後 lift.ll の md5 |
|---|---|---|---|---|---|---|
| subset r1 / r2 | 150 | 6 / 5 | 0.34 | `cbee7ce0` / `da00f50d` | 2 行 (`uselistorder` 1 行の並び) | `23c8ea5b` / `23c8ea5b` |
| subset s3〜s8 | 150 | 未計測 (timeout 90 内に完了) | — | 6 回中 5 種類 (`669013af` が 2 回) (`cc6dac6c` `669013af` `669013af` `907ab19c` `7eae26d1` `ae3a6356`) | 全て `uselistorder` 行の並びのみ | 6 回すべて `23c8ea5b` |
| chunk 0 a / b | 1900 | 25 / 23 | 0.34 | 一致 | 0 | (未生成) |

- **原因 (範囲内)**: 差は RetDec の `uselistorder` 指示行の並び (LLVM use-list order) だけ。`ir_normalize.py` は変えず、A7 (`ir5_patch.py` の `uselistorder` 行除去) を通すと、150 range の 8 回 (r1, r2, s3〜s8) で `lift.ll` が全一致した。
- **未確認 (§14 の記述との差)**: §14 は `@global_var_*` 定義行の位置の差も挙げたが、本節の subset では再現しなかった。`--full` (全 range・Ghidra 入力) でのみ出るかは未切り分け。
- **受入 1 (原因の段)**: 「RetDec drc.ll の `uselistorder` 並びが揺れる」までは確定。`--passes` 単位の切り分けは未実施。
- **受入 2 (固定化)**: 既存の A7 段が `uselistorder` を除去しているため、`lift.ll` 段では既に吸収されている。新たな正規化は未実装 (不要の可能性が高い)。ただし `boot_final.ll` の行順差 (§14 の記述) を A7 後の段で消せるかは未確認。
- **受入 3 (`--full` 2 回の `ir_sha256` 一致)**: **未実施**。`functions_dll.csv` の生成に Ghidra 12.1.4 が要るが、runner に `[GHIDRA]` が無く、`work-m11` 素材にも含まれない (`tools/m11/m11_bounds.py`・`m11_tail.py` が `m2/work/ghidra_dll/functions_dll.csv` を読む)。
- **未解決**: (a) `--full` 2 回の実測と ir_sha256 一致の判定 (起票先 #1664 に残す)。(b) `@global_var_*` 行位置の差の有無 (同 #1664)。
- 追加の注意: 全 range (`boot_ranges.txt` 全文) を 1 引数で渡すと `Argument list too long` で失敗する (`m11_lift_all.sh` が 1900 個ずつに分割する理由)。測定は `[RETDEC]` を使った。

## 17. #1664 受入 3: HEAD `dcc609a9` (origin/main) で `--full` を 2 回実行 (Q1・Q2)

- 測定 commit: `dcc609a9` (origin/main 起点の `1664-full-ir-sha`)。測定時点のコード差分 0。
- 条件: PE `fl-win64` の `block00031_PE.bin` (sha256 `b2c64da4…`)・`toolchain-retdec` (`$RUNNER_TEMP/retdec`)・`work-m11`・`work-liftdiff`。Ghidra 12.1.4 (sha256 `ddac49f9…` 一致・JDK 21.0.12) で `tools/m2/work/ghidra_dll/functions_dll.csv` を再生成 (476 秒・rc 0・59,010 行)。`FL_WIN64_DIR` / `RETDEC_ROOT` / PATH は §14 と同じ。
- Q2 の前に `work/ir_conditions.json`・`boot*.lift.ll`・`boot*.drc.*`・`boot_final.ll`・`lift_pe.sha256` を削除してから全再生成した。

| 測定 | rc | 所要秒 | load (開始→終了) | ir_sha256 | reached_stage | survey ok / trap / miss |
|---|---|---|---|---|---|---|
| Q1 `m11_e2e.sh --full` | 0 | 531 (8 分 51 秒) | 1.06 → 1.08 | `e13e9bc5…` | 4 | 872 / 23 / 46 |
| Q2 同 (生成物削除後に再生成) | 0 | 531 (8 分 51 秒) | 0.99 → 1.01 | `e13e9bc5…` | 4 | 872 / 23 / 46 |

- **結論 (受入 3)**: 同一 HEAD・同一 PE・同一素材で `ir_sha256` が一致した (Q1 = Q2 = `e13e9bc5…`)。`M11_SUMMARY` の `units_run_full` 53 / `units_total` 942 / `stop_reason` も一致。
- **注意 (一致の強さ)**: 同じ条件の過去の組 (§14 N1≠N2、§15 N3≠N4) は不一致だった。今回の 1 組の一致は非決定が消えた証拠ではない。`ir_sha256` を再現性の gate として使うなら、同条件の複数回 (3 回以上) 実測が要る。本 run では時間の都合で 2 回までとした。
- **未実施 (受入 1・2 の残り)**: `--passes` 単位の切り分け、`@global_var_*` 行位置差の有無、`base.py` との整合記述。これらは本 PR の対象外で、#1664 に残す。
- 再現: §14 と同じ。Ghidra は `analyzeHeadless <proj> dll_proj -import block00031_PE.bin -scriptPath tools/m2/ghidra_scripts -postScript DumpFunctions.java <csv>` (JDK 21 を JAVA_HOME に指定)。
