# SHX-T27 (#1630): unit 18 の GetLocaleInfoW 反復と file API 到達経路の切り分け (親 #1493 / 関連 #1050)

## 1. 結論

- 測定 commit: `5d167ecd` (origin/main 取り込み後の commit 済み HEAD)。build 前に `git rev-parse HEAD` を確認。
- 受入条件「`SHIMX_TRACE_FILE` の ftrace 件数 > 0」は **未達** (0 行)。件数 0 のため #1050 は close 不可と判定する。
- trace 上の停止は `unit 18` の `GetLocaleInfoW` 66 回反復の後で、`memory access out of bounds` (`dllmain_done=false` / `units_run=17`)。前回の実測 (`3cdf8329`、`tools/m11/REPORT_N1050.md` §7) と同一の結果。
- 停止の trap 位置は `function_4133f0` (wasm-function[1352])。前回までの「stack 最上段が export 無し」は誤りで、export 名で解決すると `function_4133f0` である。
- ftrace が 0 バイトのままである事実は確認した (`FS` export 済みの現行 build でも同じ)。停止が unit 18 の `GetLocaleInfoW` 反復の後に起きる事実も確認した。ただし「そのため file API に到達しない」という因果は未検証。

## 2. 実測 (測定 commit `5d167ecd`、検証 HEAD `7738ce46` の clean worktree `work/wt_verify`)

| 段階 | コマンド | 結果 |
|---|---|---|
| trace variant build | `bash tools/m11/shimx_link/build.sh --trace --soft` | rc=0 / 13.9 s / `signature mismatch=1 undefined symbol=0 duplicate=0` |
| 実 boot (ftrace) | `SHIMX_TRACE_FILE=/ftrace.jsonl node tools/m11/shimx_link/run_trace.mjs $W/m11_sx_trace_soft.cjs --out $W/verify` (`$W` = `tools/m11/work/shimx_link` の絶対パス。`.cjs` は絶対パスで渡す) | rc=0 / 0.42 s / `boot_stage=1` `init_count_var=18` `units_run=17` `icall_ok=24` `icall_miss=1` `dllmain_done=false` `threw="memory access out of bounds"` |
| trace | 同上 (run.json) | `total_calls=97` `distinct_called=28` `dropped=0` |
| ftrace 行数 | `wc -l <tag>.ftrace.jsonl` | **0 行** (0 バイト)。`FS` は export 済み・`ftrace_error` 無し |

- 測定時 load (1 分平均): 0.69 (`uptime`、boot 直前)。
- 既存 `work-m11` の `.cjs` (旧 build) は `FS` 未 export のため `Aborted('FS' was not exported)` で落ちる。これは `build.sh` の現行版で再 build すると解消する。
- 参考: 比較用の旧 HEAD `9f968b27` から測定 commit `5d167ecd` までの `tools/m11`・`tools/shimx` の差分は 2 ファイル (`REPORT_APPENDIX_960.md`・`m11_sdiv_variant.py`) の追加のみ (+64 行)。`9f968b27` は測定対象ではない。

### 2-1. unit 別の trace calls (run.json)

| unit | calls | distinct | 呼出 (new) |
|---|---|---|---|
| 0 | 5 | 5 | GetCurrentThreadId, TlsAlloc, LocalAlloc, TlsSetValue, TlsGetValue |
| 2 | 21 | 12 | VerSetConditionMask, VerifyVersionInfoW, GetModuleHandleW, GetProcAddress, SetThreadLocale, InitializeCriticalSection, GetVersion, GetSystemInfo, GetCommandLineW, GetStartupInfoW, GetACP |
| 16 | 3 | 2 | VirtualAlloc, LoadStringW |
| 17 | 2 | 2 | GetVersionExW |
| 18 | 66 | 13 | GetModuleFileNameW, WideCharToMultiByte, GetThreadLocale, GetCPInfo, IsValidLocale, GetLogicalProcessorInformation, GetLastError, **GetLocaleInfoW (反復)**, EnumCalendarInfoW |

- 末尾 12 件 (seq 85〜96) は全て unit 18 の `GetLocaleInfoW`。
- file API (CreateFileW / CreateFileA / GetFileAttributesW / FindFirstFileW / FindFirstFileExW / FindNextFileW / ReadFile) は 0 件。

## 3. trap stack の解決 (export 名)

`run_trace.mjs` の stack 注釈は `wasm-objdump` が無いため無効だった。代わりに `.cjs.wasm` の export section を直接読んで番号を解決した。

| wasm-function | 関数 | 役割 (IR 上) |
|---|---|---|
| 1352 (最上段・trap) | `function_4133f0` | 呼出元 `function_446400` 等から呼ばれる。役割の詳細は未確定 |
| 4468 | `function_446400` | locale 情報 (LCType 20・27・28…) を集める。`function_446370` 等を呼ぶ |
| 4522 | `function_44bb70` | `function_446400` の呼出元 |
| 4592 | `function_455790` | 上位の呼出元 |
| 11482 | `m11_tr_function_455790` | trace wrapper |
| 1328 | `m11_icall` | icall 経由 |
| 1346 | `function_4120c0` | 初期化 |
| 1347 | `m11_InitLib` | |
| 1350 | `function_41d8f0` | |

- 呼出チェーン (静的): `function_41d8f0` → `function_4120c0` → (icall) `function_455790` → `function_44bb70` → `function_446400` → `function_4133f0` (trap)。
- `function_446370` / `function_4463d0` は `GetLocaleInfoW` を 1 回だけ呼ぶ薄いラッパで、反復ループの本体ではない。`GetLocaleInfoW` の反復は `function_446400` の呼出元側に由来する (静的解析で確定できず)。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `GetLocaleInfoW` 66 回反復の駆動関数 (ループ本体) の特定と、反復が止まらない理由 | file API 到達前の停止原因が未確定 | #1630 (本 issue) |
| `function_446400` → `function_4133f0` の OOB の値の追跡 (動的) | 停止の直接原因が未確定。件数 0 の根本 | #1630 (本 issue) |
| `function_4133f0` と D19 (DEFECTS.md) の関係 | D19 の類型判定が未確定 (`REPORT_N1050.md` §7-3 と整合) | #1629 (SHX-T26) |
| `midiOutShortMsg` の型不一致 `signature mismatch=1` | trace variant の link 整合 | #1628 (SHX-T25) |

## 5. 検証の起点と鮮度

- 測定 commit: `5d167ecd624185d98140f4d7bb641484a8ff3de2` (コード差分の最終 commit。commit 済み・clean)。
- 測定の場所: `git worktree add --detach work/wt_verify 7738ce46` (main の作業ツリーは使わない)。素材 `work-m11.tar.zst` を worktree 直下に `tar --zstd -xf` で展開 (`tools/m11/work/` 233 エントリ・gitignore)。測定後 `git worktree remove --force work/wt_verify` で後始末する。
- 鮮度 (§6 形式): `git diff 5d167ecd 7738ce46 -- tools/m11 tools/shimx --stat` の出力は次のとおり (測定 HEAD `7738ce46`)。

```
 tools/m11/REPORT_SHX-T27.md | 68 +++++++++++++++++++++++++++++++++
 1 file changed, 68 insertions(+)
```

- 上記の後に REPORT 自身を修正した commit (`4ec4dfae`) を積んだ。`git diff 5d167ecd HEAD -- tools/m11 tools/shimx` は `tools/m11/REPORT_SHX-T27.md` のみで、コード差分は 0。
