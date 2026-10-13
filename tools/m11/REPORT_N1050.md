# m11 本番 harness の shimx file trace 実 boot 収集 (#1050 / 親 #789)

既知類型との関係: 該当なし (ftrace 0 行は収集経路・file API 呼出の有無に関する結果で、lift 欠陥の類型 (DEFECTS.md) には当たらない)。ただし §4 の trap 位置 `function_8c5eb0` は DEFECTS.md の D19 と同一関数で、同一原因かは未確認。

## 1. 結論

- 全再生成 `m11_e2e.sh --full` は rc=0 で通り、`reached_stage=4` (期待値 `M11_EXPECT_STAGE=4` と一致)。実測 604.7 s。
- `--trace --soft` の trace variant は `_shimx_set_trace_file` を export し、実 boot で `dllmain_done=true` まで進んだ。
- 実 boot の `<tag>.ftrace.jsonl` は **0 行** (元 run の実測)。boot 中 (17 unit) に file API (CreateFileW / CreateFileA / GetFileAttributesW / FindFirstFileW / FindFirstFileExW / FindNextFileW / ReadFile) の呼出が 1 件も無いため。
- 受入条件「件数と api 内訳」は **未達**。0 件は実測結果として記録するが、目的 (実 boot の file API trace の取得) は達成していない。#1050 に残す。
- 収集経路が file API の呼出を記録できることは、SHX-T12 単体テストのネガコン付き実行で確認済み (§3-2)。ただし m11 本番 wasm 上での probe は未実施。

## 2. 実測

環境: ランナー (Ubuntu, JDK 21.0.12, Ghidra 12.1.4 build 20260921)。素材 `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` / `work-m11` を展開。

| 段階 | コマンド | 結果 |
|---|---|---|
| Ghidra 再生成 | `analyzeHeadless ... -postScript DumpFunctions.java` | rc=0 / 600 s (`functions_dll.csv` 2,087,706 bytes) |
| 全再生成 | `FL_WIN64_DIR=... bash tools/m11/m11_e2e.sh --full` | rc=0 / 604.7 s / `reached_stage=4` (`trap "unreachable" @ function_8c5eb0`) |
| trace variant build | `bash tools/m11/shimx_link/build.sh --trace --soft` | rc=0 / `signature mismatch=1 undefined symbol=0 duplicate=0` (§4 で説明) |
| 実 boot (trace) | `SHIMX_TRACE_FILE=... node tools/m11/shimx_link/run_trace.mjs m11_sx_trace_soft.cjs --out ...` | rc=0 / `boot_stage=1` `units_run=17` `icall_ok=24` `icall_miss=1` `dllmain_done=true` `longjmp_hit=1` / trace `total_calls=106` `distinct_called=29` |
| ftrace | 同上 | `m11_sx_trace_soft.ftrace.jsonl` 0 行 (元 run の記録。ファイル自体の再計測は §5) |

- 回帰ゲート: `m11_judge.py --require-stage 4 --min-survey-ok 800` は rc=0 (`survey_ok=870` / `survey_trap=25` / `survey_miss=46`)。`units_run_full=53`。
- `--trace` (fail-fast GUI) 版は `LoadStringW` 未実装で `Aborted` (0.45 s)。`--soft` 版を採用。
- 全再生成前の旧 `work-m11` IR では `memory access out of bounds` で unit 17 前後に停止していた (`m11_run.mjs` の trace 無し経路でも同じ)。全再生成後は解消。

### 2-1. 検証起点

- 全再生成・trace build・実 boot の**実行 commit hash は元 run のログに残っておらず、特定できない**。
- 代わりに code tree を実測で固定した: `git diff 1ef8ccfb 945d2fd -- tools/m11 tools/shimx` の変更は `tools/m11/REPORT_N1050.md` の 37 行追加のみ。よって `tools/m11` / `tools/shimx` の code は main (`1ef8ccfb`) と PR head (`945d2fd`) で同一であり、元 run は同じ code tree で行われたと推定する (推定)。
- 以後の run は、実行前に `git rev-parse HEAD` を REPORT に書く。

## 3. 数え方・ネガティブコントロール

### 3-1. 数え方と再計算

- trace の `total_calls` は `run_trace.mjs` が出力する `trace.calls` の合計。関数別の内訳は `tools/m11/work/ftrace/m11_sx_trace_soft.run.json` の `trace.calls`。
- 0 件の判定 (元 run): `calls[].name` のうち file API 名 (上記 7 件) との積集合を取った。結果は空集合。
- 再計算:
  ```sh
  python3 -c "import json;d=json.load(open('tools/m11/work/ftrace/m11_sx_trace_soft.run.json'));print(sorted({c['name'] for c in d['trace']['calls']}))"
  ```
