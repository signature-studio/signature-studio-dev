# REPORT 付録 (#3800 KH-64): Delay の引数過不足 108 件の ABI 規則 (部分: 22 件を規則化)

親 #3096 の残件。census の正本は `REPORT_APPENDIX_3075.md` §10-7p-3 (引数数不一致 108)。本付録が本件の正本: §10-7u。

#### 10-7u. #3800 (KH-64) 1 単位: Delay の引数過不足のうち呼出先 `FUN_180fd4f30` の 22 件を機械語で確定し規則化 (部分・Delay はビルド未通過)

- **既知類型との関係 (DEFECTS.md)**: 該当 ID なし。RetDec 路線の D5 (xmm 引数の欠落) と近縁だが、本件は Ghidra 路線の C 化で**整数引数 (rcx) が呼出元から落ちた**もの。stereo・resonator の ABI 規則 (`REPORT_APPENDIX_3071.md` §10-7r) と同型。
- **結論**: Delay の emcc error は 555 → **533** (−22)。うち引数数不一致は 108 → **86** (−22)。呼出元の機械語 (capstone) で引数の源を確定した 22 件を `patches.py` の `ABI['delay']` に、規則 1 件 = 呼出し 1 件 (件数 1 を assert) で入れた。
  - 受入 1 (108 件の規則化): **部分 (22/108)**。残り 86 件は子 issue に分割 (下表)。
  - 受入 2 (引数数不一致 0 件): **未達** (86 件)。
  - 受入 3 (Gain/Haas/Gate の生成物が変わらない): **達成** (下の cmp)。
  - 受入 4 (repo 外で測定): **達成** (repo 外の作業ディレクトリ。`work/` を作っていない)。
