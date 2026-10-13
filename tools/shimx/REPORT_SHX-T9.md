# tools/shimx REPORT 付録 — SHX-T9 (#177) DllMain closure の SHIMX_TRACE 収集と残一覧

> 本体: `tools/shimx/REPORT.md` §6 (T9)。収集の再現は `tools/m11/shimx_link/` (`e2e.sh`)。
> 2026-10-13 / HEAD 基点 `e398b2c` (main) / emcc 6.0.12 (ST のみ・-O0)。

## 1. 結論

- DllMain closure は**未完** (Todo 維持)。逐次起動は unit #18 の `_UStrAsg` OOB (#232) で止まり、unit 完走 (stage 5/6) は未達。
- SHIMX_TRACE の収集は現 HEAD で再測し、GetProcAddress miss / LoadLibrary 失敗 / CreateProcess 拒否の一覧を得た。
- **survey の `range` 連鎖 (unit 160 以降 783 件) は shimx 起因ではなく harness 側の未解決事項** (§3)。survey の ok 数は本付録の採用値に使わない。

## 2. 実測 (現 HEAD, `bash tools/m11/shimx_link/e2e.sh`, 4 分 59 秒, exit 0)

| 項目 | 実測 |
|---|---|
| リンク 5 variant | 全て signature mismatch 0 / undefined 0 / duplicate 0 |
| 逐次起動 (`trace_soft_fix`) | init_count 18 / units_run 17 / threw = memory access out of bounds (#232) |
| 逐次起動 (`plain_failfast`, `trace_failfast_fix`) | init_count 16 / threw = Aborted (fail-fast、GUI `LoadStringW` 段) |
| survey 1〜159 (有効区間) | ok 137 / oob 6 / closure_outside 14 / halt0 2 |
| survey 160〜942 | range 783 (§3 の harness 問題。採用不可) |

### 2.1 GetProcAddress miss (trace 実測, unit 初回)

| 対象 | 件数 | 初回 unit | 扱い |
|---|---|---|---|
| kernel32 `#39682` (Delphi 文字列を序数判定) | 1 | 2 | R1 (`shimx_set_intptr_limit` 等 / 敷設 ≥0x10000) |
| ntdll.dll (名前空) | 1 | 18 | 未調査 |
| kernel32 名前 (空名等) | 10 | 36 | 未調査 |
| ole32 | 6 | 107 | 未調査 |
| dwmapi | 23 | 146 | GUI 系 (tools/gui) |
| user32 | 1 | 146 | GUI 系 |
| shell32 | 1 | 137 | 未調査 |
| advapi32 | 1 | 146 | 未調査 |
| shcore | 1 | 146 | GUI 系 |

R3 (lifttab) で kernel32 UI 言語 3 名と shell32 序数 9 名はトークン解決済み (`[shimx] lifttab:` 行で確認)。

### 2.2 LoadLibrary 失敗

| DLL | 初回 unit | 扱い |
|---|---|---|
| Msctf.dll | 104 | R4 (擬似 DLL 登録の要否は未決) |
| avrt | 146 | R4 |
| PowrProf.dll | 146 | R4 |

### 2.3 CreateProcess 拒否 / ShellExecute

trace 上 0 件。

### 2.4 fail-fast 到達

- 逐次起動の shimx 起因 fail-fast: **0** (停止要因は `_UStrAsg` OOB = lift 側 #232、GUI の `LoadStringW` は GUI 担当)。
- survey 1〜159 の halt0 2 件 (unit 115・unit 145) は shimx の abort ではなく Halt0。unit 115 は R7 (`EnterCriticalSection(NULL)`) の survey 到達点と同じ unit 番号だが、因果は未確認。

## 3. harness 未解決: survey の range 連鎖

- unit 159 (1 始まり) の OOB 後、unit 160 以降が `_m11_call_unit` の戻り -1 (`i >= count` 判定) になる。
- 直接プローブ (boot 後に 157〜160 を順に呼ぶ) では `_m11_unit_va` は一貫した値を返し、テーブルは壊れていない。
- trap 後に `__emscripten_stack_restore(sp0)` を入れた切り分けプローブは、120 秒の timeout 内に結果を出せず結論に至っていない (未完)。
- 次の作業: `survey_trace.mjs` の trap 後復帰手順 (sp0 の取り方) と `m11_call_unit` の戻り値判定を、既存 `m11_survey.mjs` と突き合わせる。起票先: #773 (SHX-T9b)。

## 4. 残一覧 (BACKLOG 反映用の要約)

| 区分 | 件数 | 起票先 |
|---|---|---|
| DllMain closure 完走 (stage 5/6) | 未達 | #232 (load 系 OOB、unit #18) |
| GetProcAddress 名前空 miss (kernel32/ole32/shell32/advapi32/ntdll) | 上記 §2.1 | shimx BACKLOG (P1/P2 追加候補) |
| LoadLibrary 失敗 (Msctf / avrt / PowrProf) | 3 | R4 → #178 系 |
| survey range 連鎖 (harness) | 783 unit | #773 (SHX-T9b) |
| intptr 閾値 (R1) | 1 | shimx 本体 |
