# 付録: icall #1014 (ICALL-15) — FLEngine 2 関数の落ち 366 site のブロック単位 before / after 分類

> 親: #847 (ICALL-9)。受入条件 1 (SCCP の機構特定) は PR #1250 で達成済み (`REPORT_APPENDIX.md` §12.3)。本付録は受入条件 2 (ブロック単位の before / after 分類) の結果。受入条件 3 (修正と kept の実測) は未達 (§4)。
> 既知類型との関係 (`docs/DEFECTS.md`): **該当なし**。

## 1. 結論

- 落ちた 366 site は**全て消失**。別関数へ移ったものは 0 (落ちた site のブロック label は、どの関数の段にも現れない)。
- 両関数とも同じ段の流れになる (段番号は `--print-after-all` の dump 順):
  1. GVN 段 (function_1cc0000 は 401、function_1cc9b70 は 402): stub 呼出しを含むブロックは 114 / 121。
  2. SCCP 段 (405 / 406): stub 呼出しが消える。ブロック数は変わらない (303 → 303、316 → 316)。
  3. Jump Threading 段 (413 / 414): 落ちた site のブロック 114 + 114 が消える。ブロック数は 303 → 29、316 → 42。
- 残る kept 8 site (function_1cc9b70 の 6 ブロック) は最終 IR まで残り、restored IR の `__icall_dispatch` 8 件と一致 (`REPORT_APPENDIX.md` §12.4.1)。

## 2. 測定

- 測定 commit: `29ae3986` (分類スクリプト `tools/icall/sites_block_classify.py` を追加した commit)。
- 入力: `measure_flengine_split.sh` の出力 (HEAD `26f90ada`、素材 `fl-win64` の `block00031_PE.bin`、4 core)。
  - `measure_flengine_split.sh`: real 130.4 s。base 366 / c2 366 (基準どおり)。site 374 (0xc589b0 側 183 / 0x128f9e0 側 191)。
  - 段 dump: `passes_stub` 709 段。
- `sites_block_classify.py` (`29ae3986`): real 67.3 s (user 20.6 s / sys 46.8 s)。RetDec v5.0 (`/opt/retdec`) で段 dump を 1 回取り、709 段を関数ごとに解析する。
- 段 dump の stub と site の対応: 全 stub 呼出しには `!insn.addr` が付く段がある (段 81 〜 100 の全モジュール段。以後は関数別モジュールになり付かない)。その最後の段 100 (`Global Variable Optimizer`) の stub 375 件のうち 374 件が site と 1:1 に対応した。残る 1 件は comis stub (`function_1cd3fe0`)。
  - 対応規則: stub の `!insn.addr` は `sites[].new` の直後 (+78 バイトが 367 件、+81 バイトが 7 件)。最寄りの下位の `new` へ割り当てる。
  - 段 81 を使うと、段 81 〜 100 の間の block 組み直しで 12 site の label が変わる。GVN に近い段 100 を採用した。

## 3. 結果

| 関数 (lift 名) | 元 VA | site | dropped | kept | stub を含むブロック (GVN 段) | stub 呼出し (GVN → SCCP) | ブロック数 (GVN → SCCP → JT) |
|---|---|--:|--:|--:|--:|--:|--:|
| `function_1cc0000` | 0xc589b0 | 183 | 183 | 0 | 114 | 183 → 0 | 303 → 303 → 29 |
| `function_1cc9b70` | 0x128f9e0 | 191 | 183 | 8 | 121 (site を含む 120 + comis 1) | 192 → 9 | 316 → 316 → 42 |

- 全 234 ブロック (site を含むラベル) で、そのブロックに含まれる site 数 = GVN 段のそのブロックの stub 数 (不一致 0)。
- 落ちた 228 ブロックは、SCCP 段で stub 呼出しが 0 になり、ブロック自体は残る。Jump Threading 段で消える (最初に消えた段は全件 Jump Threading)。
- kept 6 ブロック (function_1cc9b70) は SCCP 後も Jump Threading 後も残る。SCCP 後の stub 9 = kept 8 + comis 1。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入条件 3: 畳み込まれた switch 枝の動的検証 (native で `g22 > 1` を通す入力) と、修正して kept を減らす実測 | 366 site が真の死コードか lift 欠陥かが未決。修正方針を決められない | #1014 (継続) |

## 5. 検証

- 再現: `FL_WIN64_DIR=<fl-win64 展開先>/extracted bash tools/icall/measure_flengine_split.sh <outdir>` の後、`python3 tools/icall/sites_block_classify.py <outdir>/base/rw.dll <outdir>/base/after.ranges <outdir>/base/map.json <outdir>/base/sites_after.json <outdir2>`。段 dump は `<outdir2>/print_after_all.txt` に残る。
- `29ae3986` で再実行した `summary.txt` と `site_block.tsv` は、作業ツリー版の出力と `cmp` で一致。
- 測定経路の差分 (`git diff --stat 26f90ada 29ae3986 -- tools/icall/measure_flengine_split.sh tools/icall/roundtrip.sh tools/icall/audit_icall.py tools/icall/icall_rewrite.py tools/icall/ir_icall_restore.py tools/icall/passes_stub_count.py tools/icall/sccp_stub_drop.py`) は出力 0 行。
- コード差分 (`git diff 29ae3986 HEAD -- tools/icall ':!*.md'`) は本付録の変更後も出力 0 行。
