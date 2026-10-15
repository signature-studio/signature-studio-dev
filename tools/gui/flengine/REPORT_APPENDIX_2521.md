# REPORT_APPENDIX_2521 — `m11_ov.c` の既定変更 (#2521) と GUI build の固定 (PR #3485)

> **正本**: `tools/gui/flengine/REPORT.md` の §1〜§6i (gate 値は既定 0 の `m11_ov.c` で測った値)。本付録は #2521 の既定変更 (`M11_FIX_535BF2` 0 → 1) が GUI 側ビルドに入らないことの照合。REPORT.md の 250 行上限のため付録に置いた (内容は削除していない)。

`tools/m11/m11_ov.c` の `M11_FIX_535BF2` 既定が 0 → 1 になった (`d80e9909f`)。GUI 側 build (`tools/gui/flengine/build.sh`) は `m11_ov.c` を `$CF` で直接コンパイルするため、`CF` に `-DM11_FIX_535BF2=0` を足して従来値 (0) に固定した (commit `2ec9c4715`)。上の §1〜§6i の gate 値は、既定 0 の `m11_ov.c` で測った値のまま有効。

| 項目 | 値 |
|---|---|
| 照合の方法 | `clang -E -P` で `m11_ov.c` を前処理。素材の `work/boot_final3_sigs.h`・emscripten の headers は空スタブ (両側で同じ)。GUI の `CF` と同じ `-DM11_LB_BASE=0 -DM11_OV_CLASSCREATE=0` と `-w -O0 -pthread` を付ける |
| 変更前 (`44a7f4465` の `m11_ov.c`、既定 0) | 1704 行 |
| 修正後 HEAD (`CF` に `-DM11_FIX_535BF2=0`) | 1704 行。変更前と **差 0** (`cmp` で一致) |
| ネガコン (修正前の `CF` を HEAD の `m11_ov.c` に当てる) | 1721 行。変更前と **17 行差** (`function_535c11` / `function_535bf2` の転記が入る) |
| GUI の e2e | 再実行していない (素材 `work-m11`・toolchain が PR #3485 の run に無い)。前処理が同一なので GUI の `m11_gui.cjs` の入力は変わらない |
