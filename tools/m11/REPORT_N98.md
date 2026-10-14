# M11 REPORT (#1524 / [M11-N98] / 親 #1371): set_other 410 引数の実値化 (imm 61 件)

結論: 台帳の imm 61 件を機械語で再分類した。**型幅ぶんの定数で値が決まるのは 6 件だけ** (`full_const`)。残り 55 件は、上位ビットが旧値に依存する部分書込 (`mov r8b/r9b/r8w, N` 35 件・`mov dword [rsp+N]` の i64 スロット 9 件) か、旧値への加減算 (`add/sub edx|r8d, N` 11 件) で、定数ではない。台帳の `imm` 分類は、この 55 件では誤りだった。6 件は `bits` 照合つきの fix として IR に入れ (fix 18 → 24)、検算 410/410 一致を維持した。受入 3 (survey 退行なし) は素材の欠けで測れず、未達 (§5)。

既知類型との関係: 該当なし (lift 欠陥ではなく sigfix の引数復元の範囲に関する話。DEFECTS.md の類型とは別)。

## 1. 入力と再現

- 入力 IR: `tools/m11/work/boot_final.ll` (`work-m11` 展開物・sha256 `69c774ded8aaf717…`)。REPORT_N86 §9 と一致。
- PE: `fl-win64` の `extracted/block00031_PE.bin` (sha256 `b2c64da4…`)。
- 実行:
  1. `python3 m11_post.py work/boot_final.ll work/sigfix_stats/final3_base.ll --pads work/sigfix_stats/pads.json` → 既定出力 sha `ecab191b…` (REPORT_N86 §4 と一致)
  2. `python3 m11_argrecover.py work/sigfix_stats/pads.json --pe $PE --out work/sigfix_stats/fixes.json` → 0 詰め site 1049・引数 1963・set_other 系 410・fixes 33 (`set_const` 18 + `stack_imm` 15)
  3. `python3 m11_setother_ledger_verify.py work/sigfix_stats/fixes.json --pe $PE` → `match 410`・exit 0
  4. `python3 m11_setother_imm_class.py work/sigfix_stats/fixes.json work/sigfix_stats/final3_base.ll --pe $PE` → `full_const 6 / partial_write 35 / stack_partial 9 / arith 11`
- 出力 dir `work/sigfix_stats/` は gitignore 対象で commit しない。

## 2. imm 61 件の内訳 (実測)

| 分類 | 件数 | 機械語 (直前の書込) | 値が定まるか |
|---|---|---|---|
| full_const | 6 | `mov byte ptr [rsp+0x20/0x28], 0` (i8 引数 4 件)・`mov dword ptr [rsp+0x28], 2` (i32 引数 2 件) | 定まる (書込幅 = 型幅) |
| partial_write | 35 | `mov r8b, N` 20・`mov r9b, N` 14・`mov r8w, N` 1 | 定まらない (上位ビット旧値依存) |
| stack_partial | 9 | `mov dword ptr [rsp+0x20], N` (i64 スロット) | 定まらない (上位 32bit 旧値依存) |
| arith | 11 | `add edx, N` 9・`sub edx, N` 1・`sub r8d, N` 1 | 定まらない (旧値への加減算) |

- 台帳の `imm` は「定数代入」の意味だが、部分書込・加減算を含む。kind 名の見直しは、本 REPORT では行わず分類で示す。
- 分類の根拠: x86-64 の 32bit レジスタ書込は上位 32bit をゼロ拡張する (全幅を定める)。8/16bit 書込と、型より狭いメモリ書込は、上位が旧値依存 (`m11_setother_imm_class.py` の `classify`)。

## 3. 実装 (IR への適用)

- `m11_argrecover.py`: `stack_imm_of` を追加。stack 引数の直前窓の `mov byte|word|dword|qword ptr [rsp+disp], imm` から (値, 書込幅 bit) を取り、`fixes` の `bits` に載せる。書込幅を `ops[0].size * 8` から取る (文字列解析はしない)。
- `m11_post.py`: `--fixes` の読込みで `bits` を保持し、`bits` が引数の型幅 (`iN`) と一致する時だけ fix を適用する。既存の `set_const` fix は `bits` を持たないため従来どおり適用される。

