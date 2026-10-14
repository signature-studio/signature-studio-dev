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

## 15. CFG rax-in (`--cfg-rax`) と #3065 取り込み後の閉包 50 (REPORT_AGG2D.md §15 の測定値)

> 測定 commit: `bbf86210` (`--cfg-rax` を入れたコード commit)。base = `origin/main` `80c4e81b` (#3065 取り込み後)。
> `git diff 80c4e81b bbf86210 -- tools/flelift/x64c.py tools/shared/oss/blend2d/` = 変更 3 ファイル (x64c.py +14/-1, agg2d_cfg_rax.py 新規, agg2d_lift_probe.py +18)。
> 再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/oss/blend2d/agg2d_cfg_rax.py` (0.4 s) と `agg2d_lift_probe.py` (5.5 s)。出力は `tools/shared/work/` (gitignore)。
> 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (5.6 s)。`toolchain-emsdk` は未使用。

### 15.1 CFG 間接 call / jmp の全数 (`.text` 全体)

| 項目 | 値 | 根拠 |
|---|---|---|
| CFG スロット / thunk | `0x1801b7308` / `0x1801b5b90` (bytes `ffe0` = `jmp rax`) | load config・PE |
| `call [slot]` / `jmp [slot]` | 42 / 14 (計 56) | `agg2d_cfg_rax.py` (ff 15/25 のバイト走査 + capstone で再確認) |
| 負例 (slot + 8) | 0 件 | 同スクリプト (0 件でなければ rc=1) |
| 命令境界が揃った直前窓 (≥4 命令) | 43 / 56 | 直前 96 B の逆同期 |
| rax の最後の定義 (call 42 件 / jmp 14 件) | call: mov reg,mem 17・mov reg,reg 14・call 戻り値 9・ror 2 / jmp: 窓内に定義無し 9・同期不可 3・add 1・call 戻り値 1 | 同 (明示 operand の書き込みで判定。capstone の `regs_write` は暗黙の書き込みしか返さないので使わない) |
| 定義と site の間に分岐・ret | 23 / 56 | 同 |

読み: rax の定義は実行時値 (メモリ load・レジスタ・戻り値・計算) で、定数追跡では閉じない (§7 と同じ結論)。rax-in は rax の値をそのまま dispatch すれば足り、定義元の解決は要らない。窓外で定義される 9 件 (jmp の「窓内に定義無し」) と、分岐を跨ぐ 23 件は静的には確かめられていない。

### 15.2 x64c 閉包 50 (Agg2D vtable 79 root) の CFG 規則と未対応 (#3065 後)

| 項目 | 既定 (`--cfg-rax` 無し) | `--cfg-rax` |
|---|---|---|
| 関数 / 命令 | 221 / 27,684 | 221 / 27,684 |
| CFG の dispatch (`LD64(slot)` を経由) | 8 (直接形 6 + レジスタ経由形 2) | 2 (レジスタ経由形のみ) |
| `ott_dispatch(R[RAX])` (rax-in) | 0 | 6 (jmp 4 + call 2) |
| 未対応 site / mnemonic | 13 / 6 | 13 / 6 (CFG だけを変えるため同じ) |
| 未 lift の直接 call | 0 | 0 |

- 未対応 13 site の内訳 (閉包 50): `vsubsd` (d==s2) 5・`cmpneqpd` 2・`vdivsd` (d==s2) 2・`vxorps` 2・`vpsrldq` 1・`vcvttpd2dq` 1。`int 0x29` (fail-fast) は意図的な abort で unsup には数えていない。
- #3065 (`origin/main` へ取り込み済み) の前の測定 (REPORT §9、`53b584d8` 時点) は未対応 363 site / 33 mnemonic。#3065 の VEX/FMA 対応で 13 site / 6 mnemonic に減った。
- `vsubsd`・`vdivsd` の未対応は `d == s2` の場合のみ (3 オペランド形の宛先と第 2 ソースが同じ)。他の VEX スカラー形は #3065 で対応済み。

### 15.3 既定の出力は変わらない (byte 一致)・構文

| 項目 | 結果 |
|---|---|
| 既定 (`--cfg-rax` 無し) の閉包 50 の `fle_lifted.c` / `lift_meta.json` | `80c4e81b` の x64c.py と **byte 一致** (`cmp`。`$RUNNER_TEMP/x64c_base.py` で再生成) |
| 既定版・`--cfg-rax` 版の生成 C の構文 | `gcc -fsyntax-only -w -I tools/flelift/rt` rc=0 (両方) |
| ネガティブコントロール | probe の辞書検査 (既知値 `0x180009ea0` 表に有り・thunk `0x1801b5b90` 表に無し) は従来どおり `True` / `False` |

### 15.4 未検証・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 生成 C の実行 (rax-in が実機の target と一致するか・dispatch 表に載るか) | 受入 (b) の画素比較の前提。未検証のまま `--cfg-rax` を既定にできない | #146 (harness 待ち) |
| レジスタ経由 CFG 形 (`mov reg,[slot]; call reg`) 2 site は ON でも `LD64(slot)` のまま | 2 site が thunk を dispatch して silent に抜ける恐れ | 子 issue (T-SH-51) |
| `--cfg-rax` の既定化 | FLEngine の lift 出力が変わる → boot KPI の前後比較が要る (未実施) | 子 issue (T-SH-51) |
| 未対応 13 site (6 mnemonic) | 閉包 50 の lift の残り (到達は未確認。ott_unsup は到達時のみ abort) | 子 issue (T-SH-50) |
