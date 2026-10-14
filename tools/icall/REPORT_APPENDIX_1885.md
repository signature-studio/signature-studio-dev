# REPORT_APPENDIX_1885 — OTT F 0x1801a31fb の jt_dropped の機構 (ICALL-48)

親: #1839 (ICALL-42) / 前提: `tools/icall/REPORT_APPENDIX_1839.md` の未解決 (0x1801a31fb が before 段階で jt_dropped)。

既知類型との関係: 該当なし (DEFECTS.md の既知 ID には一致しない。近いのは「分岐の誤結線」だが D1b・D9 とは機構が異なる。下記)。

## 結論

- 0x1801a31fb (`jmp r9`, targets 17) が before 段階で `jt_dropped` なのは、**jump table の入口 `jbe 0x1801a31e0` (0x1801a30e8) の真の側が、RetDec の before IR で `dec_label_pc_1801a3198` (ret ブロック) へ誤結線されている** ため。
- その結果、0x1801a31e0〜0x1801a31fe の dispatch ブロック (`mov rdx,r9` → `lea` → 表引き → `add` → `add rcx,r8` → `jmp r9`) が before IR に 1 命令も残らない。`insn.addr` を持つ命令が無いので audit は `jt_dropped` と判定する。
- ICALL-42 の 7 件 (switch 畳み込み) とは別機構。`switch` は `function_1801a30d0` に 0 件。
- 修正は RetDec の CFG 構築側 (before 段階の jcc 結線) で行うべきで、`ir_icall_restore.py` で addr を捏造する範囲を超える。本 run では修正せず、残件として記録する (受入条件の「不要なら説明可能な残件」に該当)。

## 機構の根拠 (before.0.drc.ll / dsm)

対象の関数は `function_1801a30d0` (F.ranges `0x1801a30d0-0x1801a3260`)。

| 項目 | 機械語 (OTT_vst2_win64.dll 逆アセンブル / dsm) | before.0.drc.ll |
|---|---|---|
| 入口判定 | `0x1801a30e4 cmp r8,0x10` / `0x1801a30e8 jbe 0x1801a31e0` | `br i1 %0, label %dec_label_pc_1801a3198, label %dec_label_pc_1801a30ee, !insn.addr !2571` (`%0 = icmp ult i64 %arg3, 17`) |
| 飛び先 0x1801a31e0 | dispatch 入口 (`mov rdx,r9`) | 対応ラベル `dec_label_pc_1801a31e0` が**無い** (関数内 14 ラベル、`switch` 0 件) |
| 0x1801a31e0〜0x1801a31fe | `mov rdx,r9`・`lea r9,[rip-0x1a31ea]`・`mov eax,[r9+r8*4+0x2840e0]`・`add r9,rax`・`add rcx,r8`・`mov rax,r11`・`jmp r9` (0x1801a31fb) | `insn.addr` 付きの命令 0 件 |
| 0x1801a3198 | `mov rax,r11; ret` | `ret i64 %arg1` (jbe の真の側が誤ってここへ向く) |

- jump table の 17 エントリは全て 0x1801a3200〜0x1801a3258 の範囲 (`[0x1801a320e, 0x1801a320b, …]` = 関数 `function_1801a3200`〜`function_1801a3258` 内)。
- `function_1801a30d0` の before.0.log は `converting function` まで完走し、警告は出ていない (NonRecursiveCFGBuilder の警告は別関数)。

## 同型の欠落の他の site との比較 (jmp reg の入口 jcc)

`before.0.drc.dsm` の jmp reg 13 site について、直上 0x60 B 以内の jcc の飛び先が before IR のラベルに有るかを突合した (`jcc→dispatch` は jump table 入口の候補)。

| jmp reg site | 入口 jcc (dsm) | 入口飛び先が before IR にラベル有 | 判定 |
|---|---|---|---|
| 0x1801a31fb (r9) | 0x1801a30e8 → 0x1801a31e0 | **無** | jt_dropped (本件) |
| 0x1801a2c92 (r11) | 0x1801a2bae → 0x1801a2c78 | 無 | 別 site (jt_present ではない。本件と同型の可能性があるが未検証) |
| 0x1801a2f36 (r11) | 0x1801a2e88 → 0x1801a2f1c | 無 | 同上 |
| 0x1801ac729 (rcx) | 0x1801ac5ba → 0x1801ac6ea | 有 | ICALL-42 の switch 畳み込み側 |

