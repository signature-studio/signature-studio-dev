# REPORT_APPENDIX_4835 — Delay の引数数不一致の ABI 規則 (KH-118 / #4835)

`ghidra_route/patches.py` の `ABI['delay']` に入れた規則 `delay 2666` (呼出元 `FUN_180fbbfb8` → `FUN_180fbdfcc`) の根拠。
PR #4866 のレビュー指摘 (round 1・round 2) への対応。

## 現状 (現 HEAD の規則 = 1 件)

- 規則は `delay 2666` の 1 件のみ。`delay 4329` (`FUN_180fcdbfc` → `FUN_180fbde90`) は撤回済み (下の節)。
- **現 HEAD の emcc census・cmp・decompile・`ABI rule hit 1` は未測定**。理由: 測定に必要な素材 `plugins-kilohearts` と `toolchain-emsdk` が、round 2 の fix run の `$ARTIFACTS_DIR` に無かった (`fl-win64.tar.zst` のみ)。Ghidra 出力を再生成できず、assert の通過も確認していない。
- 再測定の手順: PR 本文の `oc_artifacts: plugins-kilohearts toolchain-emsdk` で素材を取得した run で、下記の 3 項目を `e1071546e` (before) と現 HEAD (after) の両方で測る。
  1. `delay` の emcc census (引数数不一致と合計)
  2. `ghidra_to_c.py delay` の `ABI rule hit 1: delay 2666 ...` が assert を通った出力
  3. Gain / Haas / Gate の生成 C の `cmp` (before と after)

## 旧 2 規則版の数値 (未再現の旧値)

以下は実装時 (測定 commit `cb6c1937c`・2 規則版) の PR 本文の値。**未再現の旧値**で、現 HEAD の値ではない。
round 1 の fix run では素材が無く再現していない。現 HEAD (1 規則版) の数値の代わりに使わない。

- 測定 commit: `cb6c1937c`。検証起点 (baseline): `e1071546e`。
- 素材 (実装時): `plugins-kilohearts` → Installer zip → `payload.dat` → `windows.zip` → `winpkg/HeartCore.core_64` (76,642,304 B)。`[GHIDRA]` 12.1.4 (zip sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)・JDK 21 (temurin-21)・`[EMSDK]` 6.0.12。n=1。
- decompile (`DecompEach.java`): delay 閉包 139 関数 → 139/139 OK。gain・haas・gate の 10 関数 → 10/10 OK。
- emcc 件数 (delay・`emcc -c -ferror-limit=0`・census):

| 区分 | `e1071546e` (baseline) | `cb6c1937c` (2 規則版・旧値) |
|---|---|---|
| 引数数不一致 | 86 | 84 (−2) |
| 合計 | 427 | 425 (−2) |

  注: 本 issue の前提の「555 → 533」は REPORT_APPENDIX_3800 の旧 HEAD (`f6ff6ec2`) の値。現 main は emcc 427 件。
- Gain / Haas / Gate の生成 C (`cmp`): gain・haas・gate ともに 0 差分 (`e1071546e` と `cb6c1937c`)。
- Stereo: `cmp` 未測定 (decompile 集合が揃わなかった)。`delay` の規則は `name == 'delay'` のときだけ適用されるため、Stereo の出力は規則の有無で変わらない想定。実測は未確認。

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
| 現 HEAD (1 規則版) の census・cmp・decompile・`ABI rule hit 1` | 未測定 (素材 `plugins-kilohearts` 不足) | #4835 |
| Stereo の cmp | 未測定 | #4835 |
| delay の数値検証 (1000 trial・第二 oracle) | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] |
