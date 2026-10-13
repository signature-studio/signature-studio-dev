# 付録: icall #1206 — jump table の cmp/je 展開の効果 (ICALL-21, 測定 commit `f7bebc7b`)

> 本書は #1206 の全文 (旧 `REPORT_APPENDIX.md` §17 相当)。`REPORT_APPENDIX.md` は 250 行上限 (`docs/DOC_MAP.md` §1) のため §17 の本文を本書に分割移動した (内容は無変更)。

---

## 17. #1206 (ICALL-21): jump table の cmp/je 展開の効果 (測定 commit `f7bebc7b` = main)

素材 `fl-win64` (`block00031_PE.bin`・`block18983_PE.bin`)・`toolchain-retdec`。再現 `tools/icall/roundtrip.sh <PE> <F> <label> <outdir>`。foreground、load 0.54。

- FLEngine: `.pdata` 関数 `0x40d210--0x40d31b`。`jmp [r10+rdx*8+0x40]` (9 target) は before/after とも `jmptable 1 (dropped 0)`。`rewrite.txt` は `jt-chain 0`。`jt` 展開は `jmp reg` にしか掛からず、メモリ形には掛からない (`icall_rewrite.py` L579)。効果は構造上 0 で、落ち site の増減は測れない。範囲 `0x40d253--0x40d31b` で流すと関数境界を外して `indexed` 判定になるため、必ず `.pdata` 範囲を使う。
- Fruity Balance (`bal_ranges.txt`, 36 s 未満): before 非IAT call 35・落ち 35 (dropped 34) → after 0。jump table 0 件。jt 展開は対象外。
- Fresh Air (`work-icall` `rt_freshair-core/sites_after.json`): jt_dropped 2 件 (`jmp r9`, 16 / 17 target)。ただし `audit_fa.json` の `jmptable_dropped` は 1 で不一致。原因未確定。Fresh Air 本体は `plugins-freshair` 未取得のため再実行していない。
- OTT F (`work-icall` `rt_ott-F/sites_after.json`): jt_dropped 8 件、全て `jmp reg` (r8 ×3, r9 ×2, rcx ×3)。`jt` 展開の対象。OTT 本体の再実行は本 run で未実施。

| 対象 | jump table 件数 | jt_dropped | 形 | 展開 pass の対象 | 実測 |
|---|--:|--:|---|---|---|
| FLEngine 0x40d253 | 1 | 0 | `jmp [mem]` | 対象外 | before = after |
| Balance | 0 | — | — | — | 監査のみ |
| Fresh Air | 2 (`sites_after.json`) / 1 (`audit_fa.json`) | 不一致・原因未確定 | `jmp r9` | 対象 | 未再実行 |
| OTT F | 8 | 8 | `jmp reg` | 対象 | 未再実行 |

未解決: (1) メモリ形 `jmp [r10+rdx*8+d]` への `jt` 展開対応と FLEngine の効果測定 → #1402 (ICALL-26)。(2) Fresh Air の jt_dropped を素材付きで再実行し、2 件 (`sites_after.json`) と 1 件 (`audit_fa.json`) の不一致の原因を確定する → #1403 (ICALL-27)。不一致は原因未確定のまま、どちらの件数が正しいかは本 run では判定していない。