注: 0x1801a2c92・0x1801a2f36 は本 audit の jmptable 8 件に含まれない (`jt_present`/`jt_dropped` の集計対象外)。同型かどうかは本 run では確定していない。

## 再現とネガティブコントロール

- 再現: `python3 tools/icall/repro_1885.py <rt_ott-F>` (0.28 s、load average 0.04–0.14)。出力: dsm jbe→0x1801a31e0 / IR true→dec_label_pc_1801a3198 / IR true == dsm 飛び先: False / dispatch ラベル: False / switch: 0 / insn.addr 行 (関数全体): 160 / dsm の jmp r9 0x1801a31fb: True。
- ネガティブコントロール: 正しく結線された入口 jcc `0x1801ac5ba` (dsm → 0x1801ac6ea、ICALL-42 側の switch 畳み込み site) に同じ突合を当てると IR true 一致 = True (n=1)。対象 site だけ不一致になることを確認した。

## 判定ロジックの確認

- `audit_icall.py` の `jt_dropped` 判定は「区間内の `!insn.addr` が 0 件」。0x1801a31fb は区間 (`map.json` の insn_ranges にも 0x180314c7d・274 B で存在) の before 段階で `insn.addr` が 0 件。
- 0x1801a31fb の before 区間は ICALL-42 (`REPORT_APPENDIX_1839.md`) と同じ判定規則で扱った。判定ロジックは変更していない (`audit_icall.py` 差分 0)。

## 実測 (測定対象)

測定 commit: `09ed7bbc` (audit 変更を含む最後のコード commit、`REPORT_APPENDIX_1839.md` と同じ)。
`git diff 09ed7bbc origin/main -- tools/icall/audit_icall.py tools/icall/ir_icall_restore.py` の出力は空 (判定ロジック差分 0)。
`tools/icall` 全体では main 取り込みで 13 ファイル・667 行の差分があるが、本件の判定に使ったファイルは含まない。

素材: `work-icall` の `rt_ott-F` (before.0.drc.ll / before.0.drc.dsm / F.ranges / map.json)、`analysis-ott-binaries` の `OTT_vst2_win64.dll`。

| 入力 | 結果 |
|---|---|
| before.0.drc.ll `function_1801a30d0` の `br` (0x1801a30e8) | 真の側 `dec_label_pc_1801a3198`、dsm の jbe 飛び先 0x1801a31e0 と不一致 |
| before.0.drc.ll 内の `dec_label_pc_1801a31e0` | 0 件 |
| before.0.drc.ll 内の `switch` (`function_1801a30d0`) | 0 件 |
| audit (before) `jmptable` | `jt_dropped=1 jt_present=7` (`audit_before.txt` と一致) |

## 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| RetDec の before 段階で jump table 入口 jcc (0x1801a30e8) の真の側が ret ブロックへ誤結線される機構の、RetDec 内の発生段 (CFG 構築 / LLVM 変換 のどこか) は未特定 | 残件 1 件 (0x1801a31fb)。修復方針が RetDec 側か前段か未確定 | #1885 のコメントで残件として明記 (本 PR は調査記録のみ) |
| 0x1801a2c92・0x1801a2f36 (jmp r11) の入口飛び先も before IR に無い。同型かは未検証 | 本 audit の jmptable 集計外 (jt_present/jt_dropped 対象外) の可能性 | 子 issue の候補 (本 run では起票しない: 実装作業ではなく再測定・検証のため、PR 本文の未解決表に残す) |
| DEFECTS.md への新類型行 | 「分岐の真の側が ret ブロックへ誤結線」の類型行案 (下記) | PM 判断 (DEFECTS.md は PM が編集) |

### DEFECTS.md 類型行案

| 項目 | 内容 |
|---|---|
| 症状 | jump table 入口の jcc の真の側が RetDec の before IR で ret ブロックへ向き、dispatch ブロックが消える。audit は `jt_dropped` |
| 根本原因 | RetDec の before 段階で、jcc の飛び先 (dispatch 入口) が CFG 上の別ブロックへ張り替えられる (発生段は未特定) |
| 観測 | OTT F `function_1801a30d0` の `jbe 0x1801a31e0` → IR `br i1 %0, label %dec_label_pc_1801a3198` (本 REPORT の表) |
| 検出信号 | 機械語 jcc の飛び先ラベルが before IR に無い。jmp reg の直上 jcc の飛び先ラベル欠落 |
| 修復 | 未定 (RetDec 側の CFG 構築が正しい飛び先を保つよう修正するか、前段で jcc 飛び先を固定する) |