- 主張の対象は ftrace ファイルの行数であり、`calls[].name` の積集合は別手段の補助にすぎない。ftrace ファイル自体の `wc -l` は §5 のとおり再計測できていない。

### 3-2. ネガティブコントロール (SHX-T12 の単体テストで同じ collector を実測)

収集経路 (`tools/shimx/src/trace.c` の `ftrace_open`) は、m11 本番と同じ `shimx_set_trace_file` から呼ばれる。m11 側の経路は `build.sh` L120 の EXPORTS (`_shimx_set_trace_file`) と `run_trace.mjs` L24 / L107 (`ccall('shimx_set_trace_file')`)。

本修正 run で次を実行した:

- 前提: emsdk 6.0.12 を `/home/runner/work/_temp/emsdk` に install (pin 版。`[EMSDK]` の代替。素材 `toolchain-emsdk` は本 run では未展開)。
- コマンド: `bash tools/shimx/test/ftrace/ftrace_test.sh` (HEAD = `945d2fd8` の worktree 上の tools/shimx は main と同一)
- 結果: rc=0 / 5.98 s。
  - `events=10` / `by_api` = CreateFileW 2・CreateFileA 1・GetFileAttributesW 2・FindFirstFileW 2・FindNextFileW 2・ReadFile 1。file API の呼出が JSON 行として記録された。
  - ネガコン ✓ トレース無効時は JSON 行なし。
  - ネガコン ✓ `SHIMX_TRACE_FILE` 指定あり → JSON 行 1 件以上 / 指定なし → ファイル無し。
  - ✓ 既存 stderr トレースと JSON 行は混ざらない。
- loadavg は未計測。

注: SHX-T12 単体テストは NODERAWFS の環境変数経路と ST ビルドで行を出すことを示すもので、m11 本番 wasm 上で行が出る実測 (probe) ではない。その probe は素材 `work-m11` が要るため未実施。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 boot で file API が発生しない原因の切り分け (`reached_stage=4` の trap `function_8c5eb0` の手前か後段か)。17 unit までは GetProcAddress / TlsAlloc 等の初期化系のみ | 受入条件「件数と api 内訳」が未達 | #1050 に残す |
| trace variant build の `signature mismatch=1`: **期待どおりではない**。通常ビルドの既存記録は 0 件 (`tools/m11/trap_triage/REPORT_860.md` L11・`REPORT_596.md` L110 の `wasm-ld signature mismatch 0`)。ただし比較元は `m11_build.sh` で、本 trace variant は `shimx_link/build.sh` のため直接の比較ではない。原因は未特定 | trace variant の link 結果の整合が未確認。`_shimx_set_trace_file` の export 自体は確認済み | #1050 に残す |
| `function_8c5eb0` の trap が D19 (DEFECTS.md, 件数 0 ループの do-while 化) と同一関数。D19 の修復 (`m11_guard699.py`) が本 run の HEAD に効いているかは未確認 | 実 boot が unit 56 付近で止まる。file API 呼出の到達を妨げる可能性 | #1050 に残す |
| `--full` の IR sha256 は実行ごとに変わる (`tools/m11/REPORT_N27.md` §12 の既知事項)。元 run の `ir_sha256=2290a625...` は 1 回限りの値 | 再現時の比較基準にならない | 既知事項 (対応なし) |
| SHX-T12 `tools/shimx/REPORT_SHX-T12.md` §7 の「m11 harness に `shimx_set_trace_file` の export を足す」未起票項目は、build.sh の export と run_trace.mjs の ccall で実装済み。SHX-T12 側の記述は本 PR の範囲外のため未更新 | SHX-T12 REPORT の状態表記が古い | PM 判断 (#789 側で REPORT を更新) |

## 5. 本修正 (差し戻し対応) の実施内容と未実施

- 実施: §2-1 の検証起点、§3-2 のネガコン (SHX-T12 単体テスト rc=0 / 5.98 s)、§4 の既知類型・signature mismatch・未解決の表形式化。
- 未実施 (理由つき):
  - **ftrace ファイル自体の `wc -l`**: `tools/m11/work/ftrace/` が無く、元 run の ftrace ファイルを再計測できない。`work-m11` は `$ARTIFACTS_DIR` に無く (`ls` で `fl-win64.tar.zst` のみ確認)、fix run では展開できない。PR 本文の `oc_artifacts` 行で review run が取得して再計測する想定。
  - **全再生成・trace build・実 boot の再実行**: Ghidra 600 s + regen 605 s + 実 boot が fix の上限 40 分に収まらず、また `work-m11` が無いため不可。
