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

- **結論 (pass 単位)**: `--print-after-all` の stderr (約 17,954 件の IR dump・81 MB) は P1 と P2 で警告行を除いて一致した (警告は run ごとに 1〜2 件揺れる。§20 項 5・項 6)。`uselistorder` は pass dump に 1 行も現れない (0 件)。最終 `drc.ll` の差は `@WriteFile` の `uselistorder` 1 行の並び (`{ 0, 1, 2, 4, 3 }` と `{ 2, 0, 1, 4, 3 }`) だけ。つまり並びは LLVM の最終 writer 段で生じ、pass の中身の差では無い。
- **結論 (ASLR)**: ASLR を無効にすると 2 回とも `7eae26d1` で一致した。並びの揺れは実行ごとのアドレス (ポインタ) の割り当てに由来する可能性が高い。ただし ASLR を無効にしたときの `lift.ll` 段は未計測で、この結論は「可能性が高い」止まり。
- **受入 2 (固定化)**: A7 (`tools/m5/ir5_patch.py` の `uselistorder` 行除去) を通した `lift.ll` は、上記の 5 本の drc.ll (md5 4 種類) すべてで `23c8ea5b` に収束した。`tools/liftlib/liftlib/passes/base.py` の `normalize()` (A7) も同じ正規表現で除去し、P1・N1・N2 の 3 本の出力が `94a8363c` で一致した (Z1 は lift 段が未計測のため対象外)。新しい正規化は不要と判断する。**§19 で覆った: 新しい正規化 (A7 の空行ごと除去) が必要 (旧 A7 は先頭の空行を残すため `boot_final.ll` が揺れた)。**
- **未解決**: (a) `--passes` 相当の段の切り分けは `--print-after-all` で代替した。LLVM writer 段で並びが変わる仕組みそのものは未確認。(b) ASLR 無効時の `lift.ll` 段は未計測。(c) `@global_var_*` 行位置差 (§14) は今回の 150 range では再現せず、未切り分け (`--full` 全 range で要確認)。
- **§19 での扱い (PR #2442)**: 受入 1 は未達のため #1664 の範囲から外し、子 issue #2456 (原文の受入 1) に移した。上の「#1664 に残す」は、この移管で読み替える。
- **訂正 (#2456・§20)**: 上の「並びは LLVM の最終 writer 段で生じる」は根拠不足として取り下げる。`.ll` と `.bc` が同じ run 内で両方とも run ごとに変わるため、差は書き出し前のモジュール内の状態にある (§20)。
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
- **検証範囲 / 範囲外**: 範囲内は `m11_e2e.sh --full` (F1〜F3)・`tools/m11/test_a7_uselistorder.py`・素材 `work-m11` の drc.ll boot0〜3 の directive 残り。範囲外は `tools/liftlib/tests/test_unit.py` (T1〜T25。下の T1 節の表)。
- **`test_unit.py` (HEAD `7b996184`・本 run の実測)**: `work-m6-ott` を `tar --zstd -xf` で `tools/m6/work/`・`tools/ott/work/`・`tools/m8/work/`・`tools/m9/work/`・`tools/m10/work/` に展開して実行した (前回の round の run では素材が無く rc 1)。`python3 tools/liftlib/tests/test_unit.py` は **rc 1**: T1 ok の後、T2 で `OTT_DLL` (`analysis-ott-binaries` の `OTT_vst2_win64.dll`) が無く `FileNotFoundError` で止まる (`__main__` は 1 件目で停止する)。そこで T1〜T25 を 1 件ずつ呼んで結果を取った。本 run の素材は fl-win64・toolchain-emsdk・toolchain-retdec・work-liftdiff・work-m11・work-m6-ott。`analysis-ott-binaries`・`work-liftlib`・`work-liftlib-targets` は本 run に無い。

| 結果 | テスト | 理由 |
|---|---|---|
| ok | T3・T5・T8・T9・T16b・T18・T20・T21・T22・T23・T24・T25 | 素材不要 |
| ok (一部 skip) | T1・T17・T19 | T1: OTT (1 本目) のみ比較。FA・KH の 2 本目は素材無しで skip。T17: T17b は `LL_XRET_*` 未設定で skip。T19: `add_func` は Serum2 PE 無しで skip |
| skip | T11 | `OTT_DLL` 無し (`ott.drc.ll` は有り) |
| FAIL | T2・T7・T10・T12・T13・T14・T15・T16 | `OTT_DLL` 無し (FileNotFoundError) |
| FAIL | T4・T6 | FA 素材 (`liftlib/work/fa_gain`・`targets/freshair/work/win/`) 無し。base.py を通らない |

- **base.py を通ったテスト**: `base.run_base` を呼ぶテストのうち、本 run で通ったのは T1 だけ。T10・T12〜T16 は `OTT_DLL` 無しで未実行、T11 は skip、T17b は `LL_XRET_*` 無しで skip。

### base.py の空行差の実測 (レビュー minor 対応・本 run)

- 方法: 変更前 (`git archive 52ad0ce1^ tools/liftlib` の `base.py`・A7 の 3 行無し) と現在 (`7b996184`) で `base.run_base(ott.drc.ll, base.make_args())` → `IR.Module.parse(text).dump(strip=True)` を出し、`wc -lc` と非空行を比べた。

| 版 | 行数 | bytes | 非空行 (空白のみの行を除く) |
|---|---|---|---|
| 変更前 | 24,971 | 1,032,343 | 22,699 |
| 変更後 | 24,816 | 1,032,188 | 22,699 |

- 差は空行 155 行・155 B で、`ott.drc.ll` の directive ブロック数 (155) と一致する。非空行は両版で完全一致 (`diff` 0 行)。残留の `uselistorder` は両版とも 0 行。
- T1 は `nb()` で空行を除いてから比べるため、この差は検出しない。T1 ok が示すのは非空行の一致だけ。
- **代替の実測 (T1 ではない)**: `work-m11` の `boot0〜3.drc.ll` (RetDec の実出力) に `tools/m5/ir5_patch.py` と `base.py` の `normalize` を当てると、残留の `; uselistorder directives` と `uselistorder ` はどちらも 0 件。ただし 2 つの全体出力は一致しない (`!insn.addr` 等の metadata 行の扱いの差で、A7 と無関係。PR 前から)。A7 の一致の証拠にはしない。
- **限界**: `uselistorder_bb` (基本ブロック用 directive) は A7 の正規表現 (`uselistorder ` の空白あり) に一致せず除去されない。素材の drc.ll boot0〜3 では 0 件 (`grep -c uselistorder_bb` で実測)。回帰テストには含まれない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| T2・T7・T10・T12〜T16 (`OTT_DLL` 系) と T4・T6 (FA 素材) が本 run で未実行 | base.run_base を通る T10・T12〜T16 の A7 変更の影響を、本 run では見ていない | 親 #960 へ提案 (本 PR の `oc_artifacts` に `analysis-ott-binaries` を追加済み。取得できた run で `test_unit.py` を再実行し、結果を #960 に書く) |
| base.py の A7 変更で OTT の lift 出力の空行が 155 行減る (非空行は同一・上表) | 空行数に依存する下流の sha 固定 (golden) への影響は未測定 | 親 #960 へ提案 |
| RetDec 段の `uselistorder` 並びの差の起点 (`--passes` 相当の段・LLVM writer 段の仕組み) | 受入 1 の残り。RetDec 側の決定化の採否 (§19 で保留) の根拠 | 子 issue #2456 |
| `@global_var_*` の出力順が実行ごとに変わる仕組み (RetDec / LLVM writer 段) | lift.ll 単体の比較にだけ出る。`boot_final.ll` は merge の `sorted()` で一致 | 親 #960 へ提案 (観測のみ。順序の由来は §18 の writer 段まで) |
| `ir5_patch.py` の複製 (`tools/plugins/lift/passes/`・`tools/m3/ir_patch.py`・`tools/targets/*/`) の同じ空行残り | m11 の `--full` が使わない複製で未測定。A7 は変更していない | 親 #960 へ提案 |
| `uselistorder_bb` (基本ブロック用 directive) が A7 で除去されない | 素材 drc.ll boot0〜3 では 0 件。回帰テストの対象外 | 親 #960 へ提案 |
- 再現: §14 と同じ (`FL_WIN64_DIR`・`RETDEC_ROOT`・`PATH` を設定し `bash tools/m11/m11_e2e.sh --full` を 3 回)。RetDec 単体は §18 の手順で chunk を 2 回流し、`m2/ir_normalize.py` → `m5/ir5_patch.py` → `m11_gen_ir2.sh` を通して `boot_final.ll` の md5 を比べる。

## 20. #2456: uselistorder 並びの差が入る段の切り分け (#1664 受入 1 の残り)

- 既知類型との関係: 該当なし (DEFECTS.md の silent miscompile 類型ではない。A7 後の lift.ll は全 run 一致)。既知事象は #668 (LIFTLIB-9・`tools/liftlib/REPORT_APPENDIX_D.md` §22) の m11 側の再現。
- 測定 commit: `1a6fb03e` (`fix(m11): take RetDec path from RETDEC env (#2456)`。origin/main `54bacdc0` 起点の `2456-retdec-uselistorder-origin`)。その前の `be4c830b` (スクリプト初版) は RetDec を既定位置 (`RETDEC_ROOT` 未指定時の既定。`docs/REFERENCES.md` `[RETDEC]` と同じ実体) から読んだ。その `retdec-decompiler` と展開物の sha256 は一致 (`9d49ffcf…`) を確認済み。`git diff 1a6fb03e HEAD -- tools ':!tools/m11/REPORT_APPENDIX_960.md'` は **0 行**。
- 条件: PE `fl-win64` の `block00031_PE.bin` (sha256 `b2c64da4…`)・`toolchain-retdec` (RetDec v5.0。`RETDEC` で指定)・`work-m11` の `boot_ranges.txt` 先頭 150 range (`--select-decode-only --timeout 250`)。RetDec 1 回 9.4〜9.7 秒・load 0.2〜0.8 (4 コア)。
- 再現: `M11_PE=<fl-win64>/extracted/block00031_PE.bin RETDEC=<toolchain-retdec>/bin/retdec-decompiler bash tools/m11/uselist_origin_2456.sh 4 3 2 2` (ASLR 有効 4・無効 3・無効 + tcache 2・pass dump 2)。全体 3 分 21 秒。集計は `uselist_origin_2456.py`。独立検算は `grep -cE '^\s*uselistorder(_bb)?\s'` (python と一致)。

### 結果 (1a6fb03e・1 回の全実行)

| run | 条件 | drc.ll | drc.bc | drc.c | lift.ll (A7 後) | 指示行 |
|---|---|---|---|---|---|---|
| on1〜on4 | ASLR 有効 | cbee7ce0 / b8d6a850 / b8d6a850 / cc6dac6c | de95e19f / 565f21e7 / 565f21e7 / e256166e | fffbd338 ×4 | 946aefb3 ×4 | 741 / 741 / 741 / 742 |
| off1〜3 | ASLR 無効 (`setarch x86_64 -R`) | 451df75d ×3 | f99b628a ×3 | fffbd338 ×3 | 946aefb3 ×3 | 742 ×3 |
| tc1・2 | ASLR 無効 + `GLIBC_TUNABLES=glibc.malloc.tcache_count=0` | 886852d5 ×2 | 1a4d9f52 ×2 | fffbd338 ×2 | 946aefb3 ×2 | 741 ×2 |
| pass1 | `--print-after-all` (ASLR 有効) | 1691474e | 02f3068d | fffbd338 | — | 741 |
| pass2 | 同上 | 02bb23bf | 4b83b81e | fffbd338 | — | 741 |

- 群ごとの distinct (drc.ll / drc.bc / drc.c / lift.ll / 指示行と空行を除いた drc.ll): on 3 / 3 / 1 / 1 / 1、off 1 / 1 / 1 / 1 / 1、tc 1 / 1 / 1 / 1 / 1。
- ASLR 有効の drc.ll は、計 4 回の計測 (16 run) で 8 種。同じ手順の計測 (スクリプトの版は違う) でも組が変わった。
- ASLR 無効の drc.ll も計測ごとに変わった: `907ab19c` (be4c830b の計測・3 run とも同一) → `451df75d` (1a6fb03e)。違いは環境変数 `RETDEC` の有無だけで、プロセスのスタック位置が変わった、と推定する (未確認。n が少ない)。ASLR 有効の pass2 の drc.ll (下の再現) も `907ab19c` で、be4c830b の ASLR 無効の値と一致した。drc.ll の値は ASLR の on/off では分かれないかもしれない。
- 指示行の数は、説明行 `; uselistorder directives` (76 = directive を持つ関数数) を除いたもの。

### 再現 run (コード差分 0 の HEAD `b4b7370d`・fix round 1)

- 再現 HEAD: `b4b7370d` (PR #2530 の head)。`git diff 1a6fb03e b4b7370d -- tools ':!tools/m11/REPORT_APPENDIX_960.md'` は 0 行。同じスクリプトを前景で 1 回実行 (`M11_PE=<fl-win64>/extracted/block00031_PE.bin RETDEC=<toolchain-retdec>/bin/retdec-decompiler bash tools/m11/uselist_origin_2456.sh 4 3 2 2`)。PE sha256 `b2c64da4…`・RetDec sha256 `9d49ffcf…` (1a6fb03e と同じ)。

| 群 | drc.ll | 指示行除去 drc.ll | drc.c | lift.ll (A7 後) | 指示行数 |
|---|---|---|---|---|---|
| on1〜4 (ASLR 有効) | `30cd458d`・`c3334c92`・`6c09a7a9`・`f250e521` (4 種) | `407eb71e` ×4 | `fffbd338` ×4 | `946aefb3` ×4 | 741・740・741・742 |
| off1〜3 (ASLR 無効) | `fd47ef1b` ×3 | `407eb71e` ×3 | `fffbd338` ×3 | `946aefb3` ×3 | 739 ×3 |
| tc1・2 (ASLR 無効 + tcache 0) | `c96f0e04` ×2 | `407eb71e` ×2 | `fffbd338` ×2 | `946aefb3` ×2 | 741 ×2 |
| pass1・2 (`--print-after-all`・ASLR 有効) | `cc6dac6c`・`907ab19c` | `407eb71e` ×2 | `fffbd338` ×2 | —(pass dump の run には無い) | 742・741 |

- 群ごとの distinct (drc.ll / drc.bc / drc.c / lift.ll / 指示行除去 drc.ll): on 4 / 4 / 1 / 1 / 1、off 1 / 1 / 1 / 1 / 1、tc 1 / 1 / 1 / 1 / 1。
- 差が出た関数 (run 対の和集合): `function_408400`・`function_4099c0`・`function_407a50` の 3 関数 (1a6fb03e の計測の 5 関数と違う)。
- pass dump: pass1・pass2 の stderr は全体で `340d476b`・81,366,993 B (一致)。警告 1 件 (`function_4087e0`) を含む。警告行を除くと両方 `bcb87297`。
- 所要 (RetDec・逐次・4 コア): 1 回 9.6〜9.9 秒 (ASLR 有効・無効・tc 共通)、pass dump 1 回 59.6 秒。RetDec の合計 206.6 秒。load 1.00〜1.16。

### 切り分け

1. **差は指示行だけ**: 指示行と空行を除いた drc.ll は全 11 run で 1 種 (`407eb71e`)。drc.c と A7 後の lift.ll も全 run 一致 (再現 run でも同じ)。負例: 同じ on 群の生の drc.ll は計測ごとに変わる (1a6fb03e の計測では 3 種・再現 run では 4 種)。→ §19 の A7 がこの差を吸収する。
2. **差は一部の関数に限られる**: directive を持つ 76 関数のうち、最終計測の run 対で差が出たのは 5 関数 (`function_407520`・`function_408400`・`function_4099c0`・`function_4087e0`・`function_40b620`)。差は指示行の有無 (一方の run にだけ指示がある) と、指示値の順列の両方。同じ行の集合で並びだけ違う関数は 0 件。例: `@WriteFile` の指示値が `{ 0, 1, 2, 4, 3 }` と `{ 2, 0, 1, 4, 3 }` で違う (§18 と同じ指示。計測 1 回目で確認)。
3. **差は書き出し前のモジュール内状態にある**: 同一 run の `.ll` と `.bc` が両方 run ごとに変わる (on 群で各 3 種)。ログでは `.ll`・`.bc` が `.c` より前に続けて書かれる。二つの writer が同じ状態から別々に揺れるとは考えにくいので、揺れは writer より前にある (推定)。→ §18 の「writer 段」は取り下げ (上の訂正)。
4. **アドレス依存 (推定・n は少ない)**: ASLR 無効でヒープの割り当てだけ変えた tc は off と drc.ll・drc.bc が違う (`451df75d` → `886852d5`、`f99b628a` → `1a4d9f52`)。ASLR 無効の drc.ll の値も計測ごとに変わった (上の結果)。順序は割り当てられたポインタ値に依存する、と推定する。機構 (どの container か) は未特定。同梱 toolchain の `retdec.tar.xz` は include/・bin/・lib/・share/ のみで、`.cpp` と `.c` が 0 件 (展開して確認。コードでの確認はできない)。
5. **pass 単位 (未達)**: `--print-after-all` の IR テキスト (17,954 件) は、警告行を除くと 2 run で一致する (再現 run: 両方 `bcb87297`・指示行 0)。stderr 全体の md5 は、1a6fb03e の計測と再現 run では `340d476b`・81,366,993 B で一致したが、PR #2530 のレビュー時の再現では警告 1 行の差で不一致 (pass2 が `b050138d`・81,367,079 B。項 6)。同じ 2 run の drc.ll と drc.bc は違う (上表)。テキストは use-list の順序を持たないので、テキストに差が無いことは「順序が変わらない」根拠にならない。段の特定には use-list 付きの per-pass dump が要るが、v5.0 バイナリは `--print-after-all`・`--print-before-all` しか持たない。差の入る範囲は、ログの `Input binary to LLVM IR decoding` の後から `.ll`/`.bc` の書き出しまでの最適化フェーズ群 (推定)。
6. 副次観測: HLL 段の「outside of a loop」(`break` の位置) の警告は run ごとに 1 件 (1a6fb03e の計測は on4 だけ 2 件、再現 run は on3 だけ 2 件。関数は `function_4087e0`・`function_408b60`)。stderr の差は、観測した範囲では警告行だけ。`.c` は全 run 同一。揺れの原因は未特定で、DEFECTS 類型には当てない (出力に影響が無いため)。

### 受入 1 の到達

- 達成: 差の場所 (drc.ll の指示行。差の関数の集合は計測ごとに変わる: 1a6fb03e の計測で 5 関数・再現 run で 3 関数)・差の段 (書き出し前のモジュール内状態、writer ではない・推定)・性質 (ポインタ値に依存・推定)。
- 未達: pass 単位 (`--passes` 相当) の特定。use-list を見る手段が v5.0 の配布物に無い。子 issue #2577 に移した (#2456 の範囲は raw 出力の特定まで)。
- 決定への影響: §19 の方針 (RetDec 側は決定化せず、A7 で吸収) を維持する。RetDec 側の決定化はソース非同梱のため採らない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| pass 単位の段の特定 (use-list 付き per-pass dump が無い) | 上流 (RetDec) の修正箇所が決まらない | 子 issue #2577 (#2456 から移管) |
| アドレス依存の機構 (どの container か) | 推定止まり (tcache 摂動と環境変数の 2 種で観測。n は少ない) | 子 issue #2577 (同上) |
| HLL 段の break 警告の件数の揺れ | `.c` に影響なし (全 run 同一) | 親 #960 へ提案 (観測のみ) |
