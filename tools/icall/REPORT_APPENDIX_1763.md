# REPORT_APPENDIX_1763 — OTT F の jt_present→jt_dropped 遷移 (ICALL-38)

親: #1763 / 前提: #1573 (ICALL-31) の roundtrip 再実行 (`jt_dropped=8`)。

## 結論

8 site の遷移について、切り分けの結果は次のとおり。

- **rewrite 側の比較列 (`jt` 展開) は 8 site とも生成されている** (`rewrite.txt` `jt-chain 8`)。case 数も targets 数と一致する。
- after の IR では、その比較列の new 区間に `!insn.addr` が **8 site とも 0 件**。audit はこれで `jt_dropped` と判定する。
- 比較列は RetDec 出力で `switch` に畳まれ、`switch` 自体には addr が付かない。**「畳み込みで addr が消えた」が最有力だが、畳み込み前後の IR を直接突き合わせて確定させてはいない**。
- audit の判定 (addr の有無) は、IR に残っている事実を数えている。判定ロジックの誤りは見つからなかった。
- 修正 (switch に畳まれた比較列の区間から addr を復元する) は `ir_icall_restore.py` 側になりうるが、本 run では未実施。
→ 未解決 (起票先: 子 issue。下記)。

## 実測

素材: `work-icall` (`rt_ott-F` = after、`rt_ott-F271` は別 run の参照)、`analysis-ott-binaries` の
`plugins/ott/binaries/OTT_vst2_win64.dll` (3,146,752 B)。

before は `audit_icall.py --pe OTT_vst2_win64.dll --funcs F.ranges --ir rt_ott-F/before.0.drc.ll` で再実行した
(issue 本文の before 集計 `jt_present=7`・`jt_dropped=1` を再現)。after は `rt_ott-F/sites_after.json` の値を使った。

| jmp site (orig VA) | 形 | targets | before | after |
|---|---|---|---|---|
| 0x18011e279 | jmp r8 | 9 | jt_present | jt_dropped |
| 0x18011e5c2 | jmp r8 | 17 | jt_present | jt_dropped |
| 0x18011e7d1 | jmp rcx | 3 | jt_present | jt_dropped |
| 0x18011e83d | jmp rcx | 20 | jt_present | jt_dropped |
| 0x180120b1d | jmp r8 | 11 | jt_present | jt_dropped |
| 0x1801a2a4b | jmp r9 | 16 | jt_present | jt_dropped |
| 0x1801a31fb | jmp r9 | 17 | **jt_dropped** | jt_dropped |
| 0x1801ac729 | jmp rcx | 5 | jt_present | jt_dropped |

- before 段階で既に `jt_dropped` だったのは 0x1801a31fb の 1 件。残り 7 件が before `jt_present` → after `jt_dropped` に遷移した。この 1 件と遷移 7 件は別機構として扱う (本 run では未切り分け)。
- rewrite は 8 site すべて `jt-chain` 展開 (`rewrite.txt`: `jt-chain 8`)。`map.json` の `insn_ranges` で各 jt 比較列は元 VA に区間対応づけられている (例: 0x18011e279 → new 0x18030b095, 146 B)。

## 機構の根拠

1. `icall_rewrite.py` L591-596: `jmp reg` の jt site は `('jt', reg, targets)` テンプレートで `lea r11,[rip+target]; cmp reg,r11; je` の列に置き換える。展開は正しく、case 数は targets 数と一致する。
2. after の RetDec 出力 (`after.0.drc.ll`) では、この比較列が `switch i32 ... [ i32 <case>, label ... ]` に畳まれる (例: 関数 `@function_18030b030`、case 8 件)。
3. RetDec の出力では `switch` 命令に `!insn.addr` は付かない (before/after 全 switch 40/48 件とも addr 無し)。
4. 比較列の区間 (`insn_ranges` の new 区間) に入る `!insn.addr` メタは after IR で **8 site 全て 0 件**。
   audit はこの有無で `jt_present` / `jt_dropped` を決めるため、8 site が `jt_dropped` になる。

よって「展開 pass が 7 site の IR を壊した」のではなく、「畳み込みで addr が消えた」。
`switch` の lift は RetDec 側の挙動で、audit の判定はそれを正しく記録している。

## 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| jt 比較列が RetDec で `switch` に畳まれ、区間の `insn.addr` が消える (8 site) | `ir_icall_restore.py` が addr を戻せず、addr 依存の監査・後段が jt site を落ちと数える | #1839 (ICALL-42) |
| 0x1801a31fb が before 段階で `jt_dropped` (機構未切り分け) | 切り分け対象の残り 1 件 | #1839 (ICALL-42) に含める |

## 検証

- 本 run はコードを変更していない (付録の追加のみ)。`tools/icall` のコード差分 0。
- 測定 commit: 本 run の測定元は `4c3f7458` (origin/main)。付録の内容は上記の再実行結果に基づく。
