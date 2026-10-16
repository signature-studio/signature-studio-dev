# REPORT 付録 (#5384 KH-158): Delay の stereo ABI 族前半 3 callee (呼出し 6 件) を機械語で確定し規則化

親 #4880 (KH-126) の分割 1。後半 3 callee は #5385。census の正本は `REPORT_APPENDIX_3800.md` §10-7u (引数数不一致の分類)。本付録が本件の正本。

#### 10-7z. #5384 (KH-158): `FUN_180fdc6ec`・`FUN_180fdc844`・`FUN_180fdc858` の呼出し 6 件を規則化

- **結論**: Delay の emcc error は origin/main `8ffe080e6` の 407 → **401** (−6)。引数数不一致は 77 → **71** (−6)。規則化した 6 件は、callee 3 種 × 呼出元 2 箇所 (測定値は現 head `5f52f1368` の再測定。前回の `e959dcd02` 値 409・73 は main 取り込み前のもの)。
- **受入 1** (6 件の呼出元の機械語で引数の源を確定): **達成 (6/6)**。`REPORT_APPENDIX_3071.md` §10-7r と同じ規則 (callee の戻り値を引数と取り違えない・入口 xmm0 の経路を確定) で確認。
- **受入 2** (`ABI['delay']` に規則 1 件 = 呼出し 1 件・件数 1 を assert): **達成** (6 件とも件数 1 で通過。ネガティブコントロールで rc=1)。
- **受入 3** (Gain / Haas / Gate / Stereo の生成 C と sigs.json が origin/main と `cmp` 0 差分): **達成** (現 head `5f52f1368` と origin/main `8ffe080e6` で、gain・haas・gate・stereo の `.c`・`sigs.json`・`globals.json` 計 12 本を `cmp`。差分 0)。
- **受入 4** (残件数を書く): **達成** (下表 census)。
- **数値の扱い**: emcc 通過は値の正しさを示さない。callee の入力 (xmm0 の bit 列) の源を機械語で確定したが、Delay の wasm は全体で未成立のため 1000 trial 突合は未実施 (#3073 [KH-41] が担当・open)。

**測定 commit** (コードを変えた最後の commit): `5f52f1368` (origin/main `8ffe080e6` 取り込み後の HEAD)。`git diff 5f52f1368 HEAD -- tools/targets/kilohearts/ghidra_route` の出力は 0 行 (本節の commit は ghidra_route を変えない)。
**前回の測定 commit**: `e959dcd02` (main 取り込み前)。`git diff e959dcd02 5f52f1368 -- tools/targets/kilohearts/ghidra_route` = `patches.py` 1 file・16 insertions。内訳は main 由来の #4889 (KH-128・`FUN_180fbc1f4` の呼出し 2 件 + 宣言・入力・戻り値の 3 規則) と #5362 (KH-154・`FUN_181384040` のブロック規則 1 件)。delay の emcc error は 409 → 401、census は 73 → 71 に変わった。原因はこの main 由来の規則 (#4889・#5362)。規則別の寄与は未分離。
**同条件の origin/main `8ffe080e6`**: emcc error 407・census 77。`git diff 8ffe080e6 HEAD -- tools/targets/kilohearts/ghidra_route` は本 PR の 6 規則 (11 行) だけなので、main 比の −6 (census 77 → 71) は本 PR の規則による。
**検証起点** (baseline): origin/main `092a9a0e8`。`git diff 092a9a0e8 e959dcd02 -- tools/targets/kilohearts/ghidra_route` = `patches.py` 1 file・11 insertions (規則 6 件 + 注釈)。
**環境** (repo 外・`$RUNNER_TEMP`): 素材 `plugins-kilohearts` の Installer zip → `payload.dat` → `windows.zip` → `winpkg/HeartCore.core_64`。[GHIDRA] 12.1.4 (GitHub Releases `ghidra_12.1.4_PUBLIC_20260921.zip` の sha256 先頭 16 桁 `ddac49f903da9d5b` が REPORT_APPENDIX_3071 の記録と一致)・JDK 21 (temurin-21)・emsdk (`toolchain-emsdk`)。n=1。
**実測 (n=1・現 head `5f52f1368`)**: `analyzeHeadless` DecompEach (lift 集合 151 VA・151 OK) 37.2 s・`ghidra_to_c.py delay --fix bitcast,intload,stackpair,assoc,concat` (rc=0)・`emcc -c -ferror-limit=0` 15.8 s (load 1.33)。Ghidra 12.1.4 は公式 release を sha256 `ddac49f9…` で照合して取得 (repo 外)。

**機械語の確定 (capstone 逆アセンブル・呼出し 6 件)**

callee の入口は `movaps xmm1,xmm0` 等で xmm0 (入力 bit 列) を読む (`180fdc7c2`・`180fdc739`)。`180fdc6ec`・`180fdc844`・`180fdc858` は `r8`・`rdx` を設定して共通本体 (`180fdc7b8`・`180fdc714`) へ `jmp` する thunk。

| 呼出元 (C 行 → 機械語の call) | 呼出先 | 引数の源 (呼出し直前の xmm0) | 根拠 |
|---|---|---|---|
| 3595 → `180fc6b39` (`180fc6870` 内) | `FUN_180fdc6ec` | 入口 float (`fVar3`) | `180fc6897 je 180fc6b39`。`180fc6885 movd edx,xmm0` 以後 `xmm0` 未変更 (`cvtss2sd` 前の入口値)。C 3595 の条件は `_DAT_1822822a0` 比較 (実行時マスク) |
| 3653 → `180fc6d65` (`180fc6b50` 経路) | `FUN_180fdc6ec` | 入口 float (`fVar3`) | `180fc6b61 je 180fc6d65`。`180fc6b50 vmovd eax,xmm0` (読むだけ)・xmm0 未変更 |
| 3785 → `180fc745c` (`180fc6d70` 内) | `FUN_180fdc844` | 入口 float (`fVar22`) | `180fc7121 je 180fc745c`。`180fc7110 vmovd eax,xmm0` (読むだけ) |
| 3909 → `180fc7100` (`180fc6d70` 内) | `FUN_180fdc844` | 入口 float (`fVar22`) | `180fc6d97 je 180fc7100`。`180fc6d85 movd edx,xmm0` 以後 xmm0 未変更 |
| 4042 → `180fccf08` (`180fcce40` 内) | `FUN_180fdc858` | 入口 `param_1` (ABS 前) | `180fcce60 movq rdx,xmm0`・`180fcce65 movaps xmm6,xmm0` で保持。`180fcceff`〜`180fccf08` で xmm0 を書き換えない |
| 4136 → `180fcd3da` (`180fcce40` 内・flag≠0) | `FUN_180fdc858` | 入口 `param_1` (ABS 前) | `180fcd1a7 jae 180fcd3da` は `180fcd1b3 vmovq xmm0,r9` より前に分岐。xmm0 は入口のまま |

- 規則 (`patches.py` の `ABI['delay']`・件数はすべて 1 件): `FUN_180fdc6ec(f2u(fVar3))` 2 件・`FUN_180fdc844(f2u(fVar22))` 2 件 (callee 宣言 `uint`・float 入力の bit 列)、`FUN_180fdc858(d2u(param_1))` 2 件 (callee 宣言 `ulonglong`・double 入力の bit 列)。
- 呼出元の関数 (`FUN_180fc6870`・`FUN_180fc6d70`・`FUN_180fcce40`) の戻り値は、呼出し後の `uVar1`・`uVar25`・`dVar2` に入る。規則は呼出し引数だけを変え、戻り値の使い方は変えない。

**callee の戻り値・多値戻りの扱い**: 3 callee の戻り値は、呼出元で `uVar1` (`ulonglong`)・`uVar25`・`dVar2` に入る。規則は引数の bit 列だけを決め、戻り値の取り方は変えていない (`REPORT_APPENDIX_3071.md` §10-7r の「callee の戻り値を C 化しない」と同じ扱い)。

**census (emcc の排他的集計・`emcc_census.py`)**

| 区分 | `8ffe080e6` (origin/main・比較元) | `5f52f1368` (本 PR・現 head) |
|---|---|---|
| 128bit レーン型 | 166 | 166 |
| **引数数不一致** | **77** | **71** |
| 演算・代入・ポインタの型不一致 | 164 | 164 |
| 合計 | 407 | 401 |

- 注: 同じ DecompEach 出力 (151 関数・151 OK) から、同じ `ghidra_to_c.py` と `emcc` で生成した同条件の実測。`e959dcd02` (main 取り込み前の測定 commit) の値は引数数不一致 73・合計 409・演算型 170。`e959dcd02` → `5f52f1368` の 409 → 401 は、main 由来の #4889 (KH-128) と #5362 (KH-154) の規則 (`patches.py` 16 行) が delay の生成 C を変えたことによる (規則別の寄与は未分離)。`REPORT_APPENDIX_4883.md` の 82 (`f787a1c08` 時点) とは測定条件を揃えていないため直接比べない。

**Gain / Haas / Gate / Stereo の不変 (受入 3)**: 同じ DecompEach 出力から、origin/main `8ffe080e6` と現 head `5f52f1368` の `ghidra_to_c.py` で生成し、`gain`・`haas`・`gate`・`stereo` の `.c`・`sigs.json`・`globals.json` を `cmp`。差分 0 (12 本)。`delay` の `.c` は main と本 PR で変わる (受入 2 の対象)。

**ネガティブコントロール**: 作業コピーで規則 `4136` の正規表現の関数名を 1 字変える (`180fdc858`→`180fdc859`) と、`python3 ghidra_to_c.py delay …` は `AssertionError: ABI rule hit 0: delay 4136 FUN_180fcce40 dVar2 = FUN_180fdc858 (xmm0 = param_1)` で **rc=1**。件数 assert が効くことを確認。

**未解決 (起票先付き)**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 後半 3 callee (`FUN_180fcd400`・`FUN_180fdc700`・`FUN_180fdc6d8`・計 6 件) ※本表は `5f52f1368` 時点。以後 5 件を確定 (4048 含む、#5385 付録 §10-7aa・§10-7ab)。残りは `FUN_180fcd400` の 4060 の 1 件 | stereo 族の残件 | #5385 [KH-159] (#4880 の分割 2・既存・open) |
| 引数数不一致の残り 71 件 (呼出先 `FUN_180fc6870` 17・`FUN_180fc6d70` 16 ほか) | Delay の emcc 不通過 (wasm 不成立) | #3844 [KH-79]・#3847 [KH-73]・#4917 [KH-135] (既存・open) |
| Delay の数値未検証 (1000 trial・ネガコン・第二 oracle) | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] (open・既存) |

注: 本件の 6 件の呼出先 (`FUN_180fdc6ec`・`FUN_180fdc844`・`FUN_180fdc858`) は、#3844 の残件の呼出先 (`FUN_180fc6870`・`FUN_180fc6d70`) とは別の callee。#3844 の残件の数え方は変わらない (`FUN_180fc6870` 17・`FUN_180fc6d70` 16 のまま)。本件は #4880 の子として閉じる。

**残件 71 件の呼出し名 (現 head `5f52f1368` の emcc.log・行番号から集計)**: `FUN_180fc6870` 17・`FUN_180fc6d70` 16・`FUN_180fdc470` 4・`FUN_180f8791c` 3・`FUN_180fdfdb0` 3・`FUN_180fd0ac8` 3・`FUN_180fb5dd0` 2・`FUN_180fcd400` 2 ほか。呼出し名が 25 種 (本件の `FUN_180fdc6ec`・`FUN_180fdc844`・`FUN_180fdc858` は残件から消えた)。
