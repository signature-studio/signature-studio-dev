# liftdiff REPORT 付録: LD-209 (#4305) native 側の候補単位の戻し (`0x5d19e0` の両側持ち越しの切り分け)

親 #3385 (LD-156)。前提は `REPORT_APPENDIX_LD156.md` (`native=1, sta` で match・n=2 だが、native 側の候補単位の戻しが未実装だった)。

測定 commit: **`7ac689777`** (表の数値を出したときのコード。`rt/ld_native.c` と `ld156_chunk0_carryover.py`)。
**注意 (レビュー指摘 1 の修正後)**: 以降の commit で `rt/ld_native.c` の sta 除外リストに `g_nrst`・`g_nnrst` を加えた。このため `7ac689777` の数値は、修正後のコードでは**無効** (未再測定)。`native sta`・`native all` を含む行 (`native_reset_diff` 339) は特に影響を受ける。修正後の再測定は #4305 の範囲で保留 (素材 `toolchain-emsdk`・`work-m11`・`work-liftdiff` が当該 run で `$ARTIFACTS_DIR` に無く、未実施)。

既知類型との関係: 該当なし (`docs/DEFECTS.md` の類型とは別。runner の case 間の持ち越し)。

## 結論

- **native 側の候補別 RESET を実装した** (`rt/ld_native.c` の `NRESET <mask>`・mask は wasm の RESET と同じ 1=stk・2=sta・4=img)。`ld156_chunk0_carryover.py --native-reset <cand>` で指定できる。
- **修正前のコード (`7ac689777`) では、native 側の候補を戻しても `0x5d19e0` は match しなかった** (wasm `sta` の条件で `none`・`stk`・`sta`・`img`・`all`、いずれも mismatch 0/11)。ただし `sta`・`all` の行は、レビュー指摘 1 (`g_nrst`/`g_nnrst` の複製で `all` が img を戻さない) の修正前の数値で、修正後のコードでは未再測定。`all` を含めた結論は再測定まで保留する。
- 修正後の `all` 行の再測定は、本 run では素材不足で未実施 (§3 の注意)。
- LD-156 の `native=1, sta` (native を作り直す) の match は、native 作り直しだけに依存する。native の候補単位の戻しでは再現しなかった。native 作り直しが消している持ち越しは、この 3 種 (stk・sta・img) の戻しでは捉えられていない。

## 1. 測定条件

- 素材: `fl-win64` ([WIN64]・`FL_WIN64_DIR`)・`work-m11` (`tools/m11/work/`)・`work-liftdiff` (`tools/liftdiff/work/`)・`toolchain-emsdk` ([EMSDK])。
- wasm は `build_wasm.build(t, force=True)` で作り直した (`wasm_size` 4464346・`sig_mismatch` 0)。
- 対象は chunk 0 の `0x5d19e0` 1 件 (`sample:800` の 0〜399 件目)。
- 機: 4 vCPU。並列は 4 本 (`&` + `wait`)。load は 1.0〜3.8 (実行中に測定・各回の値は下表)。

## 2. 方法

- `rt/ld_native.c`: `SNAPSHOT` の後に `nrst_snap()` で、候補ごとの複製を取る。
  - stk: `[sp-128K, sp-8K)` (run_case の scrub 域)。
  - sta: `[__data_start, _end)` から、ヒープ管理変数・`ld_blks`・`ld_wr`/`ld_nwr`・`ld_arena_pristine`・`g_line`/`g_linecap`・`g_tr_va`/`g_tr_orig`/`g_ntr_set` を除いた残り。
  - img: PE image (`ld_img`・`g_imgsize`)。
- `NRESET <mask>` で複製に戻し、戻した byte 数 (戻し前の内容と複製の差) を `{"nreset":m,"diff":d}` で返す。
- `ld156_chunk0_carryover.py --native-reset <cand>` (`--native 0` のときだけ使う): 対象の直前に `NRESET` を送り、応答を読む。wasm の `RESET` 応答も読むようにした (LD-156 の driver は読んでいなかった)。
- 出力行に `native_reset_diff`・`wasm_reset_diff` を足した (戻しが効いた証跡)。

## 3. 結果 (`results/ld209_native_reset.tsv`)

