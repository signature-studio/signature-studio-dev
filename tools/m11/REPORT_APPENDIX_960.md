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
- **受入 2 (固定化)**: A7 (`tools/m5/ir5_patch.py` の `uselistorder` 行除去) を通した `lift.ll` は、上記の 5 本の drc.ll (md5 4 種類) すべてで `23c8ea5b` に収束した。`tools/liftlib/liftlib/passes/base.py` の `normalize()` (A7) も同じ正規表現で除去し、P1・N1・N2 の 3 本の出力が `94a8363c` で一致した (Z1 は lift 段が未計測のため対象外)。新しい正規化は不要と判断する。**§19 で覆った: 新しい正規化 (A7 の空行ごと除去) が必要 (旧 A7 は先頭の空行を残すため `boot_final.ll` が揺れた)。**
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

## 19. #1664: `ir_sha256` の揺れの原因 (A7 の空行残り) と修正、修正後の `--full` n=3

- 測定 commit: `52ad0ce1` (origin/main `3d011ecd` 起点の `1664-ir-sha-stable`。A7 の修正 + 回帰テスト `tools/m11/test_a7_uselistorder.py`)。REPORT の追記 commit との差: `git diff 52ad0ce1 HEAD -- tools ':!tools/m11/REPORT_APPENDIX_960.md'` は **0 行** (docs の 2 行のみ別)。
- 条件: PE `fl-win64` の `block00031_PE.bin`・RetDec v5.0 (`[RETDEC]`)・`work-m11` 素材の `boot_ranges.txt` (7,360 range を 1,900 ずつ 4 chunk。下の「原因」「修正の実測」の RetDec 単体の再現はこの range を使い、`--full` が `m11_bounds.py` で再生成した range も 7,360 個)・`m2/ir_normalize.py` → `m5/ir5_patch.py` → `m11_gen_ir2.sh`。Ghidra 12.1.4 (sha256 `ddac49f9…` 一致・JDK 21) で `functions_dll.csv` を再生成 (約 7.5 分・rc 0)。

### 原因 (受入 1・2)

- **揺れは 2 種で、`ir_sha256` に効くのは 1 種だけ**。同一 PE・同一 range で RetDec を 2 回流し (修正前の A7)、各段を比較した。

| 段 | 差の内容 | boot_final.ll への効き方 |
|---|---|---|
| drc.ll (4 chunk 全て) | `uselistorder` の並び・有無 (raw は 4 chunk とも 2 回で md5 が違う) | A7 が行を除去するため効かない |
| lift.ll chunk 1 | 空行 1 行 (directive ブロックが 1,492 個 / 1,491 個。除去後に先頭の空行が残る関数の数が違う) | **効く** (boot_final.ll の md5 `809664c3` ≠ `5b2d3776`・差は空行 1 行) |
| lift.ll chunk 3 | `@global_var_196eb70` の定義順 (drc.ll の時点で既に違う) | 効かない (`m11_merge.py` が globals を `sorted()` するため) |
| lift.ll chunk 0・2 | 差なし (md5 一致) | — |

- **空行の由来**: LLVM の writer は、use-list の並びが既定と違う関数にだけ `\n; uselistorder directives\n  uselistorder ...` を `}` の直前に出す。旧 A7 は `uselistorder` 行と `; uselistorder directives` 行を消すが、その**前の空行**を消さない (`(?m)^\n\n\n+` は 3 連続以上しか畳まない)。directive の有無が実行ごとに変わるため、残る空行の数が変わる。§15 の N3/N4 の `boot1.lift.ll` の空行 1 行差・`boot_final.ll` の空行数 48,683 / 48,684 の差と同じ chunk・同じ型 (directive の有無が違う)。
- **`@global_var_*` の定義順**: RetDec が globals を出す順そのものが実行ごとに違う (§14 の `@global_var_13bd880` の移動と同種)。順序の由来 (LLVM の writer 段・§18) は未特定。ただし `m11_merge.py` が `sorted()` で並べ直すので、m11 の IR (boot_final.ll) には出ない。lift.ll 単体の比較には出る。

### 固定化の方法 (受入 2)

- **A7 段での正規化を採った**。RetDec 側の決定化は採らない: RetDec は配布済みの v5.0 バイナリで、並びが変わる段は LLVM の writer 段まで絞れた (§18) が仕組みは未特定のため。
- 修正: `tools/m5/ir5_patch.py` と、その vendored 版 `tools/liftlib/liftlib/passes/base.py` の A7 に `^\n; uselistorder directives\n(uselistorder 行)*` を**空行ごと**除去する正規表現を追加した (2 ファイルの A7 は同じ除去を保つ)。directive が無い関数は `ret ...\n}` で終わるため、directive を消した後の形が一致する。`lift.ll` の行数は directive ブロック 1 個につき 1 行減る。
- `m5/ir5_patch.py` 以外の `ir5_patch.py` の複製 (`tools/plugins/lift/passes/`・`tools/targets/*/`) は変更していない (m11 の `--full` が使わない複製で、各 target の golden・hash への影響を測っていないため)。

### 修正の実測 (RetDec 2 回 → gen_ir2。boot4〜boot6 は `work-m11` の同一ファイル)

| 条件 | lift.ll md5 (chunk 0 / 1 / 2 / 3) | boot_final.ll md5 |
|---|---|---|
| 修正前 r1 | `faf82880` / `7cfda2ed` / `3d4cb31b` / `1ff1e879` | `809664c3` |
| 修正前 r2 | `faf82880` / `44a3a092` / `3d4cb31b` / `d3bbf26f` | `5b2d3776` |
| 修正後 r1 | `f9e096a3` / `72ba7652` / `0ff4739b` / `bb1aa9f6` | `089f1ad5` |
| 修正後 r2 | `f9e096a3` / `72ba7652` / `0ff4739b` / `9b333790` | `089f1ad5` |

