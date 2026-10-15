# liftdiff REPORT 付録: LD-156 (#3385) chunk 0 `0x5d19e0` の両側持ち越しの切り分け

親 #2723 (LD-126)。前提は `REPORT_APPENDIX_LD121.md` §3 (`0x5d19e0` は両側を作り直したときだけ match・n=2) と `REPORT_APPENDIX_LD126.md` (wasm 候補 RESET の実験。chunk 1 の 18 関数)。
前提の PR #3393 (LD-126 の実装) は 2026-10-15 01:09Z に merge 済み。

測定 commit: **`0de02db4e`** (コードを変えた最後の commit。`tools/liftdiff/ld156_chunk0_carryover.py`)。
この commit 以降に入るのは本付録と `results/ld156_chunk0_carryover.tsv`・`results/ld156_raw/` だけ。

既知類型との関係: 該当なし (`docs/DEFECTS.md` の類型とは別。runner の case 間の持ち越し)。

## 結論

- 対象は chunk 0 の 1 関数 `0x5d19e0` (sample:800 の 0〜399 件目の唯一の対象)。
- **native を作り直し、wasm の C 静的変数 (`sta`) だけを SNAPSHOT 時点へ戻すと match** (n=2・11/11 case equal)。
- 対照 (`native=0, none`) と wasm 単独の候補 (`stk`・`sta`・`img`・`all`、native は作り直さない) は、いずれも mismatch (n=1)。
- native 作り直し + wasm `stk`・`img`・`all` は n=2 で mismatch。`all` が `sta` の効果を消すことは、`REPORT_APPENDIX_LD126.md` の chunk 1 の結果 (`all` で 18/18 mismatch) と同じ向き。
- 残りの未達 (native 側の候補単位の戻し) は未実装。§5 の子 issue に移す。

## 1. 測定条件

- 素材: `fl-win64` (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`・`extracted/block00031_PE.bin`)・`work-liftdiff` (`tools/liftdiff/work/`)・`work-m11` (`tools/m11/work/`)。`toolchain-emsdk` は `/opt/emsdk` (emcc 6.0.12・pin 版)。`ANALYSIS_DIR=$HOME/analysis`。
- wasm は `build_wasm.build(m11, force=True)` で作り直した (9.4 s・`wasm_size` 4463245・`sig_mismatch` 0)。展開済みの `work/m11/ld_wasm.cjs` は現行 `rt/ld_wasm.c` と食い違い (`ld_w_snapshot` の引数数) で使えなかった。
- 機: 4 vCPU・RAM 15 GiB。並列は 4〜5 本 (`&` + `wait`)。load は測定前の 1 分平均で 0.3〜1.8 (各回の load は未記録・n=1/2)。
- 1 条件の wall: 単独 140 s (`none`)・4 並列 148〜167 s (wasm 単独)・5 並列 171〜184 s (native 作り直し)。

## 2. 方法

- `ld156_chunk0_carryover.py`: cmd_batch の chunk 0 (sample:800 の 0〜399 件目) を 1 組の runner で流す (`ld121_restart_probe.py` と同じ開始状態)。
- `--native 1`: 対象関数の直前に native runner を作り直す (`make_runners` の native 側を閉じて開き直す)。
- `--reset <cand>`: 対象関数の直前に `RESET <mask>` を wasm に送る (`ld126_wasm_state.py` と同じ mask: `stk`=1・`sta`=2・`img`=4・`all`=7・`none`=0)。
- 判定は `liftdiff.make_record` の verdict。case の outcome は TSV に残す。

## 3. 結果 (`results/ld156_chunk0_carryover.tsv`)

| native | wasm RESET | n | verdict | case equal |
|---|---|---|---|---|
| 0 (作り直しなし) | none | 1 | mismatch | 0/11 |
| 0 | stk | 1 | mismatch | 0/11 |
| 0 | sta | 1 | mismatch | 0/11 |
| 0 | img | 1 | mismatch | 0/11 |
| 0 | all | 1 | mismatch | 0/11 |
| 0 | img | 2 | mismatch | 0/11 |
| 1 (作り直し) | none | 2 | mismatch | 0/11 |
| 1 | stk | 2 | mismatch | 0/11 |
| 1 | **sta** | **2** | **match** | **11/11** |
| 1 | img | 2 | mismatch | 0/11 |
| 1 | all | 2 | mismatch | 0/11 |

- `none` (native=0) の mismatch は `REPORT_APPENDIX_LD121.md` の結論と一致する (再現)。
- `native=1, sta` の match は n=2 で再現した (`r1` と `r2` の両方が match)。

## 4. 未確認

- **RESET が実際にメモリを戻したかは未確認**。戻したバイト数・snapshot との差分の証跡は取っていない (`REPORT_APPENDIX_LD126.md` §4 と同じ未解決)。`sta` だけ match で他が mismatch になるのは、戻しが効いた結果とも、戻さない候補の偶然とも区別できていない。
- `sta` は heap 高水位の管理変数 (`ld_heap_hw`・`ld_heap_used`) を含むため、C 静的変数の中身と heap 高水位は分かれていない (LD-126 §2 と同じ)。
- native 側の持ち越し (native の静的領域・スタック) の候補単位の戻しは未実装。よって「両側の組合せ」の切り分けは、native 作り直し (both 相当) の 1 種類だけで、native の候補ごとの切り分けは無い。
- `sta` の native=0 (作り直しなし) は n=1 のみ。native 作り直しを加えたときだけ match するかは、この測定では確かめていない (n=1 の mismatch だけ)。

## 5. 子 issue (受入条件 2 の残り)

- native 側の候補単位の戻し (native の静的領域・スタックを SNAPSHOT 時点へ戻す RESET)。`rt/ld_native.c` に候補別 SNAPSHOT/RESET の機構が無いため、実装が要る。
- RESET の効きの証跡 (戻したバイト数・snapshot との差分) は取っていない。これは本 PR では未解決のまま残し、§4 に書いた。

## 6. 再現

```sh
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64" ANALYSIS_DIR="$HOME/analysis"
cd tools/liftdiff
python3 ld156_chunk0_carryover.py --native 1 --reset sta --out work/ld156/n1_sta_r1.jsonl
```
