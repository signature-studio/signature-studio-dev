# liftdiff REPORT 付録: LD-121 (#2681) shard 1 の 19 関数の揺れの原因分類 (runner 作り直し実験)

親 issue #2258 (LD-96)。前提は `REPORT_APPENDIX_LD96.md` §8 (高水位外の heap 残存の計測・測定 commit `7d434168`)。
測定 commit: **`8aac412b`** (driver `ld121_restart_probe.py` を追加した commit)。

## 結論

- 揺れの原因は **wasm runner 側に持ち越される状態**。chunk 1 の 18 関数は、wasm runner だけを各関数の直前に作り直すと全て `match`、native runner だけを作り直すと全て `mismatch` のまま (n=2 で再現)。
- chunk 0 の 1 関数 `0x5d19e0` は、wasm だけ・native だけの作り直しでは `mismatch` のまま。**両側を作り直したときだけ `match`** (n=2)。両側の持ち越しに依存する。
- **heap 高水位外の残存は揺れの単独原因ではない**。19 関数のうち、wasm の先頭 case に高水位外の残存があるのは 3 関数 (`0x4bf600`・`0x7850d0`・`0xb77200`、全 case の最大 11 B)。残存 0 の 16 関数も揺れ、wasm 作り直しで一致する。
- 持ち越しを運ぶ wasm 側の状態 (heap 高水位外を除く候補) は**未特定**。子 issue #2723 に分割した。

## 1. 測定条件

- 素材: `fl-win64` (`extracted/block00031_PE.bin`)・`work-liftdiff`・`work-m11` を展開。`toolchain-emsdk` は runner 既存の `/opt/emsdk` (emcc 6.0.12・pin と一致) を使い、展開はしていない。`simd.c` は素材版 (sha256 `d82e2759…`)。再ビルド後も同じ。
- ビルド: `build_wasm.build(t, False)` (`simd.c` は再生成されない)、`gcc` で `work/ld_native`。
- 測定機: 4 vCPU。4 条件 (`none`・`native`・`wasm`・`both`) は同時に流した。

## 2. 方法

- `ld121_restart_probe.py`: sample:800 の chunk を cmd_batch と同じ 400 件境界で切り、chunk 1 (400..799) または chunk 0 (0..399) を 1 組の runner で流す (`ld96_heap_audit.py --mode full` と同じ開始状態。`ld96` の chunk 1 の既存 verdict 18/18 と一致することを確認)。
- 19 関数の直前に、`--restart` で指定した側の runner を作り直す。作り直した側は chunk 開始時と同じ init 状態になり、もう一方は前の関数の状態を持ち越す。
  - `none`: 作り直しなし (従来の chunk 実行)。`native`: native だけ。`wasm`: wasm だけ。`both`: 両方。
- 19 関数の選び方は `results/ld58_m11_sample800_shards_t1.tsv` で r1=match かつ s1=mismatch (`ld96_heap_audit.py` と同じ)。

## 3. 結果

| 条件 | chunk 1 (18 関数) | chunk 0 (`0x5d19e0`) | n=2 |
|---|---|---|---|
| `none` (作り直しなし) | mismatch 18/18 | mismatch | 全件一致 |
| `native` (native だけ作り直し) | mismatch 18/18 | mismatch | 全件一致 |
| `wasm` (wasm だけ作り直し) | **match 18/18** | mismatch | 全件一致 |
| `both` (両方作り直し) | match 18/18 | **match** | 全件一致 |

- 全 19 件の行は `results/ld121_restart_probe.tsv` (列 `class`: `wasm 側の持ち越し` 18・`両側の持ち越し` 1)。
- case 単位 (chunk 1 の 18 関数 × 11 pattern = 198 case): `none` は `diff` 70・`native_fault` 61・`both_fault` 22・`hang` 26・`wasm_trap` 12・`equal` 7。`wasm` 作り直しでは `equal` 89・`native_fault` 81・`both_fault` 13・`hang` 15。`diff` は 0。
- 所要 (wall・n=1 は chunk 1 の 4 並列、n=2 は同じ条件の再実行): chunk 1 では `none` 276 s・`wasm` 326 s (n=2: 319 s)・`native` 378 s (375 s)・`both` 327 s (319 s)。chunk 0 (4 並列) は 155〜162 s (n=2: 154〜166 s)。load は未記録。

## 4. heap 残り仮説の判定 (§8 の既存計測との突合)

