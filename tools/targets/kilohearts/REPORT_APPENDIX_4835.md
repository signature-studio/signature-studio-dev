# REPORT_APPENDIX_4835 — Delay の引数数不一致の ABI 規則 (KH-118 / #4835)

`ghidra_route/patches.py` の `ABI['delay']` に入れた規則 `delay 2666` (呼出元 `FUN_180fbbfb8` → `FUN_180fbdfcc`) の根拠。
PR #4866 のレビュー指摘 (round 1) への対応。

## 測定の範囲と再現性

- **測定 commit (実装時の 2 規則版)**: `cb6c1937c`。検証起点 (baseline): `e1071546e`。
- **差分 0 の証跡 (2 規則版)**: `git diff cb6c1937c HEAD -- tools/targets/kilohearts/ghidra_route` の出力は空 (fix 前)。
- **再現の状況**: round 1 対応の fix run では `plugins-kilohearts` が `$ARTIFACTS_DIR` に無く (`fl-win64.tar.zst` のみ)、Ghidra 出力を再生成できなかった。
  下の census・cmp の数値は実装時の PR 本文の値で、fix run では再現していない (未再現)。
- **fix 後 (1 規則版)**: `delay 4329` を撤回したため、件数は 2 規則版と異なる。1 規則版の census・cmp は未測定。

## 規則 `delay 2666` の根拠

| 項目 | 内容 |
|---|---|
| 呼出元 | `FUN_180fbbfb8` (生成 C の 2666 行) |
| 呼出先 | `FUN_180fbdfcc` |
| 第 1 引数 (rcx) の源 | 入口の `param_1` |
| 機械語 | `180fbbfdb mov rbx,rcx` → `180fbbfde call 0x180fbdfcc`。直線で rbx 不変 |
| callee 宣言 | `short FUN_180fbdfcc(short *param_1)` (`REPORT_APPENDIX.md` §10-7n の Ghidra 出力引用)。`(short *)` と整合 |

## 規則 `delay 4329` を撤回した理由

- 呼出元 `FUN_180fcdbfc` (`180fcdc1f mov rbx,rcx` → `180fcdc22 call 0x180fbde90`) は機械語で rcx = 入口 `param_1` と確認した。
- しかし callee `FUN_180fbde90` の **生成宣言の行が repo 内に無い**。`(short *)` の型は未確定。
- `tools/targets/kilohearts/snapins/harness/scen_qemath.h` の 39 行は `0x180fbde90` を「CRT 分類器 `_dtest` (rcx=double*)」として呼ぶ。この記述が正しければ `(short *)` は誤り。harness 記述の出典は未確認。
- emcc は pointer 型の不一致を警告として通すため件数に出ない。値の正しさを検証できないので、規則は撤回し未確定のまま残す。
- 再確定の条件: `FUN_180fbde90` の生成宣言 (Ghidra 出力の行) を引用できること。この PR の範囲外。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 呼出元 `FUN_180fcdbfc` → `FUN_180fbde90` (4329) の ABI 規則 | 該当呼出しの emcc 引数数不一致が残る。callee の型 (short * / double *) 未確定 | #4835 (本 issue・Refs) |
| 2 規則版の census・cmp・decompile の再現 | 実装時の値は未再現 | #4835 |
| 1 規則版の census・cmp | 未測定 | #4835 |
| Stereo の cmp | stereo の 0 差分は未確認 | #4835 |
| delay の数値検証 (1000 trial・第二 oracle) | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] |
