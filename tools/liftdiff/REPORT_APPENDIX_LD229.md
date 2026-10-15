# liftdiff REPORT 付録: LD-229 (#4631) native 作り直しが戻す持ち越しの切り分け (`0x5d19e0`)

親 #3385 (LD-156)。前提は `REPORT_APPENDIX_LD209.md` (native 側の候補 stk・sta・img の戻しで、`0x5d19e0` は `sta` でだけ match・stk・img は mismatch)。前提の PR #4611 (LD-209) は 2026-10-15 に main へ merge 済み。

測定 commit: **`f6af8ce45`** (`rt/ld_native.c` の候補 mask 8 = anon mmap と、`ld156_chunk0_carryover.py` の `--native-reset mmap`)。測定はこの commit の `rt/` から作り直した (`ensure_native()` と `build_wasm.build(force=True)`)。

## 結論

- native 側に候補 `mmap` (anon の rw-p mapping。ヒープ外・stdio buffer 等) を追加した。`0x5d19e0` は **wasm `sta` + native `mmap` で match** (n=2。verdict は両回とも match)。
- 対照は両方 mismatch: wasm `none` + native `mmap` (n=1)、wasm `sta` + native `none` (n=1)。
- case の内訳は 11 件中 `equal` 10 件・`hang` 1 件 (`z`)。`sta_mmap` の r1 では `z` の native 側が `crash`・wasm 側が `hang` で、status が一致しない (verdict は match)。r2 は 11 件とも status が一致する。`z` の status は run ごとに揺れる (`z` は timeout 境界の case で、本測定では原因を切り分けていない)。
- `native_reset_diff` は 39891 B。`mmap` の戻しは効いている (戻し前の内容と複製が異なる byte がある)。
- 残る持ち越しは、`sta` 領域 (wasm・native とも) と native の anon mmap の組み合わせで消える。どちらか単独では消えない。どの mapping が効いているかは未切り分け。

## 1. 測定条件

- 素材: `fl-win64` ([WIN64]・`FL_WIN64_DIR`)・`toolchain-emsdk` ([EMSDK])・`work-m11` (`tools/m11/work/`)・`work-liftdiff` (`tools/liftdiff/work/`)。`$ARTIFACTS_DIR` に 4 件の実在を確認して展開した。
- wasm は `build_wasm.build(m11, force=True)` で作り直した (`wasm_size` 4464620・`sig_mismatch` 0・`undefined` 0)。
- 対象は chunk 0 の `0x5d19e0` 1 件 (`sample:800` の 0〜399 件目)。全条件 `native=0` (native は作り直さない)。
- 機: 4 vCPU。4 本を並列で回した (各回 177〜192 s)。実行中の load は 3.1 前後。

## 2. 方法

- `rt/ld_native.c`: `nrst_snap()` の末尾で、`/proc/self/maps` の anon rw-p 領域のうち、image・arena・heap・`g_file`・複製 buffer 自身を除いたものを候補 `NRST_MMAP` (= 8) として複製する。`NRST_MAX` は 8 → 64 に増やした。
- 戻す前に `msync(MS_ASYNC)` で mapping の存在を確かめ、munmap 済みの区間は戻さない (`skip` として応答に出す)。
- `NRESET <mask>` の応答は `{"nreset":m,"diff":d,"skip":s}`。
- `ld156_chunk0_carryover.py --native-reset mmap` (mask 8)・`sta_mmap` (10)・`all_mmap` (15) を追加。

## 3. 結果 (`results/ld229_raw/`・commit `f6af8ce45`)

| wasm RESET | native RESET | n | verdict | case equal | native diff (B) | wasm diff (B) |
|---|---|---|---|---|---|---|
| sta | mmap | 2 | **match (11/11 ×2)** | 11 | 39891 | 343847 |
| none | mmap | 1 | mismatch (0/11) | 0 | 39891 | – |
| sta | none | 1 | mismatch (0/11) | 0 | – | 343847 |

- 対照 `none/none` は本 commit で再測定していない (`REPORT_APPENDIX_LD156.md` の `native=0, none` mismatch と一致する)。
- 戻しの効きは byte 数で確認した。`native_reset_diff` が 0 でないことは、戻す前の native 状態が snapshot と異なることを示す。

## 4. 未確認

- `mmap` の中のどの mapping が効いたか (stdio buffer・libc の malloc 用 mmap・その他) は切り分けていない。
- `none/mmap` は n=1。`sta/none` は n=1。n=2 は `sta/mmap` だけ。
- 戻した後の native 状態と作り直し後の一致は見ていない (LD-209 §4 と同じ)。
- LD-121 の both 条件 (`native=1` と wasm 作り直し) は本 driver で流していない。
- `skip` (munmap 済み区間) の件数は各 NRESET 応答に出るが、本 REPORT では集計していない。
- `all_mmap` (15) は測定していない。

## 5. 子 issue

- 上記 §4 の mapping 単位の切り分け (どの mapping が効くか) は、本 issue の受入条件に含まれていない。必要なら別 issue で扱う。本 PR の未解決表に書く。

## 6. 再現

```sh
# 環境変数は docs/REFERENCES.md §4 を参照 ([WIN64] の展開先を FL_WIN64_DIR に指定する)
cd tools/liftdiff
python3 -c "import sys; sys.path.insert(0,'.'); from ldlib import build_wasm; t=build_wasm.load_target('targets/m11.json'); build_wasm.ensure_native(); build_wasm.build(t, force=True)"
python3 ld156_chunk0_carryover.py --native 0 --reset sta --native-reset mmap --out results/ld229_raw/sta_mmap_r1.jsonl
python3 ld156_chunk0_carryover.py --native 0 --reset none --native-reset mmap --out results/ld229_raw/none_mmap_r1.jsonl
python3 ld156_chunk0_carryover.py --native 0 --reset sta --native-reset none --out results/ld229_raw/sta_none_r1.jsonl
```

## 7. 測定 commit 以降の差分 (`git diff f6af8ce45 HEAD -- tools/liftdiff`)

本付録と `results/ld229_raw/` の追加のみ。`rt/`・`ld156_chunk0_carryover.py` は測定 commit から変更なし。
