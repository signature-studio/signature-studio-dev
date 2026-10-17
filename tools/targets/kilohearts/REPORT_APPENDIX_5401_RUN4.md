# REPORT 付録 (#5401 KH-160・4 回目): `FUN_180fd0ac8` の呼出し 3 件の規則化

親の受入 (残り件数の一括規則化) は 1 run に収まらないため、呼出しを 1 件ずつ確定する (規則 1 件 = 呼出し 1 件・件数 1 を assert)。
今 run は直前の停止報告の「次の一手」 (`FUN_180fd0ac8` の 3 呼出し) を実施した。同 callee は #3847 [KH-73] の範囲でもあるため、PR 本文の未解決表で重複を明示する。

**結論**: `ABI['delay']` に規則を 3 件追加 (`FUN_180fd0ac8` の呼出し 3 件・4694 / 4727 / 4801 行)。基点 (origin/main `af24091a4`) の census は引数数不一致 **61**、規則追加後は **58** (−3)。Gain / Haas / Gate の `.o` は基点と `cmp` 一致。

**測定 commit**: 規則を入れた最後の commit (本 PR の `ghidra_route` 変更 commit)。
**比較対象**: `af24091a4` (origin/main・規則追加前)。同じ session で同じ FX・同じ素材で測定。

**機械語の根拠 (callee `FUN_180fd0ac8`)**

- 入口 `180fd0ac8` で `mov ebx, ecx` (rcx = param_1 を保持)。rdx・r8 は `lea` で書いてから使い、r9 は読まない。よって呼出し側が渡す rdx・r8・r9 の値は結果に影響しない。
- 宣言 `void FUN_180fd0ac8(undefined4 param_1, undefined8, undefined8, undefined8)` は 4 引数のままにする (宣言は変えない)。呼出し側は `FUN_180fd0ac8(param_1,0,0,0)` と書く。

**今 run の規則 (`patches.py` の `ABI['delay']`・件数 1 を assert・通過)**

| 呼出元 (VA・C 行) | 呼出先 | 字句の一意化 |
|---|---|---|
| `FUN_180fd099c` 内 (C 4694 行・180fd0a06 の経路) | `FUN_180fd0ac8(param_1,0,0,0)` | `piVar3[0x3e] != 0` の if の中 (インデント 6 桁) |
| `FUN_180fd0a64` 内 (C 4727 行・180fd0a88) | `FUN_180fd0ac8(param_1,0,0,0)` | `TerminateProcess(uVar2,param_1);` の直後・`ExitProcess` の前 |
| `FUN_180fd0b50` 内 (C 4801 行) | `FUN_180fd0ac8(param_1,0,0,0)` | if の中 (インデント 4 桁) |

3 件とも字句は `FUN_180fd0ac8(param_1);` で同じため、直前の文脈で 1 件ずつ特定した (`ghidra_to_c.py` の本文ごとの適用で、各規則が 1 関数 1 件ずつ当たることを確認)。

**census (`gtype_census.sh`・FX = `bitcast,intload,stackpair,assoc,concat,gtype,lanes`・n=1)**

| 区分 | af24091a4 (main・規則追加前) | 本 PR (規則 3 件追加) |
|---|---|---|
| 128bit レーン型 | 134 | 134 |
| **引数数不一致** | **61** | **58** |
| 演算・代入・ポインタの型不一致 | 77 | 77 |
| 合計 (error 行) | 272 | 269 |

測定の詳細: `gtype_census.sh` 全体 約 47 s (analyzeHeadless 151 VA 全 OK・load は測定開始時)。素材 `plugins-kilohearts` の Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B)。Ghidra 12.1.4 は公式 release、sha256 先頭 16 桁 `ddac49f903da9d5b` で照合。emsdk は `[EMSDK]` (6.0.12)。素材・ツールは repo 外 (`$RUNNER_TEMP/kh`)。

**不変 (受入)**: `gtype_census.sh` の基点 (`origin/main` の ghidra_route を `git archive` で展開した版) で作った `.o` と、本 PR の `.o` を `cmp`。Gain 1435 B・Haas 3217 B・Gate 3756 B とも「旧規則と一致」。stereo は `ABI['stereo']` が `FUN_180fd4f30(` の規則だけを流用するため、今回の 3 件は stereo に入らない。

**未解決 (起票先付き)**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残りの引数数不一致 58 件 | Delay の emcc 不通過 (wasm 不成立) | #5401 (Refs・残りは親の本文に追記) / #3847 [KH-73] |
| `FUN_180fd0ac8` は #3847 の範囲と重なる | 規則が二重に入る恐れ | #3847 [KH-73] (本 PR で先行・重複は PM が整理) |
| 規則 3 件の数値未検証 (emcc 通過だけでは値の正しさは言えない) | 値の正しさは未確認 | #3073 [KH-41] |
