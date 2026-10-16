# REPORT 付録 (#5310 KH-149): Delay の void 宣言の関数の戻り値 (機械語で照合済み)

親 #4686 (KH-109)・上位 #4672 (KH-107)。#4686 が残した Delay の void 戻り値の emcc error 4 件 (issue 本文の行 2121・3968・4329・5001) を、呼出元の機械語で確認する。

## 結論

- 4 件の呼出し直後に読まれる戻り値レジスタは **機械語で確認済み** (下の表・`void_ret_check.sh` の実出力)。4 件とも戻り値を使っている。
- 4329 の呼出先 `FUN_180fd27a8` は、機械語上 `call FUN_180fbde90` の後に rax・ax を書かずに `ret` する。よって呼出元が読む `ax` は `FUN_180fbde90` の戻り値の下位 16 bit である可能性が高い (未確認。`FUN_180fbde90` の戻り値型を機械語で見ていない)。前回の付録の「本体は `return;` で矛盾する」は、この機械語と合わない。
- emcc error は 4 件とも再現した (既定 FX・`gtype_census.sh`)。
- 本 PR で規則を 2 件入れた (`patches.py` の `ABI['delay']`)。`FUN_180fe24b8` は `ulonglong` (戻り値は `FUN_180fe2470` の rax をそのまま通す)、`FUN_180fd27a8` は `short` (戻り値は `FUN_180fbde90` の ax をそのまま通す)。機械語で `ret` 直前が callee の呼出しと `ret` だけであることを確認した。
- 残り 2 件 (2122 `FUN_180fc4590`・3968 `FUN_180fdc880`) は xmm0 を返す。本体に `return;` と値を返す経路が混在するため、経路ごとの戻り値を決めてから規則にする。受入 2 の残り・3 は未達 (#5310 Refs)。

## 規則投入後の測定 (本 PR)

- 測定 commit: 本 PR の `patches.py` 変更 (規則 2 件) を入れた HEAD。基点 (`ac3d117b5`) では delay emcc error **309**、規則投入後は **307**。
- 消えた行: 4329 (`FUN_180fd27a8`)・5001 (`FUN_180fe24b8`) の 2 件。残った void 関連は 2122・3968 (xmm0 callee 2 件)。
- Gain/Haas/Gate の `.o` を基点と `cmp` で比較: 3 件とも一致 (1435 / 3217 / 3756 B)。
- 規則の件数 (ABI の assert) は 1 件ずつ一致 (`abi_hits == 1`)。

## 測定条件

- 測定 commit: `6c660a18f` (`origin/main`)。本 PR のコード変更は `tools/targets/kilohearts/ghidra_route/void_ret_check.sh` のみ (照合の修正)。`ghidra_to_c.py` と `patches.py` は変えていない。
- 素材: `plugins-kilohearts` → Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B、sha256 先頭 16 桁 `d55ce8b4c0ad7ebe` 一致)。
- `[GHIDRA]` 12.1.4 (zip sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)・JDK 21 (temurin-21)・`[EMSDK]` 6.0.12 (`toolchain-emsdk`)。
- 作業ディレクトリは repo 外 (`$RUNNER_TEMP/kh149`)。`work/` には置いていない。

## 呼出し点の照合 (`void_ret_check.sh` の実出力)

PE の objdump は `call   0x<番地>` の形で出る。前回の照合は `0x` なしの形しか見ておらず、実出力が空だった。本 PR で両方の形を見るように直した。

| issue の行 | 既定 FX の生成 C の行 | 呼出元 → 呼出先 | 呼出し番地 | 呼出し直後に読むレジスタ (実出力) | 判定 |
|---|---|---|---|---|---|
| 2121 | 2122 | `FUN_1802ed790` → `FUN_180fc4590` | `1802ed7c1` | `cvtsd2ss xmm0,xmm0` (xmm0) | 戻り値を使う |
| 3968 | 3968 | `FUN_180fc6d70` → `FUN_180fdc880` | `180fc7004` | `movsd xmm2,xmm0` (xmm0) | 戻り値を使う |
| 4329 | 4329 | `FUN_180fcdbfc` → `FUN_180fd27a8` | `180fcdc2d` | `movzx ecx,ax` (ax) | 戻り値を使う |
| 5001 | 5001 | `FUN_180fd2a60` → `FUN_180fe24b8` | `180fd2a64` | `test rax,rax` (rax) | 戻り値を使う |

- 4329 の呼出先 `FUN_180fd27a8` の機械語 (`180fd27a8`): `movsd [rsp+8],xmm0`・`sub rsp,28`・`lea rcx,[rsp+30]`・`call 180fbde90`・`add rsp,28`・`ret`。戻り値は `FUN_180fbde90` の戻り値 (rax) をそのまま通す。
- 生成 C の宣言 (`void`) と Ghidra の `return;` は、`FUN_180fbde90` の戻り値型が未確定のため出た誤り。
- 2122・3968・5001 の callee 本体の戻り値 (xmm0・rax) は、生成 C の `return` だけでは確定しない (`summary.tsv` の `body_bytes` が 1 で、関数範囲が Ghidra で正しく取れていない)。規則を入れるには機械語での確認が要る。未了。

## 測定値 (既定 FX・`gtype_census.sh`)

- decompile 151/151 OK・所要 42.2 s・load 0.93 (4 vCPU)。
- delay の emcc error 行 **312** (前回 REPORT_APPENDIX_5664 の既定 FX の値 315 と違う。差の原因は未確認)。内訳: 128bit レーン型 166・引数数不一致 62・演算・代入・ポインタの型不一致 84。
- Gain/Haas/Gate の `.o` は **1435 / 3217 / 3756 B** (基準と一致。規則は入れていないため変化なし)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `FUN_180fbde90` の戻り値型 (`FUN_180fd27a8` の戻り値 ax の根拠) | 4329 の規則を決められない | #5310 (Refs) |
| `FUN_180fc4590`・`FUN_180fdc880`・`FUN_180fe24b8` の本体の戻り値 (xmm0・rax) の機械語確認と規則 | 2122・3968・5001 が未解消 | #5310 (Refs) |
| Delay の数値検証 (戻り値の型を変えた後の bit-exact) | emcc 通過だけでは値は言えない | #3073 [KH-41] |

## 再現

```
bash tools/targets/kilohearts/ghidra_route/void_ret_check.sh <HeartCore.core_64>
bash tools/targets/kilohearts/ghidra_route/gtype_census.sh <work>
```
