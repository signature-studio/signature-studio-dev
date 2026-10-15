# REPORT_APPENDIX_1116 — #1116 HeapAlloc 0 返却規約の検証 (全文)

`REPORT.md` の 1116 節の全文を分割移動 (250 行上限のため・内容は無変更)。

- 変更: `lift/gen_stubs_sigs.py` の `HEAP_C` と `harness/scen_khmath.h` `n_HeapAlloc` / `scen_khmaster.h` `khb_HeapAlloc` を同じ規約 (1MiB 超・領域超過で `return 0`、cursor 不変) に揃えた。
- 実測 (HEAD 19cdf357、gcc -O0 x86_64 ホスト): `python3 tools/targets/kilohearts/snapins/harness/heap_alloc_diff.py` → `total=32 mismatches=0` (exit 0)。
- 未実施: `run_all.sh` による 13 本 + khmrel/khmaster/khmring の bit-exact 突合、RetDec lift、emcc 再ビルド。理由は素材不足 (`$ARTIFACTS_DIR` は `fl-win64.tar.zst` のみ = FL Studio インストーラー 1 本。`plugins-kilohearts` / `toolchain-retdec` / `toolchain-emsdk` 無し)。#1116 で継続。