- 高水位外の残存 (`REPORT_APPENDIX_LD96.md` §8 の計測・全 case の最大値、`results/ld96_heap_residue.tsv`): wasm は `0x4bf600`・`0x7850d0`・`0xb77200` の 3 関数だけ (各 11 B)。native は 19 関数すべて 0。`0x5d19e0` は wasm も 0。
- 残存 0 の 16 関数 (chunk 1 の 15 関数と `0x5d19e0`) も揺れる。よって高水位外の残存は揺れの**必要条件でも単独の原因でもない**。残存を持つ 3 関数が揺れる説明も、この計測からは出ない。
- 復元の仕組み (`rt/ld_core.h` の `ld_model_reset`): 各 case の前に、heap は `[0, max(hw, LD_HEAP_RESERVED))` を pristine から戻し、image の WR 範囲と arena も戻す。高水位より外の書込みは戻されず、case 間で持ち越せるのは heap ではこの範囲だけ。
- wasm 作り直しで 18 関数が一致するのは、高水位外の残存以外の wasm 側の状態 (候補: wasm スタック・高水位内外の C 静的変数・WR 範囲外の image・JS ランナ側の状態) が効いているため。どれかは本付録では特定していない (子 issue #2723)。

## 5. 読み取り

- chunk 1 の 18 関数: wasm 側の持ち越しが原因。必要条件 (wasm を作り直すと一致) と、native 側の持ち越しが無害であること (native を作り直しても不一致のまま) の両方を満たす。
- `0x5d19e0`: 両側の持ち越しに依存する。wasm 単独で作り直すと native 側の持ち越しが残り、native 単独では wasm 側の持ち越しが残るため、どちらも単独では揺れが消えない。残存 0 のため、heap 高水位外とは無関係。
- 交絡の注意: 作り直しは対象関数の直前だけで、先行関数の列は変えていない。どの先行関数の状態が効いたかは分からない (関数順の実験は未実施)。
- `REPORT_APPENDIX_LD96.md` §8.6 の未解決のうち「wasm ランナ再起動による消去の検証」は、本付録 §3 の `wasm` 条件で答えた。「残存を持たない 16/19 関数の揺れの原因」は wasm 側の持ち越しと分かった (残存とは別)。その他の行は #2258 に残す。

## 6. 測定 commit と差分

- 測定 commit: `8aac412b`。測定後に `tools/liftdiff/ldlib`・`tools/liftdiff/rt`・`tools/liftdiff/liftdiff.py`・`tools/liftdiff/ld121_restart_probe.py` は変えていない。
- `git diff 8aac412b HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py tools/liftdiff/ld121_restart_probe.py | wc -l` は 0 (本 PR の REPORT・TSV の変更はコード範囲外)。

## 7. 再現

```sh
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"          # extracted/block00031_PE.bin を含む展開先
cd "$(git rev-parse --show-toplevel)"
tar --zstd -xf "$ARTIFACTS_DIR/work-liftdiff.tar.zst"
tar --zstd -xf "$ARTIFACTS_DIR/work-m11.tar.zst"
mkdir -p "$RUNNER_TEMP/fl-win64"
tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" extracted/block00031_PE.bin
sha256sum tools/liftdiff/work/m11/simd.c | cut -c1-16   # d82e27592c03a316 でなければ停止
cd tools/liftdiff
gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm
python3 -c "import sys; sys.path.insert(0,'.'); from ldlib import build_wasm as b; b.build(b.load_target('targets/m11.json'), False)"
for m in none native wasm both; do python3 ld121_restart_probe.py --part 1 --restart $m --out work/ld121/$m.jsonl; done
for m in none native wasm both; do python3 ld121_restart_probe.py --part 0 --restart $m --out work/ld121/p0_$m.jsonl; done
```

- 生データは `work/ld121/` (gitignore)。集計 TSV は `results/ld121_restart_probe.tsv` (コミット済み)。
- 注: `--restart` の作り直しは、作り直さない側の runner も一時的に生成して捨てる (`Session.make_runners` が両方作るため)。結果には影響しない。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| wasm 側の持ち越し状態の特定 (heap 高水位外を除く候補の絞り込み) | 揺れの機構 (受入 (b)) | #2723 (子) |
| `0x5d19e0` の両側持ち越しの中身 (native 側の状態を含む) | chunk 0 の 1 関数の説明 | #2723 (子) |
| 先行関数のどれが効いたか (関数順を変える実験) | 持ち越しの発生源 | #2723 (子) |
