# REPORT 付録 (#5310 KH-149): Delay の void 宣言の関数の戻り値 (機械語で照合済み)

親 #4686 (KH-109)・上位 #4672 (KH-107)。#4686 が残した Delay の void 戻り値の emcc error 4 件 (issue 本文の行 2121・3968・4329・5001) を、呼出元の機械語で確認する。

## 結論

- 4 件の呼出し直後に読まれる戻り値レジスタは **機械語で確認済み** (下の表・`void_ret_check.sh` の実出力)。4 件とも戻り値を使っている。
- 4329 の呼出先 `FUN_180fd27a8` は、機械語上 `call FUN_180fbde90` の後に rax・ax を書かずに `ret` する。よって呼出元が読む `ax` は `FUN_180fbde90` の戻り値の下位 16 bit である可能性が高い (未確認。`FUN_180fbde90` の戻り値型を機械語で見ていない)。前回の付録の「本体は `return;` で矛盾する」は、この機械語と合わない。
- `FUN_180fe24b8` も同様に、`call FUN_180fe2470` の後に rax を書かずに `ret` する (未確認。`FUN_180fe2470` の生成宣言は repo 内に無い)。
- 本 PR では **戻り値型の規則を入れない** (0 件)。`FUN_180fbde90`・`FUN_180fe2470` の生成宣言 (Ghidra 出力の行) を引用できず、戻り値型を機械語で確定できないため。`short`・`ulonglong` は根拠の無い推定だった。emcc は pointer・整数型の不一致を通すので、件数が減っても値の正しさは検証されない。
- 4329・5001 は規則を外し、#5310 に残す。残り 2 件 (2122 `FUN_180fc4590`・3968 `FUN_180fdc880`) は xmm0 を返す。本体に `return;` と値を返す経路が混在するため、経路ごとの戻り値を決めてから規則にする。受入 2 の残り・3 は未達 (#5310 Refs)。
- 再確定の条件 (4329・5001 共通): callee の生成宣言行 (`FUN_180fbde90`・`FUN_180fe2470`) を Ghidra 出力から引用し、ret 経路で rax (ax) が戻り値になることを機械語で示す。`HeartCore.core_64` は `fl-win64` 素材に無いため、`plugins-kilohearts` 由来の素材が要る。

## 測定 (本 PR)

- 測定 commit: 本 PR の最終 commit (規則 0 件・`patches.py` は `ac3d117b5` と同一)。`git diff ac3d117b5 HEAD -- tools/targets/kilohearts/ghidra_route` は空。
- 規則を入れていないため、`patches.py` は基点 (`ac3d117b5`) と同一。delay emcc error は基点の値のまま (4329・5001 は残る)。ただし **本 PR では再測定していない** (素材不足・下の「素材」を参照)。
- 規則変更がないため Gain/Haas/Gate の `.o` も基点と同一と見込むが、これも未測定。

## 素材

- 素材ディレクトリ (`ARTIFACTS_DIR`) には `fl-win64.tar.zst` のみ。`tar --zstd -tf` で `HeartCore.core_64` / `plugins-kilohearts` は見つからなかった。
- そのため `void_ret_check.sh` の実出力 (下の表) は、本 PR で `HeartCore.core_64` に対して再実行していない。表は前回 (#5820・#5841) の確認結果。

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
- 2122・3968・5001 の callee 本体の戻り値 (xmm0・rax) は、生成 C の `return` だけでは確定しない (`summary.tsv` の `body_bytes` が 1 で、関数範囲が Ghidra で正しく取れていない)。規則を入れるには機械語での確認が要る。未了。

## 実測 (KH-149 受入 2・3・4 の再測定)

- 基点: `origin/main` `749a27433` (規則 0 件)。`gtype_census.sh` (既定 FX)・decompile 151/151 OK・delay emcc error **309**・Gain/Haas/Gate `.o` 1435 / 3217 / 3756 B。
- 規則投入 (`FUN_180fdc880` の戻り値 xmm0): delay emcc error **308** (3968 の `void` エラーが消えた)・Gain/Haas/Gate の `.o` は 3 件とも基点と `cmp` 一致。
- 機械語: `FUN_180fdc880` の ret (`180fdca0b`) は 1 出口。直前の `movq xmm0,r10`・`mulsd`・`movsd [rsi],xmm0` で xmm0 を確定し、呼出元 180fc7004 が `movsd xmm2,xmm0` で読む。
- 未規則: `FUN_180fc4590` (2122)。本体の `return;` は 39 件で、経路ごとに xmm0 が違う。経路ごとの決定が要る (未了)。
- 素材: `plugins-kilohearts`・`fl-win64`・`toolchain-emsdk` は `$HOME/artifacts` に実在。Ghidra は公開 release の `ghidra_12.1.4_PUBLIC_20260921.zip` を取得 (sha256 `ddac49f9…d2db` 一致)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `FUN_180fbde90` の戻り値型 (`FUN_180fd27a8` の戻り値 ax の根拠) と `FUN_180fe2470` の戻り値型 (`FUN_180fe24b8` の戻り値 rax の根拠) | 4329・5001 の規則を決められない (規則 0 件) | #5310 (Refs) |
| `FUN_180fc4590`・`FUN_180fdc880` の本体の戻り値 (xmm0) の経路別の決定と規則。`FUN_180fe24b8` の本体の戻り値 (rax) の機械語確認 | 2122・3968・5001 が未解消 | #5310 (Refs) |
| Delay の数値検証 (戻り値の型を変えた後の bit-exact) | emcc 通過だけでは値は言えない | #3073 [KH-41] |
| `HeartCore.core_64` を含む `plugins-kilohearts` 素材の取得 | 上の機械語照合と `void_ret_check.sh`・`gtype_census.sh` の再測定ができない | 依頼 (`oc_artifacts: fl-win64 plugins-kilohearts`) |

## 再現

```
bash tools/targets/kilohearts/ghidra_route/void_ret_check.sh <HeartCore.core_64>
bash tools/targets/kilohearts/ghidra_route/gtype_census.sh <work>
```
