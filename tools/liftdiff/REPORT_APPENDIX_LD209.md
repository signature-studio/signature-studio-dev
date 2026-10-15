# liftdiff REPORT 付録: LD-209 (#4305) native 側の候補単位の戻し (`0x5d19e0` の両側持ち越しの切り分け)

親 #3385 (LD-156)。前提は `REPORT_APPENDIX_LD156.md` (`native=1, sta` で match・n=2 だが、native 側の候補単位の戻しが未実装だった)。

測定 commit: **`91122e803`** (表の数値を出したときのコード。`rt/ld_native.c` は修正 commit `f914bfd0d` と main 取り込み後の内容)。wasm・native とも、この commit の `rt/` から作り直して測定した (`build_wasm.build(force=True)`・`ensure_native()` で `work/ld_native` が 10:36 に作り直されたことを確認)。

以前の測定 commit `7ac689777` の数値は、レビュー指摘 1 (`g_nrst`・`g_nnrst` の複製) の修正前のもので、**結論に使わない**。下の表は全て `91122e803` で測り直した値。

## 結論

- **native 側の候補単位の戻し (sta) で、`0x5d19e0` は match する** (`wasm sta` + `native sta`・n=2 で 11/11 equal・2/2)。
- `native all` (stk・sta・img の全部) も match (n=2 で 11/11・2/2)。
- `native stk`・`native img` 単独は match しない (n=2 で 0/11・2/2)。`0x5d19e0` の持ち越しは sta 領域に入っていて、stk・img には無い。
- 前回 (修正前) の「候補戻しでは再現しない」は、`g_nrst`・`g_nnrst` の複製で sta の戻しが不完全だったことによる誤り。修正後はこの前提を外す。
- ただし、戻しの対象は「sta 領域のうち、ヒープ管理変数などを除いた残り」。どの変数が効いているかは未切り分け。切り分けは子 issue #4631 で行う。

## 1. 測定条件

- 素材: `fl-win64` ([WIN64]・`FL_WIN64_DIR`)・`toolchain-emsdk` ([EMSDK]・`/opt/emsdk`)・`work-m11` (`tools/m11/work/`)・`work-liftdiff` (`tools/liftdiff/work/`)。`$ARTIFACTS_DIR` に 4 件とも実在を確認して展開した。
- wasm は `build_wasm.build(t, force=True)` で作り直した (`wasm_size` 4464468・`sig_mismatch` 0・`undefined` 0)。修正前の 4464346 とは差がある (`rt/` の変更による)。
- 対象は chunk 0 の `0x5d19e0` 1 件 (`sample:800` の 0〜399 件目)。全条件 `native=0` (native は作り直さない)。
- 機: 4 vCPU。各測定は 1 本ずつ foreground で実行 (1 回約 152 秒)。実行中の load は 0.8〜1.5。

## 2. 方法

- `rt/ld_native.c`: `SNAPSHOT` の後に `nrst_snap()` で、候補ごとの複製を取る。
  - stk: `[sp-128K, sp-8K)` (run_case の scrub 域)。
  - sta: `[__data_start, _end)` から、ヒープ管理変数・`ld_blks`・`ld_wr`/`ld_nwr`・`ld_arena_pristine`・`g_line`/`g_linecap`・`g_tr_va`/`g_tr_orig`/`g_ntr_set`・`g_nrst`/`g_nnrst` (修正) を除いた残り。
  - img: PE image (`ld_img`・`g_imgsize`)。
- `NRESET <mask>` で複製に戻し、戻した byte 数 (戻し前の内容と複製の差) を `{"nreset":m,"diff":d}` で返す。
- `ld156_chunk0_carryover.py --native-reset <cand>` (`--native 0` のときだけ使う): 対象の直前に `NRESET` を送り、応答を読む。wasm の `RESET` 応答も読む。
- 出力行に `native_reset_diff`・`wasm_reset_diff` を足した (戻しが効いた証跡)。

## 3. 結果 (`results/ld209_native_reset.tsv`・raw は `results/ld209_raw/`)

| wasm RESET | native RESET | n | verdict | case equal | native diff (B) | wasm diff (B) |
|---|---|---|---|---|---|---|
| sta | stk | 2 | mismatch (0/11 ×2) | 0 | 0 | 343847 |
| sta | img | 2 | mismatch (0/11 ×2) | 0 | 0 | 343847 |
| sta | sta | 2 | **match (11/11 ×2)** | 11 | 39454 | 343847 |
| sta | all | 2 | **match (11/11 ×2)** | 11 | 39454・39453 | 343847 |
| none | sta | 1 | mismatch (0/11) | 0 | 39454 | – |

- `none/none` (wasm 戻しなし・native 戻しなし) は `7ac689777` の n=1 の値を流用しない。本 commit では再測定していない (対照は `REPORT_APPENDIX_LD121.md` の `none` mismatch と一致する)。
- `native=1` (作り直し) + wasm `sta` の match (LD-156) と、`native=0` + native `sta` 戻し + wasm `sta` の match は、どちらも `0x5d19e0` の持ち越しを消す。作り直しと候補戻しの両方で match するので、持ち越しは sta 領域にあると見ている。
- `native stk`・`native img` の diff は 0 で、`0x5d19e0` は stk・img に残存を持たないことと整合する (LD-96 の残存 0 と一致)。

## 4. 未確認

- sta 領域の中のどの変数・どの範囲が効いているかは切り分けていない (sta 全体を戻すと match する、ということだけ分かる)。
- `wasm none` + `native sta` (wasm 戻しなし) は本 commit で未測定 (`none/sta` は mismatch・n=1)。wasm 側の sta が必要かは、この表では確定していない。
- 戻しの効きは byte 数だけ。戻した後の native 状態と作り直し後の一致は見ていない。
- LD-121 の both 条件 (`native=1` と wasm 作り直し) は本 driver では流していない (LD-156 §4 と同じ)。
- `native_reset_diff` が sta の 39454 B のうち何が効いたかは未確認。

## 5. 子 issue

- sta 領域の中の範囲の切り分け (どの変数・どの範囲で match するか)。`0x5d19e0` の持ち越しの実体はここにある。
- 子 issue: **#4631** (`[LD-229]`・親 #3385)。PR 本文の未解決表に同じ番号を書く。

## 6. 再現

```sh
# 環境変数は docs/REFERENCES.md §4 を参照 ([WIN64] の展開先を FL_WIN64_DIR に指定する)
cd tools/liftdiff
python3 -c "import sys; sys.path.insert(0,'.'); from ldlib import build_wasm; t=build_wasm.load_target('targets/m11.json'); build_wasm.ensure_native(); build_wasm.build(t, force=True)"
python3 ld156_chunk0_carryover.py --native 0 --reset sta --native-reset sta --out work/ld209/sta_r1.jsonl
python3 ld156_chunk0_carryover.py --native 0 --reset sta --native-reset all --out work/ld209/all_r1.jsonl
```

## 7. 測定 commit 以降の差分 (`git diff 91122e803 HEAD -- tools/liftdiff`)

本付録と `results/ld209_*` の変更のみ。`rt/`・`ld156_chunk0_carryover.py` は変更なし (差分 0 行)。測定の再現には影響しない。
