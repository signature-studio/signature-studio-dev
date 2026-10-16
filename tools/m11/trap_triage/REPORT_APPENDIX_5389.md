# REPORT_APPENDIX_5389: strict 候補の証拠表 行 78・81〜84 の保留 5 件の判定理由 (#5389)

REPORT_718 §4o の正本。親 #4886 (分割元)・前 run の停止報告 (#5389 コメント) の表を、判定理由つきで整理し直したもの。

## 1. 結論

- 母数 5 (証拠表 行 78・81・82・83・84)。真陽性 0・偽陽性 0・保留 5。
- 5 件とも保留のまま確定しない。理由は件ごとに異なる (§3)。
- 件 83・84 は機械語と IR で段数・幅が一致しない。lift 段の欠陥か、IR 側の解釈の誤りかは、本 issue では確定しない。判断は PM に戻す (PM 判断 `oc-pm-decision` の R7 既定案に従う)。
- 偽陽性率は母数 288 の判定が終わるまで書かない。

## 2. 入力と再現

- IR: `work-m11` の `tools/m11/work/boot_final.ll` (sha256 `69c774ded8aaf717…`)。もう一系統 `597757f4…` は素材に無く、使っていない。
- PE: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。
- 測定 commit: `e5261de58` (origin/main)。本 PR はコードを変えていない。`git diff e5261de58 HEAD -- tools/m11/guard699 tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_dump.py` = 0 行。
- 実行 (`e5261de58`・foreground): `scan_guard.py --pe ... --report strict.json` (4.7 s、strict 288)。`strict_evidence.py --out strict_evidence.tsv` (TSV 288 行)。`judge_dump.py <IR> strict_evidence.tsv <行> <行>` で 78・81〜84 をダンプ。
- 機械語は `objdump -D -b binary -mi386:x86-64` で PE の `VA-0x400000-0x1000+0x400` から切り出して逆アセンブル。

## 3. 件ごとの判定

| 行 | 関数 | jcc・脱出先 | 判定 | 理由 |
|---|---|---|---|---|
| 78 | function_12e21a0 | `12e227e: jg 12e22b7` | 保留 | 機械語は count を 2 回読む。1 回目の入口 guard `12e2228: jle 12e22d2` と 2 回目の `12e227e: jg 12e22b7` は本 run で逆アセンブルで確認。IR 側の対応 (入口判定のスキップ先・exit) は前 run (#5389 停止報告) の記録で、本 run では再照合していない。未確認は、間の `call 417fc0` を挟んだ 1 回目と 2 回目の count が同じ値か (IR の load 元の SSA 同一性)。 |
| 81 | function_1310300 | `13103e8: jg 1310460` | 保留 | count 源は同形に見える: 機械語は `[(%rsp)+0x818]+20*rax` の dword を読んで `-1` (`13103db`〜`13103e3`)、IR の `%59 = 20*rax + %27` の i32 load と同形。ただし同一性は未照合で、jcc の左辺は機械語 `ecx` (edx 由来で 0)、IR の比較は `%79`・`%89` 系で、SSA 対応が未確定。 |
| 82 | function_1311050 | `13110b2: jg 1311118` | 保留 | 機械語の count は間接呼び出し `call *0x28(%rax)` の戻り値。IR は `arg+2800` 起点の load 連鎖で、同じ源とは言えない。 |
| 83 | function_13114d0 | `1311555: jg 13115b7` | 保留 (段数・幅の不一致) | 機械語は `mov 0x2d0cd2(%rip)` → `[[0x15E2218]]` → `mov 0x10(%rcx),%esi` で、2 段・dword 読み。IR は `load i32 inttoptr 18752024` (`[0x11E2218]`) → `+16` の 1 段・dword。機械語の RIP 相対先 `0x15E2218` は IR の `0x11E2218` と ImageBase 分だけずれて一致するが、段数が 1 段足りない。 |
| 84 | function_13114d0 | `1311737: jg 1311784` | 保留 (段数の不一致) | 機械語は `[[0x15E0E00]+0x10]` の 2 段。IR は `[0x11E0E00]+16` の 1 段。83 と同型。 |

## 4. 機構の型

- 段数の不一致 (83・84): 機械語は間接参照を 2 段、IR は 1 段。lift 段で 1 段落ちたか、IR 側の解釈の誤りかは未確定。`ldfix/REPORT_2794.md` の類型と同型かは未確認。
- SSA 同一性の未確定 (78・81): count の源は同じ見込みだが、jcc の左辺と IR の icmp の値の対応を追っていない。
- 間接呼び出し (82): count が `call *0x28(%rax)` の戻り値。IR 側に同じ呼び出しが無く、比較できない。

## 5. 未解決

- 行 78・81: SSA 同一性と count 読みの同一性を確定する。
- 行 82: 間接呼び出しの戻り先の値を IR の何と対応させるかを決める。
- 行 83・84: 段数の不一致が lift 段の欠陥か、IR 側の解釈の誤りか。判断は PM に戻す。
