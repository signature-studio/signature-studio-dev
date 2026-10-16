# liftdiff REPORT 付録: LD-226 (#4590) sta_img にスタック復元を足すと効果が消える機構

親 #3384 (LD-155)。前提は `REPORT_APPENDIX_LD126.md` §3・§3.1 (sta_img で match 4 件、スタック復元 (`all`) で 0 件)。
LD-240 (#4801) で hi 区間の測定誤りを直した (下の §0)。

測定 commit: **`e4c198b59`** (コードを変えた最後の commit。`rt/ld_wasm.c`・`rt/ld_runner.mjs`・`ldlib/build_wasm.py`)。

## 0. 前回の誤り (LD-240 で修正)

- 前版の `hi` の RESET 差分 587,202,032 B は、`ld_w_reset` が wasm 内で戻す処理のせいで出た誤りだった。
- `hi` 区間 `[SP, stack_base)` は、戻す処理自身のフレーム (`-O0` の `i`・`k`・`diff`) と重なる。`memcpy` でこの区間を戻すと、戻し中のループ変数が上書きされ、戻り値が壊れる。
- 戻り値の 575,469,632 は、その壊れた値の一つ (`stack_end` のアドレスと一致した) で、差分量ではない。
- 修正: 戻しと差分の数えを JS 側 (`ld_runner.mjs` の `resetRegions`) に移した。wasm 側は区間情報を読むゲッターだけにする。
- 修正後の `hi` 区間の差分は 15,321,083 B (`sta_img` 同様の大きさ) で、前版の 587 MB は消えた。
- 前版 `hi` の「match 0/17」は誤った差分による結果なので、根拠にしない。

## 1. 測定条件

- 素材: `fl-win64` (`extracted/block00031_PE.bin`)・`work-liftdiff`・`work-m11`・`toolchain-emsdk`。
- wasm: `build_wasm.py targets/m11.json --force` (`wasm_size` 4464521・`sig_mismatch` 0)。
- 機: 4 vCPU・RAM 15 GiB。5 条件を `xargs -P 3` で流した。wall 7 分 16 秒 (436 s)。load 1.74〜2.14。
- 対象: shard 1 の chunk 1 の対象件数は **17**。REPORT の 18 件と 1 件違う (`0x959a40` は chunk 1 に入るが、本測定の対象 aud 集合では 17 件として数えた。`0x44ec40`・`0x5d19e0` は chunk 1 の外)。件数の食い違いは未確認 (未解決)。

## 2. 方法

- `ld_w_snapshot` で、スタックを 3 区間に分けて複製する:
  - `deep` (mask 128): `[stack_end, SP−128K)`
  - `win` (mask 512): `[SP−128K, SP)` (case 開始時の 0 埋め窓)
  - `hi` (mask 256): `[SP, stack_base)`
- `sta_img` は mask 6 (sta + img)。`sta_img_deep`・`sta_img_win`・`sta_img_hi` は、それぞれ 6 に上の 1 区間を足した mask。`all` = 7。
- `all` = 7 は deep + win + hi で、`[stend, stbase)` 全体を戻す。`REPORT_APPENDIX_LD126.md` §3 の stk と同じ範囲。

## 3. 結果 (コミット済み HEAD・n=1・対象 17 件)

| 条件 | match | mismatch | RESET 差分の先頭 4 件 (B) |
|---|---|---|---|
| `sta_img` (6) | 4 | 13 | 15,321,054 / 39,744 / 9,658 / 193,698 |
| `sta_img_deep` (6+128) | 4 | 13 | 15,321,060 / 39,752 / 9,658 / 193,698 |
| `sta_img_win` (6+512) | 4 | 13 | 15,451,859 / 40,027 / 9,963 / 324,290 |
| `sta_img_hi` (6+256) | 4 | 13 | 15,321,083 / 39,757 / 9,682 / 193,722 |
| `all` (7) | 4 | 13 | 15,451,894 / 40,048 / 9,987 / 324,314 |

- 5 条件とも match 4 件。match 4 件は `0x4bf600`・`0x50ab90`・`0x7850d0`・`0xb77200`。全件の verdict は `results/ld226_sta_img_stack.tsv`。
- 前版 (誤った差分) からの変化は、`sta_img_hi` と `all` で `0x4bf600`・`0x50ab90`・`0x7850d0`・`0xb77200` の 4 件が mismatch → match になったこと。他の値は変わらない。
- `sta_img_hi` の RESET 差分 (15,321,083 B) は、`sta_img` 本体の差分 (15,321,054 B) と同じ桁。戻し区間は正しく数えられている。

## 4. 読み取り

- 前版の「`hi` を足すと match 0 件」は、誤った差分による結果だった。修正後は、どの区間を足しても match 4 件は消えない。
- 「スタック復元 (`all`) で効果が消える」(前版 LD-226 の結論) は、修正後の測定では再現しなかった (`all` = match 4)。前版の 0 件は、§0 の戻し処理の不具合に由来する。
- LD-126 §3 の stk/all の結果 (none と同じ outcome) は、この修正の対象外のため、再確認していない (§6)。
- RESET の効きの証跡は、各区間で戻したバイト数 (上表) が 0 でないことで確認した。

## 5. 再現

```sh
export ANALYSIS_DIR=<[ANALYSIS-DIR]>   # fl-win64 を $ANALYSIS_DIR/win64 に展開 (extracted/ が直下)。docs/REFERENCES.md §4
cd "$(git rev-parse --show-toplevel)/tools/liftdiff"
python3 ldlib/build_wasm.py targets/m11.json --force
mkdir -p work/ld226
printf '%s\n' sta_img sta_img_deep sta_img_win sta_img_hi all | xargs -P 3 -I{} sh -c 'python3 ld126_wasm_state.py --reset {} --out work/ld226/{}.jsonl > work/ld226/{}.log 2>&1'
python3 ld226_summarize.py > results/ld226_sta_img_stack.tsv
```

- 生データは `work/ld226/` (gitignore)。集計 TSV は `ld226_summarize.py` で作る。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `all` = `none` の一致の確認 (none の 5 条件との突き合わせは未実施) | LD-126 の stk 結論の再確認 | #3384 (LD-155) |
| 対象件数 17 と REPORT の 18 の食い違い | 対象集合の確定 | #3384 (LD-155) |
| n=2 反復 | 結論の再現性 | #3384 (LD-155) |
