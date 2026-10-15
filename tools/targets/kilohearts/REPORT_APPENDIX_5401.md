# REPORT 付録 (#5401 KH-160): Delay の引数過不足 79 件のうち 1 件を機械語で確定し規則化 (部分)

親の受入 (残り 71 件の一括規則化) は 1 run に収まらないため、呼出しを 1 件ずつ確定する (規則 1 件 = 呼出し 1 件・件数 1 を assert)。

**結論**: Delay の emcc 引数数不一致は 79 → **78** (−1)。規則化した 1 件は `FUN_180fd2f20` 内の `FUN_180fe3510()` (C 5129 行)。

**issue 本文との差**: 本文は「残り 71 件」だが、`main` (`06db17776`) の census は 79 件 (`FUN_180fbc1f4` 2 件 (1101・1107) を含む)。`FUN_180fbc1f4` の規則は #4889 (PR #5397・open・main に未取り込み) にあり、本 PR では入れない (重複を避ける)。

**測定 commit**: 本節の規則を含む commit (本 PR の最後のコード変更)。`git diff <測定 commit> HEAD -- tools/targets/kilohearts/ghidra_route` は本 PR 内で 0 行の見込み (commit 後に記録)。
**検証起点** (baseline): origin/main `06db17776`。

**規則 1 件 (`patches.py` の `ABI['delay']`・件数 1 を assert・通過)**

| 呼出元 (VA) | 呼出先 | 機械語の根拠 |
|---|---|---|
| 180fd2f20 (C 5129 行) | `FUN_180fe3510()` (宣言 `void (longlong param_1)`) | 180fd2f2a `mov rdi,rcx` → 180fd2f30 `mov rcx,[rcx+0x90]` → 180fd2f37 `test rcx,rcx` → 180fd2f3c `call 180fe3510`。rcx = `[param_1+0x90]`。callee 入口 `test rcx,rcx`・`[rcx+0x10]` で rcx を読む |

**census (`gtype_census.sh` 相当・FX = `bitcast,intload,stackpair,assoc,concat,gtype,lanes`・n=1)**

| 区分 | `main` 06db17776 | 本 PR |
|---|---|---|
| 128bit レーン型 | 134 | 134 |
| **引数数不一致** | **79** | **78** |
| 演算・代入・ポインタの型不一致 | 90 | 90 |
| 合計 (error 行) | 303 | 302 |

**不変 (受入)**: Gain / Haas / Gate の生成 C と sigs.json は、規則の有無で `cmp` 一致 (差分 0)。

**残件 78 件の内訳 (callee 別・本 run の census)**: `FUN_180fc6870` 17・`FUN_180fc6d70` 16・`FUN_180fdc470` 4・`FUN_180f8791c` 3・`FUN_180fdfdb0` 3・`FUN_180fd0ac8` 3・`FUN_180fbc1f4` 2 (#5397 待ち)・他は 1〜2 件。`FUN_180fc6870`・`FUN_180fc6d70` は SIMD 本体を持つ大きな callee で、引数源の確定に機械語の長い追跡が要る。

**未解決 (起票先付き)**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残り 78 件の規則化 (1 件のみ本 PR) | Delay の emcc 不通過 (wasm 不成立) | #5401 (Refs・残りは親 issue の本文に追記) |
| `FUN_180fbc1f4` 2 件 (1101・1107) | #5397 (KH-128) の規則が main 未取り込み | #5397 (open) |
| Delay の数値未検証 | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] |
