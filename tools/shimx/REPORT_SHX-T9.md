# tools/shimx REPORT 付録 — SHX-T9 (#177) DllMain closure の SHIMX_TRACE 収集と残一覧

> 本体: `tools/shimx/REPORT.md` §6 (T9)。収集の再現は `tools/m11/shimx_link/e2e.sh` (前提: `tools/m11/m11_e2e.sh` の出力 = `tools/m11/work/`。素材 `oc_artifacts: fl-win64 work-m11 work-liftdiff`)。
> 数値の出典は commit 済みの `tools/m11/shimx_link/results/` (自動生成物)。PR 基点 `e398b2c` (main)。
> 2026-10-13 修正: 差し戻し (reviewer) を受けて、survey の数値を commit 済み results の値に揃えた。

## 1. 結論

- DllMain closure は**未完** (Todo 維持)。逐次起動 (`trace_soft_fix`) は unit #18 の `_UStrAsg` OOB (#232) で止まり、unit 完走 (stage 5/6) は未達。
- SHIMX_TRACE の収集は `results/survey.md` の集計から行った。GetProcAddress miss 65 件 / LoadLibrary 失敗 3 種 / CreateProcess 拒否 0 件。
- survey の unit 160 以降を「harness の range 連鎖 (783 件)」とした前版の記述は、commit 済み results から裏付けられないため取り下げる (§3)。

## 2. 実測 (出典: commit 済み results)

| 項目 | 値 | 出典 |
|---|---|---|
| リンク 5 variant | signature mismatch 0 / undefined 0 / duplicate 0 | `tools/m11/shimx_link/REPORT.md` (前回 run の値。本修正では再測していない) |
| 逐次起動 `trace_soft_fix` | init_count 18 / units_run 17 / threw = memory access out of bounds (#232) | `results/trace_units.md` |
| 逐次起動 `plain_failfast` | init_count 16 / units_run 15 / threw = Aborted (GUI `LoadStringW` の fail-fast) | `results/runs.json` |
| survey 942 unit 全体 | abort 1 / closure_outside 46 / halt0 53 / ok 800 / oob 41 / noproc 1 (合計 942) | `results/survey.md` |

### 2.1 GetProcAddress miss (`results/survey.md` の SHIMX_TRACE 集計, 計 65 件)

ログ行には名前部分が出ていない (`kernel32.dll!` の後が空) ため、DLL 単位で集計する。

| 対象 | 件数 | 初回 unit | 区分 | 扱い |
|---|---|---|---|---|
| kernel32 `#39682` (序数) | 1 | 2 | 序数 | R1 (`shimx_set_intptr_limit` 等 / 敷設 ≥0x10000) |
| kernel32 | 11 | 36 | 非 GUI | 未調査 |
| ntdll.dll | 1 | 18 | 非 GUI | 未調査 |
| ole32 | 6 | 107 | 非 GUI | 未調査 |
| shell32 | 1 | 137 | 非 GUI | 未調査 |
| advapi32 | 1 | 146 | 非 GUI | 未調査 |
| dwmapi | 23 | 146 | GUI 系 | tools/gui |
| user32 | 8 | 146 | GUI 系 | tools/gui |
| comctl32 | 12 | 299 | GUI 系 (common controls) | tools/gui |
| shcore | 1 | 146 | GUI 系 | tools/gui |

- 集計: 非 GUI 20 (kernel32 11 + ntdll 1 + ole32 6 + shell32 1 + advapi32 1) / GUI 系 44 (dwmapi 23 + user32 8 + comctl32 12 + shcore 1) / 序数 1。計 65。
- comctl32 は DLL 名で GUI 系に分類した (common controls は GUI 担当の領域)。ログに名前が出ていないため、個々の API 名での分類は未確認。
- R3 (lifttab) で kernel32 UI 言語 3 名と shell32 序数 9 名はトークン解決済み (`[shimx] lifttab:` 行で確認)。

### 2.2 LoadLibrary 失敗

| DLL | 初回 unit | 扱い |
|---|---|---|
| Msctf.dll | 104 | R4 (擬似 DLL 登録の要否は未決) |
| avrt | 146 | R4 |
| PowrProf.dll | 146 | R4 |

### 2.3 CreateProcess 拒否 / ShellExecute

`results/survey.md` の SHIMX_TRACE 行に 0 件。ShellExecuteW は survey の API 呼出表にも無い。

### 2.4 fail-fast 到達

- **逐次起動 (`trace_soft_fix`, 17 unit + #18) の shimx 起因 fail-fast: 0**。停止要因は `_UStrAsg` OOB (lift 側の #232)。
- **survey の unit 115**: `[shim] FAIL-FAST: unimplemented Win32 API: EnterCriticalSection (NULL/misaligned)` (`results/survey.md` §fail-fast、`results/stub_usage.md`)。shimx `locks.c` の `cs_of()` が出す fail-fast であり、shimx 起因として数える。R7 (`tools/shimx/REPORT_R1-R8.md`) の既定方針 (NULL は fail-fast のまま) に従う。lift 側ポインタ不正が原因かは未確認。起票先: R7 の既存項目 (新規起票なし)。
- **GUI 系**: `plain_failfast` は `LoadStringW` の fail-fast で Aborted (`results/runs.json`)。GUI 担当。

## 3. survey の unit 160 以降 (前版の記述を取り下げ)

- 前版の「unit 160 以降 783 件が `_m11_call_unit` の戻り -1 (range)」は、commit 済み results から裏付けられなかった。`results/survey.md` に range 行は無く、`results/stderr_trace_soft_fix.txt` (12 行) にも `SXL_SURVEY` 行は無い。根拠 (実行ログ) を示せない推定値のため、本付録の数値からは除く。
- 942 unit の集計 (§2) は合計 942 で一致する。unit 別の range 判定は results には残っていない。
- 原因の切り分け (`survey_trace.mjs` の trap 後復帰、`m11_call_unit` の戻り値判定) は #773 (SHX-T9b) で扱う。#773 の前提 (range 連鎖の存在) は再測で確認されるまで未確認扱い。

## 4. 残一覧 (BACKLOG 反映用の要約)

| 区分 | 件数 | 起票先 |
|---|---|---|
| DllMain closure 完走 (stage 5/6) | 未達 | #232 (CLOSED・停止点 `_UStrAsg` OOB のみ記録) |
| GetProcAddress 名前空 miss (非 GUI) | 20 | shimx BACKLOG (P1/P2 追加候補) |
| GetProcAddress GUI 系 miss | 44 | tools/gui |
| GetProcAddress 序数 miss (kernel32 `#39682`) | 1 | R1 (intptr 閾値 / 敷設) |
| LoadLibrary 失敗 (Msctf / avrt / PowrProf) | 3 | R4 → #178 系 |
| survey unit 115 の shimx fail-fast (EnterCriticalSection NULL) | 1 | R7 (既存) |
| survey unit 160 以降 (range 連鎖の有無) | 未確認 | #773 |

## 5. 再現性

- 本 PR の修正は素材 (`work-m11` / `work-liftdiff`) が無い環境で行ったため、`e2e.sh` の再実行は**行っていない**。数値はすべて commit 済み results からの引用。
- 再測の前提: `oc_artifacts: fl-win64 work-m11 work-liftdiff` を依頼に付け、`bash tools/m11/m11_e2e.sh` (lift 成果物) を先に通すこと。
