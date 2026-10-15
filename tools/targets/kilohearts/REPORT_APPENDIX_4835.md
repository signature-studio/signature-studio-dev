# REPORT_APPENDIX_4835 — Delay の引数数不一致の ABI 規則 (KH-118 / #4835)

`ghidra_route/patches.py` の `ABI['delay']` に入れた規則 `delay 2666` (呼出元 `FUN_180fbbfb8` → `FUN_180fbdfcc`) の根拠。
PR #4866 のレビュー指摘 (round 1・round 2) への対応。

## 現状 (現 HEAD の規則 = 1 件)

- 規則は `delay 2666` の 1 件のみ (`ghidra_route/patches.py`)。`delay 4329` (`FUN_180fcdbfc` → `FUN_180fbde90`) は撤回済み (下の節)。
- 測定 commit (コードを変えた最後の commit): `5631f59c2`。測定した HEAD: `6ebc4a30c` (以降は docs のみ)。基点: `e1071546e`。
- `git diff cb6c1937c 6ebc4a30c -- tools/targets/kilohearts/ghidra_route`: `delay 4329` の削除 1 件のみ (`patches.py` 4 行増減)。
- 測定条件: 素材 `plugins-kilohearts` (Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B)・`toolchain-emsdk` (emcc 6.0.12)。`[GHIDRA]` 12.1.4 (公式 zip sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)・JDK 21 (temurin-21)。`gtype_census.sh` を `git archive` で展開した `e1071546e` と `6ebc4a30c` に適用。FX = `bitcast,intload,stackpair,assoc,concat,gtype`・n=1。
- 実測 (round 3 の reviewer run・`oc-review` の測定):

| 項目 | `e1071546e` (before) | `6ebc4a30c` (現 HEAD) |
|---|---|---|
| delay emcc 合計 (error 行) | 348 | 347 |
| 引数数不一致 | 86 | 85 |
| レーン型 / 演算・代入の型不一致 | 167 / 95 | 167 / 95 |
| delay 閉包 decompile | 151/151 OK | 151/151 OK |
| `ghidra_to_c.py delay` の `ABI rule hit 1: delay 2666` | — | assert 通過 (rc=0) |
| Gain / Haas / Gate の `.o` (B) | 1435 / 3217 / 3756 | 同じ (`cmp` 一致) |
| Gain / Haas / Gate の生成 C | — | before と `cmp` 一致 |

- Stereo: `cmp` 未測定。`delay` 規則は `name == 'delay'` のときだけ適用されるため、Stereo の出力は変わらない想定。実測は未確認 (#4835 に残す)。
- census の合計は FX (`--fix` の組み合わせ) に依存する。上の値は上記 FX 条件でのみ有効。

## 規則 `delay 2666` の根拠

| 項目 | 内容 |
|---|---|
| 呼出元 | `FUN_180fbbfb8` (生成 C の 2666 行) |
| 呼出先 | `FUN_180fbdfcc` |
| 第 1 引数 (rcx) の源 | 入口の `param_1` |
| 機械語 | `180fbbfdb mov rbx,rcx` → `180fbbfde call 0x180fbdfcc`。直線で rbx 不変 |
| callee 宣言 | `short FUN_180fbdfcc(short *param_1)` (`REPORT_APPENDIX.md` の 138 行。呼出元の機械語は同 142 行) |

## 規則 `delay 4329` を撤回した理由

- 旧 2 規則版では `delay 4329` (`FUN_180fcdbfc` → `FUN_180fbde90`) を追加していた。
- 呼出元 `FUN_180fcdbfc` の機械語 (`180fcdc1f mov rbx,rcx` → `180fcdc22 call 0x180fbde90`) では rcx = 入口 `param_1` と確認した。
- しかし callee `FUN_180fbde90` の **生成宣言の行が repo 内に無い**。`(short *)` の型は未確定。
- `tools/targets/kilohearts/snapins/harness/scen_qemath.h` の 39 行は `0x180fbde90` を「CRT 分類器 `_dtest` (rcx=double*)」として呼ぶ。この記述が正しければ `(short *)` は誤り。harness 記述の出典は未確認。
- emcc は pointer 型の不一致を警告として通すため件数に出ない。値の正しさを検証できないので、規則は撤回した。
- 再確定の条件: `FUN_180fbde90` の生成宣言 (Ghidra 出力の行) を引用できること。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 呼出元 `FUN_180fcdbfc` → `FUN_180fbde90` (4329) の ABI 規則 | 該当呼出しの emcc 引数数不一致が残る。callee の型 (short * / double *) 未確定 | #4835 (本 issue・Refs) |
| Stereo の cmp | 未測定 (規則は `name == 'delay'` のみのため変化なしの想定) | #4835 |
| delay の数値検証 (1000 trial・第二 oracle) | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] |
