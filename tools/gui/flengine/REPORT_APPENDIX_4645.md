# REPORT 付録 — #4645 (GUI-26): EnumDisplayMonitors callback `0x85df70` の icall miss

REPORT §6j の全文。要約と未解決は [REPORT.md](REPORT.md) §6j・§7 を参照。

## 1. 原因と対応

- 原因: `0x85df70` は `m11_extra_ranges5.txt` (boot5, #132) の範囲だが、素材 `work-m11` に `boot5.lift.ll` が無く、`e2e.sh` も boot5 を lift していなかった。そのため callback が IR に無く `m11_icall` が miss していた。
- 対応: `e2e.sh` が複製側 (`$TREE/m11`) で `m11_lift.sh m11_extra_ranges5.txt boot5` を実行するようにした (`m11_e2e.sh` #132 と同じ。元の `tools/m11` は読取のみ)。`judge.py` は無変更。

## 2. 実測 (boot)

- baseline / GUI とも `units_run 110` (旧 109)、`icall_miss 4` (旧 7)。miss 先は `0xfa9390` のみ (`0x85df70`・`0x457860` が解消)。
- 測定 commit `5c9a67101` (現 head・foreground 1 回) の e2e: rc 1・`JUDGE FAIL (14/15)`。FAIL は B1 の `GetMem 774 (base 772)` のみ (詳細は [REPORT.md](REPORT.md) §6j)。B1 は現 head で PASS しない。
- `results/` の現 head の出力 (`boot.json`・`baseline_boot.json`・`survey_*.json`・`ir_sha256.txt`) は、この e2e の実行結果で書き換えた。`survey_soft_chain.json` の `ok/trap/miss/icall_miss` は `875/20/46/46` で、本文の値と一致する。`mem_*`・`Halt0`・`MessageBoxA` の calls も変わっている (`git diff -- tools/gui/flengine/results/survey_soft_chain.json` で確認)。
- 解消は boot 経路で確認。残件 `0xfa9390` は子 #4730 (GUI-27)。

## 3. survey の値 (訂正)

survey には 2 つの結果ファイルがあり、値が違う。REPORT の旧記述 (「764/1/46/131」) は隔離版の値で、chain 版の値とは別物。

| ファイル | 測定 commit `5c9a67101` (現 head・2026-10-15 実測) | main `2d7331209` 側 |
|---|---|---|
| `results/survey_soft.json` (隔離版) | `ok/noproc/miss/trap` = 764/1/46/131 (S1 の実測と一致) | 764/1/46/131 |
| `results/survey_soft_chain.json` (chain 版) | 875/1/46/20 (`results/` は e2e 実行後も commit 済みの値と一致。`git status` 差分 0) | 872/1/47/22 |

- 隔離版 `survey_soft.json` の値は f0235912 から現 head まで同じ。
- chain 版 `origin/main` (`2d7331209`) との差は main 側の測定 (#4649 など) によるもので、本 PR の merge で PR 側を採った結果。
- chain 版の `icall_miss` (50 対 46)・`reach` (33 対 34)・`m11_stub_total` (200 対 203) も同じ理由で、本 PR の変更 (boot5 lift) の効果ではない。
- 旧 REPORT の 871 (`ok`) との差は既存の不整合で、子 #4731 (GUI-28) が原因を切り分ける。

## 4. 測定の鮮度

- 測定 commit は `5c9a67101` (コードを変えた最後の commit)。e2e の入力 (`tools/gui` `tools/m11` `tools/shim` `tools/shared` の実行コード) は、この commit と main 取り込み後の現 HEAD で差分 0 (差分は REPORT・results・本付録だけ。REPORT §6j の `git diff` 出力を参照)。
- 素材は `oc_artifacts` 行の 5 点 (fl-win64・work-m11・toolchain-emsdk・toolchain-retdec・apt-mingw) を展開して使った。