- 修正後の chunk 3 は globals の順で lift.ll が違うまま、boot_final.ll は一致した (merge の `sorted()` による)。
- 回帰テスト `python3 tools/m11/test_a7_uselistorder.py` は修正後 2 ファイルとも PASS。旧 A7 (`git show 3d011ecd:tools/m5/ir5_patch.py`) に流すと「directive 有り/無しで出力が違う」で FAIL する (負例)。

### `--full` n=3 (受入 3)

| 測定 | rc | 所要秒 | load (開始→終了) | ir_sha256 | reached_stage | survey ok / trap / miss |
|---|---|---|---|---|---|---|
| F1 `m11_e2e.sh --full` | 0 | 448 | 0.76 → 1.07 | `63fae2dc…` | 4 | 872 / 23 / 46 |
| F2 同 (生成物削除後に再生成) | 0 | 442 | 0.99 → 1.00 | `63fae2dc…` | 4 | 872 / 23 / 46 |
| F3 同 (生成物削除後に再生成) | 0 | 461 | 0.92 → 0.92 | `63fae2dc…` | 4 | 872 / 23 / 46 |

- **結論**: 同一 HEAD・同一 PE・同一素材で `--full` の `ir_sha256` が 3 回とも一致した。F1・F2・F3 の `boot_final.ll` は `cmp` で bytes 一致。`M11_SUMMARY` の `units_run_full` 53 / `units_total` 942 / `stop_reason` も一致。
- **一致の強さ**: 修正前は同条件で一致 (§17 Q1=Q2) と不一致 (§14 N1≠N2・§15 N3≠N4) が混在したため、修正前後を同一 n で比べてはいない。修正後は原因 (空行) を直したうえでの n=3 で、RetDec 単体の再現 (上表) でも一致を確認した。`--full` の F1 と F3 では boot0〜boot5 の lift.ll も全て bytes 一致した (RetDec 単体の再現で出た chunk 3 の globals の順差は、この 2 回では出なかった)。
- F2・F3 の前に `work/ir_conditions.json`・`boot*.lift.ll`・`boot*.drc.*`・`boot_final.ll`・`lift_pe.sha256` を削除してから全再生成した。
- **検証範囲 / 範囲外**: 範囲内は `m11_e2e.sh --full` (F1〜F3)・`tools/m11/test_a7_uselistorder.py`・素材 `work-m11` の drc.ll boot0〜3 の directive 残り。範囲外は `tools/liftlib/tests/test_unit.py` T1 (下表 1 行目)。
- **T1 (本 run)**: `python3 tools/liftlib/tests/test_unit.py` は rc 1 (`FileNotFoundError: tools/m6/work/ott.drc.ll`)。本 run の素材は fl-win64・toolchain-emsdk・toolchain-retdec・work-liftdiff・work-m11 の 5 本で、`work-m6-ott` が無かった。PR 本文の oc_artifacts に `work-m6-ott` を追加した (次の review run で取得)。T1 の 2 本目の loop が読む `targets/*/work/**/lift_gain`・`poc_gain/work` は許可名の対象外 (docs/WORKFLOW.md §11 に無い) で、無いと `os.path.exists` で skip される。次の run で T1 が ok でも、証拠は OTT (1 本目) だけになる。
- **代替の実測 (T1 ではない)**: `work-m11` の `boot0〜3.drc.ll` (RetDec の実出力) に `tools/m5/ir5_patch.py` と `base.py` の `normalize` を当てると、残留の `; uselistorder directives` と `uselistorder ` はどちらも 0 件。ただし 2 つの全体出力は一致しない (`!insn.addr` 等の metadata 行の扱いの差で、A7 と無関係。PR 前から)。A7 の一致の証拠にはしない。
- **限界**: `uselistorder_bb` (基本ブロック用 directive) は A7 の正規表現 (`uselistorder ` の空白あり) に一致せず除去されない。素材の drc.ll boot0〜3 では 0 件 (`grep -c uselistorder_bb` で実測)。回帰テストには含まれない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `test_unit.py` T1 (`base.run_base` の OTT golden 比較) が未実行。素材 `work-m6-ott` が本 run に無い | `base.py` の A7 変更が OTT の lift 出力を変えないことの実測が無い | 既存 issue #1664 にコメント (次の review run で実測し、結果を書いてから merge) |
| `@global_var_*` の出力順が実行ごとに変わる仕組み (RetDec / LLVM writer 段) | lift.ll 単体の比較にだけ出る。`boot_final.ll` は merge の `sorted()` で一致 | 親 #960 へ提案 (観測のみ。順序の由来は §18 の writer 段まで) |
| `ir5_patch.py` の複製 (`tools/plugins/lift/passes/`・`tools/m3/ir_patch.py`・`tools/targets/*/`) の同じ空行残り | m11 の `--full` が使わない複製で未測定。A7 は変更していない | 親 #960 へ提案 |
| `uselistorder_bb` (基本ブロック用 directive) が A7 で除去されない | 素材 drc.ll boot0〜3 では 0 件。回帰テストの対象外 | 親 #960 へ提案 |
- 再現: §14 と同じ (`FL_WIN64_DIR`・`RETDEC_ROOT`・`PATH` を設定し `bash tools/m11/m11_e2e.sh --full` を 3 回)。RetDec 単体は §18 の手順で chunk を 2 回流し、`m2/ir_normalize.py` → `m5/ir5_patch.py` → `m11_gen_ir2.sh` を通して `boot_final.ll` の md5 を比べる。
