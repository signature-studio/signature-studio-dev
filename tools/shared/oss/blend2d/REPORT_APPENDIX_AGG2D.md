# Agg2D glue 付録 — vtable 比較・呼び出し元の手がかり (T-SH-02, #146)

> 本体: `REPORT_AGG2D.md` (結論と索引)。本付録は 250 行上限のため §12・§13 を分割移動した (内容は削除していない)。

## 12. vtable の slot 単位比較: Blend2D.dll と dsp_ippv2

> 測定 commit: `53b584d8` (`agg2d_vtable.py` の import 用定数 (`CTOR_VA`・`VTABLE_VA`) を戻し、`agg2d_vtable_cmp.py` のヘッダを直した commit。DLL 指定と ctor/vtable の自動検出は `cc8baecb` で導入)。
> `git diff 53b584d8 HEAD -- tools/shared/oss/blend2d/agg2d_vtable.py tools/shared/oss/blend2d/agg2d_vtable_cmp.py` の出力は 0 行 (以後に変えたのは REPORT・`docs/DOC_MAP.md` のみ)。
> 再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/oss/blend2d/agg2d_vtable_cmp.py` (依存: `pefile`・`capstone`)。出力は `tools/shared/work/agg2d_vtable_cmp.json` (gitignore)。
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
- 両 DLL とも vtable は 130 slot。Blend2D.dll では no-op の slot が 49 ある (同一の `ret 0`、`0x18000c530`)。dsp_ippv2 では 42 slot が実処理を持つ。
- Blend2D.dll で実体のある slot は **81** (= 130 − 49。code 76 + ret_const 3 + store_ret 2)、そのうち unique 関数は **78** (code 76 + ret_const 1 + store 1)。vtable 直下の実体関数は 78。
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
| 格納先を指す参照 | 3 件: `0x6555c2` (`mov qword ptr [rip+X], 0`、初期化)・`0x655602` (格納)・`0x655609` (`cmp qword ptr [rip+X], 0`、判定) | 同 3) (命令形は capstone で確認) |

**判明**: block18797 は `Blend2D.dll` を読み込み、`AggCreateInstance` を解決して結果を 1 つの global に保持する lazy 初期化 loader。格納先の参照は 3 件だけで、初期化 store 1・格納 1・判定 1 (`cmp` は `0x655609` の 1 箇所)。
**未判明**: 同 block 内に、この global を使って `AggCreateInstance` を呼ぶ消費側は無い。loader 関数を返す getter の有無と、その呼び出し元。残り 144 block が同型の loader か。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| loader の呼び出し元 (getter 経由の消費側) の特定 | FL 描画経路の画素比較 (受入条件 (b)) の起点 | #146 |
| 145 block の loader が同型か | 呼び出し元の候補数 | #146 |

## 15. x64c の未対応 6 mnemonic の被覆 (#3138、閉包 50 の unsup 13 site)

> 測定 commit: `fe2dc9ed` (コードを変えた最後の commit: `feat(flelift): cover the 6 unsup mnemonics of the Agg2D closure in x64c`)。`git diff fe2dc9ed HEAD -- tools/flelift tools/shared/oss/blend2d ':(exclude)*.md'` の出力は 0 行 (以後の変更は REPORT の文言のみ)。
> 再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/oss/blend2d/agg2d_lift_probe.py [出力 JSON]` (約 4 秒)。差分試験: `python3 tools/flelift/tests/x64c_vex_diff.py` (約 2 秒、GNU as / gcc が必要)。

**閉包別の lift 結果** (変更前 = `8d8d0e6a`、変更後 = `fe2dc9ed`。`agg2d_lift_probe.py` の `depths`)

