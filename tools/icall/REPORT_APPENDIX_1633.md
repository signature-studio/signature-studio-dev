# 付録: icall #1633 (ICALL-37) — Fresh Air SlateCore の closure 外 callee で wasm が err になる関数

> 親: #1451 (ICALL-28)。本付録は ICALL-37 の結論を記録する。

## 1. 結論

- 当初の前提 (15 関数とも closure 外 callee で `missing function`) は**不成立**。15 関数のうち `missing function` は 8 行 (callee 5 種 + import 1)、残り 7 行は `native code called abort()` と `memory access out of bounds`。
- 原因: 元の closure (`fa_ranges.txt`・131 関数) の直接 call 閉包は実際には 151 関数で、20 関数が漏れていた。
- 扱い方針は **closure 拡張 (roots への追加)** を採用。`fa_ranges_1633.txt` (151 範囲) で RetDec を再実行し、route を作り直した。stub 化はしない (native 基準を持つ callee を stub で置くと、比較が stub の挙動を測ることになるため)。
- 結果: wasm のみ err **15 → 9**。closure 拡張で 6 関数が 8/8 bit 一致に変わった (§4)。
- 残り 9 件は `native code called abort()` (6)・`memory access out of bounds` (2)・import 未実装 `GetCurrentThreadId` (1)。closure 外 callee 起因ではないため子 issue に切り出す (§4.1)。

## 2. 15 件の内訳 (旧 closure 131 関数の sweep)

測定 commit: `7e665077` (main 取り込み後・コード変更前)。`fa_sweep.sh 8 60` の wasm のみ err 15 件:

| VA | 件数 | wasm のエラー | 分類 |
|---|---|---|---|
| 1803b5500 | 8 | missing function `function_1803b5546` | closure 外 callee |
| 1803fb6f0 | 8 | missing function `function_1803b5546` | closure 外 callee |
| 18040c950 | 8 | missing function `function_18040ca0d` | closure 外 callee |
| 180c8b280 | 2 | memory access out of bounds | 別原因 |
| 180c8b310 | 8 | native code called abort() | 別原因 |
| 180c9d880 | 8 | native code called abort() | 別原因 |
| 180ca1480 | 8 | missing function `function_180ca1651` | closure 外 callee |
| 180da3f80 | 8 | native code called abort() | 別原因 |
| 180da5f20 | 8 | missing function `function_180da6084` | closure 外 callee |
| 180f9e540 | 8 | missing function `GetCurrentThreadId` | import 未実装 |
| 18103fd60 | 8 | native code called abort() | 別原因 |
| 181057b38 | 8 | memory access out of bounds | 別原因 |
| 181057d20 | 8 | missing function `function_181066530` | closure 外 callee |
| 18106632c | 8 | missing function `function_181066530` | closure 外 callee |
| 18106a3ba | 8 | native code called abort() | 別原因 |

## 3. 閉包拡張の内訳

- 旧 closure: `work/fa_ranges.txt` = 131 関数 (`func_map` と同数)。
- 直接 call / 末尾 jmp の推移閉包 (`closure.py --roots <131 関数>`): **151 関数**。差分 20 関数を `tools/icall/fa_ranges_1633.txt` に入れた。
- RetDec の `func_map` (decode 対象) は 131 → 141 件に増えた (+10)。閉包 151 のうち 10 件は拡張後も `func_map` 外 (`1803b5546`・`18040ca0d`・`1808299a6`・`180829caa`・`180c98030`・`180c982ca`・`180c995ac`・`180ca1651`・`180da6084`・`180da6850`)。
- `1803b5546`・`18040ca0d`・`180ca1651`・`180da6084` は `func_map` 外のままで、IR にも route にも無い。それでも `1803b5500`・`1803fb6f0`・`18040c950`・`180da5f20` は bit 一致になった。呼び出し先が実行経路に乗らなかったためと推定するが、未検証。

## 4. 測定 (HEAD `28f99759`、閉包 151 範囲で RetDec 再実行)

測定 commit: `28f99759` (`tools/icall/fa_ranges_1633.txt` を追加した commit。以降のコード変更なし)。

| 項目 | 値 |
|---|---|
| `roundtrip.sh` (freshair-core, 151 範囲) | 40.97 s、load 0.02 |
| `fa_route_build.sh` | 9.64 s |
| `fa_sweep.sh 8 60` | 141 関数、75.1 s、load 0.11 |
| 区分 | bit 一致 53 / native crash・timeout 73 / wasm のみ err 9 / 値の不一致 6 (合計 141) |

旧測定 (`7e665077`・131 関数) との比較: bit 一致 40 → 53、native crash 66 → 73、wasm のみ err 15 → 9、値の不一致 10 → 6。

母数が 131 → 141 に増えたため、区分の増減は「閉包拡張による変化」と「母数増」の両方を含む。

閉包拡張で 8/8 bit 一致になった行 (旧 missing 由来): `1803b5500`・`1803fb6f0`・`18040c950`・`180da5f20`・`181057d20`・`18106632c` (6 件)。
`180ca1480` は missing から `abort` に変わった (wasm_err は 8 のまま)。

### 4.1 残り wasm のみ err 9 件 (子 issue へ)

| VA | 原因 | 件数 |
|---|---|---|
| 180c8b310・180c9d880・180ca1480・180da3f80・18103fd60・18106a3ba | native code called abort() (wasm 側 abort 経路) | 6 |
| 180c8b280・181057b38 | memory access out of bounds (shift 後の memory 外参照) | 2 |
| 180f9e540 | `GetCurrentThreadId` 未実装 (import) | 1 |

これらは closure 外 callee 起因ではない。子 issue で切り分ける: abort 6 件・out of bounds 2 件は #1852 (ICALL-44)。`GetCurrentThreadId` 1 件は #1853 (ICALL-45) で解消 (§4.2)。

### 4.2 #1853 (ICALL-45): GetCurrentThreadId shim

- 原因: `tools/icall/rt/icall_rt.c` に `GetCurrentThreadId` の実装が無く、wasm 側で `missing function` になっていた。
- 対応: 戻り値 `1` の実関数を追加 (native 参照 `tools/ott/native/ott_native.c` の `k_GetCurrentThreadId` と同値)。
- 測定 commit: `927089fb` (コード変更はこの commit のみ)。`fa_sweep.sh 8 60` を HEAD で再実行。

| 項目 | 値 |
|---|---|
| `180f9e540` (`fa_cmp.py --n 8`) | bit 一致 8/8、wasm_err 0 (修正前 wasm_err 8) |
| `fa_sweep.sh 8 60` (141 関数) | real 1m11.185s、load 0.64 (実測) |
| 区分 | bit 一致 55 / native crash・timeout 73 / wasm のみ err 8 / 値の不一致 5 (合計 141) |

§4 (`28f99759`) との比較: wasm のみ err 9 → 8、bit 一致 53 → 55、値の不一致 6 → 5 (`180f9e540` が bit 一致に変わった)。
残りの wasm のみ err 8 件は abort 6 件・out of bounds 2 件で、#1852 (ICALL-44) の範囲。

## 5. 再現

```
bash tools/icall/roundtrip.sh "tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64" tools/icall/fa_ranges_1633.txt freshair-core
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_sweep.sh 8 60
```

前提: `work-icall` (`rt_freshair-core` の素材)・`plugins-freshair` (`fetch.sh` 済み)・`toolchain-retdec`・`toolchain-emsdk`。
`libottnative.so` は `tools/ott/work/` に既存 (`fa_cmp.py` が参照)。
