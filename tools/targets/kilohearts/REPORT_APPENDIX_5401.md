# REPORT 付録 (#5401 KH-160): Delay の引数過不足を機械語で確定し規則化 (部分)

親の受入 (残り件数の一括規則化) は 1 run に収まらないため、呼出しを 1 件ずつ確定する (規則 1 件 = 呼出し 1 件・件数 1 を assert)。

**結論**: `ABI['delay']` に規則を 2 件追加 (前 run の `FUN_180fe3510` 1 件・今 run の `FUN_180fe4394` 1 件)。測定 commit `524325f89` で Delay の emcc error は **287** (引数数不一致 **69**)。同じ素材・同じ FX で main (`961b565cb`) は 288 (引数数不一致 70)。Gain / Haas / Gate の `.o` は差 0。

**測定 commit**: `524325f89` (`ghidra_route` を変える最後の commit)。
**比較対象**: `961b565cb` (origin/main・規則追加前)。同じ session で同じ FX・同じ素材で測定。

**今 run の規則 (`patches.py` の `ABI['delay']`・件数 1 を assert・通過)**

| 呼出元 (VA) | 呼出先 | 機械語の根拠 |
|---|---|---|
| 180fe34d3 (C 6887 行・`FUN_180fe34b0` 内) | `FUN_180fe4394(longlong)` | 180fe34b1 の入口 `mov rbx,rcx` で入力 rcx を保持し、180fe34c1〜34cf は rcx を書き換えない。`call 180fe4394` (180fe34d3) の直前の rcx = 入口 param_1。callee 180fe4394 は入口で `test rcx,rcx` し `rbx = rcx` で使う。よって引数は `FUN_180fe34b0` の入力 param_1 |

前 run の規則 (`FUN_180fe3510`・180fd2f3c・rcx = `[param_1+0x90]`) は `524325f89` でも有効 (census の同じ行で通過)。

**census (`gtype_census.sh`・FX = `bitcast,intload,stackpair,assoc,concat,gtype,lanes`・n=1)**

| 区分 | 961b565cb (main・規則追加前) | 524325f89 (測定 commit) |
|---|---|---|
| 128bit レーン型 | 134 | 134 |
| **引数数不一致** | **70** | **69** |
| 演算・代入・ポインタの型不一致 | 84 | 84 |
| 合計 (error 行) | 288 | 287 |

測定の詳細: `analyzeHeadless` DecompEach (lift 集合 151 VA・151 OK) で約 35 s、`gtype_census.sh` 全体 35 s (load 0.66 → 0.72・測定開始時)。素材 `plugins-kilohearts` の Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B、sha256 先頭 16 桁 `d55ce8b4c0ad7ebe`)。Ghidra 12.1.4 は公式 release (`ghidra_12.1.4_PUBLIC_20260921.zip`) を取得し、sha256 先頭 16 桁 `ddac49f903da9d5b` で照合。emsdk = `[EMSDK]`。素材・ツールは repo 外 (`$RUNNER_TEMP/kh`)。

**不変 (受入)**: `gtype_census.sh` の基点 (`origin/main` の ghidra_route を `git archive` で展開) で作った `.o` と、現 HEAD の `.o` を `cmp`。Gain 1435 B・Haas 3217 B・Gate 3756 B とも一致 (差 0)。`FUN_180fe4394` は Gain / Haas / Gate の生成 C に現れない (grep で確認)。

**残件 (引数数不一致・524325f89・emcc.log の呼出し行を callee で集計)**: `FUN_180fc6870` 17・`FUN_180fc6d70` 16・`FUN_180fdc470` 4・`FUN_180f8791c` 3・`FUN_180fdfdb0` 3・`FUN_180fd0ac8` 3・その他 23 件 (callee 1〜2 件ずつ)。`FUN_180fc6870`・`FUN_180fc6d70` は SIMD 本体を持つ大きな callee で、引数源の確定に機械語の長い追跡が要る。

**未解決 (起票先付き)**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残りの引数数不一致 69 件の規則化 (本 PR は 2 件) | Delay の emcc 不通過 (wasm 不成立) | #5401 (Refs・残りは親 issue の本文に追記) |
| 規則 2 件の数値未検証 (emcc 通過だけでは値の正しさは言えない) | 値の正しさは未確認 | #3073 [KH-41] |
