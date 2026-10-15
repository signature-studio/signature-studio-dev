# REPORT 付録 (#5401 KH-160): Delay の引数過不足 79 件のうち 1 件を機械語で確定し規則化 (部分)

親の受入 (残り件数の一括規則化) は 1 run に収まらないため、呼出しを 1 件ずつ確定する (規則 1 件 = 呼出し 1 件・件数 1 を assert)。

**結論**: `ABI['delay']` に規則 1 件 (`FUN_180fe3510`) を追加。現 head `26bc08453` での Delay の emcc error は **288** (引数数不一致 70・lanes 併用)。規則 1 件の寄与は fb4b67659 で 79 → 78 (下表)。main 由来の #4889・#5384 の規則が残りの減少分。

**測定 commit**: `26bc08453` (main 取り込み後の現 head。`tools/targets/kilohearts/ghidra_route` を変える最後の commit)。
**鮮度の証跡**: `git diff 26bc08453 HEAD -- tools/targets/kilohearts/ghidra_route` = 差分 0 (本付録の commit は付録だけを変える)。
**旧測定 (参考)**: `463bd7f02` は main 由来の #5384 規則 6 件 (`patches.py` 11 行) が入る前の commit。同じ FX で 294・76 (旧付録の値)。現 head との差 6・6 は #5384 の規則による。
**比較対象**: `fb4b67659` (本 PR の規則を入れた最初の commit・main 取り込み前)。旧測定の値をそのまま載せる。

**規則 1 件 (`patches.py` の `ABI['delay']`・件数 1 を assert・通過)**

| 呼出元 (VA) | 呼出先 | 機械語の根拠 |
|---|---|---|
| 180fd2f20 (C 5129 行) | `FUN_180fe3510()` (宣言 `void (longlong param_1)`) | 180fd2f2a `mov rdi,rcx` → 180fd2f30 `mov rcx,[rcx+0x90]` → 180fd2f37 `test rcx,rcx` → 180fd2f3c `call 180fe3510`。rcx = `[param_1+0x90]`。callee 入口 `test rcx,rcx`・`[rcx+0x10]` で rcx を読む |

**census (`gtype_census.sh`・FX = `bitcast,intload,stackpair,assoc,concat,gtype,lanes`・n=1)**

| 区分 | fb4b67659 (旧・本規則の基準) | 463bd7f02 (旧・#5384 前) | 26bc08453 (現 head・測定) |
|---|---|---|---|
| 128bit レーン型 | 134 | 134 | 134 |
| **引数数不一致** | **78** | **76** | **70** |
| 演算・代入・ポインタの型不一致 | 90 | 84 | 84 |
| 合計 (error 行) | 302 | 294 | 288 |

**測定の詳細 (26bc08453・n=1)**: `analyzeHeadless` DecompEach (lift 集合 151 VA・151 OK) 約 35〜40 s・`gtype_census.sh` 全体 35 s (load 1.32 → 1.39)。素材 `plugins-kilohearts` の Installer zip → `payload.dat` → `windows.zip` → `HeartCore.core_64` (76,642,304 B)。Ghidra 12.1.4 は公式 release を取得し、zip sha256 先頭 16 桁 `ddac49f903da9d5b` で照合。emsdk = `[EMSDK]` (6.0.12)。素材・ツールは repo 外 (`$RUNNER_TEMP`)。

**不変 (受入)**: Gain / Haas / Gate の `.o` は、現 head の生成 C と、`origin/main` の ghidra_route (規則なし) で作った生成 C とで `cmp` 一致 (3 本とも差分 0・1435 / 3217 / 3756 B)。Gain / Haas / Gate の生成 C (`gain.c`・`haas.c`・`gate.c`) に `FUN_180fe3510` は現れない (grep で確認)。

**残件 (引数数不一致・現 head・emcc.log の生行を呼出先で集計・重複含む)**: `FUN_180fc6870` 17・`FUN_180fc6d70` 16・`FUN_180fdc470` 4・`FUN_180f8791c` 3・`FUN_180fdfdb0` 3・`FUN_180fd0ac8` 3 ほか。census の 70 件とは数え方が違う (生行は 88 行で、呼出先を特定できない行が 16 行)。`FUN_180fc6870`・`FUN_180fc6d70` は SIMD 本体を持つ大きな callee で、引数源の確定に機械語の長い追跡が要る。

**未解決 (起票先付き)**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残りの引数数不一致 70 件の規則化 (本 PR は 1 件) | Delay の emcc 不通過 (wasm 不成立) | #5401 (Refs・残りは親 issue の本文に追記) |
| Delay の数値未検証 | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] |
