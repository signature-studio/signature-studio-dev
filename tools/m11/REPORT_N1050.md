# m11 本番 harness の shimx file trace 実 boot 収集 (#1050 / 親 #789)

既知類型との関係: 該当なし (trace.calls 上の file API 0 件は収集経路・file API 呼出の有無に関する結果で、lift 欠陥の類型 (DEFECTS.md) には当たらない)。ただし §4 の trap 位置 `function_8c5eb0` は DEFECTS.md の D19 と同一関数で、同一原因かは未確認。

## 1. 結論

- 全再生成 `m11_e2e.sh --full` は rc=0 で通り、`reached_stage=4` (期待値 `M11_EXPECT_STAGE=4` と一致)。実測 604.7 s。
- `--trace --soft` の trace variant は `_shimx_set_trace_file` を export する。実 boot は `dllmain_done=false` / `boot_stage=1` / `units_run=17` で `memory access out of bounds` により停止した (snapshot `m11_sx_trace_soft.run.json` と `m11_sx_trace_soft_fix.run.json` の両方で同値)。以前の「dllmain_done=true まで進んだ」は出典を示せない誤記のため撤回する。
- 実 boot の trace.calls 上に file API 名 (CreateFileW / CreateFileA / GetFileAttributesW / FindFirstFileW / FindFirstFileExW / FindNextFileW / ReadFile) は **0 件** (元 run の実測)。ftrace ファイル自体の行数は未実測 (§5)。
- 受入条件「件数と api 内訳」は **未達**。0 件は実測結果として記録するが、目的 (実 boot の file API trace の取得) は達成していない。#1050 に残す。
- 収集経路が file API の呼出を記録できることは、SHX-T12 単体テストのネガコン付き実行で確認済み (§3-2)。ただし m11 本番 wasm 上での probe は未実施。

## 2. 実測

環境: ランナー (Ubuntu, JDK 21.0.12, Ghidra 12.1.4 build 20260921)。下表の実測は元 run のもの (実行 commit は §2-1 のとおり未特定)。本 fix run で展開した素材は `work-m11` の 4 ファイル (`tools/m11/work/m11_image.bin`・`tools/m11/work/shimx_link/m11_sx_trace_soft.{cjs,cjs.wasm,run.json}`) のみ。`fl-win64` / `toolchain-retdec` / `toolchain-emsdk` は本 fix run では展開していない。

| 段階 | コマンド | 結果 |
|---|---|---|
| Ghidra 再生成 | `analyzeHeadless ... -postScript DumpFunctions.java` | rc=0 / 600 s (`functions_dll.csv` 2,087,706 bytes) |
| 全再生成 | `FL_WIN64_DIR=... bash tools/m11/m11_e2e.sh --full` | rc=0 / 604.7 s / `reached_stage=4` (`trap "unreachable" @ function_8c5eb0`) |
| trace variant build | `bash tools/m11/shimx_link/build.sh --trace --soft` | rc=0 / `signature mismatch=1 undefined symbol=0 duplicate=0` (§4 で説明) |
| 実 boot (trace) | `SHIMX_TRACE_FILE=... node tools/m11/shimx_link/run_trace.mjs m11_sx_trace_soft.cjs --out ...` | `boot_stage=1` `units_run=17` `icall_ok=19` `icall_miss=1` `dllmain_done=false` `longjmp_hit=0` `threw="memory access out of bounds"` / trace `total_calls=94` `distinct_called=26` `dropped=0` (出典: `work-m11` 内 `tools/m11/work/shimx_link/m11_sx_trace_soft.run.json`。`_fix` 版も同値) |
| ftrace | 同上 | trace.calls 上の file API 名 0 件 (元 run の記録)。`m11_sx_trace_soft.ftrace.jsonl` の行数は未実測 (§5) |

