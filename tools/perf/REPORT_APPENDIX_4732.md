# PERF-P27 (#4732): Fresh Air の再 lift (impbase 分離・fa_ prefix) と単独署名

REPORT_P15.md §8 の続き。正本はここ。親 #3680 (PERF-P23) の畳み込み手順 2〜4 の入力になる。

| 項目 | 結果 (実測) |
|---|---|
| 再 lift | `x64c.py --impbase 0x1F00000` (既定 `0x1D80000` から変更)。`--img 0x180000000 --shift 0x17E000000 --img-size 0x2319000`。functions 57、insns 2102、unsup `{}`、unlifted callees 0、imports 22、traps 0 |
| IAT pseudo-VA | `0x1F00000`〜`0x1F000FB` (IAT slot 252 個)。OTT 側に pseudo-VA の敷設は無い (`tools/ott/` に `IMP_VA` の定義・使用は無い)。Fresh Air の画像窓 (wasm `0x02000000`〜`0x04319000`) とも重ならない |
| compile | `fle_lifted.c` を `emcc -c -O0` で warnings 0 / errors 0 |
| 全 TU の `emcc -c` | `fle_lifted.c`・`fle_data.c`・`fle_cpu.c`・`fle_glue.c` が全て通る (`tools/perf/p20/work/fa2/rt`) |
| 改名 | `f_<va>` → `fa_f_<va>`、`imp_<名>` → `fa_imp_<名>`、`ott_dispatch` → `fa_dispatch`、`R`/`X`/`fCF` 等のフラグ・`ott_*` 系は `fa_rename.h` (`-include`) で改名。`IMP_VA_BASE` は `0x1F00000ULL` に置換 |
| 単独署名 | `fa_gain_sig.mjs` 400 シナリオ・seed 64030: `5e5287b5` (基準と一致)。出力が変わったシナリオ 371/400 |
| NC (入力を変える) | `NEG=1`: `40290578` (基準と不一致) |
| 定義シンボルの重なり | Fresh Air 側 220 個、OTT rt の全 TU 側 58 個。重なり 0 (`comm -12`)。改名なしの原版 lift では重なり 6 (`imp_*`)。`imp_`/`f_`/dispatch だけ改名した段階では 13 (`R`/`X`/フラグ/`ott_*`) が残った。`fa_rename.h` を足して 0 |
| build | real 9.34 s、load 0.49〜0.60 (4 vCPU) |

- 測定 commit: `631f58a3b` (`tools/perf/p20/build_fa_renamed.sh` を追加した commit。コードを最後に変えた commit)。
  `git diff 631f58a3b HEAD -- tools/perf/p20` の出力は、本 PR の追記時点で空。
- 既存の `tools/perf/p20/build_fa_gain.sh` (`--impbase 0x1D80000`・改名なし) は変えていない。単独 instance の基準はそのまま。
- 環境: node v22.23.3、emcc 6.0.12 (`toolchain-emsdk`、`activate 6.0.12`)、素材 `plugins-freshair` (`fetch.sh` で factory .epf 8 本を確認)。
- `lb_x64c.py --prefix` は使わなかった。同 wrapper は OTT 版 `x64c.py` の出力 `ott_lifted.c` だけを改名する。Fresh Air は flelift 版 `x64c.py` (`fle_lifted.c`) を使うため、同じ経路では改名できない。改名は `build_fa_renamed.sh` の sed と `fa_rename.h` で行った。
- 未検証: 畳み込み後の link・memory import 版の build・OTT との同居時の署名 (#3680 の手順 2〜4)。