| 閉包 | funcs | insns | unsup_sites 前 → 後 | unsup_mnemonics 前 → 後 | unlifted_callees 前 → 後 |
|---|---|---|---|---|---|
| 0 | 79 | 4,265 | 0 → 0 | 0 → 0 | 107 → 107 |
| 1 | 110 | 9,007 | 4 → 0 | 2 → 0 | 36 → 36 |
| 3 | 168 | 22,681 | 13 → 0 | 6 → 0 | 26 → 26 |
| 50 | 221 | 27,684 | **13 → 0** | 6 → 0 | 0 → 0 |

funcs・insns・unlifted は変更前後で同一 (受入条件 (1) 達成)。probe の CFG 間接 call のネガティブコントロールは両方で通過 (既知 slot は dispatch 表に載り、未知値は載らない)。

**mnemonic 別の被覆 (閉包 50)**

| mnemonic | 形 | 変更前 site | 変更後 | 実装 |
|---|---|---|---|---|
| vsubsd | d==s2、s1≠d | 5 | 0 | `vex3()` の d==s2 tmp 経路 (`s1 - s2`。下位 lane のみ、上位 lane は s1 から、YL 0 化) |
| vdivsd | d==s2、s1≠d | 2 | 0 | 同上 (`s1 / s2`) |
| vxorps | 3-op | 2 | 0 | `VEX3` に `xorps` を追加 |
| cmpneqpd | 2-op | 2 | 0 | `cmppd_pred(4)` (NEQ_UQ。NaN 比較は真) |
| vpsrldq | 3-op (imm) | 1 | 0 | `vex_leg()` の 3-op 形 (バイトシフト、YL 0 化) |
| vcvttpd2dq | 2-op | 1 | 0 | `VEX2` に `cvttpd2dq` を追加 |
| 合計 | | 13 | 0 | |

**差分試験** (`tools/flelift/tests/x64c_vex_diff.py`): **44 PASS / 0 FAIL**。既存 35 件は変更なし、新規 9 件を末尾に追加。新規の内訳は vsubsd (d==s2) 1、vdivsd (d==s2) 1、vsubss (d==s2) 1、vdivss (d==s2) 1、vxorps 1、vcvttpd2dq 1、cmpneqpd 2 (NaN 比較・非 NaN 比較)、vpsrldq 1。期待値は Python で Intel SDM の意味から計算し、x64c の C 出力は参照しない。

**ネガティブコントロール**: tmp 経路の被演算子の順を入れ替え (`a_ op b_` → `b_ op a_`) ると **FAIL 4 件** (vsubsd・vdivsd・vsubss・vdivss) になり、元に戻すと 44/44 PASS (`git diff` で復元を確認)。途中の経緯: 初版では vdivsd のオペランドが乱数で一致して入れ替えても PASS したため、prep で X4 = 2.0・X6 = 7.0 に固定した。同様に ss 系は NICE 値の下位 32bit が 0 のため、単精度用の prep (下位 32bit に値を置く) を追加した。

**C 出力の差分** (閉包 50 の `fle_lifted.c`): 変更前 58,903 行 → 変更後 58,914 行。`diff` の変更は **13 行 (`ott_unsup` の 13 site) を 24 行 (新 handler) に置換する hunk のみ**で、他の行は変化しない。内訳: vsubsd 5 site × 2 行、vdivsd 2 × 2、vxorps 2 × 2、vpsrldq 1 × 2、vcvttpd2dq 1 × 2、cmpneqpd 2 × 1 (計 24 行)。閉包 0・1・3 の C 出力の diff は取っていない (unsup 表は上の通り)。

**FLEngine の lift 出力** (受入条件 (3)): `block00031_PE.bin` を `--closure 0`、entries は `tools/flelift/fle_entries.json`、引数は `fle_lift.sh` と同じ (emcc は省略)。変更前は `origin/main` の `x64c.py` を一時ディレクトリに置いて実行。両方 **7,018 関数 / 340,761 命令 / unsup {} / unlifted 0 / import 354**。`fle_lifted.c` と `lift_meta.json` は `cmp` で**バイト一致** (差分 0)。FLEngine の lift には今回の変更が効く unsup 箇所が無く、出力は変わらない。lift 所要は各 19 秒。
