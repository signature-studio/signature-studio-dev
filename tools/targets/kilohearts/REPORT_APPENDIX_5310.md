# REPORT 付録 (#5310 KH-149): Delay の void 宣言の関数の戻り値 (機械語で照合済み)

親 #4686 (KH-109)・上位 #4672 (KH-107)。#4686 が残した Delay の void 戻り値の emcc error 4 件 (issue 本文の行 2121・3968・4329・5001) を、呼出元の機械語で確認する。

## 結論

- 4 件の呼出し直後に読まれる戻り値レジスタは **機械語で確認済み** (下の表・`void_ret_check.sh` の実出力)。4 件とも戻り値を使っている。
- 4329 の呼出先 `FUN_180fd27a8` は、機械語上 `call FUN_180fbde90` の後に rax・ax を書かずに `ret` する。よって呼出元が読む `ax` は `FUN_180fbde90` の戻り値の下位 16 bit である可能性が高い (未確認。`FUN_180fbde90` の戻り値型を機械語で見ていない)。前回の付録の「本体は `return;` で矛盾する」は、この機械語と合わない。
- `FUN_180fe24b8` も同様に、`call FUN_180fe2470` の後に rax を書かずに `ret` する (未確認。`FUN_180fe2470` の生成宣言は repo 内に無い)。
- 本 PR で入れた規則は **`FUN_180fdc880` (3968) の 2 件** (宣言 `double`・`return *param_2;`) のみ。根拠は下の「機械語」節。`FUN_180fbde90`・`FUN_180fe2470` の戻り値型は未確定のため、4329・5001 の規則は入れない (それらの規則は 0 件)。`short`・`ulonglong` は根拠の無い推定だった。emcc は pointer・整数型の不一致を通すので、件数が減っても値の正しさは検証されない。
- 2122 (`FUN_180fc4590`) は未投入。本体の `return;` が 39 件あり、経路ごとの xmm0 を決めてから規則にする。受入 2 の残り・受入 3 は未達 (#5310 Refs)。
- 再確定の条件 (4329・5001 共通): callee の生成宣言行 (`FUN_180fbde90`・`FUN_180fe2470`) を Ghidra 出力から引用し、ret 経路で rax (ax) が戻り値になることを機械語で示す。`HeartCore.core_64` は `fl-win64` 素材に無いため、`plugins-kilohearts` 由来の素材が要る。

## 機械語 (3968 `FUN_180fdc880` の規則の根拠)

- `FUN_180fdc880` の ret (`180fdca0b`) は 1 出口。直前の `movq xmm0,r10`・`mulsd xmm0,[..]`・`movsd [rsi],xmm0` で xmm0 を確定し、ret まで変わらない。
- 呼出元 `180fc7004` は call 直後に `movsd xmm2,xmm0` で xmm0 を読む (戻り値を使う)。

## 測定

- 測定 commit: `a83469d96` (コードを変えた最後の commit。`origin/main` `d1ed6512d` の取り込みと規則 3968 の 2 件を含む)。`git diff a83469d96 HEAD -- tools/targets/kilohearts/ghidra_route` は空 (以後の commit は文書のみ)。
- 基点: `origin/main` `d1ed6512d` (PR が取り込んだ main)。`ghidra_route` は現 `origin/main` `c59316313` と同一。
- 素材: `plugins-kilohearts` (Installer zip → payload.dat → windows.zip/1ccb1df8c8f10745 → `HeartCore.core_64`、76,642,304 B)・`toolchain-emsdk` (emsdk 6.0.12)。Ghidra 12.1.4 は GitHub release `ghidra_12.1.4_PUBLIC_20260921.zip` を取得し sha256 `ddac49f9…d2db` の一致を確認、JDK 21 (temurin-21)。
- 手順: `bash tools/targets/kilohearts/ghidra_route/gtype_census.sh <work>` (既定 FX・`<work>` は `$RUNNER_TEMP` 配下の repo 外)。decompile 151/151 OK、rc 0。HEAD の wall 58.6 s (load は未記録)。

| 対象 | delay emcc error | Gain / Haas / Gate の `.o` |
|---|---|---|
| 基点 `d1ed6512d` | **306** | 1435 / 3217 / 3756 B |
| HEAD `a83469d96` (規則 3968 投入) | **305** | 1435 / 3217 / 3756 B。基点と `cmp` 一致 (3 件とも) |

- 基点と HEAD の emcc error 行の差は 1 行だけ: `operand of type 'void' where arithmetic or pointer type is required` (3968 の `FUN_180fdc880` の void 宣言由来) が HEAD で消えた。増えた行は 0。
- 規則の適用件数: 3968 の 2 規則 (宣言 `double`・`return *param_2;`) は `ghidra_to_c.py` の規則ごとのヒット数 assert (`hit == 1`) を通過し、各 1 件ずつ生成 C に当たった。
- 旧記録 (基点 `749a27433` の 309 → 308。#5862 の規則を含まない時点) は現在の値ではない。

## 素材

- この fix run の `ARTIFACTS_DIR` には `fl-win64`・`plugins-kilohearts`・`toolchain-emsdk` の 3 点が実在した。3 点とも `tar --zstd -xf` で展開して使った。
- `void_ret_check.sh` の実出力 (下の表) は本 fix run で `HeartCore.core_64` に対して再実行し、表と一致した。
- 再現に要る素材: `oc_artifacts: fl-win64 plugins-kilohearts toolchain-emsdk` (PR 本文に記載)。

## 呼出し点の照合 (`void_ret_check.sh` の実出力・本 fix run で再実行)

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

## 再現

```
bash tools/targets/kilohearts/ghidra_route/void_ret_check.sh <HeartCore.core_64>
bash tools/targets/kilohearts/ghidra_route/gtype_census.sh <work>
```