## 4. 結果 (実測)

| 項目 | 値 | 計測 |
|---|---|---|
| 既定出力 `final3_base.ll` sha256 | `ecab191b…` (変化なし) | REPORT_N86 §4 と一致 |
| 台帳 set_other 系 | 410 (378 + 32) | 変化なし |
| 検算 `m11_setother_ledger_verify.py` | match 410・exit 0 | 変化なし |
| fixes | 33 (`set_const` 18 + `stack_imm` 15) | 18 → 33 |
| IR に入った fix (`--report`) | 18 → **24** | `sigfix_const_recovered` (旧コード 18 / 新コード 24) |
| 既定 IR との差分 (fix 適用時) | `chk_new.ll` vs `chk_old.ll` で **差分 2 行** (`function_a97410` の i32 引数 2 件: 0 → 2) | `diff` |
| `bits` 照合で落ちた stack_imm | 9 件 (i64 スロットへの `mov dword`) | 15 - 6 |

注: `stack_imm_fix 15` のうち 9 件は `bits` (32) と引数型 (i64) が違うため `m11_post.py` で適用されない。適用されるのは `function_a97410` の i32 2 件・`function_697510` の i8 4 件 (値 0 は既定の 0 詰めと同じ) の 6 件で、IR に実差分を作るのは i32 2 件だけ。

## 5. 受入条件の判定

| 受入 | 判定 | 根拠 |
|---|---|---|
| 1. imm 61 件から実値化し、kind 別件数を REPORT に残す (未分類 0) | **部分達成** | 61 件を 6 / 35 / 9 / 11 に分類 (未分類 0)。実値化は 6 件 (IR に入ったのは i32 2 件の実差分) |
| 2. 別アルゴリズム検算で一致 | **達成** (台帳 410・分類 61 件は既存検算 `m11_setother_ledger_verify.py` の match 410 で確認) | §1 の 3 |
| 3. `M11_SIGFIX_RECOVER=1` の `m11_e2e.sh` で survey 退行なし | **未達** | §6 |

## 6. 未達 (受入 3) の理由と残件

- `m11_e2e.sh` の既定経路は `work/ir_conditions.json`・`work/lift_pe.sha256` を要する。`work-m11` の展開物には無いため、`m11_gen_ir2.sh` で IR を作り直すと `69c774…` は再現できない (REPORT_N86 §6 と同じ結果)。
- `--full` の再生成は Ghidra 中間物 `functions_dll.csv` が素材に無く、`m11_bounds.py` が fail-closed で止まる (REPORT_N86 §6・§9)。
- よって、この run では `69c774…` の IR で survey を取れない。survey 退行の判定は、IR の build 条件 (`ir_conditions.json`) が揃うまで保留。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `69c774…` IR の build・survey (受入 3) | 6 件の fix の survey 退行が未判定 | #1154 (REPORT_N86 §8 と同じ) |
| partial_write 35・stack_partial 9・arith 11 (計 55 件) の値を、上位ビット・旧値の SSA 接続で定める | 0 詰め引数の意味が未保証 | #1660 ([M11-N112]・親 #1524) |

## 7. 再現・測定 commit

- 測定 commit: `55b65295` (コード変更の最後の commit)。コードは `tools/m11/m11_argrecover.py`・`tools/m11/m11_post.py`・`tools/m11/m11_setother_imm_class.py`。
- 測定 commit から HEAD までのコード差分: 本 REPORT を含む commit 以降のコード差分は無い (`git diff 55b65295 HEAD -- tools/m11 ':(exclude)*.md'` の出力は 0 行)。
- `55b65295` を `git worktree add --detach` で展開して §1 の 4 コマンドを実行し、§4・§2 の値を再現した (`ecab191b…`・`match 410`・分類 6/35/9/11・`sigfix_const_recovered 24`)。検証 worktree は削除済み。
- 検算の独立性は限定的: `m11_setother_imm_class.py` は `m11_argrecover.py` の窓 (`REGS`・`rw`・`memops_of`) を流用する。REPORT_N86 §3 の「命令列の取得と窓は台帳と共通」と同じ制約で、窓の誤りは検出できない。