- 回帰ゲート: `m11_judge.py --require-stage 4 --min-survey-ok 800` は rc=0 (`survey_ok=870` / `survey_trap=25` / `survey_miss=46`)。`units_run_full=53`。
- `--trace` (fail-fast GUI) 版は `LoadStringW` 未実装で `Aborted` (0.45 s)。`--soft` 版を採用。
- 全再生成前の旧 `work-m11` IR では `memory access out of bounds` で unit 17 前後に停止していた (`m11_run.mjs` の trace 無し経路でも同じ)。全再生成後は解消。
- 本 fix run の再実行 (展開した `work-m11` の `m11_sx_trace_soft.cjs` を `tools/m11/shimx_link/run_trace.mjs` で実行、HEAD `1aa0f211`): rc=0。`boot_stage=1` `units_run=17` `icall_ok=19` `icall_miss=1` `dllmain_done=false` `longjmp_hit=0` `threw="memory access out of bounds"` / trace `total_calls=94` `distinct_called=26` `dropped=0`。`run.json` の保存値と一致。file API 名の積集合は空。
- 同じ再実行で `SHIMX_TRACE_FILE` を指定すると `Aborted('FS' was not exported)` で落ちる (artifact の `.cjs` は `FS` を export しない版。現在の `build.sh` L127 は export する)。そのため ftrace ファイルは生成されず、行数は取得できていない (§5)。

### 2-1. 検証起点

- 全再生成・trace build・実 boot の**実行 commit hash は元 run のログに残っておらず、特定できない**。
- 代わりに code tree を実測で固定した: `git diff 1ef8ccfb 8597b970 -- tools/m11 tools/shimx` の変更は `tools/m11/REPORT_N1050.md` の 79 行追加のみ (`tools/shimx` の差分は 0 行)。よって `tools/m11` / `tools/shimx` の code は main (`1ef8ccfb`) と PR head (`8597b970`) で同一であり、元 run は同じ code tree で行われたと推定する (推定)。
- 以後の run は、実行前に `git rev-parse HEAD` を REPORT に書く。

## 3. 数え方・ネガティブコントロール

### 3-1. 数え方と再計算

- trace の `total_calls` は `run_trace.mjs` が出力する `trace.calls` の合計。関数別の内訳は `tools/m11/work/shimx_link/m11_sx_trace_soft.run.json` の `trace.calls`。
- 0 件の判定 (元 run): `calls[].name` のうち file API 名 (上記 7 件) との積集合を取った。結果は空集合。
- 再計算:
  ```sh
  python3 -c "import json;d=json.load(open('tools/m11/work/shimx_link/m11_sx_trace_soft.run.json'));fa={'CreateFileW','CreateFileA','GetFileAttributesW','FindFirstFileW','FindFirstFileExW','FindNextFileW','ReadFile'};print(sorted(fa & {c['name'] for c in d['trace']['calls']}))"
  ```
- snapshot (`work-m11` 展開物) での結果: `[]` (空集合)。`total_calls=94` / `distinct_called=26` / `dropped=0`。`m11_sx_trace_soft_fix.run.json` も同じ。
- 主張の対象は ftrace ファイルの行数であり、`calls[].name` の積集合は別手段の補助にすぎない。ftrace ファイル自体の `wc -l` は §5 のとおり再計測できていない。

### 3-2. ネガティブコントロール (SHX-T12 の単体テストで同じ collector を実測)

収集経路 (`tools/shimx/src/trace.c` の `ftrace_open`) は、m11 本番と同じ `shimx_set_trace_file` から呼ばれる。m11 側の経路は `build.sh` L120 の EXPORTS (`_shimx_set_trace_file`) と `run_trace.mjs` L24 / L107 (`ccall('shimx_set_trace_file')`)。

本修正 run で次を実行した:

- 前提: `tools/shimx/test/ftrace/ftrace_test.sh` L15 が `[EMSDK]` (`docs/REFERENCES.md`) の `emsdk_env.sh` を source する。この経路は runner 上の既存 install を使う。`toolchain-emsdk` の artifact は本 fix run では展開していない。
- 実行 HEAD: `1aa0f211` (commit 済み・PR head)。コマンド: `bash tools/shimx/test/ftrace/ftrace_test.sh`
- 結果: rc=0 / 3.89 s (`uptime` load average 0.60)。全 6 段 PASS (`完了: SHX-T12 ftrace 全 PASS`)。
  - `events=10` / `by_api` = CreateFileW 2・CreateFileA 1・GetFileAttributesW 2・FindFirstFileW 2・FindNextFileW 2・ReadFile 1。file API の呼出が JSON 行として記録された。
  - ネガコン ✓ トレース無効時は JSON 行なし。
  - ネガコン ✓ `SHIMX_TRACE_FILE` 指定あり → JSON 行 1 件以上 / 指定なし → ファイル無し。
  - ✓ 既存 stderr トレースと JSON 行は混ざらない。
