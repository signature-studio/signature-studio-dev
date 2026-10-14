# liftdiff REPORT 付録: LD-122 (#2682) 0x959a40 の全体 run 限定 diff の出所

親 #2258 (LD-96)・前段 `REPORT_APPENDIX_LD96.md` §8、`REPORT_APPENDIX_LD58.md` §7。

## 結論

- 0x959a40 の全体 run 限定 diff の出所は、**同じ runner で 0x959a40 より前に流れる 0x50abe0 の case 列**。
  0x50abe0 を直前に 1 本だけ置いた `[0x50abe0, 0x959a40]` で、単独では match の 0x959a40 が mismatch になる (§4 A)。
- 出所は関数・case の単位まで特定した。0x50abe0 の case 列は「q0 より前の case (z〜pall2)」と「q0」の両方が要る (§4 E1・E2・E4)。
- 直前の 0x43a3f0 は出所ではない (`[0x43a3f0, 0x959a40]` は match: §4 S27)。
- 出所は runner の内部状態。fresh な runner を挟むと消える (§4 F)。どの wasm 側状態が残るか (機構) は未特定。
- 受入 (b): 出所の REPORT 記載は達成。機構の確定と、全体 run 間の揺れの説明は未解決 (§5・#2258 残作業)。

## 1. 測定条件

- 測定 commit: **`4efe8c5b`** (コードを変えた最後の commit。driver `tools/liftdiff/ld122_origin.py` を含む。`fbb3cfca` で追加し `4efe8c5b` で label 名のみ変更)。
- 素材: `fl-win64` (`extracted/block00031_PE.bin`・sha256 `b2c64da4…`)・`work-liftdiff` の `tools/liftdiff/work/m11` (`simd.c` sha256 `d82e2759…` 一致)・`work-m11`・`toolchain-emsdk` (`[EMSDK]` 既存)。
- wasm: `build_wasm.build(t, False)` で `5d88dda2` の worktree にて再ビルド (link 3.1 s)。`simd.c` は素材版のまま (sha256 `d82e2759…`)。以後 `ldlib`・`rt` は変えていない (§6)。
- 測定機: 4 vCPU。全体 run 前の load 0.2〜0.3。

## 2. 再現

```sh
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"      # 素材展開後 (REPORT_APPENDIX_LD96 §8.7 と同じ手順)
cd "$(git rev-parse --show-toplevel)/tools/liftdiff"
python3 liftdiff.py batch targets/m11.json --set sample:800 --shards 12 --nobuild --state auto --out work/m11/batch_final_r1.jsonl
python3 ld122_origin.py > results/ld122_959a40_origin.tsv   # 約 100 s
```

## 3. 全体 run での 0x959a40

- `batch --set sample:800 --shards 12` (測定 commit `4efe8c5b`・wall 1m54s): 0x959a40 は `mismatch` (`callee_divergence`)。
  - p1・pall: `ret` が違う (native `0xffffd4e8`・wasm `0x2206ec00`) かつ trace の index 2 に `wasm_extra_entry` 0x956550 (native_len 2・wasm_len 3)。
  - qall: `ret` のみ (native `0xfffefb20`・wasm `0x2206a5c0`)。
- 0x959a40 は chunk 1 (`vas[400:800]`) の shard 4 (`[4::12]`・33 関数) に入り、その 29 番目 (前置 28 関数)。前置列は `ld122_origin.py` の `SHARD` に置いた。
- 同じ runner で前置列を流し直した replay (`R_shard4_replay`) も `mismatch` (§4)。全体 run の 0x959a40 の結果は、この runner の状態で決まる。

## 4. 切り分け (`results/ld122_959a40_origin.tsv`・測定 commit `4efe8c5b`)

各行は 1 本の runner で「前置 → 0x959a40 (全 pattern)」を流した結果。X = 0x50abe0, Z = 0x43a3f0, W = 0x5bfff0。`PRE_Q0` = z・s・p0・p1・p01・pall・pall2。

| 実験 | 流した順 | 0x959a40 の verdict |
|---|---|---|
| solo | 0x959a40 のみ | match |
| A | X → Y (全 pattern) | **mismatch** (×3 反復で同じ) |
| B | W → Y | match |
| C | W → X → Y | mismatch |
| D | X → Z → Y | mismatch |
| S27 | Z → Y | match |
| F | X → Y、ただし X と Y の間で runner を作り直す | match |
| E1 | X (PRE_Q0 のみ) → Y | match (×2 反復) |
| E2 | X (q0 のみ) → Y | match |
| E4 | X (PRE_Q0 + q0) → Y | **mismatch** |
| E5 | X (qall・vm0・u16 のみ) → Y | match |
| R | shard 4 の 29 関数を順に流す | **mismatch** |

- A・C・D・E4・R が mismatch、solo・B・S27・F・E1・E2・E5 が match。
- W (0x5bfff0) だけを前に置く場合は match (B)。X を含むことが必要。
- F で runner を作り直すと消える。残存は runner の内部状態にある。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x50abe0 の z〜pall2 と q0 が残す wasm 側の状態の機構 (どの領域・どの書込み)。heap 残存は未計測 (LD-96 §8 の監査は 0x50abe0 の先頭 case z のみ、残存 0) | 受入 (b) の原因の確定 | #2258 (残作業) |
| 全体 run 間の揺れの説明。LD58 の shard 12 は r1 のみ match (`REPORT_APPENDIX_LD58.md` §7)。本 run の全体 run は 2 回 (`5d88dda2`・`4efe8c5b`) とも mismatch。replay は反復で安定 | 件数の揺れ | #2258 (残作業) |
| 0x50abe0 の q0 の outcome が run で違う (前回の全体 run は `hang` (wasm timeout)・測定 commit `4efe8c5b` の全体 run と replay は `both_fault`)。timeout 判定の負荷依存が揺れの候補 (未検証) | 揺れの説明 | #2258 (残作業) |

## 6. 差分

- 前段 `5d88dda2` → 測定 commit `4efe8c5b`: `git diff 5d88dda2 4efe8c5b -- tools/liftdiff` は新規ファイル `tools/liftdiff/ld122_origin.py` のみ (ldlib・rt・liftdiff.py は変更 0 行)。
- 測定 commit → HEAD のコード差分: `git diff 4efe8c5b HEAD -- tools/liftdiff/ld122_origin.py tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py | wc -l` = 0 (本付録と results の追加のみ)。
- 生ログ (`work/`) は gitignore 対象のため repo には入れていない。集計は `results/ld122_959a40_origin.tsv` (コミット済み)。