| wasm RESET | native RESET | n | verdict | case equal | native diff (B) | wasm diff (B) |
|---|---|---|---|---|---|---|
| none | none | 1 | mismatch | 0/11 | – | – |
| none | sta | 1 | mismatch | 0/11 | 339 | – |
| sta | stk | 1・2 | mismatch | 0/11 | 0 | 343847 |
| sta | sta | 1・2 | mismatch | 0/11 | 339 | 343847 |
| sta | img | 1・2 | mismatch | 0/11 | 0 | 343847 |
| sta | all | 1・2 | mismatch | 0/11 | 339 | 343847 |

- `native=1` (作り直し) + wasm `sta` の match (LD-156) とは、native 側の条件が違う (作り直しと、候補単位の戻し)。
- 修正前の `native stk`・`img` は diff 0。この 0 は、`0x5d19e0` が stk・img に残存を持たない (LD-96 の残存 0 と一致) ことと整合する。stk・img の戻しは sta 領域に触れないので、修正の影響は受けないと見ている (未再測定)。
- 修正前の `native sta` (339 B) は、`g_nrst`/`g_nnrst` の複製を含んでいたため、戻し量の数値を信用しない (修正後は変わる)。
- `none/none` と `none/sta` は n=1。受入の候補測定は n=2 (`sta/all`・`sta/stk`・`sta/sta`・`sta/img` の n=2 は修正前の数値)。

## 4. 未確認

- **native の作り直しが戻している持ち越しの中身は、この 3 種に入っていない。** native 作り直しは `ld_native` を exec し直すので、プロセス全体 (libc の malloc 状態・TLS・ヒープ外の mmap) を戻す。`stk`・`sta`・`img` の戻しはこれらを含まない。本測定では、どの領域が効いているかは切り分けられていない。
- 戻しの対象外の libc 状態 (malloc の arena・stdio buffer 等) は、この実装では戻していない。
- `native=1` と `native=0, sta` の差を見るための、native 作り直しと候補戻しの組合せ (作り直し + wasm `sta` 以外) は未測定。
- LD-121 の both 条件 (`native=1` と wasm 作り直し) は本 driver では流していない (LD-156 §4 と同じ)。
- 候補戻しが効いた証跡は byte 数だけ。戻した後の native の状態が作り直し後と一致するかは見ていない。

## 5. 子 issue

- native 作り直しが戻す持ち越し (プロセス全体・libc の内部状態) の切り分け。`0x5d19e0` の残りの原因はここにあると見ている。受入条件 2 の残り (作り直し条件との差) は、この子の範囲。
- 子 issue: **#4631** (`[LD-229]`・親 #3385)。PR 本文の未解決表に同じ番号を書く。

## 6. 再現

```sh
# 環境変数は docs/REFERENCES.md §4 を参照 ([WIN64] の展開先を FL_WIN64_DIR に指定する)
cd tools/liftdiff
python3 -c "import sys; sys.path.insert(0,'.'); from ldlib import build_wasm; t=build_wasm.load_target('targets/m11.json'); build_wasm.ensure_native(); build_wasm.build(t, force=True)"
python3 ld156_chunk0_carryover.py --native 0 --reset sta --native-reset sta --out work/ld156/w_sta_n_sta_r1.jsonl
```

## 7. 測定 commit 以降の差分 (`git diff 7ac689777 HEAD -- tools/liftdiff`)

測定 commit 以降に `rt/ld_native.c` が変わった (レビュー指摘 1 の修正)。`ld156_chunk0_carryover.py` は変わっていない。

- `git diff 7ac689777 HEAD -- tools/liftdiff/rt/ld_native.c` = 修正 commit の差分 (`g_nrst`・`g_nnrst` の除外 2 行 + `ex[]` 配列を 32 へ・注釈 1 行)。**測定と一致しない** (冒頭の注意)。
- `git diff 7ac689777 HEAD -- tools/liftdiff/ld156_chunk0_carryover.py` = 0 行
- 修正後の `ld_native` は `gcc -O1 -g -Wall -Wno-unused-function` でコンパイル成功 (警告は既存の `ld_core.h` のもの)。動作の再測定は未実施。
