> **正本**: `tools/plugins/dynamics/REPORT.md`。本書は REPORT の付録 (250 行上限のため分割移動。内容は無変更)。

# tools/plugins/dynamics/REPORT_APPENDIX.md — #1412 脱落の原因 (付録)

## A. `.pdata` define 脱落の原因 (#1412)

REPORT §4 の「脱落の原因」の全文。 本付録は本体から分割移動した。

- 既定の RetDec 呼出し (`--disable-static-code-detection` 無し) が、定数 libc 系の関数を
  「statically linked function」として除去する (`e.retdec.log` の `Running phase: removing functions from standard libraries`)。
  19048 の欠落 210 件のうち **208 件** は dsm の `statically linked function` 行の開始 VA と一致 (`e.drc.dsm`)。 残る 2 件は
  `CreateEngine` (0x18000b1a0) / `entry_point` (0x18000bb98) で、RetDec は名前付きの `function:` として出力しており、
  `define @CreateEngine` / `define @entry_point` は final.ll に存在する。 `engine_defs.py` は `function_<VA>` 形式しか見ないため、この 2 件は偽陽性。
- ネガティブ/切替の実測: `PLUG_NO_STATIC_DETECT=1 bash tools/plugins/dynamics/engine_lift.sh 19048` で `missing_define` 210 → **2** (97 B)、`missing_ref` 67 → **0**、`define` 1,504 → 1,712。
- 19252 は切替前後とも 2 件 (165 B) で不変 (静的検出の対象外。 原因は未特定のまま)。
- ただし切替後の 19048 は `emcc -c` rc 1 (fixcmp 後も rc 1): `e.final.ll` の `%arg2` i32/i64 不整合 (既存の修正対象) の後に、`e.fixcmp.ll` で `%penv` の i64/ptr 不整合が露見 (未修正)。 既定の切替は `lift_ranges.sh` の既定値 (#1486) に関わるため、既定の変更は本 run では行わない。
