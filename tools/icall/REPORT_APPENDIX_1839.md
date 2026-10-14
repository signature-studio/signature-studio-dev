# REPORT_APPENDIX_1839 — OTT F の jt 比較列 switch 畳み込みと audit 判定 (ICALL-42)

親: #1763 (ICALL-38) / 前提: `tools/icall/REPORT_APPENDIX_1763.md` (#1763 ブランチ) の切り分け。

## 結論

- 8 jmptable site のうち **7 件は、RetDec が比較列を `switch` に畳んだ結果、区間内の `!insn.addr` が 0 件になっていた**。
  畳み込み後の区間終端 (new) が `switch` の default 先と一致し、case 数 = targets − 1 で対応する。`jt_dropped` は
  addr 消失による誤判定だった (jt 比較列は生成されて存在する)。
- 0x1801a31fb は before 段階から `jt_dropped` で、switch も default 一致も無い。別機構として残す (未解決)。
- 修正方針: `ir_icall_restore.py` で addr を捏造しない。audit 側で「畳み込まれた jt」を `jt_folded` として分けて数える。
  addr の復元は行わない (復元すると RetDec の switch 出力を書き換える必要があり、検証範囲が広がるため)。

## 畳み込み前後の突合 (OTT F, 測定 commit は下記)

新区間は `map.json` の `insn_ranges` (new, len, orig)。default は `after.0.drc.ll` の `switch` 終端ラベル。

| jmp site (orig VA) | targets | 新区間 (new) | 区間内 addr | switch default == 区間終端 | switch case 数 |
|---|---|---|---|---|---|
| 0x18011e279 | 9 | 0x18030b095 (146 B) | 0 | yes | 8 |
| 0x18011e5c2 | 17 | 0x18030b75e (274 B) | 0 | yes | 16 |
| 0x18011e7d1 | 3 | 0x18030bf11 (50 B) | 0 | yes | 2 |
| 0x18011e83d | 20 | 0x18030c039 (322 B) | 0 | yes | 19 |
| 0x180120b1d | 11 | 0x180310a19 (178 B) | 0 | yes | 10 |
| 0x1801a2a4b | 16 | 0x180313eb7 (258 B) | 0 | yes | 15 |
| 0x1801a31fb | 17 | 0x180314c7d (274 B) | 0 | **no** | — |
| 0x1801ac729 | 5 | 0x18031a7b9 (82 B) | 0 | yes | 4 |

before IR は `switch` 40 件すべてに `!insn.addr` が無く、畳み込みは after で初めて addr を落とす。

## 判定ロジックの検証

- 全 `switch` 48 件のうち、default が jt の区間終端に一致するのは jt の 7 件のほか、jt でない区間の終端に一致する
  switch が多数ある。`jt_folded` は `o in jt_vas` (jmptable site) のガードで除外され、偽陽性は 0。
- 0x1801a31fb の区間終端 (0x180314d8f) に一致する switch は無い (近傍の `0x180314d91` は case 16 で別の switch)。

## 実測

測定 commit: `09ed7bbc` (audit 変更を含む最後のコード commit)。素材: `work-icall` の `rt_ott-F` (after.0.restored.ll / map.json / F.ranges)、
`analysis-ott-binaries` の `OTT_vst2_win64.dll`。

| 入力 | `--map` | jmptable (before) | jmptable (after) |
|---|---|---|---|
| 修正前 audit (origin/main の `audit_icall.py`) after.0.restored.ll | — | — | `jt_dropped=8` |
| 修正後 audit before.0.drc.ll | 指定 | `jt_dropped=1 jt_present=7` (issue 本文と一致) | — |
| 修正後 audit after.0.restored.ll | 指定 | — | `jt_dropped=1 jt_folded=7` |
| 修正後 audit after.0.restored.ll | 未指定 | — | `jt_dropped=8` (後方互換) |

修正後 after の call 行: `kept_indirect=81 resolved_direct=67 other_insn=0 dropped=0 => lost 0 (非IAT 0) | tail-jmp 11 (lost 0) | jmptable 8 (dropped 1, folded 7)`

## 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x1801a31fb が before 段階で `jt_dropped` (switch 無し・default 不一致・jmp VA が before IR に無い) | 残件 1 件。受入条件「jt_dropped=0 または説明可能な残件数」の説明可能な残件 | #1839 (本 PR のスコープ外として残す) |
