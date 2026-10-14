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
| Fresh Air | 2 (`sites_after.json`) / 1 (`audit_fa.json`) | 不一致・原因は #1403 で確定 | `jmp r9` | 対象 | 再実行済 (下記) |
| OTT F | 8 | 8 | `jmp reg` | 対象 | 未再実行 |

### #1403 (ICALL-27) の追記: Fresh Air の件数不一致の原因

- 再実行: `roundtrip.sh` を `plugins-freshair` の SlateCore.core_64 に対して実行 (rc=0、38 秒、`work/rt_freshair-rerun/`)。
- サイト単位の before 判定 (`sites_before.json`): `jmp r9` @0x1810304bb = `jt_present` (16 target)、`jmp r9` @0x181030c6b = `jt_dropped` (17 target)。
- after 判定 (`sites_after.json`): 2 件とも `jt_dropped`。
- 件数不一致の原因: `audit_fa.json` は before 側の集計 (before の 2 件のうち 1 件が `jt_present`、1 件が `jt_dropped`) で、`sites_after.json` は after 側の集計 (2 件とも `jt_dropped`)。食い違いは集計の段階が違うことによる。
- 未解析: before で `jt_present` だった 0x1810304bb が after で `jt_dropped` になった機構 (rewrite 側か restore 側か) は本 run では切り分けていない。
- 結論: `jt_dropped` は before 1 件 / after 2 件。after の 2 件は rewrite 由来の可能性があるため、別途切り分けが必要。

未解決: (1) メモリ形 `jmp [r10+rdx*8+d]` への `jt` 展開対応と FLEngine の効果測定 → #1402 (ICALL-26)。(2) OTT F の jt_dropped 8 件の展開後残件数 → #1573 (ICALL-31) で実測済み。結果と数値は `REPORT_APPENDIX_1573.md`。
