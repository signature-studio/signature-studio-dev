# REPORT 付録 (#6160 / KH-181): FUN_180fc6870 呼出しの xmm0 源 (受入 1 の一部)

親: #5440 (分割元 #6160)。本付録は受入 1 のうち 0 引数呼出し 1 件の規則と、呼出し 17 件の内訳の確認結果。

## 1. 規則 (`patches.py` の `ABI['delay']`・commit `c4a9461e4`)

- 測定 commit: `c4a9461e4` (コードを変えた最後の commit)。
- 規則: `FUN_1802ed7f0` 内 934〜935 行の `fVar23 = (float)FUN_180fc6870();` (0 引数) を、`*(float *)(*(longlong *)(param_2 + 0x3198) + 0xa8) * 1.5707963705062866f` を引数に渡す形にする。件数 1 を assert。
- 機械語 (`0x1802ed7f0`〜): `1802ed936 movss xmm7,[rcx+0xa8]` (rcx = [param_2+0x3198]、`mov rcx,[rdx+0x3198]` は 1802ed87c・1802ed8c8 で設定) → `1802eda13 mulss xmm7,[0x181563038]` → `1802eda1b movaps xmm0,xmm7` → `1802eda1e call 0x180fc6870`。
- 定数 `[0x181563038]` の float 値は `0x3fc90fdb` = 1.5707963705062866 (π/2) を `HeartCore.core_64` から確認。
- 間の区間 (1802ed936〜eda1e) に xmm7 への書込み・rcx の書換え・call は無い (直線区間)。
- 1802eda2a の `call 0x180fc6d70` の xmm0 = xmm7 (movaps・1802eda27) は変えない。`FUN_180fc6d70` は本規則で変わらない。

## 2. 呼出し 17 件の内訳 (`callref_scan.py` で `call 180fc6870` を列挙)

| 呼出元 | 件数 | 引数 | 機械語での xmm0 源 | 状態 |
|---|---:|---|---|---|
| `FUN_1802ed7f0` 934 行 (1802eda1e) | 1 | 0 | `xmm7` = [param_2+0x3198]+0xa8 の float × π/2 | **本 PR で規則化** (件数 1 assert) |
| `FUN_180289ea0` 内 4 組 (180289fb0〜18028a396) | 16 | 1 | `xmm10`・`xmm11`・`xmm8`・`xmm7` (4 組・各 4 lane) の lane 0〜3 | 機械語で lane 対応を確認した (下表)。C 側は `auVar50._N_4_` のまま。lane を規則化していない |

16 件 (4 組の lane) は、機械語で「各組が V の lane 0〜3 を xmm0 に入れてから call する」形であることまでを確認した。C の印字 `auVar50._0_4_`〜`._12_4_` が同じ lane と対応するかは確認し切っていない。規則化していない。次の run に残す。
注: 16 件は #6210 (KH-184) の census で既に引数数不一致から外れている (C 側は 1 引数で通る)。したがって「引数数不一致 40」には含まれない。残りの 40 件は別の callee。

| 組 | 機械語の lane 作り方 | 呼出し VA |
|---|---|---|
| A (V=xmm10) | `movaps xmm0,V` (lane0)・`movshdup xmm0,V` (lane1)・`movaps xmm0,V; unpckhpd xmm0,V` (lane2)・`shufps V,V,0xff; movaps xmm0,V` (lane3) | 180289fb0・fbe・fd0・fe2 |
| B (V=xmm10) | 同形 | 18028a123・131・143・155 |
| C (V=xmm11) | 同形 | 18028a251・25f・271・283 |
| D (V=xmm7) | 同形 | 18028a369・376・386・396 |

## 3. census (`gtype_census.sh`・既定 FX・基点 `origin/main` `101c61351`・HEAD `c4a9461e4`)

| 測定 | delay emcc error 行 | 引数数不一致 | 型不一致 | lane (V128) |
|---|---:|---:|---:|---:|
| 基点 `101c61351` | 273 | 41 | 67 | 165 |
| HEAD `c4a9461e4` | 272 | 40 | 67 | 165 |

- 差分: 引数数不一致 41 → 40 (-1)・error 行 273 → 272 (-1)。`delay.c:935` の `single argument 'fParam' was not specified` が消えた。他の行は変わらない。
- gain / haas / gate の `.o` は HEAD と基点 (`ghidra_route` を `$RUNNER_TEMP/kh/base_route` に退避したもの) で `cmp` 一致: gain 1435 B・haas 3217 B・gate 3756 B。
- 測定: `gtype_census.sh` 全体 real 47.6 s (HEAD 測定時 load は 1.0 前後・4 vCPU・n=1)。

## 4. 残件

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 16 件 (`FUN_180289ea0` 4 組) の C 側 `auVar50._N_4_` と機械語の lane 対応の確認・規則化 (件数 1 を各 assert) | emcc は通るが数値は未検証 (lane の取り違えの有無は未確認) | #6160 (受入 2) |
| 引数数不一致の残り 40 件 (呼出先 `FUN_180fc6d70` 16 ほか) | Delay の emcc 不通過 (wasm 不成立) | #5440 [KH-163]・#3847 [KH-73] (既存) |
