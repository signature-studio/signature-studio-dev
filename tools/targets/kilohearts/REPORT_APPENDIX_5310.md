# REPORT 付録 (#5310 KH-149): Delay の void 宣言の関数の戻り値 (機械語で照合済み)

親 #4686 (KH-109)・上位 #4672 (KH-107)。#4686 が残した Delay の void 戻り値の emcc error 4 件 (issue 本文の行 2121・3968・4329・5001) を、呼出元の機械語で確認する。

## 結論

- 4 件の呼出し直後に読まれる戻り値レジスタは **機械語で確認済み** (下の表・`void_ret_check.sh` の実出力)。4 件とも戻り値を使っている。
- 4329 の呼出先 `FUN_180fd27a8` は、機械語上 `call FUN_180fbde90` の後に rax・ax を書かずに `ret` する。よって呼出元が読む `ax` は `FUN_180fbde90` の戻り値の下位 16 bit である可能性が高い (未確認。`FUN_180fbde90` の戻り値型を機械語で見ていない)。前回の付録の「本体は `return;` で矛盾する」は、この機械語と合わない。
- `FUN_180fe24b8` も同様に、`call FUN_180fe2470` の後に rax を書かずに `ret` する (未確認。`FUN_180fe2470` の生成宣言は repo 内に無い)。
- 本 PR で入れた規則は **`FUN_180fdc880` (3968) の 2 件** (宣言 `double`・`return *param_2;`) のみ。根拠は下の「機械語」節。`FUN_180fbde90`・`FUN_180fe2470` の戻り値型は未確定のため、4329・5001 の規則は入れない (この 2 件は 0 件)。`short`・`ulonglong` は根拠の無い推定だった。emcc は pointer・整数型の不一致を通すので、件数が減っても値の正しさは検証されない。
- 2122 (`FUN_180fc4590`) は未投入。本体の `return;` が 39 件あり、経路ごとの xmm0 を決めてから規則にする。受入 2 の残り・受入 3 は未達 (#5310 Refs)。
- 再確定の条件 (4329・5001 共通): callee の生成宣言行 (`FUN_180fbde90`・`FUN_180fe2470`) を Ghidra 出力から引用し、ret 経路で rax (ax) が戻り値になることを機械語で示す。`HeartCore.core_64` は `fl-win64` 素材に無いため、`plugins-kilohearts` 由来の素材が要る。

## 機械語 (3968 `FUN_180fdc880` の規則の根拠)

- `FUN_180fdc880` の ret (`180fdca0b`) は 1 出口。直前の `movq xmm0,r10`・`mulsd xmm0,[..]`・`movsd [rsi],xmm0` で xmm0 を確定し、ret まで変わらない。
- 呼出元 `180fc7004` は call 直後に `movsd xmm2,xmm0` で xmm0 を読む (戻り値を使う)。

## 測定

- 測定 commit: `f79ef799d` (規則を入れた最後のコード commit)。HEAD `0274d50f0` は REPORT の 1 行修正のみ。`git diff f79ef799d HEAD -- tools/targets/kilohearts/ghidra_route` は空。
- 基点: `origin/main` `749a27433` (規則 0 件)。測定は既定 FX (`gtype_census.sh`)、decompile 151/151 OK。
- 結果 (測定 commit の記録。Gain/Haas/Gate の `.o` は基点と比べた値):
  - delay emcc error: 基点 **309** → 規則投入後 **308** (3968 の `void` エラーが消えた)。
  - Gain/Haas/Gate の `.o` 1435 / 3217 / 3756 B は 3 件とも基点と `cmp` 一致。
- 規則の適用件数は記録していない。「309 → 308」が規則の適用によるものだという根拠は、この記録だけでは確認できない。
- **この fix run では再測定していない**。`ARTIFACTS_DIR` に `plugins-kilohearts` が無く、`HeartCore.core_64` を開けなかったため。上の結果は測定 commit 時点の記録である。

## 素材

- この run の `ARTIFACTS_DIR` には `fl-win64.tar.zst` のみ。`plugins-kilohearts` (`HeartCore.core_64`)・`toolchain-emsdk` は無い。
- そのため `void_ret_check.sh` の実出力 (下の表) は、本 run で `HeartCore.core_64` に対して再実行していない。表は前回 (#5820・#5841) の確認結果。
- 再測定・再照合には `oc_artifacts: fl-win64 plugins-kilohearts toolchain-emsdk` が要る (PR 本文に記載)。

## 呼出し点の照合 (前回の `void_ret_check.sh` 実出力)

PE の objdump は `call   0x<番地>` の形で出る。前回の照合は `0x` なしの形しか見ておらず、実出力が空だった。前回の修正で両方の形を見るようにした。

| issue の行 | 既定 FX の生成 C の行 | 呼出元 → 呼出先 | 呼出し番地 | 呼出し直後に読むレジスタ (実出力) | 判定 |
|---|---|---|---|---|---|
| 2121 | 2122 | `FUN_1802ed790` → `FUN_180fc4590` | `1802ed7c1` | `cvtsd2ss xmm0,xmm0` (xmm0) | 戻り値を使う |
| 3968 | 3968 | `FUN_180fc6d70` → `FUN_180fdc880` | `180fc7004` | `movsd xmm2,xmm0` (xmm0) | 戻り値を使う |
| 4329 | 4329 | `FUN_180fcdbfc` → `FUN_180fd27a8` | `180fcdc2d` | `movzx ecx,ax` (ax) | 戻り値を使う |
| 5001 | 5001 | `FUN_180fd2a60` → `FUN_180fe24b8` | `180fd2a64` | `test rax,rax` (rax) | 戻り値を使う |

- 4329 の呼出先 `FUN_180fd27a8` の機械語 (`180fd27a8`): `movsd [rsp+8],xmm0`・`sub rsp,28`・`lea rcx,[rsp+30]`・`call 180fbde90`・`add rsp,28`・`ret`。戻り値は `FUN_180fbde90` の戻り値 (rax) をそのまま通す。
- 生成 C の宣言 (`void`) と Ghidra の `return;` は、`FUN_180fbde90` の戻り値型が未確定のため出た誤り。
- 2122・3968・5001 の callee 本体の戻り値 (xmm0・rax) は、生成 C の `return` だけでは確定しない (`summary.tsv` の `body_bytes` が 1 で、関数範囲が Ghidra で正しく取れていない)。3968 は上の機械語で確定した。2122・5001 は未了。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `FUN_180fbde90` の戻り値型 (`FUN_180fd27a8` の戻り値 ax の根拠) と `FUN_180fe2470` の戻り値型 (`FUN_180fe24b8` の戻り値 rax の根拠) | 4329・5001 の規則を決められない (規則 0 件) | #5310 (Refs) |
| `FUN_180fc4590` (2122) の本体の戻り値 (xmm0) の経路別の決定と規則。`FUN_180fe24b8` の本体の戻り値 (rax) の機械語確認 | 2122・5001 が未解消 | #5310 (Refs) |
| Delay の数値検証 (戻り値の型を変えた後の bit-exact) | emcc 通過だけでは値は言えない | #3073 [KH-41] |
| 規則 (3968) の適用件数の確認と、本 HEAD での再測定 (309 → 308) | 測定 commit 時点の記録のみ。この run では未確認 | 依頼 (`oc_artifacts: fl-win64 plugins-kilohearts toolchain-emsdk`) |

## 再現

```
bash tools/targets/kilohearts/ghidra_route/void_ret_check.sh <HeartCore.core_64>
bash tools/targets/kilohearts/ghidra_route/gtype_census.sh <work>
```
