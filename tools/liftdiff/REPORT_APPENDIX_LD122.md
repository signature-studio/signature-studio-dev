# liftdiff REPORT 付録: LD-122 (#2682) 0x959a40 の全体 run 限定 diff の出所

親 #2258 (LD-96)・前段 `REPORT_APPENDIX_LD96.md` §8、`REPORT_APPENDIX_LD58.md` §7。

既知類型との関係: 該当なし。`docs/DEFECTS.md` の D12 (ours harness) は比較範囲の不足 (出力バッファだけ比較して callee-saved 破損が見えない) で、本件とは別機構。本件は同一 runner で先行する関数が残す wasm 側の状態 (runner 状態の持ち越し) で、機構は未特定 (§5)。

## 結論

- 0x959a40 の全体 run 限定 diff の出所は、**同じ runner で 0x959a40 より前に流れる 0x50abe0 の case 列**。
  0x50abe0 を直前に 1 本だけ置いた `[0x50abe0, 0x959a40]` で、単独では match の 0x959a40 が mismatch になる (§4 A)。
- 出所は 0x50abe0 の case 列 (pattern 単位) まで。**q0 を含む区間が要る**: fvm 経路が走る条件で、z〜pall2 だけ前置すると match、q0 を加えると mismatch (§4 E1・E4)。**z〜pall2 が要るかは未切り分け**: E2 (q0 のみ) は fvm が走らず、E4 と比べると fvm の有無が交絡する (§4 注)。
- 直前の 0x43a3f0 は出所ではない (`[0x43a3f0, 0x959a40]` は match: §4 S27)。
- 出所は runner の内部状態。fresh な runner を挟むと消える (§4 F)。どの wasm 側状態が残るか (機構) は未特定。
- 受入 (b): 出所の REPORT 記載は達成。機構の確定、z〜pall2 の必要性、全体 run 間の揺れの説明は未解決 (§5。機構は #2723 へ移管、他は PM agent の判断待ち)。

## 1. 測定条件

- 測定 commit: **`4efe8c5b`** (コードを変えた最後の commit。driver `tools/liftdiff/ld122_origin.py` を含む。`fbb3cfca` で追加し `4efe8c5b` で label 名のみ変更)。
- 素材: `fl-win64` (`extracted/block00031_PE.bin`・sha256 `b2c64da4…`)・`work-liftdiff` の `tools/liftdiff/work/m11` (`simd.c` sha256 `d82e2759…` 一致)・`work-m11`・`toolchain-emsdk` (`[EMSDK]` 既存)。
- wasm: `build_wasm.build(t, False)` で `5d88dda2` の worktree にて再ビルド (link 3.1 s)。`simd.c` は素材版のまま (sha256 `d82e2759…`)。以後 `ldlib`・`rt` は変えていない (§6)。
- 測定機: 4 vCPU。全体 run 前の load 0.2〜0.3。

## 2. 再現

```sh
# 素材 (REPORT_APPENDIX_LD96 §8.7 と同じ展開)。fl-win64 は $ARTIFACTS_DIR に置かれている前提
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"
cd "$(git rev-parse --show-toplevel)"
tar --zstd -xf "$ARTIFACTS_DIR/work-liftdiff.tar.zst" tools/liftdiff/work/m11   # 素材版 simd.c・boot_state.json (--state auto)・sigs.json
tar --zstd -xf "$ARTIFACTS_DIR/work-m11.tar.zst"                                # tools/m11/work
mkdir -p "$RUNNER_TEMP/fl-win64"
tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" extracted/block00031_PE.bin
sha256sum tools/liftdiff/work/m11/simd.c | cut -c1-16   # d82e27592c03a316 でなければ停止
cd tools/liftdiff
gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm
# build() は既存 wasm の有無ではなく mtime (ldlib/build_wasm.py の newer()) で再ビルドを判断する。checkout 直後は rt/ などのソースが同梱 obj より新しく、同梱の ld_wasm.wasm (4455266 B) があっても全 obj が再コンパイルされ再リンクされる (fix run で 4457524 B)。この行は常に実行する (§1 と同じ呼び出し。force なし。[EMSDK] が必要・docs/REFERENCES.md §4)
python3 -c "from ldlib import build_wasm as b; b.build(b.load_target('targets/m11.json'))"
python3 liftdiff.py batch targets/m11.json --set sample:800 --shards 12 --nobuild --state auto --out work/m11/batch_final_r1.jsonl
python3 ld122_origin.py > results/ld122_959a40_origin.tsv   # wall は stderr の `# <実験名> <N>s` 行
```

## 3. 全体 run での 0x959a40

- `batch --set sample:800 --shards 12` (測定 commit `4efe8c5b`・wall 1m54s): 0x959a40 は `mismatch` (`callee_divergence`)。全体 run の判定は記録ごとに揺れる (下表)。
  - p1・pall: `ret` が違う (native `0xffffd4e8`・wasm `0x2206ec00`) かつ trace の index 2 に `wasm_extra_entry` 0x956550 (native_len 2・wasm_len 3)。
  - qall: `ret` のみ (native `0xfffefb20`・wasm `0x2206a5c0`)。
- 0x959a40 は chunk 1 (`vas[400:800]`) の shard 4 (`[4::12]`・33 関数) に入り、その 29 番目 (前置 28 関数)。
- **SHARD (`ld122_origin.py`) の導出**: `liftdiff.py` の `cmd_batch` は chunk ごとに `run_functions(part)` を呼び、shard k は `part[k::12]` (`ldlib/session.py`)。jsonl は part の順 (chunk 内の sort 順) に書かれるので、jsonl の 401〜800 行の `[4::12]` が shard 4 になる。次の 1 コマンドで先頭の 29 件を出し、driver の `SHARD` (29 件目が 0x959a40) と一致することを確かめる。
  ```sh
  sed -n '401,800p' work/m11/batch_final_r1.jsonl | python3 -c "import sys,json; rs=[json.loads(l)['function']['va'] for l in sys.stdin]; print(' '.join(rs[4::12][:29]))"
  ```
  - 初版の作成 run では jsonl と `work/m11/sigs.json` が素材に無く、このコマンドは実行していなかった。fix run (`ede666e6`・素材展開後) で実行し、出力の 29 件は driver の `SHARD` と同一で末尾が 0x959a40 だった。
- 同じ runner で前置列を流し直した replay (`R_shard4_replay`) も `mismatch` (§4)。
- 全体 run の記録 (0x959a40 と、同じ chunk で 0x959a40 の直前に流れる X = 0x50abe0 の q0)。判定は 4 記録で mismatch 3・match 1 で、決める条件は未特定 (§5)。

| run | commit | 0x959a40 | X の q0 | 備考 |
|---|---|---|---|---|
| 全体 run (前回) | 5d88dda2 | mismatch | hang (wasm timeout) | jsonl は本 run の素材に無い |
| 全体 run | 4efe8c5b | mismatch | both_fault | wall 1m54s |
| 独立再実行 (レビュー) | ede666e6 | match | hang | レビュー run の報告値。開始時 load 4.5 |
| 独立再実行 (fix run) | ede666e6 | mismatch | both_fault | wall 2m11s・開始時 load 4.50 |

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
- F で runner を作り直すと消える。残存は runner の内部状態にある。同じ型の現象 (runner の作り直しで消える) は `REPORT_APPENDIX_LD121.md` §3 にある。
- **fvm の注意**: `_fvm_cases` (`ldlib/session.py`) は、その関数の case に equal・diff・wasm_trap が 1 つも無いときだけ走り、`'s'` の native fault アドレスから候補を作る。E2 の X 側は `q0` のみで `'s'` が無いため候補 0 となり、fvm 行が出ない (first_outcomes に fvm 行なし)。E4 の X 側は `'s'` を含み fvm 行が出る。よって E2 対 E4 は fvm の有無と前置の内容が交絡し、z〜pall2 の要不要は言えない。fvm が走る条件同士の対比は E1 (match) 対 E4 (mismatch) だけで、q0 の要否はこれで言う。
- tail (qall・vm0・u16) は必要ではない: E4 は tail を含まないのに mismatch (A と同じ判定)。E5 (tail のみ) は match。
- E4 は 1 回のみ測定 (反復なし)。E1 は ×2 反復で match。
- 再実行: `ede666e6` の driver 出力は本表の TSV と `cmp` でバイト一致した (fix run。レビュー run も同じ TSV を報告)。R (shard 4 の replay) は 3 回の別 run (`4efe8c5b` の TSV・レビュー run・fix run) とも mismatch。
- TSV の `Y_tags` 列は driver が `make_record(sess, rec, {})` (IR 特徴なし) で作るため、batch の tags と同じとは限らない。本表の判定は verdict と outcome で行い、tags は参考。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x50abe0 の q0 (と z〜pall2 の要否) が残す wasm 側の状態の機構 (どの領域・どの書込み)。heap 残存は未計測 (LD-96 §8 の監査は 0x50abe0 の先頭 case z のみ、残存 0) | 受入 (b) の原因の確定 | #2723 (コメントで移管)。0x959a40 は #2723 の範囲 (shard 1 の 19 関数) の外のため、範囲を広げるかは PM agent の判断待ち |
| z〜pall2 の要否。fvm を揃えた対照 (例: `[s, q0]` を前置) は未測定 (差し戻し対応の run は素材を展開できたが、この対照は測定していない) | 結論の範囲 (§結論) | PM agent の判断待ち: この対照の測定を追跡として残すか、結論を (a) の範囲のまま閉じるか |
| 全体 run 間の揺れの説明。0x959a40 の全体 run は 4 記録で mismatch 3・match 1 (§3 表)。LD58 の shard 12 は r1 のみ match (`REPORT_APPENDIX_LD58.md` §7)。R (shard 4 の replay) は 3 回の別 run とも mismatch で、全体 run の match と一致しない | 件数の揺れ | PM agent の判断待ち: 追跡先 (親 #2258 は CLOSED。#2723 の範囲外) |
| X の q0 の outcome と全体 run の判定の対応。hang の記録は 2 件 (5d88dda2 の全体 run: mismatch、レビュー run: match)。both_fault の記録は mismatch (4efe8c5b・fix run) と match (素材同梱の過去 jsonl のうち作成時期と版が本測定と別の run) の両方にある。よって X の q0 の outcome だけでは判定を決められない。timeout 判定の負荷依存は未検証 (fix run も開始時 load 4.50 で both_fault・mismatch) | 揺れの説明 | PM agent の判断待ち: 上の全体 run の揺れと同じ追跡先 |

## 6. 差分

- 前段 `5d88dda2` → 測定 commit `4efe8c5b`: `git diff 5d88dda2 4efe8c5b -- tools/liftdiff` は新規ファイル `tools/liftdiff/ld122_origin.py` のみ (ldlib・rt・liftdiff.py は変更 0 行)。
- 測定 commit → HEAD のコード差分: `git diff 4efe8c5b HEAD -- tools/liftdiff/ld122_origin.py tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py | wc -l` = 0 (出力 0 行。main 取り込み後の HEAD でも 0 行。本付録と results の追加のみ)。
- 生ログ (`work/`) は gitignore 対象のため repo には入れていない。集計は `results/ld122_959a40_origin.tsv` (コミット済み)。
