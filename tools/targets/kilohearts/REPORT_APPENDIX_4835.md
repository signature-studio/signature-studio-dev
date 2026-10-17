# REPORT_APPENDIX_4835 — Delay の引数数不一致の ABI 規則 (KH-118 / #4835)

`ghidra_route/patches.py` の `ABI['delay']` に入れた規則 `delay 2666` (呼出元 `FUN_180fbbfb8` → `FUN_180fbdfcc`) の根拠。
PR #4866 のレビュー指摘 (round 1・round 2) への対応。

## 現状 (`delay 2666` と KH-147 の `delay 4329`)

- 旧版 (`fda9d1c52`) の記録: `delay 2666` 追加のみ。`delay 4329` は当時撤回していた (下の節で再確定)。
- 測定条件: 素材 `plugins-kilohearts` (Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B)・`toolchain-emsdk` (emcc 6.0.12)。`[GHIDRA]` 12.1.4 (zip sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)・JDK 21 (temurin-21)。`gtype_census.sh` を `fda9d1c52` と `0f5bcaa89` (`git archive`) に適用。FX = `bitcast,intload,stackpair,assoc,concat,gtype`・n=1。
- 実測 (`fda9d1c52` = 現 head / `0f5bcaa89` = 基点):

| 項目 | `0f5bcaa89` (基点 = origin/main) | `fda9d1c52` (現 HEAD) |
|---|---|---|
| delay emcc error 行 (合計) | 338 | 337 |
| 引数数不一致 | 80 | 79 |
| レーン型 (128bit) | 167 | 167 |
| 演算・代入・ポインタの型不一致 | 91 | 91 |
| delay 閉包 decompile | 151/151 OK | 151/151 OK |
| `ghidra_to_c.py delay` の `ABI rule hit` | — | assert 通過 (rc=0)・全件 1 |
| Gain / Haas / Gate の `.o` | 1435 / 3217 / 3756 B | 1435 / 3217 / 3756 B |
| Gain / Haas / Gate の生成 C (`cmp`) | 一致 (4643 / 11255 / 15282 B) | 同左 |
| Stereo の生成 C (`cmp`) | 一致 (3867341 B) | 同左 |

- 差分 1 件 (引数数不一致 80→79・合計 338→337) は `delay 2666` (`FUN_180fbbfb8` → `FUN_180fbdfcc`) の効果。
- `delay` 規則は `name == 'delay'` のときだけ適用される。ただし `ABI['stereo']` へは `FUN_180fd4f30(` を呼ぶ `delay` 規則 22 件が合流する (`patches.py` 136 行)。`delay 2666` の置換先は `FUN_180fbdfcc(...)` のため stereo には入らず、Stereo の生成 C は基点と一致 (`cmp`)。
- census の合計は FX (`--fix` の組み合わせ) に依存する。上の値は上記 FX 条件でのみ有効。

## 規則 `delay 2666` の根拠

| 項目 | 内容 |
|---|---|
| 呼出元 | `FUN_180fbbfb8` (生成 C の 2666 行) |
| 呼出先 | `FUN_180fbdfcc` |
| 第 1 引数 (rcx) の源 | 入口の `param_1` |
| 機械語 | `180fbbfdb mov rbx,rcx` → `180fbbfde call 0x180fbdfcc`。直線で rbx 不変 |
| callee 宣言 | `short FUN_180fbdfcc(short *param_1)` (`REPORT_APPENDIX.md` の 138 行。呼出元の機械語は同 142 行) |

## 規則 `delay 4329` (KH-147 で再確定し追加)

- 旧版で一度撤回した `delay 4329` (`FUN_180fcdbfc` → `FUN_180fbde90`) を、callee の生成宣言を引用して再確定した。
- callee 宣言 (Ghidra 12.1.4・DecompEach・`HeartCore.core_64` 76,642,304 B): `short FUN_180fbde90(short *param_1)`。本体は `param_1[3]` を 16bit 単位で読む。
- 呼出元 `FUN_180fcdbfc` の機械語 (`callsite_disasm.py`): `180fcdc1f mov rbx,rcx` → `180fcdc22 call 0x180fbde90`。間に rcx を書く命令は無く、rcx = 入口 `param_1`。
- `scen_qemath.h` の「rcx=double*」は、呼出元の double* を `(short *)` で渡すことと矛盾しない (本体は bit 列として読む)。撤回の理由は解消した。
- 規則: `patches.py` の `ABI['delay']` に `delay 4329 FUN_180fbde90 rcx=param_1 (180fcdc22)` を 1 件 (件数 1 を assert)。

## 測定 (KH-147・測定 commit は本 PR の HEAD)

- 素材: `plugins-kilohearts` (Installer zip → payload → `HeartCore.core_64`)・`toolchain-emsdk`・`[GHIDRA]` 12.1.4 (公式 release zip を取得)・JDK 21。
- FX = `bitcast,intload,stackpair,assoc,concat,gtype`・census は `gtype_census.sh` (repo 外 `$RUNNER_TEMP/kh`)。

| 項目 | origin/main (`50e2f813b`) | 本 PR |
|---|---|---|
| delay emcc error 行 (合計) | 305 | 304 |
| 引数数不一致 | 62 | 61 |
| レーン型 (128bit) | 166 | 166 |
| 演算・代入・ポインタの型不一致 | 77 | 77 |
| delay 閉包 decompile | 151/151 OK | 151/151 OK |
| Gain / Haas / Gate の生成 C・`.o` | `cmp` 0 差分 | 同左 |
| Stereo の生成 C (`cmp`) | 0 差分 (3867384 B) | 同左 |

- 件数 62 → 61 は本規則の効果。Stereo は `FUN_180fbde90` を呼ばないため変わらない。
- 本 issue の対象 27 件のうち規則化済みは 2 件 (`delay 2666`・`delay 4329`)。残り 25 件は未着手。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 本 issue の対象 27 件のうち残り 25 件の ABI 規則 | 引数数不一致が残る | #4835 (本 issue・Refs。残りは呼出し単位で確定する) |
| delay の数値検証 (1000 trial・第二 oracle) | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] |
| delay の数値検証 (1000 trial・第二 oracle) | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] |