- **数値の扱い**: emcc 通過は値の正しさを示さない。Delay の wasm はまだ成立せず、1000 trial は未実施 (#3073 [KH-41] が担当・open)。
- **測定 commit** (コードを変えた最後の commit): `288494e23`。`git diff 288494e23 HEAD -- tools/targets/kilohearts/ghidra_route` の出力は 0 行 (本節の commit は ghidra_route を変えない)。
- **検証起点** (baseline): `091e4a7b6` (origin/main 取得時点)。`git diff --stat 091e4a7b6 288494e23 -- tools/targets/kilohearts/ghidra_route` = `patches.py` 1 file・30 insertions (commit `9b376531e` 19 行 + `288494e23` 11 行)。
- **環境** (repo 外): 素材 `plugins-kilohearts` の Installer zip → `payload.dat` → `windows.zip` → `winpkg/HeartCore.core_64` (76,642,304 B)。[GHIDRA] 12.1.4 (zip sha256 `ddac49f9…d2db` 一致)・JDK 21 (temurin-21)・[EMSDK]。n=1。
- **decompile**: `DecompEach.java` で 149 関数 (delay・gain・haas・gate・stereo の exports + also の和集合) → **149/149 OK**。
- **再現コマンド** (repo 外の作業コピーで実行): `python3 ghidra_to_c.py <name> <out> <ghidra_out> <core> --fix bitcast,intload,stackpair,assoc,concat` → `emcc -c -ferror-limit=0 -I ghidra_route <name>.c` → `emcc_census.py emcc.log`。

**emcc 件数 (census・排他的。`grep -c error:` と合計が一致)**

| 区分 | `091e4a7b6` (baseline) | `288494e23` (本 PR) |
|---|---|---|
| 未関数化 callee | 6 | 6 |
| 128bit レーン型 | 190 | 190 |
| **引数数不一致** | **108** | **86** |
| 未宣言の SIMD・AVX・swi | 46 | 46 |
| 未宣言の Win API・LOCK・MXCSR | 0 | 0 |
| code 型の間接呼出し | 0 | 0 |
| 未定義 identifier | 17 | 17 |
| 演算・代入・型不一致 | 186 | 186 |
| その他 | 2 | 2 |
| **合計** | **555** | **533** |

- 注: baseline の `code` 間接呼出しは 0 件 (main で解消済み。`REPORT_APPENDIX_3075.md` の 21 件は旧値)。3075 の 577 件との差は、推定 (未検証): decompile 集合 (149 対 151) と main 側の変更による。
- **再集計 (検証 HEAD `f6ff6ec2`・n=1)**: 旧 `emcc.log` は保存していなかったため、同 HEAD の `ghidra_route` で再生成した。手順は `DecompEach` (149/149 OK) → `ghidra_to_c.py delay --fix bitcast,intload,stackpair,assoc,concat` → `emcc -c -ferror-limit=0 -I ghidra_route`。delay の emcc error は **533 件**で、`emcc_census.py` の内訳は上表の `288494e23` 列と一致 (6・190・86・46・0・0・17・186・2)。gain 2・haas 0・gate 20・stereo 12 (`-w` 無し)。
- **引数数不一致 86 件の呼出先** (emcc 行の番号 → 源の呼出し行で callee を特定。1 行に呼出しは複数無し): 33 種。
  - `FUN_180fc6870` 17 件 (too few)・`FUN_180fc6d70` 16 件 (too many) → 子 #3844。
  - 残り **53 件 = 呼出先 31 種**: 4 件 1 種 (`FUN_180fdc470`)・3 件 3 種・2 件 13 種・1 件 14 種 (計 4+9+26+14 = 53)。→ 子 #3847 (本文の内訳を本数で訂正)。

**Gain / Haas / Gate / Stereo の不変 (受入 3)**
- 生成 C: `cmp` で baseline と **byte 一致** (gain・haas・gate・stereo の 4 本、差分 0 行)。
- `emcc -c` の `.o`: haas は baseline と sha256 先頭 16 桁 `100df756cea51496` で一致。
- gain (error 2 件)・gate (error 20 件) の emcc は `-w` 無しで baseline から既に error が出る (`build_cmp.sh` は `-w` と `-Wno-error` で通す)。emcc.log は baseline と cmp で同一。本 PR の範囲外。

**追加した規則 22 件 (`patches.py` の `ABI['delay']`・件数はすべて 1 件 (assert 通過))**

| 生成 C の行 (呼出元) | 呼出先 | rcx (第 1 引数) の源 | 機械語の根拠 (呼出元の VA: 設定 → call) |
|---|---|---|---|
| 6939・6942・6945・6948・6951・6954・6957・6960・6963・6966・6969・6972・6975 (`FUN_180fe3690`・13 件) | `FUN_180fd4f30` | `*(param_1 + off)`、off = 0x18・0x20・0x28・0x30・0x38・0x40・0x48・0x68・0x70・0x78・0x80・0x88・0x90 | `mov rcx,[rbx+off]` (180fe36a1 ほか) → `call` (180fe36ae ほか 13 箇所)。`rbx` は 180fe369e の `mov rbx,rcx` (入口の param_1) で、180fe37ae までに書換えなし |
| 6779・6783 (`FUN_180fe3310`・直線部 2 件) | `FUN_180fd4f30` | `*(param_1+0xf0)`・`*(param_1+0xe8)` | 180fe3350 `mov rcx,[rbx+0xf0]` → call 180fe3361。180fe3372 `mov rcx,[rbx+0xe8]` → call 180fe3383。`rbx` は 180fe332b `mov rbx,rcx` |
| 6801・6805 (`FUN_180fe3310`・ループ内 2 件) | `FUN_180fd4f30` | `*puVar6`・`puVar6[-1]` | 180fe3428 `mov rcx,[rdi]` → call 180fe3435。180fe3449 `mov rcx,[rdi-8]` → call 180fe3457。`rdi` は 180fe3417 の `lea rdi,[rbx+0x38]` から 180fe3460 の `add rdi,0x20` まで書換えなし |
| 6990・6993・6996・6999・7002 (`FUN_180fe3cd0`・5 件) | `FUN_180fd4f30` | `*param_1`・`param_1[1]`・`param_1[2]`・`param_1[0xb]`・`param_1[0xc]` | 180fe3cdd `mov rcx,[rcx]` (rcx = 入口の param_1) → call 180fe3ce9。180fe3cee `[rbx+8]`・180fe3d00 `[rbx+0x10]`・180fe3d12 `[rbx+0x58]`・180fe3d24 `[rbx+0x60]` → それぞれ call (3cfb・3d0d・3d1f・3d31)。`rbx` は 180fe3cda `mov rbx,rcx` |

- C 側の条件式 (`if (*(longlong *)(param_1 + 0x18) != _DAT_…)` 等) の添字と、機械語の `off` が 1 対 1 で一致する。C の `if` と呼出しの対応は番地順 = C の行順。

**ネガティブコントロール**: 作業コピーで 13 規則の版 (`9b376531e`) の `0x90` の条件式を `0x91` に壊す → `python3 ghidra_to_c.py delay …` は `AssertionError: ABI rule hit 0: delay 6975 FUN_180fe3690 rcx=[param_1+0x90]` で終了 (**rc=1**)。件数 assert が効くことを確認した。22 規則の最終版では、全規則の件数が 1 であることを生成時に assert で確認 (通過)。

**未解決 (起票先付き)**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 引数数不一致の残り 33 件 (呼出先 `FUN_180fc6870` 17・`FUN_180fc6d70` 16) | Delay の emcc 不通過 (wasm 不成立) | [KH-72] #3844 (本 PR で起票) |
| 引数数不一致の残り 53 件 (呼出先 31 種・stereo と同じ callee 族を含む) | 同上 | [KH-73] #3847 (本 PR で起票) |
| Delay の数値未検証 (1000 trial・ネガコン・第二 oracle) | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] (open・既存) |
| gain (error 2)・gate (error 20) の `-w` 無し emcc error | build_cmp.sh は `-w` で通す。本 PR で変化なし (既存の挙動) | 本 PR の未解決表に残す (WORKFLOW §3: 未解決の追跡だけの項目は子を起票しない。親 #3096 は CLOSED のためコメントでは追えない) |