- loadavg は実行直後の `uptime` で 0.60 (1 分平均) のみ記録。

注: SHX-T12 単体テストは NODERAWFS の環境変数経路と ST ビルドで行を出すことを示すもので、m11 本番 wasm 上で行が出る実測 (probe) ではない。本 fix run の m11 本番 wasm 再実行は `FS` 未 export のため ftrace を書けず (§2)、probe は未達。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 boot で file API が発生しない原因の切り分け。snapshot では `units_run=17` の範囲で GetProcAddress / TlsAlloc 等の初期化系のみ、unit 17〜18 付近で `memory access out of bounds` により停止 (`dllmain_done=false`) | 受入条件「件数と api 内訳」が未達 | #1050 に残す |
| trace variant build の `signature mismatch=1`: **期待どおりとは確認できていない** (0 件が期待値と思われるが、本 run では根拠の実測なし)。通常ビルドの既存記録は 0 件 (`tools/m11/trap_triage/REPORT_860.md` L11・`REPORT_596.md` L110 の `wasm-ld signature mismatch 0`)。ただし比較元は `m11_build.sh` で、本 trace variant は `shimx_link/build.sh` のため直接の比較ではない。原因は未特定 | trace variant の link 結果の整合が未確認。`_shimx_set_trace_file` の export 自体は確認済み | #1050 に残す |
| `function_8c5eb0` の trap が D19 (DEFECTS.md, 件数 0 ループの do-while 化) と同一関数。D19 の修復 (`m11_guard699.py`) が本 run の HEAD に効いているかは未確認 | 実 boot が unit 17〜18 付近で止まる (snapshot 実測)。file API 呼出の到達を妨げる可能性 | #1050 に残す |
| `--full` の IR sha256 は実行ごとに変わる (`tools/m11/REPORT_N27.md` §12 の既知事項)。元 run の `ir_sha256=2290a625...` は 1 回限りの値 | 再現時の比較基準にならない | 既知事項 (対応なし) |
| SHX-T12 `tools/shimx/REPORT_SHX-T12.md` §7 の「m11 harness に `shimx_set_trace_file` の export を足す」未起票項目は、build.sh の export と run_trace.mjs の ccall で実装済み。SHX-T12 側の記述は本 PR の範囲外のため未更新 | SHX-T12 REPORT の状態表記が古い | PM 判断 (#789 側で REPORT を更新) |

## 5. 本修正 (差し戻し対応) の実施内容と未実施

- 実施: §2-1 の検証起点、§3-2 のネガコン (SHX-T12 単体テスト rc=0 / 3.62 s、実行 HEAD `8597b970`)、§4 の既知類型・signature mismatch・未解決の表形式化。
- 未実施 (理由つき):
  - **ftrace ファイル自体の `wc -l`**: `work-m11.tar.zst` (`$ARTIFACTS_DIR` に存在) には `tools/m11/work/shimx_link/` の `run.json` / `stderr.txt` / `cjs.wasm` 等が入るが、`ftrace` を含むエントリは 0 件 (`tar --zstd -tf | grep -c ftrace` = 0)。よって tarball からは `<tag>.ftrace.jsonl` の行数を再計測できない。
  - **全再生成・trace build の再実行**: Ghidra 600 s + regen 605 s が fix の上限 40 分に収まらないため、この run では再実行しない。実 boot は展開済み `.cjs` で再実行した (§2)。
  - **ftrace 行数の取得**: 上記のとおり `.cjs` が `FS` を export しないため、`SHIMX_TRACE_FILE` 付きの実 boot では ftrace が生成されない。`wc -l` は取得できていない。取り直すには `FS` を export した trace variant (`build.sh --trace --soft`) の再 build が必要で、これは全再生成と同じく本 run の上限を超える。
- 素材の実在: `$ARTIFACTS_DIR` には `fl-win64` / `toolchain-emsdk` / `toolchain-retdec` / `work-m11` の 4 本が存在する (本 fix run で `ls` 確認)。展開したのは `work-m11` の上記 4 ファイルのみ。
- 検証 HEAD: 差分範囲は `git diff 8597b970 1aa0f211 --stat` (`tools/m11/REPORT_N1050.md` のみ・コード差分 0)。ネガコン (§3-2) は `1aa0f211` で実行済み。
