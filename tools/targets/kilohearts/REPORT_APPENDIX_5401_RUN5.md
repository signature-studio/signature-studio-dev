# REPORT 付録 (#5401 KH-160・5 回目): `FUN_180fe5f00` の引数なし呼出し 1 件の規則化

親の受入 (残り件数の一括規則化) は 1 run に収まらないため、呼出しを 1 件ずつ確定する (規則 1 件 = 呼出し 1 件・件数 1 を assert)。

**結論**: `ABI['delay']` に規則を 1 件追加 (`FUN_180fe5f00` の引数なし呼出し 1 件・`FUN_180fd622c` 内 5723 行)。基点 (origin/main `fe48dca85`) の census は引数数不一致 **58**、規則追加後は **57** (−1)。Gain / Haas / Gate の `.o` は基点と `cmp` 一致。

**測定 commit**: 規則を入れた最後の commit (本 PR の `ghidra_route` 変更 commit)。
**比較対象**: `fe48dca85` (origin/main・規則追加前)。同じ session で同じ FX・同じ素材で測定。

**機械語の根拠 (callee `FUN_180fe5f00`)**

- 入口 `180fe5f00` は `mov [rsp+8],ecx` → `ldmxcsr [rsp+8]` で、rcx (ecx) を MXCSR へ書く。宣言は `undefined4 param_1` の 1 引数。
- 呼出元 `FUN_180fd622c` (`180fd622c`) の else 枝 (`180fd626e` `call 180fe5f00`) の直前では、`ecx = uVar2` が `180fd6256`〜`180fd625a` で計算され、`180fd6260`〜`180fd626c` の分岐は ecx を書き換えない。よって引数は `uVar2`。
- 同じ関数の if 枝 (`180fd6283`) は `and ecx,0xffffffbf` の後に呼ぶため `uVar2 & 0xffffffbf` で、生成 C の 5721 行と一致する。

**今 run の規則 (`patches.py` の `ABI['delay']`・件数 1 を assert・通過)**

| 呼出元 (VA・C 行) | 呼出先 | 字句の一意化 |
|---|---|---|
| `FUN_180fd622c` 内 else 枝 (5723 行・180fd626e) | `func_0x000180fe5f00(uVar2)` | `else {` 直後・`return uVar1;` の直前 (他の呼出しは `uVar2 & 0xffffffbf` の if 枝) |

Ghidra は呼出先を `func_0x000180fe5f00` と印字するため、規則の検索語はそれに合わせた (`(?:func_0x000|FUN_)` の両方に当たる)。最初の版は `FUN_180fe5f00` だけを検索して件数 0 で assert 停止したため、この形に直した。

**census (`gtype_census.sh`・FX = `bitcast,intload,stackpair,assoc,concat,gtype,lanes`・n=1)**

| 区分 | fe48dca85 (main・規則追加前) | 本 PR (規則 1 件追加) |
|---|---|---|
| 128bit レーン型 | 134 | 134 |
| **引数数不一致** | **58** | **57** |
| 演算・代入・ポインタの型不一致 | 67 | 67 |
| 合計 (error 行) | 259 | 258 |

測定の詳細: 測定 commit `8d8b49ccf` で `gtype_census.sh` 全体 45.7 s (analyzeHeadless 151 VA 全 OK・load 1.00 (測定終了時))。基点 `fe48dca85` は 57.8 s (load 1.04 (測定終了時))。素材 `plugins-kilohearts` の Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B)。Ghidra 12.1.4 は公式 release (`ghidra_12.1.4_PUBLIC_20260921.zip`) を取得し、sha256 先頭 16 桁 `ddac49f903da9d5b` で照合。emsdk は `[EMSDK]`。素材・ツールは repo 外 (`$RUNNER_TEMP/kh`)。

**不変 (受入)**: 基点 (`git archive origin/main` の ghidra_route を `$RUNNER_TEMP/kh/base` に展開) で作った `.o` と、本 PR の `.o` を `cmp`。Gain 1435 B・Haas 3217 B・Gate 3756 B とも一致 (差 0)。stereo は `ABI['stereo']` が `FUN_180fd4f30(` の規則だけを流用するため、今回の 1 件は stereo に入らない。

**残件**: 引数数不一致 57 件 (測定 commit `8d8b49ccf` の `gtype_census.sh` 出力が正本)。callee 別の内訳は今 run では集計し直さない (`func_0x000` 形式の名前を含めて数え直す必要があるため)。大きい塊は `FUN_180fc6870`・`FUN_180fc6d70` で、#5440 [KH-163] が追う。

**未解決 (起票先付き)**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残りの引数数不一致 57 件の規則化 | Delay の emcc 不通過 (wasm 不成立) | #5401 (Refs・残りは親の本文に追記) / #5440 [KH-163] (`FUN_180fc6870`・`FUN_180fc6d70`) / #3847 [KH-73] |
| 規則 1 件の数値未検証 (emcc 通過だけでは値の正しさは言えない) | 値の正しさは未確認 | #3073 [KH-41] |
