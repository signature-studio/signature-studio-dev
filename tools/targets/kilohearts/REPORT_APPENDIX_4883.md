# REPORT 付録 (#4883 KH-127): Delay の引数過不足 10 件のうち 4 件を機械語で確定し規則化 (部分)

親 #4836 (KH-119) の分割 B。census の正本は `REPORT_APPENDIX_3800.md` §10-7u。本付録が本件の正本。

#### 10-7v. #4883 (KH-127): 終端・引数 0 件系の呼出し 10 件のうち 4 件を規則化

- **結論**: Delay の emcc 引数数不一致は 86 → **82** (−4)。規則化した 4 件は `FUN_180fb5c6c` 2 件・`FUN_180fb5f8c` 2 件。残り 6 件 (`FUN_180fb5dd0` 2・`FUN_180fd5bf4` 2・`FUN_180fd8988` 2) は callee の宣言・stack 引数の扱いが要るため子 #4917 (KH-135) に移した。
- **受入 1** (10 件の呼出し元を機械語で確定): **部分 (4/10)**。
- **受入 2** (`ABI['delay']` に規則 1 件 = 呼出し 1 件・件数 1 を assert): **達成** (4 件とも件数 1 で通過)。
- **受入 3** (Gain / Haas / Gate の生成 C と sigs.json が origin/main と `cmp` 0 差分): **達成** (gain・haas・gate の `.c`・`sigs.json`・`globals.json` 計 9 本、差分 0)。
- **受入 4** (残件数を書く): **達成** (下表)。
- **数値の扱い**: emcc 通過は値の正しさを示さない。Delay の wasm は成立せず、1000 trial は未実施 (#3073 [KH-41] が担当・open)。

**測定 commit** (コードを変えた最後の commit): `f787a1c08`。`git diff f787a1c08 HEAD -- tools/targets/kilohearts/ghidra_route` の出力は 0 行 (本節の commit は ghidra_route を変えない)。
**検証起点** (baseline): origin/main `16d1cc7ef`。

**規則 4 件 (`patches.py` の `ABI['delay']`・件数はすべて 1 件)**

| 呼出元 (VA) | 呼出先 | 機械語の根拠 |
|---|---|---|
| 2573 (`FUN_180fb5f8c` 内) | `FUN_180fb5c6c(2,0xc0000417,1)` | 180fb5fac `mov edx,0xc0000417`・180fb5fa6 `mov r8d,1` → 180fb5fb5 `call`。r8 = 1 |
| 5014 (`FUN_180fd2a60` 内) | `FUN_180fb5c6c(3,0x40000015,1)` | 180fd2a9d `mov edx,0x40000015`・180fd2a97 `mov r8d,1` → 180fd2aa6 `call`。r8 = 1 |
| 2521 (`FUN_180fb5e6c` 内・機械語 180fb5f35 の call) | `FUN_180fb5f8c()` (5 引数を落とす) | callee `FUN_180fb5f8c` (180fb5f8c〜) は rcx・rdx・r8・r9 を読まず、`mov ecx,0x17` 等で書換えてから使う。宣言は引数 0 件 |
| 2547 (`FUN_180fb5f5c` 内 180fb5f85 `call`) | `FUN_180fb5f8c()` (5 引数を落とす) | 同上。呼出側 180fb5f7b〜180fb5f83 は全レジスタを 0 にする |

**残件の内訳 (本 run で規則化しなかった 6 件 → 子 #4917 (KH-135))**

| 呼出先 | 件数 | 未確定の理由 |
|---|---|---|
| `FUN_180fb5dd0` (引数 0 件宣言) | 2 (2535・2546) | callee 本体 (180fb5dd0〜) が 5 番目の引数を `[rbp+0x30]` = 呼出側 `[rsp+0x20]` から読む。引数を落とすと意味が変わる (4917 で再判定: 呼出側 2 件の `[rsp+0x20]` = 0 を確定し、呼出側の規則のみ追加。callee 本体の読出し欠落は #5829 で追跡) |
| `FUN_180fd5bf4` (引数 7 件宣言) | 2 (5513・5657) | 呼出元 `FUN_180fd5bcc` (180fd5be9)・`FUN_180fd5f04` (180fd5f24) は stack 上の値を `[rsp+0x20]`・`[rsp+0x28]` に写す。呼出元の宣言が未定 |
| `FUN_180fd8988` (引数 7 件宣言) | 2 (6048・6101) | 呼出元 `FUN_180fd8aac`・`FUN_180fd8bd4` の機械語は未確定 (関数境界が外れている) |

**census (emcc の排他的集計・`emcc_census.py`)**

| 区分 | `16d1cc7ef` (baseline) | `f787a1c08` (本 PR) |
|---|---|---|
| 128bit レーン型 | 167 | 167 |
| **引数数不一致** | **86** | **82** |
| 演算・代入・ポインタの型不一致 | 175 | 175 |
| 合計 | 428 | 424 |

**実測 (n=1)**: `analyzeHeadless` DecompEach (delay の 139 関数) 28.7 s・`ghidra_to_c.py delay` 2.8 s・`emcc -c` 13.9 s。`/proc/loadavg` は計測後 `0.08 0.25 0.28`。

**再現** (作業コピーは gitignore の `tools/targets/kilohearts/work/`): `DecompEach` → `python3 ghidra_to_c.py delay … --fix bitcast,intload,stackpair,assoc,concat` → `emcc -c -ferror-limit=0 -I ghidra_route delay.c` → `python3 ghidra_route/emcc_census.py emcc.log`。
**Gain / Haas / Gate の不変 (受入 3)**: 同じ `ghidra_to_c.py` を origin/main の `patches.py` と本 PR の `patches.py` で実行し、生成物 9 本を `cmp`。差分 0。

**未解決 (起票先付き)**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 引数数不一致の残り 6 件 (`FUN_180fb5dd0` 2・`FUN_180fd5bf4` 2・`FUN_180fd8988` 2) | Delay の emcc 不通過 (wasm 不成立) | #4917 [KH-135] (本 PR で起票) |
| Delay の数値未検証 (1000 trial・ネガコン・第二 oracle) | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] (open・既存) |
