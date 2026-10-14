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
| x87 関数 45 本への間接到達の有無 (§4) | export・entry の直接 call 閉包には無い。間接 site 368 は静的に決まらない | #154 (PM 判断: §4 の (a)/(b)) |

## 3. 再現

```
FL_WIN64_DIR=<fl-win64 展開先> QFC_PY=<capstone+pefile の python> bash tools/iltools/lift_measure.sh
```

exit 1 が現状の正しい測定結果 (x87 未対応のため)。x87 対応後に PASS すべき条件は functions 11,747 / unsup 0 / unlifted 0。

## 4. x87 の到達範囲 (PM 判断の材料・`tools/iltools/x87_reach.py`)

測定 commit `2735a7ba` (測定後のコード差分 0。本節は docs のみ)。`python3 tools/iltools/x87_reach.py <block24347_PE.bin>` (集計のみ・gate なし)。

| 項目 | 値 |
|---|---|
| [A] .pdata 関数 / f* 命令 / x87 を含む関数 | 11,747 / 1,256 / **45** (lifter の unsup 1,236 と数え方が違う。差 20 は未特定) |
| [B] export 6 本 (.text 内) → 直接 call 閉包 | 835 関数 / x87 関数 **0** / x87 命令 **0** |
| [B2] entry point 0x2b35f0 → 直接 call 閉包 | 31 関数 / x87 関数 0 |
| [C] 閉包内の間接 call/jmp | 368 site (248 関数)。静的には追えない |
| [D] DIR64 reloc が関数先頭を指す (関数ポインタ・VMT 候補) | 5,785 関数 / うち x87 関数 **0** |
| [E] code 内の rip 相対 `lea` が x87 関数先頭を指す | x87 関数 **41 本** (参照は全て lea)。参照元は **3 関数**で、export 閉包にも entry 閉包にも入らない |

対照: 同じ 6 export を root にした `x64c --closure 50` は functions 824 / unsup 0 / unlifted callees 0 / imports 111。
本測定の閉包 835 との差 11 関数は callee 解決条件の差 (未確認)。

読み:
- x87 命令は export と entry から直接 call では到達しない。x87 関数 45 本のうち、閉包の外の 3 関数からだけアドレスを取られている。
- 間接 call 368 site を通じて届くかは静的には決まらない。届く経路が無いことを示すには runtime か、3 参照元の呼出し元の追跡が要る。
- PM の選択肢 (本 PR では実装しない): (a) 80bit 再現 (softfloat) か 64bit 近似 (§2) を、全 x87 関数に適用する。(b) 直接到達しない x87 関数は、呼ばれたら loud に失敗する trap stub にする。silent に誤った値を返さないための措置。(b) は x64c 側に指定経路が要る。
