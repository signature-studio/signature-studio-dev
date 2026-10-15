# REPORT_APPENDIX_3498 — #3498 の証拠表 行 4〜35 の件ごとの表と判定規則 (REPORT_718 §4h の全文)

> **正本**: 本付録。`tools/m11/trap_triage/REPORT_718.md` §4h は要約と参照のみ (250 行上限のため分割移動。本文は無変更)。

## 4h. 証拠表の行 4〜35 (#3498・母数 32 件: 真陽性 0・偽陽性 0・保留 32)

- 母数: `strict_evidence.tsv` のデータ行 4〜35 (ヘッダ除く 1 始まり) の 32 件。判定: **真陽性 0・偽陽性 0・保留 32**。確定した件数が 0 のため、偽陽性率は書かない。
- 撤回: 前版の「真陽性 29・偽陽性 0・保留 3」を撤回する。前版の真陽性は、下記 3 の (a)(b)(c) を REPORT に書かずに付けたものだった。前版の訂正 (行 11〜16・19 の保留からの付け替え、行 12 の偽陽性からの付け替え) も撤回する。
- 保留の理由: 下記 3 の (b)(c) は IR の SSA 値の追跡を要する。本 run には `work-m11` の `boot_final.ll` が無く (`$ARTIFACTS_DIR` は `fl-win64` のみ)、追跡を実行できなかった。よって本 run では IR に基づく判定は 1 件も確定していない。
- 入力 (本 run では未使用): `work-m11` の `boot_final.ll` (19,787,837 B・sha256 `69c774de…`。前版の記録)、`fl-win64` の `extracted/block00031_PE.bin`。
- 測定 commit (PR の基点 origin/main `04c0332d8`): 本 run でコードは変えていない。`git diff 04c0332d8 HEAD -- tools/m11/guard699/ tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_dump.py` = 0 行。
- 判定規則 (件ごと。文言は変えない。(a)〜(c) を真陽性の必要条件として明記する):
  1. 機械語: jcc 直前の cmp の被演算子 (a) と条件コードを取る (`judge_dump.py` の MACH)。
  2. 機械的な前提 (`judge_entry_check.py`): jcc ブロックの終端が無条件 `br` で loop head に入るか、脱出先ラベルの preds が何か。
  3. 対応の確認: (a) に対応する alloca / SSA 値 (b) を IR で遡って結び、入口 (loop head に入る経路) に (b) の判定 (icmp) が無いこと (c) を示す。
  4. 真陽性 = (c) が成り立ち、かつ入口から脱出先への直接の経路が IR に無い。偽陽性 = (b) と同じ値の同等判定が IR 側にある。保留 = (a)(b)(c) のどれかを REPORT に書けない。
  - 真陽性は (a)(b)(c) を REPORT に書けた行だけに付ける。
- 判定 (件ごと): 下表。全 32 行が保留。「前版の記録」列は前版 run の記録で、本 run では再現していない。(b)(c) は全行で未確認。

