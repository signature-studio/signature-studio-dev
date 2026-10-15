# PERF-P27 (#4732): Fresh Air の再 lift (impbase 分離・fa_ prefix) と単独署名

REPORT_P15.md §8 の続き。正本はここ。親 #3680 (PERF-P23) の畳み込み手順 2〜4 の入力になる。

| 項目 | 結果 (実測) |
|---|---|
| 再 lift | `x64c.py --impbase 0x1F00000` (既定 `0x1D80000` から変更)。`--img 0x180000000 --shift 0x17E000000 --img-size 0x2319000`。functions 57、insns 2102、unsup `{}`、unlifted callees 0、imports 22、traps 0 |
| IAT pseudo-VA | `0x1F00000`〜`0x1F000FB` (IAT slot 252 個)。OTT 側に pseudo-VA の敷設は無い (`tools/ott/` に `IMP_VA` の定義・使用は無い)。Fresh Air の画像窓 (wasm `0x02000000`〜`0x04319000`) とも重ならない |
| compile | `fle_lifted.c` を `emcc -c -O0` で warnings 0 / errors 0 |
| 全 TU の `emcc -c` | `fle_lifted.c`・`fle_data.c`・`fle_cpu.c`・`fle_glue.c` が全て通る (`tools/perf/p20/work/fa2/rt`) |
| 改名 | `f_<va>` → `fa_f_<va>`、`imp_<名>` → `fa_imp_<名>`、`ott_dispatch` → `fa_dispatch`、`R`/`X`/`fCF` 等のフラグ・`ott_*` 系は `fa_rename.h` (`-include`) で改名。`IMP_VA_BASE` は `0x1F00000ULL` に置換 |
| 単独署名 | `fa_gain_sig.mjs` 400 シナリオ・seed 64030: `5e5287b5` (基準と一致)。n=1 (1 回の測定) |
| 署名の中身 | `sig` は、シナリオごとの FNV-1a 値 (処理後の L/R 出力バッファ・this の状態 0xa0..0xd8・buf 32 B) を、さらに FNV-1a で連結した 1 個の集計 hash。シナリオ出力の連結そのものではない |
| 出力が変わったシナリオ 371/400 | 比較対象は**同じ実行内の入力 L と処理後の L** (`out_changed`。`fa_gain_sig.mjs` の `L0` と `LN`)。基準 build・改名前の原版 lift・NC との比較ではない。ゲイン処理が L を書き換えたシナリオ数で、署名とは別の量 |
| 両者が矛盾しない理由 | 署名 `5e5287b5` が一致 = 処理後の出力は基準 build と同一。371 は「入力→出力の変化」の件数で、基準との差分ではないため、両方とも成り立つ。371 は本 PR の素材では再測定していない (下の未解決) |
| NC (入力を変える) | `NEG=1`: `40290578` (基準と不一致) |
| 定義シンボルの重なり | Fresh Air 側 220 個、OTT rt の全 TU 側 58 個。重なり 0 (`comm -12`。再現は `work/fa2/lift` と `work/fa2/rt` の各 `.c` から定義シンボルを抜き出して `sort -u` した 2 本に `comm -12` をかける。repo に再現スクリプトは無い。素材が無い run では再実行していない)。改名なしの原版 lift では重なり 6 (`imp_*`)。`imp_`/`f_`/dispatch だけ改名した段階では 13 (`R`/`X`/フラグ/`ott_*`) が残った。`fa_rename.h` を足して 0 |
| build | real 9.34 s、load 0.49〜0.60 (4 vCPU)。n=1 (1 回の測定。min–max レンジは未取得) |
| 署名の所要 | real 0.06 s。n=1 |
| IAT slot と imports | IAT slot は PE の全 IAT エントリ 252 個 (pseudo-VA は slot ごとに 1 つ、`0x1F00000`〜`0x1F000FB`)。`imports 22` は lifted code が実際に呼ぶ**相異なる import 名**の数 (`x64c.py` の `used_imps`)。使われない slot は dispatch 表で `imp_unimpl` に入る。したがって 252 は敷設の単位、22 は呼出しの単位 |

- 測定 commit: `631f58a3b` (`tools/perf/p20/build_fa_renamed.sh` を追加した commit。コードを最後に変えた commit)。
  `git diff 631f58a3b HEAD -- tools/perf/p20` の出力は、本 PR の追記時点で空。
- 既存の `tools/perf/p20/build_fa_gain.sh` (`--impbase 0x1D80000`・改名なし) は変えていない。単独 instance の基準はそのまま。
- 環境: node v22.23.3、emcc 6.0.12 (`toolchain-emsdk`、`activate 6.0.12`)、素材 `plugins-freshair` (`fetch.sh` で factory .epf 8 本を確認)。
- `lb_x64c.py --prefix` は使わなかった。同 wrapper は OTT 版 `x64c.py` の出力 `ott_lifted.c` だけを改名する。Fresh Air は flelift 版 `x64c.py` (`fle_lifted.c`) を使うため、同じ経路では改名できない。改名は `build_fa_renamed.sh` の sed と `fa_rename.h` で行った。
- 未検証: 畳み込み後の link・memory import 版の build・OTT との同居時の署名 (#3680 の手順 2〜4)。
