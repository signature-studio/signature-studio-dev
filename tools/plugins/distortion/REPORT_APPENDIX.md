# tools/plugins/distortion/REPORT_APPENDIX.md — REPORT.md §5 のネガティブコントロール表 (付録)

REPORT.md の 250 行上限のため、§5 の NC 詳細表を本書へ分割移動した (内容は削除していない。 Git 履歴も残る)。 数値は HEAD c0fcf60 時点の `distortion_nega.sh` 出力 (37/37)。

| 項目 | 内容 |
|---|---|
| `distortion_nega.sh` (HEAD c0fcf60、e2e の直後) | exit 0、**9.08 s**、**37/37** 項目 |

ネガティブコントロール (数値は `distortion_nega.sh` の出力。 判定系は「期待した理由の文言で落ちたか」まで照合する):

| NC | 内容 | 結果 |
|---|---|---|
| NC-J (18 件) | `distortion_e2e.sh --judge-only` に、実測 status.csv を 1 点だけ壊した入力を与える。 対照 (無改変) は exit 0 + 最終行 OK。 壊し方: `emcc_c_rc`=1 / `lift_rc`=1 (殻と `module`) / `f80_funcs`=3 / `declares_unimpl`=5・許容超過 (Love Philter 2 > 1)・-1 / `defines`=0・9999 / 非整数 / 行の削除・重複・対象外 block の追加 / 欠落監査 csv の `missing_define`=1・`function_defines`+1・`extra_inside`=0 / ヘッダ破損 | 壊した 17 件はすべて exit 1 (ヘッダ破損のみ入力不正の exit 2)、最終行 OK なし、期待した理由の文言が出力に有り |
| NC-JE (5 件) | engines.csv の判定。 対照 exit 0。 `lift_rc`=1 / `defines`=0 / 集計不能 (-1) / 行削除 | 4 件とも exit 1 |
| NC-N (5 件) | `unimpl_names.py`。 対照 exit 0。 別名の helper (stosb→stosw) / 未実装 0 の block に名前を追記 / 件数 1 だが名前の行が無い / log 無し | 4 件とも exit 1 |
| NC-E | Soft Clipper (19078) の `final.ll` の 1 関数の `ret` を除去 | `emcc -c` rc **0 → 1** |
| NC-R | 19078 の閉包 ranges 14 本の末尾 1 本 (`function_6c11c0`) を落として再 lift | その define 1 → 0、全体 define **15 → 13** (RetDec は 1 range から 2 define を出すことがあり差は 1 と限らない) |
| NC-I | `ids_crosscheck.py` に Distructor の ID 8 の件数を 1 → 2 にした facts を与える | exit 0 → **1** (9/9 → 8/9) |
| NC-M | `matrix_check.py`: Distructor の `closure_funcs` +1 / Fast Dist の `emcc_c_rc` を 1 にした status | 72/72 → **71/72** (exit 1)、後者も 71/72 (exit 1) |
| NC-D | `engine_defs.py` に実在しない range を 1 本足す | `missing_define` **1 → 2** |
| NC-W | e2e 本体 (`--skip-lift`) に、Fast Dist の最終行が `emcc_c_rc`=1 の lift 結果を与える | e2e 全体が exit 1、最終行 OK なし、`FAIL  block 19004 … emcc_c_rc=1` を表示 (#506 で露見した「判定が落ちても e2e が exit 0」の再発防止) |
