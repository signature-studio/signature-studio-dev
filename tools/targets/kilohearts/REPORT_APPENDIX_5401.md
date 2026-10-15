# REPORT 付録 (#5401 KH-160): Delay の引数過不足 79 件のうち 1 件を機械語で確定し規則化 (部分)

親の受入 (残り件数の一括規則化) は 1 run に収まらないため、呼出しを 1 件ずつ確定する (規則 1 件 = 呼出し 1 件・件数 1 を assert)。

**結論**: Delay の emcc error は 302 → **294** (−8)、引数数不一致は 78 → **76** (−2)。減少分は main 由来の #4889 `FUN_180fbc1f4` 規則 (2 件) による。本 PR の規則 1 件 (`FUN_180fe3510`) は fb4b67659 で 79 → 78 にしている。現 main の census (06db17776 基準の 79) は本 PR の対象外。

**測定 commit**: `463bd7f02` (コードを変えた最後の commit。本 PR の規則を含む `fb4b67659` に main 取り込みを経た commit)。
**鮮度の証跡**: `git diff 463bd7f02 HEAD -- tools/targets/kilohearts/ghidra_route` の結果は **差分 0・行数 0** (検証 HEAD `44bf0eb41` は本付録だけを変える)。
**比較対象**: `fb4b67659` (本 PR の規則を入れた最初の commit) も同じ手順で測定した。
**#4889 (PR #5397) の状態**: merge 済み (`a7b088676`・main に入っている)。本 PR は `FUN_180fbc1f4` の規則を含まない (重複を避ける)。

**規則 1 件 (`patches.py` の `ABI['delay']`・件数 1 を assert・通過)**

| 呼出元 (VA) | 呼出先 | 機械語の根拠 |
|---|---|---|
| 180fd2f20 (C 5129 行) | `FUN_180fe3510()` (宣言 `void (longlong param_1)`) | 180fd2f2a `mov rdi,rcx` → 180fd2f30 `mov rcx,[rcx+0x90]` → 180fd2f37 `test rcx,rcx` → 180fd2f3c `call 180fe3510`。rcx = `[param_1+0x90]`。callee 入口 `test rcx,rcx`・`[rcx+0x10]` で rcx を読む |

**census (`gtype_census.sh`・FX = `bitcast,intload,stackpair,assoc,concat,gtype,lanes`・n=1)**

| 区分 | fb4b67659 (本規則の基準) | 463bd7f02 (現 head 相当・main 取り込み後) |
|---|---|---|
| 128bit レーン型 | 134 | 134 |
| **引数数不一致** | **78** | **76** |
| 演算・代入・ポインタの型不一致 | 90 | 84 |
| 合計 (error 行) | 302 | 294 |

**不変 (受入)**: Gain / Haas / Gate の `.o` は、fb4b67659 の生成物と 463bd7f02 の生成物で `cmp` 一致 (3 本とも差分 0・1435 / 3217 / 3756 B)。`sigs.json` も 3 本とも一致。463bd7f02 の生成 C を `origin/main` の ghidra_route (規則なし) で作った `.o` とも `cmp` 一致 (3 本とも差分 0)。`.c` は冒頭のヘッダ行 (fix 名の列挙) だけが違う。

**残件 (引数数不一致・callee 別・463bd7f02 の 76 件)**: `FUN_180fc6870` 17・`FUN_180fc6d70` 16 が中心で、他は 1〜4 件。`FUN_180fbc1f4` は 0 件になった。`FUN_180fc6870`・`FUN_180fc6d70` は SIMD 本体を持つ大きな callee で、引数源の確定に機械語の長い追跡が要る。

**未解決 (起票先付き)**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残りの引数数不一致 76 件の規則化 (本 PR は 1 件) | Delay の emcc 不通過 (wasm 不成立) | #5401 (Refs・残りは親 issue の本文に追記) |
| Delay の数値未検証 | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] |
