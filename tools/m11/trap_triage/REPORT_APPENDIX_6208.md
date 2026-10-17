# REPORT_APPENDIX_6208: 証拠表の行 78 の判定 (#6208・#5845 の子)

REPORT_718 §4o の正本 (#6208 分)。判定は**確定 0 件・保留 1 件** (行 78)。真陽性 0・偽陽性 0。
偽陽性率は母数 288 の判定が終わるまで書かない。

## 1. 結論

- 行 78 (`function_12e21a0`・`12e227e: jg 12e22b7`・機械 `ee167e`) は**保留**。
- 段数差を機械語と IR の両方で再確認した: 機械語は count を `[[cell]+0xd34]` の 3 段で読み、IR は `load i32 [cell]` を pointer として使う 2 段で読む。IR の読み出し経路は機械語と同じではない。ただし、これが lift 段の deref 脱落か IR 解釈の差かは未確定のまま。
- 段数差は本 run で再確認した (機械語 3 段・IR 2 段)。ただし、lift 段の欠落か IR 解釈の差かは**未確定**のまま (`REPORT_APPENDIX_5845` と同じ)。同型の既判定は `ldfix/results/manual_verdicts_510.jsonl` の TRUE_DROP (`11d47c0`・`100a3d0`)。
- 残る論点: 機械語の count==0 脱出 (`jg` の先) が**到達するか**。到達すれば真陽性 (構造)、しなければ偽陽性寄り。count==0 の到達は未確認のため、保留とする。PM 判断に戻す。

## 2. 入力と再現

- 本 run (fix モード・round 1 への対応) では `work-m11` が `$ARTIFACTS_DIR` に無く、`fl-win64` のみだった。よって IR の再検証 (`%14`・`%16`・`%29`・`%45`・`%46`・`%47`) と scan_guard / judge_dump の再現は、本 run では実施していない。PR 本文の `oc_artifacts: fl-win64 work-m11 work-liftdiff` で次のレビュー run に素材を渡す。
- 測定 commit: `b912d309f` (origin/main)。本 PR はコードを変えていない (`git diff b912d309f HEAD -- tools/m11/guard699 tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_dump.py` の出力は 0 行)。
- 素材: `fl-win64` の `block00031_PE.bin` (sha256 `b2c64da4…`)、`work-m11` の `tools/m11/work/boot_final.ll` (sha256 `69c774de…`)。どちらも REPORT_APPENDIX_5845 と一致。使った系統は `69c774de…` (`597757f4…` は素材に無い)。
- 再現 (foreground・各 1 回・rc 0): `scan_guard.py` で strict 288 (4.4 s)、`strict_evidence.py` で TSV 288 行 (13.1 s)、`judge_dump.py <IR> <TSV> 78 78` (rc 0)。
- 逆アセンブル: `objdump -D -b binary -mi386:x86-64`・file offset = VA − 0x400C00。

## 3. 機械語と IR の対応 (行 78)

| 項目 | 機械語 (file offset) | IR (`function_12e21a0`) |
|---|---|---|
| count1 (入口 guard) | `ee1621`〜`ee1638`: `[cell]`→P, `[P]`→Q, `[Q+0xd34]` を `call 0xaa6230` (= `function_ea6e30`) | `%4 = load i32 [cell]` (幅 i32)→`%5` sext→`%8 = load i64 [P+3380]`→`%14 = ea6e30(%8)`→`%16 slt 1` (`dec_label_pc_12e221e`) |
| count2 (ループ前) | `ee1667`〜`ee166e`: 同じ 3 段 (qword) | `%29 = ea6e30([P+3380])` (`dec_label_pc_12e222e`) |
| ループ guard | `ee167c: cmp %esi,%ebx`・`ee167e: jg ee16b7` (esi = count2−1)。`ebx=0` のとき `jg` が成立してループを飛ばす。つまり機械語は count2==0 を明示的に判定する | `%47 = icmp eq %46, 0` (`dec_label_pc_12e2285`)。`%46` の SSA 追跡 (count2 `ea6e30([P+3380])` まで) と、この `icmp` の分岐先は**本 run では未実施** (`work-m11` が `$ARTIFACTS_DIR` に無い)。既存記録 (REPORT_APPENDIX_5845) の値で、再確認していない |

- 読み出し段: 機械語は 3 段 (`[cell]`・`[P]`・`[Q+0xd34]`)、IR は 2 段 (`[cell]` を i32 で読み、その値を pointer として `+3380` を読む)。`[P]` の deref が IR で脱落し、cell の幅も i32 に縮んでいる。
- 同じ cell (file offset `0x11e29c8` = VA `0x15e35c8` (18757064)) を機械語が pointer 2 段で読む同型は `ldfix/results/manual_verdicts_510.jsonl` の TRUE_DROP (`11d47c0`・`100a3d0`) と一致する。
- 呼び出し `ee1644`〜`ee1658` (`0x173c0` = `function_417fc0` → `function_417b70`) の中で、`[Q+0xd34]` を書く経路は未確認。count1 と count2 が機械語で一致するかは、この呼び出しの副作用に依存する。

## 4. 残る論点 (PM 判断)

- 機械語では count2 が 0 のとき `jg` で脱出する (ループを飛ばす)。これは §3 の機械語の事実。
- IR 側の count==0 の扱いは本 run では確定しない。`%47 = icmp eq %46, 0` の存在と「IR で count2 が 0 でもループに入り `%45 = r − 1` が 0xffffffff へ回る」は既存記録 (REPORT_APPENDIX_5845) の主張で、`%46` の SSA 追跡 (count2 まで) を本 run で再確認していない。この主張は本 run の根拠にしない。
- count2 が 0 になるかどうか (`[Q+0xd34]` の要素数の値域と、`function_417b70` が書き換えるか) が決まれば、真陽性 (構造) か偽陽性かが決まる。
- 確認できれば: count==0 が到達 → 真陽性 (構造)。到達しない → 偽陽性。
- 未解決: count==0 の到達 (`[Q+0xd34]` の値域・`function_417b70` の副作用)。行 78 は #6208 の受入条件の一部のため、追跡先は #6208 自身とする (#6208 は open のまま残る。親 #5845 の残件は行 81・82)。子は起票しない・1 件の確認に収まるため。
