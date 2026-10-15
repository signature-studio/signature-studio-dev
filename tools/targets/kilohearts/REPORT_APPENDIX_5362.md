# REPORT 付録 (#5362 KH-154): Delay の残件 callee `FUN_181384040` (memmove shim) の pointer⇔整数 引数規則 (部分)

親 #4839 (KH-120) → #3837 (KH-72) の分割。元の受入「残りの callee の pointer⇔整数 規則」のうち、本 PR は `FUN_181384040` の呼出し 6 行だけを扱う。残りは未着手 (5362-6)。

**本 PR 後の残件 (実測)**: 引数の `passing ... to parameter` の error は 78 行 (ソース行 59 箇所)。

#### 5362-1. 結論
- **部分達成**。`FUN_181384040` の呼出し 6 行 (`FUN_18004cf20` 内の 3 箇所・if/else で重複するため 6 行) を規則化した。emcc の error 行は 415 → 409 (−6・`f4c9be58f` 時点)。現 head では 407 (下記 5362-4)。残りの pointer⇔整数 行は本 PR では分類していない (5362-6)。
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

#### 5362-4. 測定 (実測・n=1)
- **測定 HEAD: `aa3b58964`** (main `c3fcf0f97` 取り込み後の現 head。runner で再測定)。`f4c9be58f` からの `ghidra_route` 差分は main 由来の #4889 規則 (`patches.py` 10 行) で、Delay の生成 C を変える (下記)。KH-154 規則 (6 行) は両方に入っている。
- 測定環境: 素材 `plugins-kilohearts` (HeartCore.core_64 76,642,304 B) と `toolchain-emsdk` (emcc 6.0.12)、[GHIDRA] 12.1.4 (sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)、openjdk 17 (runner 既定・`analyzeHeadless` が通った。JDK 21 指定の検証はしていない)。作業領域は runner の `$RUNNER_TEMP` (repo 外)。
- decompile: `DecompEach.java` で Delay 139 関数 (proc + also) すべて OK・Gain/Haas/Gate の 10 関数すべて OK。
- emcc (`emcc -c -ferror-limit=0 -I ghidra_route delay.c`, 現 head `aa3b58964`): 実測 8.0 s・error 行 **407** (`f4c9be58f` の生成 C では 409 (実測 7.7 s)。規則なしの `origin/main` 相当の生成では 415)。
- 測定手順: `FX=bitcast,intload,stackpair,assoc,concat bash ghidra_route/gtype_census.sh <work>` (`<work>` は runner の `$RUNNER_TEMP/kh`) で decompile・C 生成・emcc・`.o` を作り、`emcc` を別途再実行して時間を測った。`gtype_census.sh` の既定 `FX` は `gtype` を含むが、本付録の `.o` と census は `gtype` 無しで揃えている。

| 分類 (`emcc_census.py`) | 規則なし (origin/main 相当) | `f4c9be58f` | 現 head `aa3b58964` |
|---|---|---|---|
| 128bit レーン型 | 166 | 166 | 166 |
| 引数数不一致 | 79 | 79 | 77 |
| 演算・代入・ポインタの型不一致 | 170 | 164 | 164 |
| 合計 | 415 | 409 | 407 |

- error 行の差分 (`f4c9be58f` → 現 head): −2 行 = #4889 規則の `FUN_180fbc1f4` 宣言が `float (float)` に変わり、呼出し 2 件 (1082・1088) の引数数不一致が解消したため (引数数不一致 79 → 77)。`FUN_181384040` の KH-154 規則 (−6 行) は両方に効いている。
- 生成 C の差分 (`f4c9be58f` → 現 head、`diff` 実測): `FUN_180fbc1f4` の宣言 (`undefined8 (undefined8)` → `float (float)`)・本体 (入力・戻り値の変換)・呼出し 2 件 (1081・1087 行付近の `-0.16609640419483185f`・`0.16609640419483185f` の引数付与)。他の差分は無し。
- 現 head の生成 C 同士の比較 (`ghidra_to_c.py delay --fix bitcast,intload,stackpair,assoc,concat`): `gtype` の有無で C が大きく変わるため、比較は同じ fix 集合どうしで行った。

#### 5362-5. Gain / Haas / Gate の不変 (受入 2)
`ghidra_to_c.py --fix bitcast,intload,stackpair,assoc,concat` で、`origin/main` (c3fcf0f97) の `ghidra_route` と現 head (`aa3b58964`) の生成 C から、`emcc -w -O1` (build_cmp.sh の `-Wno-error` 指定付き) で `.o` を作って `cmp`。

| snap-in | `.o` (`origin/main` / 現 head `aa3b58964`) | 生成 C | 判定 |
|---|---|---|---|
| gain (1 関数) | 1435 B / 1435 B | 同一 (`diff`) | **同一** (`cmp`) |
| haas (5 関数) | 3217 B / 3217 B | 同一 (`diff`) | **同一** (`cmp`) |
| gate (3 関数) | 3756 B / 3756 B | 同一 (`diff`) | **同一** (`cmp`) |

注: `origin/main` の `ghidra_route` は KH-154 規則 (本 PR の 6 行) を持たない。gain / haas / gate の生成 C は、KH-154 規則 (`FUN_18004cf20` の memmove 呼出し) と #4889 規則 (`FUN_180fbc1f4`・Delay 専用) のどちらにも当たらないため、両者の生成 C は一致する。

- 注: 最初は shim `FUN_181384040` の宣言を整数型へ変えた。Gate も同じ shim を呼ぶため `gate.o` が 3756 → 3769 B に変わった (不変の受入を破る)。そこで shim は変えず、delay の呼出し側だけを `patches.py` の規則にした。

#### 5362-6. 残件と未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| pointer⇔整数 の引数 error の残り (78 件・59 行。`FUN_180fd8aac` 10・`FUN_180fe4020` 10・`FUN_180fd1b34` 4・`FUN_180fd0898` 4・`FUN_180fd2ba0` 4 ほか) | Delay の emcc 不通過 (wasm 不成立) | 親 #5362 のチェックリストに残す (本 PR は `Refs #5362`) |
| `FUN_180fe4020` 系 (10 行) | 同上 | #5361 [KH-153] (open・既存。親 #5362 の分割先) |
| Delay の数値未検証 | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] (open・既存) |
