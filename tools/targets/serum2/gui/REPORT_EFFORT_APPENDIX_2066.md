> **付録**: `REPORT_EFFORT.md` §14 (#2066 / SR-37) の本文。行数上限 250 行のため分割移動 (内容は削除していない。測定値は `REPORT_SR37.md` が正本のため本文から外した)。

## 14. 2026-10-14 run (#2066 / SR-37): XferOnOffButton の .text 対応付けと本体バイト数

- 結論: vtable 由来の override・新規 8 関数 (`XferOnOffButton`) の .text 対応付けと本体バイト数は `gui/REPORT_SR37.md` §0・§2 が正本。呼び出し先の閉包は未測定。人日は出さない。
- 詳細 (表・再現手順・限界): `gui/REPORT_SR37.md`。測定スクリプト `gui/vtable_fn_addrs.py`・`gui/ghidra_fn_size.java`。
