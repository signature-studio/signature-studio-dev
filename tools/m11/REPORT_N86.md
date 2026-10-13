# M11 REPORT (#1371 / 親 #1154): sigfix 0 詰め set_other の代入元台帳と検算

結論: **部分達成**。set_other 416 引数 (今回の IR) を代入元の型で台帳化し、未分類 0・検算 mismatch 0 を実測した。SSA 値への接続による実値化は **0 件** で、未達。残件は既存の #1154 / #1373 に紐づける。

## 1. 代入元の台帳 (`m11_argrecover.py` の `src:*`)

測定 commit: `621c0d67` (コード変更は `m11_argrecover.py` の台帳追加と `m11_setother_ledger_verify.py`)。

| kind | 代入元 | 件数 |
|---|---|---|
| set_other | imm (定数だが fix 化されず) | 46 |
| set_other | lea_ptr | 17 |
| set_other | lea_stack | 60 |
| set_other | mem_global | 11 |
| set_other | mem_ptr | 90 |
| set_other | mem_stack | 50 |
| set_other | reg | 110 |
| stack_set_other | imm | 15 |
| stack_set_other | reg | 17 |
| **合計** | | **416** (set_other 384 + stack 32) |

未分類 0。`imm` 61 件は窓内で定数が代入されているが、`const_of` が `r8b`・`dl` 等の部分書込を未対応のため fix 化されていない。次の作業で効く候補。

## 2. 検算 (別アルゴリズム)

`tools/m11/m11_setother_ledger_verify.py`: capstone の `regs_access` / operand 型を使わず、`op_str` の文字列だけで代入元を判定する。

- 検算結果: **416 引数中 mismatch 0** (`ledger_verify_rows.json`)。
- 検算の初版は 49 件不一致だった。原因は (a) 8/16bit 部分書込 (`mov r8b, 2`) の名前を照合していなかったこと、(b) stack 引数の `al`・`xmm0` レジスタ元を `reg` と判定しなかったこと。いずれも検算側の穴で、台帳側 (capstone operand 型) が正しいことを個別に確認して修正した。

## 3. survey 退行検査 (受入 2)

同一 IR (`ir_sha256` `5389208821…`) で `m11_e2e.sh` を 2 本実行。

| 条件 | 結果 | 所要 |
|---|---|---|
| `M11_SIGFIX_RECOVER=0` | reached_stage 4, units 53/942, **survey ok 872** / trap 23 / miss 46 / clobber 0 | 10 分 2 秒 (IR 再生成込み) |
| `M11_SIGFIX_RECOVER=1` | 同上 **ok 872** / trap 23 / miss 46 / clobber 0 | 55.5 秒 (増分) |

ok 872 = 872 で退行なし。受入 2 を満たす。

## 4. 既知の IR 差分 (重要)

e2e の再生成で `boot_final.ll` が作り直され (sha `5389…`)、既定 IR の 0 詰め site は前回の 1,049 site / 2,064 引数から **1,061 site / 2,084 引数** に増えた。上記 §1 の内訳 (416) は**この新 IR での値**で、前回 `REPORT_N53.md` の 410 (378 + 32) とは一致しない。コードの書換え (既定出力) は変えていない。

## 5. 再現

- `bash tools/m11/m11_sigfix_stats.sh` で pads / fixes を生成し、`m11_setother_ledger_verify.py` で台帳を検算する。
- 前提: `work-m11` 素材 + `functions_dll.csv` (Ghidra 12.1.4 headless・JDK 21・`DumpFunctions.java`。本 run で生成し 59,010 行・9 分 47 秒)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| set_other 416 引数の SSA 値接続による実値化 (台帳の reg 110 / mem_ptr 90 / mem_stack 50 等) | 0 詰め引数の意味が未保証のまま | #1154 (親 #953) |
| `imm` 61 件の部分書込 (`r8b`・`dl` 等) を `const_of` で fix 化 | 定数復元の取りこぼし | #1154 |
| inherit 側の呼出元 def 追跡 | 受入の inherit 分 | #1373 ([M11-N87]) |
| 前回 IR (1,049 site) と現 IR (1,061 site) の差の原因切り分け | 数値の比較基準が 2 つになる | #1154 |