| 行 | 関数 | jcc → 脱出先 | 判定 | 前版の記録 (本 run で未再現) |
|---|---|---|---|---|
| 4 | function_100bb90 | 100bcf4 → 100bd4d | 保留 | `ecx(=0)` vs `r14d`。脱出先 preds は 100bd39 (本体後) のみ |
| 5 | function_1017ca0 | 1017d39 → 1017df9 | 保留 | `ebx(=0)` vs `r13d`。関数内に符号付き比較なし。preds 1017de8 (本体後) |
| 6 | function_1018db0 | 1018e1a → 1018e68 | 保留 | `eax(=0)` vs `edx`。preds は本体内の 2 辺 (1018e5e・1018e4e) |
| 7 | function_1042d20 | 1042fe8 → 10431af | 保留 | `ecx(=0)` vs `esi`。preds 1043140 (本体後) |
| 8 | function_1042d20 | 10431cf → 1043ef7 | 保留 | `edx(=0)` vs `N-1`。preds 1043eda (本体後) |
| 9 | function_1045410 | 104555b → 1045713 | 保留 | `ecx(=0)` vs `r14d (N-1)`。preds 10456fd (本体後) |
| 10 | function_1046a30 | 104c70a → 104c744 | 保留 | `[rbp+0x580](=0)` vs `ebx (N-1)`。preds 104c711 (単一ブロックの末尾判定) |
| 11 | function_1050f90 | 1050fc7 → 105103e | 保留 | `r13d(=0)` vs `eax`。preds 1051039 (本体後)。前版は真陽性。12 と同じ根拠 (同値の確認なし) |
| 12 | function_1050f90 | 10510cf → 105112e | 保留 | `r13d` vs `eax`。preds 1051129 (本体後の `%91 = icmp sgt`)。被演算子の同一性は未確認 |
| 13 | function_1060950 | 1060973 → 10609d8 | 保留 | `r13d(=0)` vs `r14d`。head の `icmp slt` は本体内の分岐。preds 10609cb (本体後) |
| 14 | function_10609f0 | 1060a06 → 1060a25 | 保留 | `esi(=0)` vs `edi (N-1)`。preds 1060a0d (後端の計数判定) |
| 15 | function_1060d20 | 1060d3d → 1060d65 | 保留 | `esi(=0)` vs `edi`。preds 1060d5b (本体後の計数)。head の icmp は byte の符号で別値 |
| 16 | function_10624d0 | 10624f1 → 106262a | 保留 | `ebx(=0)` vs `edi (N-1)`。preds 106261c (本体後の計数) |
| 17 | function_10c7cd0 | 10c8d17 → 10c8d6b | 保留 | 被演算子 `[rbp+0x774]-1` の IR 側の slot を特定できない |
| 18 | function_10c7cd0 | 10c8dc4 → 10c8e18 | 保留 | 被演算子 `[rbp+0x76c]-1` が stack 変数経由で、IR の対応を一意に確定できない |
| 19 | function_1185da0 | 1185dfe → 1185e7d | 保留 | `ebx(=0)` vs `r13d (N-1)`。preds 1185e71 (本体後) |
| 20 | function_1185e90 | 1185eea → 1185fd6 | 保留 | `ecx(=0)` vs `r14d (N-1)`。preds 1185fbe (本体後) |
| 21 | function_11862e0 | 1186323 → 11863bd | 保留 | `esi(=0)` vs `r14d`。preds 11863ad (本体後) |
| 22 | function_1189310 | 11893a0 → 11893dc | 保留 | `ebx(=0)` vs `edi (N-1)`。preds 11893a7 (head の後端判定) |
| 23 | function_1192da0 | 1192dc9 → 1192e08 | 保留 | `ebx(=0)` vs `esi (N-1)`。preds 1192dfe (本体後) |
| 24 | function_11c9930 | 11c99af → 11c9a17 | 保留 | `ebx(=0)` vs `edi (N-1)`。preds 11c99b6 (head の計数判定) |
| 25 | function_11e6e20 | 11e6e60 → 11e6ef5 | 保留 | `ebx(=0)` vs `r10d`。preds 11e6ee5 (本体後) |
| 26 | function_11e7860 | 11e788b → 11e7907 | 保留 | `esi(=0)` vs `r13d (N-1)`。preds 11e7894 (head の計数判定) |
| 27 | function_11e7fa0 | 11e7fbd → 11e802b | 保留 | `ebx(=0)` vs `esi (N-1)`。preds 11e8021 (本体後) |
| 28 | function_11e8280 | 11e82b1 → 11e82ec | 保留 | `r13d(=0)` vs `r14d (N-1)`。preds 11e82d5・11e82df (本体内)。入口の判定は byte==0 で別値 |
| 29 | function_11e84a0 | 11e8505 → 11e8541 | 保留 | 入口 `N-1 < arg1` (%8) は N-1 を共有するが、比較相手は arg1 で機械語の `N-1 < 0` と別 |
| 30 | function_1221840 | 122193e → 122196f | 保留 | `ebx(=0)` vs `esi (M-1)`。preds 1221965 (本体後) |
| 31 | function_1221840 | 122199b → 1221a3f | 保留 | `ebx(=0)` vs `edi (M-1)`。preds 1221a31 (本体後) |
| 32 | function_1221bc0 | 122251f → 122272f | 保留 | `ecx(=0)` vs `r13d (M-1)`。preds 1222545 (本体内) |
| 33 | function_1223020 | 12230df → 122330f | 保留 | `ecx(=0)` vs `r13d (M-1)`。preds 122310b・12232f7 (本体内) |
| 34 | function_1251590 | 1251621 → 12516a2 | 保留 | 外側添字 `ebx(=0)` vs `edi`。preds 1251698 (本体後) |
| 35 | function_1251590 | 1251728 → 12517db | 保留 | `ebx(=0)` vs `esi (N2-1)`。preds 12517cd (本体後) |

- 未解決 (起票先: #3498 本 issue、`Refs`): 32 件の (b)(c) の確認。`oc_artifacts: fl-win64 work-m11` で取得した run で、行ごとに (a)(b)(c) を REPORT に書く。確定できた行だけを真陽性にする。次の一手: 行 17・18 は `[rbp+0x774]`・`[rbp+0x76c]` を IR の `stack_var_` に対応づける。行 29 は脱出先 `11e85fc` と `11e8541` の後続を比べる。

