# REPORT_APPENDIX_6246 — 分割移動 (#6246): REPORT.md §19・§20 の全文 (#4011)

REPORT.md が 250 行上限のため、#6246 で §19・§20 を内容無変更で移動した (元の行 227〜248)。

## 19. #4011 [WIN-42]: vtable[0] 復元 `function_41a800` (gated `M11_M2V`) と QueryInterface `0x41c180` の C 転記 (部分達成)

- 変更: `m11_passes.py` `pass_m2s_fn41a800_vtable0` (既定 OFF・`M11_M2V=1` で有効)・`m11_ov.c` に `tr_41c180` / `tr_4467ac` を `disp_find` 登録。`tr_41c180` の戻り値は `test al,al` で非 0 → 0・0 → `0x80004002` (機械語 `41c180`〜`41c191` と一致)。
- 測定 commit: `71f6e449ac2218f3bff31a61e64da58c30dcee47`。以後の差分は REPORT.md のみ (`m11_ov.c` / `m11_passes.py` は差分 0)。以下は作者が同 commit で測定した値。**本 review 修正 run では再測定していない** (`work-m11` / `toolchain-retdec` が未取得で `tools/m11/work/` が無いため実行不可)。

| コマンド | rc | 所要 | 備考 |
|---|---|---|---|
| `m11_wndseed.sh` | 0 | 3 分 26 秒 | WNDCLASS-CHECK PASS |
| `m11_gen_ir2.sh` | — | 1 分 10 秒 | `ir_conditions.json` ldfix=applied |
| `m11_build.sh` (既定 OFF / `M11_M2V=1`) | 0 / 0 | 25 秒 | 両方 rc 0 |
| `tools/gui/flengine/build.sh` | 0 | 42 秒 | |
| `boot_halt_probe.mjs` | — | 0.56 秒 | |

- 製品 KPI (`M11_M2V` 既定 OFF / `=1`): units_run 109 / 109・last_unit.index0 114 (Halt0) / 114 (OOB)・icall_miss 7 / 7・threw null / `memory access out of bounds`・最初のウィンドウ 未到達 / 未到達。
- stage ログ: `[M2v] function_41a800 vtable0 restore: 1 sites` (pass が 1 箇所に適用)。
- 対応の根拠 (未独立確認): pass は `%arg2` を this (vtable 読出し元 `[rsi]`)・`%arg3` を IID として `m11_icall(vtva, arg2, ptrtoint arg3, out, ...)` に渡す。`%arg3` の下位 32 bit を判定に使っていた旧 IR と対応する。IR (`work/`) は本 run に無く、1 site 適用は作者の stage ログの記載のみで、本 run では独立確認していない。
- 受入: 1 (`last_unit.index0 > 114`) 未達 (114 で OOB)。2 (vtable[0] の戻り値判定) 部分達成 (`0x41c180` 以降の戻り値経路は未実測)。
- 未解決: unit 114 以降の OOB・`function_40fcf0` の AddRef `call [rax+8]` (`40fd3a`) 未復元 → 次の run (#4011)。受入 3 (CS-INIT 0x12bd390) は範囲外で #4031。

## 20. #4011 段 2: `pass_m2v_fn40fcf0_arg1` (gated `M11_M2V`, 既定 OFF, 受入 1 未達)

`function_40fcf0` の `function_40fd90` 呼出しの第 1 引数を `[self]` (VMT) に直す。`M11_M2V=1 M11_M2S=1` で last_unit 114→144 に前進したが OOB が残り、icall miss 7→16。「偽の前進」の疑いがあり、受入 1 は未達。測定・測定 commit・差分 0 の証跡・未解決は [REPORT_N4011.md](REPORT_N4011.md)。
