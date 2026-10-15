# REPORT 付録 — #4645 (GUI-26): EnumDisplayMonitors callback `0x85df70` の icall miss

REPORT §6j の全文。要約と未解決は [REPORT.md](REPORT.md) §6j・§7 を参照。

## 1. 原因と対応

- 原因: `0x85df70` は `m11_extra_ranges5.txt` (boot5, #132) の範囲だが、素材 `work-m11` に `boot5.lift.ll` が無く、`e2e.sh` も boot5 を lift していなかった。そのため callback が IR に無く `m11_icall` が miss していた。
- 対応: `e2e.sh` が複製側 (`$TREE/m11`) で `m11_lift.sh m11_extra_ranges5.txt boot5` を実行するようにした (`m11_e2e.sh` #132 と同じ。元の `tools/m11` は読取のみ)。`judge.py` は無変更。

## 2. 実測 (boot)

- baseline / GUI とも `units_run 110` (旧 109)、`icall_miss 4` (旧 7)。miss 先は `0xfa9390` のみ (`0x85df70`・`0x457860` が解消)。
- 最終 head `b2be21337` の e2e: rc 1・`JUDGE FAIL (14/15)`。FAIL は B1 の `GetMem 774 (base 772)` のみ (詳細は [REPORT.md](REPORT.md) §6j)。B1 は最終 head で PASS しない。
- `results/` の現 head の出力 (`boot.json`・`baseline_boot.json`・`survey_*.json`・`ir_sha256.txt`) は、この e2e の実行結果で書き換えた。`survey_soft_chain.json` の `ok/trap/miss/icall_miss` は `875/20/46/46` で、本文の値と一致する。`mem_*`・`Halt0`・`MessageBoxA` の calls も変わっている (`git diff -- tools/gui/flengine/results/survey_soft_chain.json` で確認)。
- 解消は boot 経路で確認。残件 `0xfa9390` は子 #4730 (GUI-27)。

## 3. survey の値 (訂正)

survey には 2 つの結果ファイルがあり、値が違う。REPORT の旧記述 (「764/1/46/131」) は隔離版の値で、chain 版の値とは別物。

| ファイル | 測定 commit `f0235912` | 本 PR HEAD `dff7cda0d` | main `2d7331209` 側 |
|---|---|---|---|
| `results/survey_soft.json` (隔離版) | `ok/noproc/miss/trap` = 764/1/46/131 | 764/1/46/131 (不変) | 764/1/46/131 |
| `results/survey_soft_chain.json` (chain 版) | 875/1/46/20 | 875/1/46/20 | 872/1/47/22 |

- 隔離版 `survey_soft.json` は `f0235912` から HEAD まで不変 (`git diff f0235912 HEAD -- tools/gui/flengine/results/survey_soft.json` は差分 2 行の追記のみで、値は同じ)。
- chain 版は `f0235912` → HEAD で値が変わっていない。`origin/main` (`2d7331209`) との差は main 側の測定 (#4649 など) によるもので、本 PR の merge で PR 側を採った結果。
- chain 版の `icall_miss` (50 対 46)・`reach` (33 対 34)・`m11_stub_total` (200 対 203) も同じ理由で、本 PR の変更 (boot5 lift) の効果ではない。
- 旧 REPORT の 871 (`ok`) との差は既存の不整合で、子 #4731 (GUI-28) が原因を切り分ける。

## 4. 測定の鮮度

- 測定 commit `f0235912` 以降の `tools/m11` には差分がある (`git diff f0235912 HEAD -- tools/m11`: 19 files、+460/-21)。`m11_gen_ir2.sh` (`M11_FIX_LD236`)・`ldfix/ldfix.py` (`fix_f3c_use` の門。#4439) などが含まれる。
- 最終 head `b2be21337` は `tools/m11` の差分を含む状態で e2e を再測定済み (REPORT §6j)。素材は `oc_artifacts` 行の 5 点 (fl-win64・work-m11・toolchain-emsdk・toolchain-retdec・apt-mingw) を展開して使った。
