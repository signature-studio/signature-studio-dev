# liftdiff REPORT 付録: LD-226 (#4590) sta_img にスタック復元を足すと効果が消える機構

親 #3384 (LD-155)。前提は `REPORT_APPENDIX_LD126.md` §3・§3.1 (sta_img で match 4 件、スタック復元 (`all`) で 0 件)。
LD-240 (#4801) で hi 区間の測定誤りを直した (下の §0)。

測定 commit: **`253902726`** (コードを変えた最後の commit。`rt/ld_runner.mjs`・`rt/ld_native.c`・`ld240_hi_probe.py`)。

## 0. 前回の誤り (LD-240 で修正)

- 前版の `hi` の RESET 差分 587,202,032 B は、`ld_w_reset` が wasm 内で戻す処理のせいで出た誤りだった。
- `hi` 区間 `[SP, stack_base)` は、戻す処理自身のフレーム (`-O0` の `i`・`k`・`diff`) と重なる。`memcpy` でこの区間を戻すと、戻し中のループ変数が上書きされ、戻り値が壊れる。
- 戻り値の 575,469,632 は、その壊れた値の一つで、差分量ではない。実測の `stack_end` (`0x224cf840` = 575,469,632) と一致した (§2)。
- 修正: 戻しと差分の数えを JS 側 (`ld_runner.mjs` の `resetRegions`) に移した。wasm 側は区間情報を読むゲッターだけにする。区間情報は戻しの前に全部読み切る (getter の呼出しは wasm スタックを使うため)。
- 前版 `hi` の「match 0/17」は誤った差分による結果なので、根拠にしない。

## 1. 測定条件

- 素材: `[WIN64]` (`extracted/block00031_PE.bin`)・`[WORK-LIFTDIFF]`・`[WORK-M11]`・`[EMSDK]`。
- wasm: `python3 ldlib/build_wasm.py targets/m11.json --force` → `OK` (`wasm_size` 4464521・`sig_mismatch` 0・`undefined` 0)。
- 機: 4 vCPU・RAM 15 GiB。5 条件を `xargs -P 3` で流した。wall 7 分 15 秒 (435 s)。load 0.44 (開始時) 〜 1.97 (終了時)。
- 対象: shard 1 の chunk 1 の対象件数は **17** (REPORT の 18 件と 1 件違う。§6)。

## 2. SNAPSHOT 直後の実測 (probe)

`ld240_hi_probe.py` (repo 内・`work/ld240/probe.json` に出力) の出力 (HEAD `253902726`、wasm は §1 のビルド):

| 項目 | 値 |
|---|---|
| SP (`emscripten_stack_get_current`) | `0x22ccf840` |
| stack_base | `0x22ccf840` |
| stack_end | `0x224cf840` (= 575,469,632) |
| スタック全体 `[stack_end, stack_base)` | 8,388,608 B (8 MiB) |
| hi 区間 `[SP, stack_base)` | **0 B** |
| deep 区間 `[stack_end, SP)` | 8,388,608 B |

- SP = stack_base なので、hi 区間は 0 B。受入条件の「hi 区間が 8 MiB 以内」は満たす (0 B)。
- probe の RESET 差分 (各 mask を別プロセスで、SNAPSHOT 直後に 1 回 RESET): `reset 1` (stk) = 5・`reset 256` (hi) = 4・`reset 512` (win) = 1・`reset 128` (deep) = 0・`reset 7` (all) = 5。連続 RESET (`6,6,2,2,4,4`) の差分は全て 0 (冪等)。
- 実行コマンド: `cd tools/liftdiff && ANALYSIS_DIR=<[ANALYSIS-DIR]> python3 ld240_hi_probe.py > work/ld240/probe.json` (27 s)。
- 修正前の値 (`reset 256 diff 575469632`) は、戻し処理の frame の書き換えで壊れた値。この PR の修正後は 4 になった。

## 3. 結果 (コミット済み HEAD・n=1・対象 17 件)

| 条件 | match | mismatch | RESET 差分の先頭 4 件 (B) |
|---|---|---|---|
| `sta_img` (6) | 4 | 13 | 15,321,054 / 14,699,527 / 9,658 / 193,698 |
| `sta_img_deep` (6+128) | 4 | 13 | 15,321,060 / 14,699,535 / 9,658 / 193,698 |
| `sta_img_win` (6+512) | 4 | 13 | 15,451,859 / 14,699,810 / 9,963 / 324,290 |
| `sta_img_hi` (6+256) | 4 | 13 | 15,321,083 / 14,699,540 / 9,682 / 193,722 |
| `all` (7) | 4 | 13 | 15,451,894 / 14,699,831 / 9,987 / 324,314 |

(上表は本測定 (`253902726`)。`0a7e580f8` 時の 2 件目以降は `sta_img_hi` で 39,757 B だった。)

- 5 条件とも match 4 件は `0x4bf600`・`0x50ab90`・`0x7850d0`・`0xb77200`。全件の verdict は `results/ld226_sta_img_stack.tsv`。
- RESET 差分の列は、対象 17 件の各 RESET で戻した byte 数 (`*.reset.json` の先頭 4 件)。RESET は対象 case の直前に送るため、各値は「その時点までに case が書き換えた量」で、snapshot からの累積ではない。同じ HEAD (`253902726`) を 2 回流した (`0a7e580f8` 時の 1 回目と本測定) ところ、verdict 19 件は一致し、`sta_img_hi` の 1 件目の差分も 15,321,083 B で一致した。2 件目以降の差分は測定ごとに変わった (`0a7e580f8` 時は `sta_img_hi` の 2 件目が 39,757 B、本測定は 14,699,540 B)。原因は未特定で、この列は n=2 でしか確認していない (未解決 → #3384)。
- 前版 (誤った差分) からの変化は、`sta_img_hi` と `all` で `0x4bf600`・`0x50ab90`・`0x7850d0`・`0xb77200` の 4 件が mismatch → match になったこと。他の値は変わらない。
- 同じ wasm で `RESET 6`・`RESET 2`・`RESET 4` を連続で送った直接確認では、いずれも `diff 0` (戻し後の 2 回目は差分なし)。戻しは冪等。

## 4. 読み取り

- 前版の「`hi` を足すと match 0 件」は、誤った差分による結果だった。修正後は、どの区間を足しても match 4 件は消えない。
- 「スタック復元 (`all`) で効果が消える」(前版 LD-226 の結論) は、修正後の測定では再現しなかった (`all` = match 4)。前版の 0 件は、§0 の戻し処理の不具合に由来する。
- SP = stack_base (§2) なので、hi 区間は実行時点で実質空。hi 区間の差分 (`sta_img_hi` の 1 件目 15,321,083 B) は、sta_img と同じ桁で、stack の区間は効果を持たない。
- LD-126 §3 の stk/all の結果は、不具合版の reset で測られたもの。再測定まで結論は保留 (`REPORT_APPENDIX_LD126.md` 注記・#3384)。

## 5. 再現

```sh
export ANALYSIS_DIR=<[ANALYSIS-DIR]>   # fl-win64 を $ANALYSIS_DIR/win64 に展開 (extracted/ が直下)。docs/REFERENCES.md §4
cd "$(git rev-parse --show-toplevel)/tools/liftdiff"
python3 ldlib/build_wasm.py targets/m11.json --force
python3 ld240_hi_probe.py > work/ld240/probe.json
mkdir -p work/ld226
printf '%s\n' sta_img sta_img_deep sta_img_win sta_img_hi all | xargs -P 3 -I{} sh -c 'python3 ld126_wasm_state.py --reset {} --out work/ld226/{}.jsonl > work/ld226/{}.log 2>&1'
python3 ld226_summarize.py > results/ld226_sta_img_stack.tsv
```

- 生データは `work/ld226/` と `work/ld240/` (gitignore)。集計 TSV は `ld226_summarize.py` で作る。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `all` = `none` の一致の確認 (none の 5 条件との突き合わせは未実施) | LD-126 の stk 結論の再確認 (LD-126 §3 は不具合版の reset。LD-240 #4801 で保留) | #3384 (LD-155) |
| 対象件数 17 と REPORT の 18 の食い違い | 対象集合の確定 | #3384 (LD-155) |
| n=2 反復 | 結論の再現性 | #3384 (LD-155) |
