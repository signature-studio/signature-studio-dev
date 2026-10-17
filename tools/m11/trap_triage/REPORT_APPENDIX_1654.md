# #1654・#1655: 証拠表の行 99〜288 の判定記録 (REPORT_718 §4c・§4e の分割移動)

本付録は REPORT_718 §4c (行 99〜193・#1654) と §4e (行 194〜288・#1655) の全文。250 行上限のため移動した (内容は削除していない)。

## 4e. 証拠表の行 194〜288 (#1655・部分達成: 判定 0 件・ダンプまで)

- 測定 commit: `b7a2a9d9` (origin/main)。`tools/m11/guard699/scan_guard.py`・`tools/m11/trap_triage/strict_evidence.py`・`judge_dump.py` はこの commit で変更されていない。
- 入力: `tools/m11/work/boot_final.ll` (19,787,837 B・`work-m11`) と `extracted/block00031_PE.bin` (22,227,016 B・`fl-win64`)。
- 実測: `scan_guard.py --report` で strict 288。`strict_evidence.py` で TSV 288 行を `tools/m11/work/strict_evidence_1655.tsv` に生成 (gitignore 対象・未コミット)。
- ダンプ: `judge_dump.py <IR> <TSV> 194 288` で 95 行を `tools/m11/work/judge_1655_dump.txt` に出力 (判定はしない)。
- 判定件数 (母数): **0 / 95**。偽陽性件数: **未判定**。偽陽性率は書かない。
- ダンプから機械的に言える事実 (判定ではない): loop_head に入口 icmp が 1 本も無いのは行 207・211・234・239・285 の 5 件。これは「真陽性の候補」ではあるが、IR 側に別名の判定がないことの確認 (SSA 追跡) は未実施。
- 判定方法 (件ごと・未実施): 機械語は jcc 直前の cmp/test の被演算子 (`MACH`) を取る。IR は `LH-icmp` と `BLK-term` の被演算子を SSA (`%<reg>.N.*`・`reg2mem` の alloca 経由) まで遡り、機械語の被演算子と同じ値に結べるかを見る。レジスタ名の一致だけでは根拠にならない。
- 残作業: 95 件の件ごとの判定 (受入 1・2)。本 issue (#1655) の範囲として未解決のまま残す。

## 4c. 証拠表の行 99〜193 (#1654・部分達成: 判定 0 件)

- 数値の出所 (未確定): 本節の内訳 (jcc・IR 終端・icmp 本数・95 件) は本 run で再現していない。`strict_evidence.py` は `088d9eaf` で導入され、その後 `e4f16b6e` で変更されている。数値を出した版の commit は特定できないため、前版の記録として扱い、確定値にしない。`git diff 088d9eaf HEAD -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py` は 0 行 (`guard699/` と `ldmach.py` は不変)。
- 入力: `work-m11` の `boot_final.ll` (本 run に無い)、`fl-win64` の `block00031_PE.bin`。
- 再実行: 未実施 (本 run。`scan_guard.py`・`strict_evidence.py` とも走らせていない)。
- 対象: データ行 99〜193 (ヘッダ除く 1 始まり) の 95 件。内訳は次のとおり。
  - jcc: `jg` 94 件、`jle` 1 件 (`function_a97930`)。
  - IR 側の帰属ブロック終端: 95 件すべて無条件 `br` (`br i1` 無し)。
  - loop_head の icmp 本数: 0 件 11、1 件 39、2 件 40、3 件 2、5 件 1、6 件 2。
- **判定件数 0 / 95・偽陽性件数 0 (判定未完)**。偽陽性率は未測定。
- 判定方法 (件ごと。未実施): 機械語は jcc 直前の cmp/test の被演算子を取る。IR は loop_head の icmp の被演算子を SSA (`%<reg>.N.*`) まで遡り、機械語の被演算子と同じ値に結べるかを見る。レジスタ名の一致だけでは根拠にならない (IR は `reg2mem` の alloca 経由で値を運ぶため、名前の一致と値の同一性は一致しない)。
- 試作した自動突合は、レジスタ名の一致だけで偽陽性にしてしまうためコミットしていない。
- 残作業: 95 件の件ごと判定 (受入条件 1・2)。本 issue (#1654) の範囲として未解決のまま残す。
