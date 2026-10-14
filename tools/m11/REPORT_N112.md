# M11 REPORT (#1660 / [M11-N112] / 親 #1524): set_other imm 非定数 55 件の旧値 def 接続

結論: 55 件 (partial_write 35・stack_partial 9・arith 11) の値は **0 件** 決まらなかった (未決 55)。
直線区間の後ろ向き追跡では、merge (分岐先の境界)・call による volatile 族の破壊・関数入口の旧値で止まる。
決める前提として CFG の到達定義 (reaching definitions) が要る。受入 1 は未達。
検算 2 本 (`m11_setother_ledger_verify.py` 410/410・`m11_setother_imm_class.py` 6/35/9/11) は再現した。値が決まっていないので受入 2 の一致は判定できない。受入 3 (survey) は素材の欠けで測れない (§5)。

## 1. 入力と再現

- 入力 IR: `tools/m11/work/boot_final.ll` (`work-m11` 展開物・sha256 `69c774ded8aaf717…`・REPORT_N98 §1 と一致)。
- PE: `$FL_WIN64_DIR/extracted/block00031_PE.bin` (`fl-win64`)。
- 素材: `work-m11` を repo root に `tar --zstd -xf` で展開 (tar 内の path は `tools/m11/work/...`)。
- 実行 (コミット済み HEAD `d24cbe51`):
  1. `bash tools/m11/m11_sigfix_stats.sh` → 0 詰め site 1049 / 引数 1963・set_other 系 410 (378 + 32)・`stack_imm_fix 15`・`const 復元可能 fixes 33`。その後 `m11_argrecover_verify.py` が `KeyError: 4` で停止 (§4)。
  2. `python3 m11_setother_ledger_verify.py work/sigfix_stats/fixes.json --pe PE` → `match 410`・exit 0。
  3. `python3 m11_setother_imm_class.py work/sigfix_stats/fixes.json work/sigfix_stats/final3_base.ll --pe PE` → `full_const 6 / partial_write 35 / stack_partial 9 / arith 11 / no_write 0`・exit 0。
  4. `python3 m11_setother_ssa_value.py work/sigfix_stats/fixes.json --pe PE` → 対象 55 件・decided 0・undecided 55。

## 2. 旧値 def 接続の結果 (実測)

`m11_setother_ssa_value.py` は書込命令の直前を後ろ向きに辿る (レジスタ族・`[rsp+disp]` スロット単位)。
途中に分岐先があれば `merge`、call で volatile 族が壊れれば `call_clobber`、関数入口で止まれば `entry` として未決にする。
`mov r, r` の全幅コピーと、32bit `add|sub` の定数連鎖だけを辿る。

| 未決理由 | 件数 | 内訳の例 |
|---|---|---|
| `partial_old_merge` | 21 | `mov r8b/r9b, N` の直前に分岐先 |
| `partial_old_call_clobber` | 12 | `mov r8b/r9b, N` の前に call |
| `partial_old_entry` | 2 | 旧値が関数入口の引数 |
| `mem_old_merge` | 6 | `mov dword [rsp+0x20], N` の前に分岐先 |
| `mem_old_call_clobber` | 3 | 同上、call |
| `arith_old_unhandled` | 9 | `add/sub edx` の旧値が `mov edx, edi/esi/r13d/eax` 等の別レジスタ・メモリ由来 (未対応の源) |
| `arith_old_copy_call_clobber` | 1 | 同上、call |
| `arith_old_arith_nonimm` | 1 | 旧値が加減算の連鎖 |
| **計** | **55** | **決まった 0** |

## 3. 受入条件の判定

| 受入 | 判定 | 根拠 |
|---|---|---|
| 1. 55 件を旧値の SSA 接続で決める (未決は件数で残す・未分類 0) | **未達** | 決まった 0 / 未決 55 (§2)。未分類 0 は満たす (全行に理由あり) |
| 2. 既存検算 2 本と一致 | **未達 (比較対象なし)** | 既存検算は再現 (`ledger_verify` match 410・`imm_class` 6/35/9/11, §1)。ただし 55 件の値が未決のため、決めた値との一致は判定できない |
| 3. `M11_SIGFIX_RECOVER=1` survey に退行なし | **未達** | §5 |

## 4. 既知の不具合 (本 run で見つかったもの)

- `m11_argrecover_verify.py` は `ALIAS[f['pos']]` で register 位置 0〜3 しか扱わない。stack 引数 (pos 4 以上) の `stack_imm_fix` 15 件で `KeyError: 4`。`m11_sigfix_stats.sh` はこの時点で停止し、`final3_rec.ll`・`sigfix_zeropad_remaining.tsv` より後の段に進まない。REPORT_N98 §4 の数値は手で確認した。`m11_sigfix_stats.sh` 単体は現状 rc≠0。
- この不具合は本 issue の受入に直接は含まれないが、受入 2・3 の入口を塞ぐ。#1660 の残件として扱う。

## 5. 受入 3 (survey) が測れない理由

- `m11_e2e.sh` の既定経路は `work/ir_conditions.json`・`work/lift_pe.sha256` を要する。`work-m11` の展開物には無い (`ls` で確認: 3 件とも不在)。
- `functions_dll.csv` は素材に無い Ghidra 中間物。`m11_bounds.py` が fail-closed で止まる (REPORT_N86 §6・§9)。
- よって `69c774…` の IR で `M11_SIGFIX_RECOVER=1` の survey は取れない。#1154 の前提と同じ。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 55 件の旧値 def 接続 (CFG の到達定義・merge の越え方・call の clobber 規則) | set_other imm 非定数 55 件の値が未決。0 詰め引数の意味が未保証 | #1660 (残り) |
| `m11_argrecover_verify.py` の stack 位置 (pos ≥ 4) 非対応 (`KeyError: 4`) | `m11_sigfix_stats.sh` が途中停止。受入 2・3 の入口 | #1660 (残り) |
| `ir_conditions.json`・`lift_pe.sha256`・`functions_dll.csv` の生成 (受入 3 の前提) | survey 退行が未判定 | #1154 (REPORT_N86 §8 と同じ) |

## 7. 測定 commit と差分

- 測定 commit: `d24cbe51` (コード変更の最後の commit。`tools/m11/m11_setother_ssa_value.py`)。
- 測定 commit から HEAD までのコード差分: 本 REPORT (md のみ) を含む commit 以降は `git diff d24cbe51 HEAD -- tools/m11 ':(exclude)*.md'` で確認する (コミット後に実行して結果を PR 本文に貼る)。
