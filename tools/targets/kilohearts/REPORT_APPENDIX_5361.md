# REPORT_APPENDIX_5361 — FUN_180fe4020 系 10 行の pointer⇔整数 引数規則 (KH-153)

issue #5361 の受入条件の測定正本。親 #4839 の分割 (残り 5 行 FUN_180fd8aac 系は #4839 に残る)。

## 測定条件 (実測・n=1)

- 基点 commit: `origin/main` (342ec0dcd)。測定 commit: `cf8667a06` (本 PR の規則 10 件を入れた最後の commit)。`--fix bitcast,intload,stackpair,assoc,concat,gtype`。
- 素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/*` → `HeartCore.core_64`。すべて repo 外 (`$RUNNER_TEMP/kh153`)。
- Ghidra 12.1.4 (公式 release `ghidra_12.1.4_PUBLIC_20260921.zip`・repo 外取得)、JDK 21 (Temurin 21.0.12.1)。emcc 6.0.12。
- decompile: `DecompEach.java` で delay の 139 関数 (`ghidra_to_c.py` の `delay` 集合) と gain/haas/gate の 10 関数を `OK` で出力。

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

- 生成 C での検証: `ghidra_to_c.py delay` の実行で 10 規則すべてが件数 1 で当たり、assert 通過 (exit 0)。

## 測定結果

### 1. Gain / Haas / Gate の `.o` (受入 2)

基点 (`origin/main` の `patches.py`) と本 PR の生成 C を `emcc -c -w -O1` で `.o` にして比較。

| 名前 | 基点 `.o` | 本 PR `.o` | `cmp` |
|---|---|---|---|
| gain | 1,435 B | 1,435 B | 同一 |
| haas | 3,217 B | 3,217 B | 同一 |
| gate | 3,756 B | 3,756 B | 同一 |

基準値 (gain 1,435・haas 3,217・gate 3,756) と一致。

### 2. delay の emcc error (既定 flags・REPORT_APPENDIX_5862 と同じ `-ferror-limit=0`)

| 条件 | error 行 | FUN_180fe4020 関連 | int-conversion / pointer 系 | 所要 (1 回) |
|---|---|---|---|---|
| 基点 (`origin/main`) | 304 | 20 | 80 | 11 s |
| 本 PR | 294 | 0 | 70 | 10 s |

- 10 件の呼出し (各 2 行 = 20 行) の型エラーが消えた。他の 10 行 (int-conversion 10 件) も減った。
- 注: `-w -Wno-error=int-conversion` を付けた測定では error 行が 224 のまま変わらなかった (警告扱いで型不一致が error に出ないため)。REPORT の既定 flags (上表) を正とする。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FUN_180fd8aac 系 5 行 (残り) | delay の emcc 不通過 | #4839 (open・親の残件) |
| delay の emcc error 294 行の残り | wasm 不成立 | #5362 のチェックリスト |
