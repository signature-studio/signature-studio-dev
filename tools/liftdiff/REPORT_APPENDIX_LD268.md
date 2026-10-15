# liftdiff REPORT 付録: LD-261 (#5268) `0x5d19e0` の持ち越し先 mapping の切り分け

成果物の名前 (`ld268_*`・`results/ld268_*`) は付番時の仮番号 LD-268 のまま (`REPORT_APPENDIX_LD261.md` と同じ扱い)。本付録の題名・issue (#5268) の番号は LD-261。

親 #3385 (LD-156)。前提は `REPORT_APPENDIX_LD261.md` (both 条件で match・none で mismatch・n=2/1) と `REPORT_APPENDIX_LD229.md` (native の anon mmap を一括で戻すと match)。本付録は、一括の `mmap` 候補 (bit 8) を領域単位に分けて、どの領域が効くかを切り分けた。

## 結論

- SNAPSHOT 直後の native の anon rw-p mapping は **6 領域** (`ld268_mmap_regions.py`・`results/ld268_mmap/regions.json`)。
- wasm `sta` を固定し、native の領域 **k=0 (`0x555555564000`・3,108,864 B) だけを戻す** と **match** (`sta_one0`・`z` 以外 10 件 equal、`z` は native crash・wasm hang)。前回の一括 `mmap` (6 領域) と同じ結果。
- k=0 を外して残り 5 領域を戻すと **mismatch** (`sta_exc0`)。k=0 は必要。
- 受入条件 1 (持ち越しの中身の特定) は **部分達成**。持ち越しの実体は k=0 の 3 MB 領域まで絞れたが、その領域の中のどの変数・構造体かは未切り分け。
- 単独の k=1〜5 (wasm none) はすべて mismatch。wasm `sta` との組み合わせの単独測定は k=0 だけで、k=1〜5 の `sta` 併用は未測定。

## 1. 測定条件

- 素材: `fl-win64` (`$ARTIFACTS_DIR/fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に展開・`FL_WIN64_DIR`)。`toolchain-emsdk`・`work-m11`・`work-liftdiff` は `$ARTIFACTS_DIR` で実在を確認し、本体の `work/` を worktree から symlink で参照。
- wasm は `build_wasm.build(t, force=True)` で作り直した (`wasm_size` 4464620・`sig_mismatch` 0・`undefined` 0。LD-261 と同じ値)。
- native は `ensure_native()` で rt/ の現版から作り直した (`work/ld_native`)。
- 対象は chunk 0 の `0x5d19e0` 1 件 (`sample:800` の 0〜399 件目)。各 run は 1 本逐次、または 2 本並列 (機 4 vCPU・load 0.7〜1.1 程度)。各 run の所要は 124〜131 s (関数 1 件の実行時間)・全体は 171〜177 s。

## 2. 方法

- `rt/ld_native.c` に 3 つのプロトコルを足した (既存の `NRESET` の挙動は変えていない)。
  - `NMMAPN`: NRST_MMAP 領域の件数と (lo, n) を返す。
  - `NRESETI k`: k 番目の領域だけを戻す (`skip` は munmap 済みの件数)。
  - `NRESETX k`: k 番目以外を戻す (leave-one-out)。
- `ld156_chunk0_carryover.py` に `--native-reset-one k`・`--native-reset-except k` を足し、出力 JSON に `native_reset_one`・`native_reset_except`・`native_reset_skip` を入れた。
- 領域番号 k は `NMMAPN` の順 (SNAPSHOT 直後の /proc/self/maps の順)。対象関数の直前の番号と同じかは未確認 (下の §4)。

## 3. 結果 (`results/ld268_mmap/`)

native の領域 (SNAPSHOT 直後):

| k | lo | n (B) |
|---|---|---|
| 0 | `555555564000` | 3108864 |
| 1 | `7ffff65d0000` | 1036288 |
| 2 | `7ffff7e06000` | 53248 |
| 3 | `7ffff7e2c000` | 532480 |
| 4 | `7ffff7fae000` | 12288 |
| 5 | `7ffff7fbb000` | 8192 |

### 3.1 wasm none・native 単独 (`--reset none`)

| 戻す領域 | verdict | native diff (B) | skip | ファイル |
|---|---|---|---|---|
| k=0 のみ | mismatch | 39891 | 0 | `one0.jsonl` |
| k=1 のみ | mismatch | 0 | 1 (munmap 済み) | `one1b.jsonl` |
| k=2 のみ | mismatch | 3 | 0 | `one2.jsonl` |
| k=3 のみ | mismatch | 0 | 0 | `one3.jsonl` |
| k=4 のみ | mismatch | 0 | 0 | `one4.jsonl` |
| k=5 のみ | mismatch | 0 | 0 | `one5.jsonl` |

### 3.2 wasm none・native 以外を戻す (leave-one-out)

| 除外 k | verdict | native diff (B) | skip | ファイル |
|---|---|---|---|---|
| 0 | mismatch | 6 | 1 | `exc0.jsonl` |
| 1 | mismatch | 39891 | 0 | `exc1.jsonl` |
| 2 | mismatch | 39891 | 0 | `exc2.jsonl` |
| 3 | mismatch | 39891 | 0 | `exc3.jsonl` |
| 4 | mismatch | 39891 | 0 | `exc4.jsonl` |
| 5 | mismatch | 39891 | 0 | `exc5.jsonl` |

注: 3.2 は wasm を none にしたままで、LD-229 の対照 (wasm none) と同じく mismatch になるのは想定どおり。3.2 の値は「wasm 側の状態が効いている」ことの確認に使う。

### 3.3 wasm sta・native の leave-one-out / 単独 (本付録の要点)

| wasm | native | verdict | native diff (B) | skip | wasm diff (B) | equal | ファイル |
|---|---|---|---|---|---|---|---|
| sta | 除外 k=0 (= k=1〜5 を戻す) | mismatch | 6 | 1 | 343847 | 0/11 | `sta_exc0.jsonl` |
| sta | 除外 k=1 (= k=0,2〜5 を戻す) | **match** | 39891 | 0 | 343847 | 10/11 (`z` 以外 10 件 equal。`z` は下の注) | `sta_exc1.jsonl` |
| sta | k=0 のみ | **match** | 39891 | 0 | 343847 | 10/11 (`z` 以外 10 件 equal。`z` は下の注) | `sta_one0.jsonl` |

- `z` (sta 条件・`sta_one0` と `sta_exc1` の両方): **native crash・wasm hang** (`z` の outcome は `hang`・native `crash`・wasm `hang`)。verdict は match だが、`z` だけは status が一致していない。
- 同じ `z` は、wasm を作り直した both 条件 (`ld268_raw/both_r1.jsonl`・`both_r2.jsonl`) では `equal / ok / ok`。`sta_exc0` (k=0 を外した mismatch) では `diff / ok / ok` で、native は crash しなかった。
- `z` だけが both 条件と異なる理由は**未確認** (LD-229 の注と同じく、`z` は timeout 境界の case で run ごとに揺れる。原因の切り分けは未実施)。
- したがって「k=0 が効く」の結論は、`z` を含む 11 件の一致ではなく、`z` 以外の 10 件の一致と `sta_exc0` の mismatch (`diff`) に基づく。

`sta_exc1` と `sta_one0` は、戻った native の領域がともに k=0 を含む (= k=0 が効く) ことを示す。`sta_exc0` は k=0 を戻さないため mismatch。

## 4. 未確認 (受入条件 1 の残り)

- **k=0 の中身 (どの変数・構造体か)** は未切り分け。`0x555555564000` が何の領域かは確認していない (`/proc/self/maps` での path 確認も未実施)。
- k=0 の中をさらに分ける (バイト範囲の半分ずつの戻し) は未実施。
- `NMMAPN` は SNAPSHOT 直後の値。対象関数の直前で領域の番号・lo が同じかは未確認 (`sta_one0` の match は同一 k=0 を戻しているので、少なくとも k=0 の番号は一致している)。
- k=1 は対象時点で munmap 済み (skip=1) で、単独 `one1` では戻せていない。`exc0` の diff 6 B の由来は**未検証**。単独の k=2 は 3 B、k=3〜5 は 0 B だが、k=1 は munmap 済みで寄与しないため、1〜5 の合計が 6 B になる説明にはならない。
- `sta` 併用の k=1〜5 単独 (wasm sta・native k のみ) は未測定。k=0 以外が単独で match するかは未確認。
- 各条件 n=1。`sta_one0`・`sta_exc1` の再現 (n=2) は未実施。

## 5. 子 issue

- 受入条件 1 の残り (k=0 の 3 MB 領域の中身を、バイト範囲の半分割りで切り分ける) は、本 issue #5268 の範囲に残す。次 run が同じ issue の続きとして扱う。
- 子 issue は起票しない (本 run の時間内に同じ issue の続きとして完結できるため)。

## 6. 再現

```sh
# FL_WIN64_DIR は $RUNNER_TEMP/fl-win64 (fl-win64 を展開)。docs/WORKFLOW.md §11
cd tools/liftdiff
python3 -c "import sys; sys.path.insert(0,'.'); from ldlib import build_wasm; t=build_wasm.load_target('targets/m11.json'); build_wasm.ensure_native(); build_wasm.build(t, force=True)"
python3 ld268_mmap_regions.py --out results/ld268_mmap/regions.json
python3 ld156_chunk0_carryover.py --native 0 --reset sta --native-reset-one 0 --out results/ld268_mmap/sta_one0.jsonl
python3 ld156_chunk0_carryover.py --native 0 --reset sta --native-reset-except 1 --out results/ld268_mmap/sta_exc1.jsonl
python3 ld156_chunk0_carryover.py --native 0 --reset sta --native-reset-except 0 --out results/ld268_mmap/sta_exc0.jsonl
```

## 7. 測定 commit 以降の差分

- 測定 commit: **`5857de81b`** (`feat(liftdiff): split native mmap reset per region for 0x5d19e0 (#5268)`。測定に使った `rt/ld_native.c`・`ld156_chunk0_carryover.py`・`ld268_mmap_regions.py` を含む commit)。
- 測定時の作業ツリーが `5857de81b` の tree と同一だったことは、測定時点の記録が無いため確認できていない。ここでは同 commit の tree から測り直していないことを明記しておく。
- `git diff 5857de81b HEAD -- tools/liftdiff ':!tools/liftdiff/REPORT_APPENDIX_LD268.md'` の出力は 0 行 (本 REPORT の訂正 commit だけを除く)。
- main の取り込みは測定後。
