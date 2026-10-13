# m11 本番 harness の shimx file trace 実 boot 収集 (#1050 / 親 #789)

## 1. 結論

- 全再生成 `m11_e2e.sh --full` は rc=0 で通り、`reached_stage=4` (期待値 `M11_EXPECT_STAGE=4` と一致)。実測 10 分 5 秒。
- `--trace --soft` の trace variant は `_shimx_set_trace_file` を export し、実 boot で `dllmain_done=true` まで進んだ。
- ただし実 boot の `<tag>.ftrace.jsonl` は **0 行**。boot 中 (17 unit) に file API (CreateFileW / CreateFileA / GetFileAttributesW / FindFirstFileW / FindFirstFileExW / FindNextFileW / ReadFile) の呼出が 1 件も無いため。0 件は実測結果として記録する。

## 2. 実測

環境: ランナー (Ubuntu, JDK 21.0.12, Ghidra 12.1.4 build 20260921)。素材 `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` / `work-m11` を展開。

| 段階 | コマンド | 結果 |
|---|---|---|
| Ghidra 再生成 | `analyzeHeadless ... -postScript DumpFunctions.java` | rc=0 / 600 s (`functions_dll.csv` 2,087,706 bytes) |
| 全再生成 | `FL_WIN64_DIR=... bash tools/m11/m11_e2e.sh --full` | rc=0 / 604.7 s / `reached_stage=4` (`trap "unreachable" @ function_8c5eb0`) |
| trace variant build | `bash tools/m11/shimx_link/build.sh --trace --soft` | rc=0 / `signature mismatch=1 undefined symbol=0 duplicate=0` |
| 実 boot (trace) | `SHIMX_TRACE_FILE=... node tools/m11/shimx_link/run_trace.mjs m11_sx_trace_soft.cjs --out ...` | rc=0 / `boot_stage=1` `units_run=17` `icall_ok=24` `icall_miss=1` `dllmain_done=true` `longjmp_hit=1` / trace `total_calls=106` `distinct_called=29` |
| ftrace | 同上 | `m11_sx_trace_soft.ftrace.jsonl` 0 行 |

- 回帰ゲート: `m11_judge.py --require-stage 4 --min-survey-ok 800` は rc=0 (`survey_ok=870` / `survey_trap=25` / `survey_miss=46`)。`units_run_full=53`。
- `--trace` (fail-fast GUI) 版は `LoadStringW` 未実装で `Aborted` (0.45 s)。`--soft` 版を採用。
- 全再生成前の旧 `work-m11` IR では `memory access out of bounds` で unit 17 前後に停止していた (`m11_run.mjs` の trace 無し経路でも同じ)。全再生成後は解消。

## 3. 数え方と再計算

- trace の `total_calls` は `run_trace.mjs` が出力する `trace.calls` の合計。関数別の内訳は `tools/m11/work/ftrace/m11_sx_trace_soft.run.json` の `trace.calls`。
- 0 件の判定: `calls[].name` のうち file API 名 (上記 7 件) との積集合を取った。結果は空集合。
- 再計算:
  ```sh
  python3 -c "import json;d=json.load(open('tools/m11/work/ftrace/m11_sx_trace_soft.run.json'));print(sorted({c['name'] for c in d['trace']['calls']}))"
  ```

## 4. 未解決 (起票先)

- **実 boot で file API が発生しない原因**: 17 unit までの範囲では GetProcAddress / TlsAlloc 等の初期化系のみ。FL の file API 呼出は後段 unit (`reached_stage` 4 の trap 手前) で起きる可能性があるが、未切り分け。`reached_stage=4` の trap (`function_8c5eb0`) の解消が前提となるため、別 issue で扱う。
- `--full` の IR sha256 は実行ごとに変わる (`tools/m11/REPORT_N27.md` §12 の既知事項)。本 run の `ir_sha256=2290a625...` は 1 回限りの値。
