# liftdiff REPORT 付録: LD-226 (#4590) sta_img にスタック復元を足すと効果が消える機構

親 #3384 (LD-155)。前提は `REPORT_APPENDIX_LD126.md` §3・§3.1 (sta_img で match 4 件、スタック復元 (`all`) で 0 件)。

測定 commit: **`7a9c41e56`** (コードを変えた最後の commit。`rt/ld_wasm.c` と `ld126_wasm_state.py`)。

## 結論

- 機構は**未特定**。受入条件は未達 (部分達成)。
- スタックを SP 基準で 3 区間に分けて、`sta_img` に足すと、深い区間 (`deep`)・SP 直下 128K の窓 (`win`) のどちらを足しても match 4 件は残る。**効果を消すのは、これらの区間ではない**。
- SP より上の区間 (`hi`) を足すと match が 0 件になる。ただし `hi` の RESET 差分は 587,202,032 B である。差分は `hi` の区間内にしかないので、`hi` の区間長 (`stbase − SP`) はこの値以上、すなわち 587 MB 以上になる。区間長そのものは測定していない。一方、`deep`・`win` の差分は小さい (`win` は `SP − winlo` が正の長さ)。stack サイズの前提と、`emscripten_stack_get_base()`・`get_end()` の返す値のどちらが正かは未確定。原因の候補 (base/end の値・snapshot の複製) は未特定 (下の未解決)。この `hi` の結果は根拠にできない。
- 戻しの証跡は取れた: RESET が返す `diff` (戻したバイト数) が 0 でない (`sta_img` の初回 RESET で 15,321,005 B)。`all` = `none` の一致の切り分けは未完 (§4)。

## 1. 測定条件

- 素材: `fl-win64` (`extracted/block00031_PE.bin`)・`work-liftdiff`・`work-m11`。`toolchain-emsdk` は runner 既存。
- wasm: `build_wasm.build(m11, False)`。`wasm_size` = 4464588 (前付録の 4459215 とはビルドの差がある)。
- 機: 4 vCPU・RAM 15 GiB。5 条件を同時に流した (`xargs -P 5`)。wall 241〜283 s。実行前の load 0.81〜1.28 (12:00 前後)。
- 対象: shard 1 の chunk 1 の対象件数は **17**。REPORT の 18 件と 1 件違う (`0x959a40` は chunk 1 に入るが、本測定の対象 aud 集合では 17 件として数えた。`0x44ec40`・`0x5d19e0` は chunk 1 の外)。件数の食い違いは未確認 (未解決)。

## 2. 方法

- `ld_w_snapshot` で、スタックを 3 区間に分けて複製する:
  - `deep` (mask 128): `[stack_end, SP−128K)`
  - `win` (mask 512): `[SP−128K, SP)` (case 開始時の 0 埋め窓)
  - `hi` (mask 256): `[SP, stack_base)`
- `sta_img` は mask 6 (sta + img)。`sta_img_deep`・`sta_img_win`・`sta_img_hi` は、それぞれ 6 に上の 1 区間を足した mask。`all` = 7。
- `all` = 7 は deep + win + hi で、`[stend, stbase)` 全体を戻す。これは `REPORT_APPENDIX_LD126.md` §3 の LD-126 の stk と同じ範囲である。したがって `all` の「スタック復元で 0 件」は、`hi` の 587 MB 以上の範囲を戻した結果を含む。`all` = `none` の解釈は `hi` の結論待ち。

## 3. 結果 (コミット済み HEAD・n=1・対象 17 件)

| 条件 | match | mismatch | RESET 差分の先頭 4 件 (B) |
|---|---|---|---|
| `sta_img` (6) | 4 | 13 | 15,321,005 / 39,744 / 9,659 / 193,698 |
| `sta_img_deep` (6+128) | 4 | 13 | 15,321,011 / 39,752 / 9,659 / 193,698 |
| `sta_img_win` (6+512) | 4 | 13 | 15,451,810 / 40,026 / 9,964 / 324,289 |
| `sta_img_hi` (6+256) | 0 | 17 | 587,202,032 (異常) |
| `all` (7) | 0 | 17 | 587,202,032 (異常) |

- match 4 件は `sta_img`・`deep`・`win` で同じ (`0x4bf600`・`0x50ab90`・`0x7850d0`・`0xb77200`)。全件の verdict は `results/ld226_sta_img_stack.tsv`。
- `hi` と `all` の RESET 差分が同じ 587,202,032 B である点は観測値である。`all` は `hi` を含むので同じ値になるが、この値の原因は未特定で、効果の所在の根拠にはしない。

## 4. 読み取り

- 効果を消す区間は、現時点では確定していない。`hi` を足すと match 0 件になるが、`hi` の差分量が観測上異常なので、その結果から区間を特定しない。
- `deep` と `win` を足しても効果は消えない。このため「SP より深い死んだフレーム」と「case 開始時の 0 埋め窓」は、単独では効果を消さない。
- `all` = `none` の一致は未確認 (RESET の効きの証跡は、差分量が取れたことで一部確認した)。

## 5. 再現

```sh
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"
cd "$(git rev-parse --show-toplevel)/tools/liftdiff"
python3 -c "from ldlib import build_wasm as b; b.build(b.load_target('targets/m11.json'), False)"
printf '%s\n' sta_img sta_img_deep sta_img_hi sta_img_win all | xargs -P 5 -I{} sh -c 'python3 ld126_wasm_state.py --reset {} --out work/ld226/{}.jsonl > work/ld226/{}.log 2>&1'
```

- 生データは `work/ld226/` (gitignore)。集計 TSV `results/ld226_sta_img_stack.tsv` は、`ld226_summarize.py` (repo 内) で `work/ld226/<条件>.jsonl` の verdict と `.reset.json` の差分から作る: `python3 ld226_summarize.py > results/ld226_sta_img_stack.tsv`。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `hi` 区間の長さ・RESET 差分 587,202,032 B の原因が未特定 (`emscripten_stack_get_base()`・`get_end()` の返す範囲と stack サイズの前提、snapshot の複製のどれが正か未確定) | `hi` 結果の信頼性・機構の特定 (受入条件) | #4801 (`[LD-240]`・子 issue。本 PR の範囲外) |
| LD-126 の「スタック復元 (`all`) で 0 件」の解釈 (`all` は `hi` と同じ範囲を含む) | `all` = `none` の一致の結論 | #4801 (`[LD-240]`) の結論待ち |
| 対象件数 17 と REPORT の 18 の食い違い | 対象集合の確定 | #3384 (LD-155) |
| n=2 反復 | 結論の再現性 | #3384 (LD-155) |
