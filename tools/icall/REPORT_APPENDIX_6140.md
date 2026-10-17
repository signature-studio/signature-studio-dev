# icall #6140 (ICALL-126): 18105d9fc の unreachable trap の位置と原因

測定 commit: `55c8efb66` (コードを変えた最後の commit)。
測定後に変えたのは本付録だけ。`git diff 55c8efb66 HEAD -- tools/icall` の出力は 0 行。

## 1. 結論

- trap の位置: wasm スタックは `function_18105d9fc` → `L__asm_movss__3_bitcast_invalid` (本体は `unreachable`)。呼び出し元は `oi.flat.ll` の `call i128 @__asm_movss__3(i32 %12)`。
- 原因: **統合由来** (lift 欠落ではない)。native は `bts ecx,0x16; movss xmm0,[rsp+8]; ret`。lift IR の `__asm_movss.3(i32)->i128` は正しい。
  `ir_merge_restored.py` は declare を先頭 chunk で決めて後続 chunk を捨てるため、chunk 間で署名が食い違う `__asm_*` が統合後に型不一致の call になる。LLVM の wasm backend (FixFunctionBitcasts) がそれを `unreachable` の thunk にする。
- 修正: 署名が食い違う `__asm_*` を chunk ごとに `<name>__9000+i` へ付け替える (declare と call の両方)。
- 結果: `18105d9fc` は 0/8 → 8/8。

## 2. 食い違いの実測 (統合前の chunk 0〜3)

署名が chunk 間で違う `__asm_*` は 9 名。宣言と呼び出しの型が合わない箇所は `__asm_movss` 9・`__asm_movss.3` 10・`__asm_movaps` 4・`__asm_movups` 6・`__asm_movaps.2` 1・`__asm_movq` 2・`__asm_movapd` 8 (`rt_freshair-6140`)。

## 3. 測定

| 手順 | 条件 | 結果 | 所要 (real) |
|---|---|---|---|
| `build.sh` (libottnative) | — | OK | 0.4 s |
| `roundtrip.sh` | `CHUNKS=4`・`fa_ranges_4271.txt`・`freshair-6140` | rc 0・`lost 6` (非IAT) | 50.9 s |
| `fa_route_build.sh` (統合・改名あり) | `FA_RT=rt_freshair-6140` | OK・`[merge] chunks 4, defines 164` | 9.6 s |
| `fa_cmp.py 18105d9fc --n 8` | `FA_MAP=rt_freshair-6140/map.json` | match 8 / mismatch 0 / wasm_err 0 | — |
| `fa_cmp.py 181056a4c --n 8` | 同上 | match 8 / mismatch 0 | — |
| `fa_cmp.py 181056aa0 --n 8` | 同上 | match 8 / mismatch 0 | — |
| `fa_cmp.py 180da6e60 --n 8` | 同上 | match 8 / mismatch 0 | — |
| `fa_sweep.sh 8 60` (改名あり) | 142 関数・75 s | bit一致 67 / native crash 71 / wasm のみ err 3 / 値の不一致 1 | 75 s |
| `fa_sweep.sh 8 60` (改名なし) | 同じ chunk・同じ map | bit一致 65 / native crash 71 / wasm のみ err 5 / 値の不一致 1 | 75 s |

改名の前後で判定が変わった関数は 2 件で、どちらも `wasm_err → match`:
`18105b4a4` (unreachable → 一致)・`18105d9fc` (unreachable → 一致)。悪化は 0 件。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `18100cc50` が `unreachable` (wasm_err 8) | sweep の wasm のみ err 3 件のうち 1 件 | 未調査。同じ宣言不一致が原因かは未確認 |
| `181057b38` `180c8b280` が `memory access out of bounds` | sweep の wasm のみ err | 本 issue の範囲外 (既存の記録どおり) |
| `180da4030` が値の不一致 (wasm の xmm0 が 0 でない) | sweep の値の不一致 1 件 | 本 issue の範囲外 |

## 5. 再現

```
bash tools/ott/native/build.sh
PE="tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
CHUNKS=4 bash tools/icall/roundtrip.sh "$PE" tools/icall/fa_ranges_4271.txt freshair-6140
FA_RT=tools/icall/work/rt_freshair-6140 bash tools/icall/fa_route_build.sh
FA_MAP=tools/icall/work/rt_freshair-6140/map.json python3 tools/icall/diff/fa_cmp.py 18105d9fc --n 8
```
