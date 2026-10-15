# REPORT 付録 (#5362 KH-154): Delay の残件 callee `FUN_181384040` (memmove shim) の pointer⇔整数 引数規則 (部分)

親 #4839 (KH-120) → #3837 (KH-72) の分割。元の受入「残りの callee の pointer⇔整数 規則」のうち、本 PR は `FUN_181384040` の呼出し 6 行だけを扱う。残りは未着手 (5362-6)。

**本 PR 後の残件 (実測)**: 引数の `passing ... to parameter` の error は 78 行 (ソース行 59 箇所)。

#### 5362-1. 結論
- **部分達成**。`FUN_181384040` の呼出し 6 行 (`FUN_18004cf20` 内の 3 箇所・if/else で重複するため 6 行) を規則化した。emcc の error 行は 415 → 409 (−6)。残りの pointer⇔整数 行は本 PR では分類していない (5362-6)。
- 規則の場所: `ghidra_route/patches.py` の `ABI['delay']` (ブロック単位の規則 1 件・件数 1 を assert)。`ghidra_to_c.py` の shim 宣言は変えない (理由は 5362-3)。
- Gain / Haas / Gate の生成 `.o` は baseline と **byte 一致** (1435 B・3217 B・3756 B)。受入 2 を満たす。

#### 5362-2. 環境 (repo 外の runner 一時領域。`work/` は使わない)
- 素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip` → `HeartCore.core_64` (76,642,304 B)。`toolchain-emsdk` → [EMSDK] 6.0.12。
- [GHIDRA] 12.1.4 (`ghidra_12.1.4_PUBLIC_20260921.zip`・sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)。Java は runner 既定の openjdk 17 で `analyzeHeadless` が通った (JDK21 指定の検証はしていない)。
- decompile: `DecompEach.java` で Delay 139 関数・Gain 1 関数・Haas 5 関数・Gate 3 関数 すべて OK。Delay 139 関数の `analyzeHeadless` 実時間は 41.7 s (1 回)。

#### 5362-3. 規則の根拠 (機械語)
`FUN_18004cf20` (vector の再確保と memmove) の逆アセンブル (capstone) で、`call 0x181384040` の直前の引数設定を確認した。

| 呼出元 | 機械語 (逆アセンブル) | 引数の値 |
|---|---|---|
| 18004d008 (else 側 1 本目) | `mov rdx,[rsi]`・`mov r8,r14`・`sub r8,rdx`・`mov rcx,rdi` → `call 0x181384040` | rcx = d = 整数 (rdi = 新 buffer)・rdx = s = 整数 ([rsi] = *param_1) |
| 18004d01a (else 側 2 本目) | `mov r8,[rsi+8]`・`sub r8,r14`・`mov rcx,r15`・`mov rdx,r14` → `call 0x181384040` | rcx = d = 整数 (r15 = rbx+4)・rdx = s = 整数 (param_2) |
| 18004d035 (if 側) | `mov rdx,[rsi]`・`sub r14,rdx`・`mov rcx,rdi`・`mov r8,r14` → `call 0x181384040` | rcx = d = 整数・rdx は shim 呼出し前に rdx が [rsi] へ差し替わるため、s = 整数 |

- 呼出元は d・s をアドレスの整数値 (rcx・rdx) で渡し、Ghidra は `uVar3`・`*param_1`・`lVar4 + 4`・`param_2` を `ulonglong` として出す。`memmove` の shim 宣言は `void*` なので、C の型不一致 (`incompatible integer to pointer conversion`) になる。
- 規則は呼出し側の `(void *)` cast。値は変わらない (整数に入ったアドレスを pointer に戻すだけ)。

#### 5362-4. 測定 (実測・n=1・load は各 run 前後で `uptime`)
- **測定 commit**: 作業ブランチ上の本 PR の commit (下記 5362-6 の hash)。baseline は `origin/main` `fdd9cf1e1`。
- emcc (`emcc -c -ferror-limit=0 -I ghidra_route delay.c`): baseline 15.7 s・error 415 行 → 本 PR 409 行。

| 分類 (`emcc_census.py`) | baseline `fdd9cf1e1` | 本 PR |
|---|---|---|
| 128bit レーン型 | 166 | 166 |
| 引数数不一致 | 79 | 79 |
| 演算・代入・ポインタの型不一致 | 170 | 164 |
| 合計 | 415 | 409 |

- error 行の差分 (文言の sort 比較): 削除 6 行 = `FUN_181384040` の `void *`・`const void *` への `incompatible integer to pointer conversion` のみ。追加 0 行。

#### 5362-5. Gain / Haas / Gate の不変 (受入 2)
同じ `ghidra_to_c.py` (`--fix bitcast,intload,stackpair,assoc,concat`) で baseline と本 PR の生成 C を作り、`emcc -c -O1` で `.o` を作って `cmp`。

| snap-in | `.c` | `.o` (baseline / 本 PR) |
|---|---|---|
| gain (1 関数) | 同一 | 1435 B / 1435 B・**同一** |
| haas (5 関数) | 同一 | 3217 B / 3217 B・**同一** |
| gate (3 関数) | 同一 | 3756 B / 3756 B・**同一** |

- 注: 最初は shim `FUN_181384040` の宣言を整数型へ変えた。Gate も同じ shim を呼ぶため `gate.o` が 3756 → 3769 B に変わった (不変の受入を破る)。そこで shim は変えず、delay の呼出し側だけを `patches.py` の規則にした。

#### 5362-6. 残件と未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| pointer⇔整数 の引数 error の残り (78 件・59 行。`FUN_180fd8aac` 10・`FUN_180fe4020` 10・`FUN_180fd1b34` 4・`FUN_180fd0898` 4・`FUN_180fd2ba0` 4 ほか) | Delay の emcc 不通過 (wasm 不成立) | 親 #5362 のチェックリストに残す (本 PR は `Refs #5362`) |
| `FUN_180fe4020` 系 (10 行) | 同上 | #5361 [KH-153] (open・既存。親 #5362 の分割先) |
| Delay の数値未検証 | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] (open・既存) |
