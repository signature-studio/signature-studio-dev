# M11 REPORT (#4905 / [M11-N228] / 親 #4891・#3907): set_other 非 imm の lea [reg+d] gep 17 件の基底 reg を到達定義で分類

結論: gep 17 件の基底 reg の到達定義を機械語の後ろ向き走査で辿り、3 値に分けた。実測は **実値化 0 / 復元不能 0 / 未決 20 (gep 17 + global_store 3) / 未分類 0**。gep 17 件は「基底が stack slot 読込 7・merge 6・ポインタ読込 4」で、どれも値が定数に決まらなかった。**IR への GEP 接続はしていない** (未解決、§4)。

## 1. 入力と手順

- 入力: `work-m11` の `tools/m11/work/boot_final.ll` (`sigfix_stats/` は素材に無いため、REPORT_N227 §1 の手順 1〜4 で再生成)。PE は `fl-win64` の `extracted/block00031_PE.bin`。
- 手順:
  1. `m11_post.py boot_final.ll sigfix_stats/final3_base.ll --pads sigfix_stats/pads.json` → 0 詰め call site 1049・引数 2064 (REPORT_N227 と一致)。
  2. `m11_argrecover.py pads.json --pe $PE --out fixes.json` → const 復元可能 fixes 33。`m11_argrecover_verify.py fixes.json` → `match 33 / mismatch 0`。
  3. `m11_setother_nonimm_class.py fixes.json --pe $PE --ir boot_final.ll` → 非 imm 349 件。
  4. `m11_setother_mem_class.py nonimm_class_rows.json --pe $PE` → 実値化 8 (`const_read`)・gep 17・global_store 3 (REPORT_N227 と一致)。
  5. `m11_setother_gep_global.py mem_class_rows.json --ir final3_base.ll --out gep_global_rows.json --pe $PE` → 対象 20 件・実値化 0・復元不能 0・未決 20・未分類 0。

## 2. 測定結果

| 接続方式 | 区分 | 件数 | 理由 (`why`) |
|---|---|---:|---|
| gep (`lea [reg+d]`) | 未決 | 7 | `base_stack_slot`: 基底 reg が `mov reg, qword ptr [rbp+d]` で決まる |
| gep | 未決 | 6 | `base_merge`: 基底 reg の定義の前に分岐合流点 |
| gep | 未決 | 4 | `base_ptr_load`: 基底 reg が `mov rax, qword ptr [rax+0x94]` 等のポインタ経由読込 |
| global_store | 未決 | 3 | `no_store_in_ir`: 3 件とも VA `0x15e3a70` への store が IR 内に 0 件 |
| 合計 | 実値化 0・復元不能 0・未決 20・未分類 0 | 20 | |

- 実値化 0 件・復元不能 0 件は、分類規則の結果として実測された値。gep 17 件の基底 reg は、どれも直線区間で `mov reg, imm` に辿り着かなかった。
- 実値化 (`base_const`) と復元不能 (`base_call_ret`) の経路は分類器に実装済みだが、本測定の 17 件では通らなかった。
- 前 REPORT (N227) の「全分岐で `未決` 固定」は、`--pe` 無しの従来経路 (`base_ssa_unmapped`) としてそのまま残した。

## 3. 接続方式 (受入 2)

- gep 17 件の対象は「`lea [reg+d]` の基底 reg の SSA 値に対する GEP」。
- 基底 reg の到達定義は、直前の命令を後ろ向きに辿って求める (`m11_setother_ssa_value.py` と同じ走査)。合流点・分岐・call (揮発族 reg) で止める。
- IR 側では、gep の呼出し引数が `i64 0` の定数になっている (例: `function_6a09b0` の呼出し 371088 行)。基底 SSA 値との対応は未実装のため、IR 接続はしていない。
- 対象 GEP (呼出し元 → 呼出し先 / 引数位置): `function_977870`→`function_6774b0` (5 件・pos 0)、`function_a962a0`→`function_697510` (1)、`function_a981f0`→`function_6a09b0` (2)、`function_cd16f0`→`function_6613b0` (1)、`function_cd3ad0`→`function_6a3d50` (1)、`function_dd5680`→`function_6be960` (1)、`function_ddf630`→`function_6be960` (2)、`function_ff0600`→`function_695a50` (1)、`function_ff0d70`→`function_699ca0` (2) と `function_697510` (1)。

## 4. 検証と限界

- 分類器は IR を変えない。判定は到達定義の区分と理由の割当だけで、値は `mov reg, imm` の 1 命令からしか決めない。
- 件数の再現: 手順 1〜5 を HEAD で実行した。手順 1〜4 の件数は REPORT_N227 と一致。手順 5 は本 PR の分類器で実測。
- 未検証: `base_const` (実値化) の経路は本測定の 17 件で通っていない。値の照合 (`m11_argrecover_verify.py`) は実値化 0 件のため対象なし (該当なし)。
- `global_store` 3 件は本 PR の対象外 (子 #4906)。分類器の出力は REPORT_N227 から変わらない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| gep 17 件の基底 SSA 値 → IR の GEP 式の対応付け (IR 接続) | 受入の『接続』の残り 17 件。IR の呼出し引数は依然 `i64 0` | #4905 (本 issue・次 run) |
| 基底 reg が stack slot 読込 (7)・ポインタ読込 (4)・merge (6) で止まる件の値の決定 | 実値化 0 のまま | #4905 (本 issue・次 run) |
| global_store 3 件の格納値の到達定義と、呼出し元外の格納探索 | 受入の『接続』の残り 3 件 | #4906 (M11-N229) |
