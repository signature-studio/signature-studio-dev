# #928 (M11-N50) m11_e2e.sh の RetDec PATH 解決 — 実測

親: #715。修正本体は `74b365f6` (main 取込済み)。本書は同 issue の受入条件の実測記録。

## 実測 (測定 commit `1f600c47`・2026-10-13・素材 fl-win64 sha256 `b2c64da4…`・PATH に retdec-decompiler 無し)

> **鮮度: 未確定**。下表は測定 commit `1f600c47` の結果。現 HEAD (`5e68d99f`) との実行コード差分は
> `git diff 1f600c47 HEAD -- tools/m11 tools/liftlib ':!*.md'` で 27 files (+1924/-32)。差分 0 でないため、下表を現 HEAD の根拠に使わない。
> 現 HEAD での再測定は未実施 (素材 `toolchain-retdec`・`toolchain-emsdk`・`work-m11` が runner の `$HOME/artifacts` に無く、RetDec・emcc も無いため)。

| 実行 | rc | 所要秒 | 結果 |
|---|---|---|---|
| `m11_lift.sh` 3 range (`boot_ranges_extra.txt` 先頭 3 件) | 0 | 8.7 | `command -v retdec-decompiler` = no のまま、`RETDEC_ROOT` 未設定時の既定 ([RETDEC]) で解決。RetDec 160 lines / ir5 111 lines |
| Ghidra 12.1.4 headless → `functions_dll.csv` (JDK 21, MAXMEM 8G) | 0 | 591 | 59 010 行 |
| `m11_e2e.sh --full` 1 回目 | 1 | 618 | lift 全段 ok (boot5 含む)。build で fail: `undefined exported symbol: "_m11_set_va_bigtrace"` (work-m11 同梱の古い `obj/rt.o`・`win.o` が `nm` で 0 件。REPORT_130 と同事象) → #1176 (`[M11-N71]`) |
| `obj/rt.o` `obj/win.o` を削除して `--full` 2 回目 | 0 | 632 | reached_stage 4 / survey_ok 870 / trap 25 (oom 1) / clobber 0 / miss 46 / ir_sha256 `1b29839e…` |

結論: retdec の PATH 解決に起因する失敗は再現しない。`--full` の残る失敗は obj 鮮度に関するもので #1176 で扱う。
reached_stage 4 の trap (`unreachable` @ function_8c5eb0) は本 issue の対象外。
