# tools/iltools — T-SH-12 (#154): ILTools_x64.dll の x64c lift 測定

## 0. 結論

- **判定: 未達 (lift 未完走)。x87 FPU 命令が x64c に無く、11,747 関数の lift が不合格**。
  QuickFontCache (tools/qfclift, PR #579) と違い、SSSE3 の 3 命令ではなく x87 の算術一式が必要。
- 対象: `block24347_PE.bin` (PE export 名 `ILTools_x64.dll`, ImageBase 0x400000, SizeOfImage 0x394000, .pdata 11,747 関数)。
- よって PR は `Refs #154` (Closes しない)。

## 1. 実測 (lift のみ、検証 HEAD はこの PR の commit)

| 項目 | 値 |
|---|---|
| roots | .pdata 11,747 (export-only 追加 0) |
| lift | functions 11,747 / insns 399,453 / unlifted callees 0 / imports 548 |
| unsupported sites | **1,236** (すべて x87) |
| 所要 | lift 単独 46.4 s、`lift_measure.sh` 全体 47 s (load 0.78 0.58 0.25, nproc 4) |
| 判定 | FAIL (exit 1) |

x87 の内訳 (site 数, 上位): fld 311 / fxch 118 / fstp 117 / fmul 202 / fadd 151 / fst 61 / fsub 21 / fmulp 26 /
faddp 47 / fcompp 36 / fdivp 24 / fabs 27 / fild 15 / fistp 6 / 他 (fldl2e, f2xm1, fscale, fsincos, frndint 各 1 ほか)。

## 2. 未解決 (起票先付き)

| 未解決 | 理由 | 起票先 |
|---|---|---|
| x87 スタック (ST(0)-ST(7)・TOP・タグ・丸め) の lift 方式 | wasm の `long double` は 64bit。80bit 拡張精度を素朴に写すと、丸め・指数域の差で silent miscompile (DEFECTS.md の数値系類型に該当しうる) | #154 (PM 判断: 80bit 再現 (softfloat 自前実装) か、64bit 近似 + 差分検査か) |
| ILTools の boot / 実行 | lift 完走後の別段 | #154 継続 |

## 3. 再現

```
FL_WIN64_DIR=<fl-win64 展開先> QFC_PY=<capstone+pefile の python> bash tools/iltools/lift_measure.sh
```

exit 1 が現状の正しい測定結果 (x87 未対応のため)。x87 対応後に PASS すべき条件は functions 11,747 / unsup 0 / unlifted 0。
