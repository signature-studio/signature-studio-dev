# REPORT #2705 — spill 宛 `128f9e0` 12 site の lift 段欠落の起点特定 (LD-125)

親: #2679 (LD-120)。前提: #2707 (merged)。子: 判定・到達経路・frame 照合は別 issue (§5)。
既知類型との関係: DEFECTS.md の D19 に近い (生 lift で欠落)。機構 (RetDec のどの段・どの処理が枝を付け替えたか) は未確定。

## 1. 測定

- 作業 worktree `ws-2705` (branch `2705-ld125-spill-128f9e0-sites`、起点 `origin/main` = `9dc017b5`)。コードを変えた commit は本 PR の `ld125_lift_gap.py` の追加のみ。
- 実行 (foreground):
  - `python3 tools/m11/ldfix/ld125_lift_gap.py` → rc=0。出力 `results/ld125_lift_gap_128f9e0.tsv`。
  - `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` → rc=0・real 3m01.8s・7/7 完了。`drops_510.tsv`・`spill178_1161.tsv`・修復後 IR の `spill178` が results/ と一致。load 0.97 (実行後の uptime)。
- 素材: `work-m11` と `work-liftdiff` を `tar --zstd -xf` で worktree `ws-2705` に展開 (gitignore 対象・commit しない)。
- 判定 (candidate_verdicts_1161.jsonl) は変更していない。`spill178_1161.tsv` は既存のまま。

## 2. 起点 (受入 1・2)

各段の IR (`function_128f9e0`) の label 数はすべて 35。lift・norm0・drc・final で同一の label 集合 (スクリプトは各段の `same set as lift: True` で照合する。この run では未再実行、下記 §1 参照)。欠落は lift 段で起きた。

機械語 (`0x1290580`〜) と IR の対応:

| 機械語 | 内容 | lift 段 IR |
|---|---|---|
| `0x12905af jne 0x1290610` | 分岐 (not taken → `0x12905b1`) | `br i1 %191, label 0x1290610, label 0x12905b1` |
| `0x12905b1`〜`0x12905da` | `je 0x1290645` | `br i1 %197, label %dec_label_pc_129460b, label %dec_label_pc_12905dc` ← **`0x1290645` ではなく `0x129460b` へ** |
| `0x1290610`〜`0x129063f` | block (bt/setb) → fall-through `0x1290645` | block 16 行、末尾 `br label %dec_label_pc_129460b` ← **`0x1290645` ではなく `0x129460b` へ** |
| `0x1290645`〜`0x129460a` | 後続 (12 site を含む・約 0x3c6 byte) | **IR に block が無い** |

- 起点: lift 段で、`0x1290645` を分岐先とする 2 本の枝 (`0x12905da je`・`0x1290610` の fall-through) が、どちらも `0x129460b` へ付け替えられている。`0x1290645`〜`0x129460a` の区間は IR から丸ごと欠落する。
- 欠落区間の始点は `0x1290645` (IR の `0x1290610` block が `0x129063f` で終わり、次の機械 leader がその後の `0x1290645`)。
- 確認: `0x1290645` の label は lift・norm0・drc・final のどこにも無い。`boot3.retdec.log` に `1290645` の文字列は無い。RetDec のどの処理が付け替えたかは未確定。
- 他の段: `boot3.drc.dsm` (RetDec の機械語表) では `0x12905da je 0x1290645` と `0x129060e jmp 0x1290645` が正しく残っている。これは IR に現れないだけ。

## 3. 欠落区間の出力 (`results/ld125_lift_gap_128f9e0.tsv`)

| 区間 | 機械 leader 数 | 備考 |
|---|---|---|
| `1290610`〜`129460b` | 376 | 本件 (IR の `0x1290610` block が次の label まで続く) |
| `128f9e0`〜`1290090`・`129010d`〜`1290178`・`12901ba`〜`12901db`・`12901fe`〜`129024a`・`129460b`〜`1294632`・`129466a`〜`129468f`・`129468f`〜`12946f9` | 1〜4 | 本件と無関係 (leader 数が小さく、12 site を含まない) |

12 site は全て `1290610`〜`129460b` の区間に入る (site 列の `where` 欄)。

## 4. 判定への含意 (受入 3 は未達)

- 12 site の store (`[rbp+d]`)・K の load・消費者 (`cmp [rbp+d],0`) は、全て欠落区間 `0x1290645`〜`0x129460a` の中にある。
- TRUE_DROP の既存型 (例: `4120c0`・REPORT_2264) は「IR に値の store / load はあり、消費者だけが脱落」が前提。今回は store と消費者の両方が欠けるため、この型に当てはまらない。
- TRUE_DROP / OK_LOAD / NO_CONSUMER は IR 上の結線 (store→load) が無いと立たないため、判定は UNDETERMINED のまま残した (`candidate_verdicts_1161.jsonl` は変更なし)。
- 判定を変えると `spill178` と drops の和集合 (69) が動く。本 PR は判定を変えず、判定は子 issue に移す。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 12 site の判定 (UNDETERMINED → TRUE_DROP / OK_LOAD / NO_CONSUMER)。欠落区間を IR に戻す修復 (lift 段の枝の付け替え) を含む | 128f9e0 の判定が UNDETERMINED のまま | 子 issue (本 PR の後に起票) |
| RetDec のどの処理が `0x1290645`→`0x129460b` を付け替えたか (機構) | 他関数の同型欠落の検出に影響 | 子 issue (同上) |
| 入口 `128f9e0` から 12 site への到達経路 (BFS の親) の記録 | 欠落区間の到達確認が未了 | 子 issue (同上) |
| frame 対応 F=2088 の照合 (site ごとの `stack_var_-(F-d)` 一致) | slot 名の誤りがあれば判定の根拠が覆る | 子 issue (同上) |
