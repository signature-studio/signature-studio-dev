# REPORT 付録 (#5401 KH-160): Delay の引数過不足 79 件のうち 1 件を機械語で確定し規則化 (部分)

親の受入 (残り件数の一括規則化) は 1 run に収まらないため、呼出しを 1 件ずつ確定する (規則 1 件 = 呼出し 1 件・件数 1 を assert)。

**結論**: 現 head `463bd7f02` の Delay の emcc error は 302 → **294** (−8)。引数数不一致は 78 → **76** (−2)。減少分は main 由来の #4889 `FUN_180fbc1f4` 規則 (2 件) による。本 PR の規則 1 件 (`FUN_180fe3510`) は fb4b67659 で 79 → 78 にしている。

**測定 commit**: `463bd7f02` (現 head。コードを変えた最後の commit は `fb4b67659` だが、そこから HEAD までの ghidra_route 差分は main 取り込みの 16 行で、本付録の census はその差分を含む現 head で測定)。
**比較対象**: `fb4b67659` (本 PR の規則を入れた最初の commit) も同じ手順で測定し、302 / 78 を得た (下表の基準列)。
**#4889 (PR #5397) の状態**: merge 済み (`a7b088676`・main に入っている)。本 PR は `FUN_180fbc1f4` の規則を含まない (重複を避ける)。
**現 main の census**: 未測定。本 PR の減少数は現 head の測定値で確定する。

**規則 1 件 (`patches.py` の `ABI['delay']`・件数 1 を assert・通過)**

| 呼出元 (VA) | 呼出先 | 機械語の根拠 |
|---|---|---|
| 180fd2f20 (C 5129 行) | `FUN_180fe3510()` (宣言 `void (longlong param_1)`) | 180fd2f2a `mov rdi,rcx` → 180fd2f30 `mov rcx,[rcx+0x90]` → 180fd2f37 `test rcx,rcx` → 180fd2f3c `call 180fe3510`。rcx = `[param_1+0x90]`。callee 入口 `test rcx,rcx`・`[rcx+0x10]` で rcx を読む |

**census (`gtype_census.sh`・FX = `bitcast,intload,stackpair,assoc,concat,gtype,lanes`・n=1)**

| 区分 | fb4b67659 | 現 head `463bd7f02` |
|---|---|---|
| 128bit レーン型 | 134 | 134 |
| **引数数不一致** | **78** | **76** |
| 演算・代入・ポインタの型不一致 | 90 | 84 |
| 合計 (error 行) | 302 | 294 |

**不変 (受入)**: Gain / Haas / Gate の `.o` は、fb4b67659 の生成物と現 head `463bd7f02` の生成物で `cmp` 一致 (3 本とも差分 0・1435 / 3217 / 3756 B)。`sigs.json` も 3 本とも一致。現 head の生成 C を `origin/main` の ghidra_route (規則なし) で作った `.o` とも `cmp` 一致 (3 本とも差分 0)。`.c` は冒頭のヘッダ行 (fix 名の列挙) だけが違う。

**残件 (引数数不一致・callee 別)**: fb4b67659 の 78 件は `FUN_180fc6870` 17・`FUN_180fc6d70` 16・`FUN_180fdc470` 4・`FUN_180f8791c` 3・`FUN_180fdfdb0` 3・`FUN_180fd0ac8` 3・`FUN_180fbc1f4` 2・他。現 head の 76 件は `FUN_180fbc1f4` が 0 件になり、`FUN_180fc6870` 17・`FUN_180fc6d70` 16 が残る。`FUN_180fc6870`・`FUN_180fc6d70` は SIMD 本体を持つ大きな callee で、引数源の確定に機械語の長い追跡が要る。

**規則 1 件 (`patches.py` の `ABI['delay']`・件数 1 を assert・通過)**

| 呼出元 (VA) | 呼出先 | 機械語の根拠 |
|---|---|---|
| 180fd2f20 (C 5129 行) | `FUN_180fe3510()` (宣言 `void (longlong param_1)`) | 180fd2f2a `mov rdi,rcx` → 180fd2f30 `mov rcx,[rcx+0x90]` → 180fd2f37 `test rcx,rcx` → 180fd2f3c `call 180fe3510`。rcx = `[param_1+0x90]`。callee 入口 `test rcx,rcx`・`[rcx+0x10]` で rcx を読む |

**census (`gtype_census.sh` 相当・FX = `bitcast,intload,stackpair,assoc,concat,gtype,lanes`・n=1)・測定 commit `fb4b67659` の値 (現 head 未測定)**

| 区分 | 基準 (06db17776 の census・前回記録) | fb4b67659 + 本規則 |
|---|---|---|
| 128bit レーン型 | 134 | 134 |
| **引数数不一致** | **79** | **78** |
| 演算・代入・ポインタの型不一致 | 90 | 90 |
| 合計 (error 行) | 303 | 302 |

**不変 (受入)**: Gain / Haas / Gate の生成 C と sigs.json は、規則の有無で `cmp` 一致 (差分 0)。fb4b67659 で測定。現 head は未測定。

**残件 78 件の内訳 (callee 別・fb4b67659 の census・現 head 未測定)**: `FUN_180fc6870` 17・`FUN_180fc6d70` 16・`FUN_180fdc470` 4・`FUN_180f8791c` 3・`FUN_180fdfdb0` 3・`FUN_180fd0ac8` 3・`FUN_180fbc1f4` 2 (main の #4889 規則で解消される見込みだが未測定)・他は 1〜2 件。`FUN_180fc6870`・`FUN_180fc6d70` は SIMD 本体を持つ大きな callee で、引数源の確定に機械語の長い追跡が要る。

**未解決 (起票先付き)**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残り 78 件の規則化 (1 件のみ本 PR) | Delay の emcc 不通過 (wasm 不成立) | #5401 (Refs・残りは親 issue の本文に追記) |
| 現 head の census・cmp の再測定 | main 由来の #4889・#5362 の規則 (16 行) で件数が動く | #5401 (`oc_artifacts: plugins-kilohearts toolchain-emsdk` を指定した次の run) |
| Delay の数値未検証 | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] |
