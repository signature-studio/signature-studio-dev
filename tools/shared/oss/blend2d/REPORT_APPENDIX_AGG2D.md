# Agg2D glue 付録 — vtable 比較・呼び出し元の手がかり (T-SH-02, #146)

> 本体: `REPORT_AGG2D.md` (結論と索引)。本付録は 250 行上限のため §12・§13 を分割移動した (内容は削除していない)。

## 12. vtable の slot 単位比較: Blend2D.dll と dsp_ippv2

> 測定 commit: `cc8baecb` (`agg2d_vtable.py` を DLL 指定と ctor/vtable の自動検出に一般化し、`agg2d_vtable_cmp.py` を追加)。
> `git diff cc8baecb HEAD -- tools/shared/oss/blend2d/agg2d_vtable.py tools/shared/oss/blend2d/agg2d_vtable_cmp.py` の出力は 0 行 (以後に変えたのは `agg2d_callers.py` の追加と REPORT・`docs/DOC_MAP.md` のみ)。
> 再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/oss/blend2d/agg2d_vtable_cmp.py` (依存: `pefile`・`capstone`、数秒)。出力は `tools/shared/work/agg2d_vtable_cmp.json` (gitignore)。
> 比較対象は `AggCreateInstance` を export する 2 DLL: **block24339 (Blend2D.dll)** と **block24356 (dsp_ippv2、IPP + AGG + GPC を同梱)**。block24355 は export 数 446・先頭が別形のため対象外。

| 項目 | block24339 (Blend2D.dll) | block24356 (dsp_ippv2) | 根拠 |
|---|---|---|---|
| ctor / vtable VA | `0x1800568a0` / `0x1801dbec0` | `0x1817b1210` / `0x18244a4c0` | `agg2d_vtable.py` (ctor 内の `lea`→`mov [rcx]` を検出。block24339 は §5 の値と一致) |
| vtable slot 数 | **130** | **130** | `agg2d_vtable.py` |
| 相異なる関数 (unique) | **79** | 128 | 同上 |
| 終端値 | `0x504d42` | `0xddb0b5008000000` | 同上 |

slot の種別は `agg2d_vtable_cmp.py` の `body_kind` で分けた (§5 の `classify` とは定義が異なる。`noop`・`ret_const`・`store_ret` を分離)。

| 種別 (slot 数) | block24339 | block24356 |
|---|---|---|
| code (実処理あり) | 76 | 123 |
| noop (`ret N` のみ) | **49** (全て `0x18000c530` を共有) | 3 |
| ret_const (`xor eax,eax; ret` 等) | 3 (`0x18000b820`) | 0 |
| store_ret (メンバ書込 + ret) | 2 (`0x1800572e0`) | 3 |
| thunk_jmp | 0 | 1 |

slot の対応 (block24339 の種別 × block24356 の種別, 件数):

| block24339 \ block24356 | code | noop | store_ret | thunk_jmp | 計 |
|---|---|---|---|---|---|
| code | 76 | 0 | 0 | 0 | 76 |
| noop | 42 | 3 | 3 | 1 | 49 |
| ret_const | 3 | 0 | 0 | 0 | 3 |
| store_ret | 2 | 0 | 0 | 0 | 2 |

**判明**:
- 両 DLL とも vtable は 130 slot。Blend2D.dll の 49 slot は同一の `ret 0` (`0x18000c530`) を指す no-op で、dsp_ippv2 では 42 slot が実処理を持つ。Blend2D.dll 側でこれらが未実装 (または no-op 扱い) であることを示す。
- Blend2D.dll で実体のある slot は **81** (= 130 − 49。code 76 + ret_const 3 + store_ret 2)、そのうち unique 関数は **78** (code 76 + ret_const 1 + store 1)。vtable 層の glue 規模はこの 78 関数が上限。
- §9 の閉包 (depth 50, 221 関数) のうち vtable 79 root を除く **142 関数** は、Blend2D 内部か glue の補助かが未判定 (帰属は未測定)。

**未検証 (本節の結論を強める前に確認が要る)**:
- 2 つの vtable が**同一 interface** (slot i が同じメソッド) であることは未確認。根拠は slot 数 130 の一致のみ。メソッド名・引数型は DLL に無い。
- FL 本体が noop slot を実際に呼ぶか (実行トレースが要る)。呼ばれないなら C++ 再実装の対象から外せるが、本節ではそこまで言えない。
- 78 関数の役割 (描画 / パス / 画素処理 / 設定) は未判定。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 2 vtable の interface 同一性 (slot 対応の確認) | noop・実体の対応付けの前提 | #146 |
| FL 本体による noop slot の呼出し有無 (実行トレース) | 再実装範囲 (78 関数 か 81 slot か) | #146 |
| 閉包の残 142 関数の帰属 (Blend2D 内部 / glue 補助) | lift か再実装かの規模 | #146 |

## 13. AggCreateInstance の呼び出し元の手がかり

> 測定 commit: `dfddf729` (`agg2d_callers.py` を追加)。`git diff dfddf729 HEAD -- tools/shared/oss/blend2d/agg2d_callers.py` の出力は 0 行。
> 再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/oss/blend2d/agg2d_callers.py` (依存: `pefile`・`capstone`、数秒、stdout に出力)。

| 項目 | 値 | 根拠 |
|---|---|---|
| UTF-16 で `Blend2D.dll` と `AggCreateInstance` を両方含む block | **145 / 313** | `agg2d_callers.py` の 1) |
| 手がかりの block | block18797 (MZ、`.text` 4.6 MB) | 同 2) |
| `Blend2D.dll` を指す参照 | VA `0x6555cd` (`lea rcx,…; xor edx,edx; xor r8,r8`、`LoadLibraryExW` 系の引数設定と読める) | 同 |
| `AggCreateInstance` を指す参照 | VA `0x6555f6` → `call 0x425280` → 戻り値を格納 | 同 |
| 格納先 (関数ポインタの保持先) | VA `0x8d8168` (格納 `0x655602`) | 同 |
| 格納先を指す参照 | 3 件: `0x6555c2` (読み出し)・`0x655602` (格納)・`0x655609` (`cmp qword ptr [rip+X], 0`) | 同 3) |

**判明**: block18797 は `Blend2D.dll` を読み込み、`AggCreateInstance` を解決して結果を 1 つの global に保持する lazy 初期化 loader。格納先の参照は loader の判定 2 箇所と格納 1 箇所だけ。
**未判明**: 同 block 内に、この global を使って `AggCreateInstance` を呼ぶ消費側は無い。loader 関数を返す getter の有無と、その呼び出し元。残り 144 block が同型の loader か。
**未検証**: `0x6555c2` の命令形 (`cmp` と推定)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| loader の呼び出し元 (getter 経由の消費側) の特定 | FL 描画経路の画素比較 (受入条件 (b)) の起点 | #146 |
| 145 block の loader が同型か | 呼び出し元の候補数 | #146 |
