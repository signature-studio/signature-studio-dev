# liftdiff LD-24 (#976) — 署名未対応 (vector/struct) 50 関数の実測と分割

> 正本: `tools/liftdiff/REPORT.md` §12 から派生。親 issue #235 の残り (#976)。
> 本節は REPORT (250 行上限) の分割移動として新設。判定は**未実装** (下記 §3 の分割で子 issue に委譲)。

## 1. 未対応の実態 (TSV 件数は実測、署名内訳は IR 未照合)

m11 closure の判定 `unexec / unsupported_sig` は **50 件** (`results/m11_closure_verdicts.tsv`、`unexec_reason` 列。本 run で件数を確認)。
判定元は `ldlib/cases.py` の `supported_sig()` で、`ok = {i1,i8,i16,i32,i64,ptr,float,double}` 以外の
型 (`i128`・構造体) を含むと弾く。署名は `tools/m11/work/boot_final3.ll` の `define` 行から `ldlib/irtool.parse_sigs` で取得する想定。

**本 run の照合状況**: `tools/m11/work/boot_final3.ll` は本 run に存在せず (`fl-win64` 素材のみ)、下表の署名内訳と 10 行の署名形は**未照合**。
下表は IR を持つ run で再生成して確定させる必要がある。内訳表の行の合計 (39 + 11 = 50) は表内で整合するのみ。

**表の再生成手順** (入力 IR は `bash tools/m11/m11_e2e.sh --full` で生成):

```
python3 tools/liftdiff/tests/ld24_sig_breakdown.py tools/m11/work/boot_final3.ll > work/ld24_sig_breakdown.md
```

- 抽出: TSV の `unexec_reason == unsupported_sig` の 50 行 (`va`・`name`) を取り、IR の `function_<VA>` の `define`/`declare` 行から ret/params を引く。
- 集計: 署名形 (ret, params) ごとの件数。出力の関数別表で `va` → ret/params の対応を確認できる (`work/` は gitignore)。
- IR に無い関数は末尾に列挙し、終了コード 1 で返す。

| 署名形 (ret / params) | 関数数 |
|---|---|
| ret=`i128`, params=`i64` | 21 |
| ret=`i128`, params=なし | 8 |
| ret=`i64`, params=`i128` | 8 |
| ret=`i128`, params=`i64,i64` | 7 |
| ret=`i128`, params=`i128` | 1 |
| ret=`i128`, params=`i64,i64,i64` | 1 |
| ret=`ptr`, params=`%tagPOINT` (`{i32,i32}` 値渡し) | 1 |
| ret=`i64`, params=`i64,i64,i128` | 1 |
| ret=`i64`, params=`i64,i128,i64` | 1 |
| ret=`i128`, params=`ptr,i64,i64` | 1 |
| **合計** | **50** |

- `i128` は 16 バイト値。現行の `cmp_ret` (`ldlib/compare.py` L123) は `rax` の 64bit 幅しか比較せず、`rdx` を見ない。
  i128 戻り値の実際の返し方 (rax:rdx か sret か) と引数の渡し方は、機械語で**未確認** (実装時に確認が要る)。
- `%tagPOINT` (8 バイト `{i32,i32}`) の値渡しの ABI も**未確認**。

## 2. 残件 (今回未実装の理由)

case 生成 (`cases.py`)・native 実行器 (`rt/ld_native.c`・`ld_ms_call.S`)・wasm 実行器 (`rt/ld_wasm.c`・`fle_ldbridge.c`)・
比較 (`compare.py` の `cmp_ret`) の 4 箇所に ABI 変更が要る。1 run (60 分) で e2e (`liftdiff_e2e.sh --m11-only`) まで
再現・検証する量に収まらないと判断した。

## 3. 分割 (子 issue)

振り分けの規則 (1 関数を 1 子に限定する): ret=`i128` は戻り値側として #1193 に入れる (params が `i128` でも #1194 には数えない)。
ret が `i128` 以外で params に `i128` または `%tagPOINT` を含むものを #1194 に入れる。
これにより #1193 = 39 件、#1194 = 11 件 (内訳: `ret=i64/params=i128` 8 + `ret=i64/params=i64,i64,i128` 1 + `ret=i64/params=i64,i128,i64` 1 + `ret=ptr/params=%tagPOINT` 1)、計 50 件で重なりは無い。
ret=`i128`・params=`i128` の 1 関数は #1193 のみで扱う (#1194 の件数には含めない)。

| 子 | 対象 | 受入条件 (要点) |
|---|---|---|
| LD-38 (#1193) | ret=`i128` 39 関数 | i128 戻り値の rax:rdx を native/wasm 両方で取得し `cmp_ret` で上位 64bit も比較。既存 pattern の結果が変わらないこと |
| LD-39 (#1194) | params に `i128` / `%tagPOINT` を含む 11 関数 | i128 引数を 2 レジスタ分に分解して投入。`%tagPOINT` の値渡しの ABI を確認し対応 |

子 issue: #1193 (LD-38)・#1194 (LD-39)。各本文に `oc_artifacts:` 行あり。

## 4. 未解決

| 未解決 | 起票先 |
|---|---|
| i128 戻り値の上位 64bit 比較 (39 関数) | #1193 (LD-38) |
| i128 引数・tagPOINT 値渡しの case 生成 (11 関数) | #1194 (LD-39) |
| 対応後の m11 sample:800 / closure 再採点の実測 | #1193 / #1194 の受入条件 |
