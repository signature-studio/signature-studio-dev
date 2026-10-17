# REPORT_APPENDIX_5361 — FUN_180fe4020 系 10 行の pointer⇔整数 引数規則 (KH-153)

issue #5361 の受入条件の測定正本。親 #4839 の分割 (残り 5 行 FUN_180fd8aac 系は #4839 に残る)。

## 測定条件 (実測・n=1)

- 基点 commit: `origin/main` (`4eaf8315c`)。測定 commit: `b3cdbcebc` (round 3 時点の head。`git diff b3cdbcebc HEAD -- tools/targets/kilohearts/ghidra_route/` は差分 0)。
- 生成フラグ: `--fix bitcast,intload,stackpair,assoc,concat,gtype` (`--fix` を付けない生成は main 側の規則 (#4889 の `FUN_180fbc1f4` 戻り値規則が `concat` 前提) で assert 停止する。基点でも同じ)。
- 素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/*` → `HeartCore.core_64`。すべて repo 外で展開 (`/tmp/opencode/kh153`)。`work/winpkg` は repo 外への symlink。
- Ghidra 12.1.4 (`ghidra_12.1.4_PUBLIC_20260921.zip`・sha256 `ddac49f9…4db`・[GHIDRA])、JDK 21 (`temurin-21`)、emcc 6.0.12 (`emsdk install/activate 6.0.12`・[EMSDK])。
- decompile: `DecompEach.java` で delay の 139 関数、gain/haas/gate の 10 関数 (`run_all.sh` [2] と同じ VA) を すべて `OK` (summary.tsv の status 集計 = OK 139 / 10・失敗 0)。

## 機械語の確認 (呼出元 `FUN_180fe4394`・capstone)

呼出し 10 件の rcx・edx。rbx = 入口 param_1 (`mov rbx,rcx`)。

| call 箇所 | rcx (第 1 引数) | edx (件数) | C の行 (生成 C の `FUN_180fe4394` 内) |
|---|---|---|---|
| 180fe43b6 | rbx+0x00 | 7 | 1 |
| 180fe43c1 | rbx+0x38 | 7 | 2 |
| 180fe43cf | rbx+0x70 | 12 (rbp+5) | 3 |
| 180fe43dd | rbx+0xd0 | 12 | 4 |
| 180fe43ec | rbx+0x130 | 2 (rbp-5) | 5 |
| 180fe441e | rbx+0x160 | 7 | 6 |
| 180fe442c | rbx+0x198 | 7 | 7 |
| 180fe443a | rbx+0x1d0 | 12 | 8 |
| 180fe4448 | rbx+0x230 | 12 | 9 |
| 180fe4457 | rbx+0x290 | 2 | 10 |

- callee `FUN_180fe4020` (`180fe4020.c`): `void FUN_180fe4020(undefined8 *param_1, longlong param_2)`。`puVar1 = param_1 + param_2` の範囲で `FUN_180fd4f30(*param_1)` を回す。第 1 引数は qword 配列の先頭ポインタ、第 2 引数は要素数。
- 呼出元の生成 C は第 1 引数を `longlong` (整数 `param_1 + off`) で渡す。Ghidra が配列先頭ポインタを整数として印字したもの。

## 規則 (1 件ずつ)

ABI 表 `patches.py` の `ABI['delay']` に、呼出し 1 件 = 規則 1 件 (件数 1 を assert) で入れた。ABI 表に入れた理由: 呼出元 (`FUN_180fe4394`) の引数の型と、callee の宣言 (`undefined8 *`) の食い違いを、呼出し側の書換えで解く。`ghidra_to_c.py` の shim 宣言は変えない (gate の `.o` を変えないため)。

| 規則 | 呼出し | 書換え後 |
|---|---|---|
| 1 | 180fe43b6 (n=7) | `FUN_180fe4020((undefined8 *)param_1,7)` |
| 2 | 180fe43c1 (n=7) | `FUN_180fe4020((undefined8 *)(param_1 + 0x38),7)` |
| 3 | 180fe43cf (n=12) | `FUN_180fe4020((undefined8 *)(param_1 + 0x70),0xc)` |
| 4 | 180fe43dd (n=12) | `FUN_180fe4020((undefined8 *)(param_1 + 0xd0),0xc)` |
| 5 | 180fe43ec (n=2) | `FUN_180fe4020((undefined8 *)(param_1 + 0x130),2)` |
| 6 | 180fe441e (n=7) | `FUN_180fe4020((undefined8 *)(param_1 + 0x160),7)` |
| 7 | 180fe442c (n=7) | `FUN_180fe4020((undefined8 *)(param_1 + 0x198),7)` |
| 8 | 180fe443a (n=12) | `FUN_180fe4020((undefined8 *)(param_1 + 0x1d0),0xc)` |
| 9 | 180fe4448 (n=12) | `FUN_180fe4020((undefined8 *)(param_1 + 0x230),0xc)` |
| 10 | 180fe4457 (n=2) | `FUN_180fe4020((undefined8 *)(param_1 + 0x290),2)` |

- 生成 C での検証: `ghidra_to_c.py delay --fix bitcast,intload,stackpair,assoc,concat,gtype` を測定 commit `b3cdbcebc` で実行。10 規則を含む delay の全規則は件数 assert を通過 (exit 0)。`--fix` を付けない生成は、main 側の `FUN_180fbc1f4` 戻り値規則 (`CONCAT44(uVar3,f2u(fVar4))` 前提) で assert 停止した (基点 `4eaf8315c` でも同じ)。

## 測定結果 (基点 `origin/main` = `4eaf8315c`・head = `b3cdbcebc`)

### 1. Gain / Haas / Gate の `.o` (受入 2)

基点と head の生成 C を `emcc -c -w -O1` で `.o` にして `cmp`。

| 名前 | 基点 `.o` | head `.o` | `cmp` |
|---|---|---|---|
| gain | 1,435 B | 1,435 B | 同一 |
| haas | 3,217 B | 3,217 B | 同一 |
| gate | 3,756 B | 3,756 B | 同一 |

### 2. delay の emcc error (既定 flags・`-ferror-limit=0`・`emcc -c -ferror-limit=0 -I<ghidra_route> delay.c`)

error 行は stderr の `error:` 行の数 (`grep -c 'error:'`)。

| 条件 | error 行 | FUN_180fe4020 関連 | int-conversion | incompatible pointer | 所要 (1 回・wall) |
|---|---|---|---|---|---|
| 基点 (`origin/main` `4eaf8315c`) | 301 | 20 | 56 | 51 | 7.6 s |
| head (`b3cdbcebc`) | 291 | 0 | 46 | 51 | 7.4 s |

- 10 件の呼出し (各 2 行 = 20 行) の型エラーが消えた。FUN_180fe4020 系の error は head で 0 件。
- 合計の差分の内訳: 合計は 301 → 291 (−10) だが、FUN_180fe4020 系は −20 なので、それ以外の error は 281 → 291 (**+10**)。増えた 10 行の出所 (カテゴリ) は、この表の計数 (`grep -c`) では切り分けていない。カテゴリ別の再計数 (素材展開 + Ghidra decompile) はこの fix round では行っていないため、出所は未確定。
- head の error 行の内訳 (上位): `member reference base type 'undefined1[6…]'` 106、`'undefined1[1…]'` 32、`incompatible pointer to integer conversion` 27、`too few arguments to function call` 26。delay の emcc 不通過は残る (wasm 不成立は未解決表の通り)。
- 注: 旧表 (`342ec0dcd` 基点 304 → `cf8667a06` 294) は main 取り込み前の値。上表 (基点 `4eaf8315c`・head `b3cdbcebc`) が現行の正本。基点の値が変わった原因は未切り分け。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FUN_180fd8aac 系 5 行 (残り) | delay の emcc 不通過 | #4839 (open・親の残件) |
| delay の emcc error 291 行の残り | wasm 不成立 | #5362 のチェックリスト |
