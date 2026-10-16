# liftdiff REPORT 付録: LD-226 (#4590) sta_img にスタック復元を足すと効果が消える機構

親 #3384 (LD-155)。前提は `REPORT_APPENDIX_LD126.md` §3・§3.1 (sta_img で match 4 件、スタック復元 (`all`) で 0 件)。
LD-240 (#4801) で RESET の測定誤りを直した (下の §0)。

測定 commit: **`4f9e652c0`** (コードを変えた最後の commit。`rt/ld_wasm.c`・`rt/ld_runner.mjs`・`ldlib/build_wasm.py`・`ld240_hi_probe.py`)。

## 0. 前回の誤り (LD-240 で修正)

- 前版の `hi` の RESET 差分 587,202,032 B と、後の版の 575,469,632 B は、どちらも測定誤り。wasm 側の `ld_w_reset` が、戻し処理自身のフレーム (`-O0` の `i`・`k`・`diff`) を hi 区間に積んで、その値を壊していた。
- 次の版では JS 側の `resetRegions` で戻すように直したが、RESET のたびに wasm の関数 (`_ld_w_nrst`・`_ld_w_rst_*`) を呼んでいた。そのフレームが hi 区間 `[spS, stack_base)` を書き換え、hi の差分 4 件に getter 由来の byte が混ざっていた。
- 修正 (測定 commit `4f9e652c0`): RESET 中は wasm の関数を一切呼ばない。区間表 (`ld_rst`) の番地と SNAPSHOT 時の値 (`ld_info`: `spS`・stack_base・stack_end・件数) を、init 時に 1 度だけ取って JS から直接読む。SNAPSHOT 関数の内側で記録した `spS` を hi 区間の下端に使う。
- 前版の「hi 0 B」「SP = stack_base」「hi の差分 4 件」は、どれも SNAPSHOT 時の値ではなかった。以下の値に置き換える。

## 1. 測定条件

- 素材: `[WIN64]` (`extracted/block00031_PE.bin`)・`work-liftdiff` (`tools/liftdiff/work/`)・`work-m11` (`tools/m11/work/`)・`[EMSDK]`。
- wasm: `python3 ldlib/build_wasm.py targets/m11.json --force` → `OK` (`wasm_size` 4464335・`sig_mismatch` 0・`undefined` 0)。
- 機: 4 vCPU・RAM 15 GiB。5 条件を `xargs -P 3` で流した。wall 432 s (7 分 12 秒)。load 0.30 (開始時) 〜 1.94 (終了時)。
- 対象: shard 1 の chunk 1 の対象件数は **17** (REPORT の 18 件と 1 件違う。§6)。

## 2. SNAPSHOT 時の実測 (probe)

`ld240_hi_probe.py` (repo 内・`work/ld240/probe.json` に出力)。HEAD `4f9e652c0`、wasm は §1 のビルド。

| 項目 | 値 |
|---|---|
| SP (SNAPSHOT 関数内 `spS`・`snap_sp`) | `0x22ccf730` |
| SNAPSHOT が戻った後の SP (RESET で戻す値) | `0x22ccf750` (= stack_base) |
| stack_base | `0x22ccf750` |
| stack_end | `0x224cf750` |
| スタック全体 `[stack_end, stack_base)` | 8,388,608 B (8 MiB) |
| hi 区間 `[snap_sp, stack_base)` | **32 B** |
| deep 区間 `[stack_end, snap_sp)` | 8,388,576 B |

- hi 区間は 32 B で、受入条件の「hi 区間が 8 MiB 以内」を満たす。
- probe の RESET 差分 (各 mask を別プロセスで、SNAPSHOT 直後に 1 回 RESET): `reset 1` (stk) = 1・`reset 256` (hi) = 0・`reset 512` (win) = 1・`reset 128` (deep) = 0・`reset 7` (all) = 1。連続 RESET (`6,6,2,2,4,4`) の差分は全て 0 (冪等)。
- 実行コマンド: `cd tools/liftdiff && FL_WIN64_DIR=<[WIN64]> python3 ld240_hi_probe.py > work/ld240/probe.json` (33 s)。

## 3. 結果 (コミット済み HEAD・n=1・対象 17 件)

| 条件 | match | mismatch | RESET 差分の先頭 4 件 (B) |
|---|---|---|---|
| `sta_img` (6) | 4 | 13 | 15,321,056 / 14,699,489 / 9,658 / 193,698 |
| `sta_img_deep` (6+128) | 4 | 13 | 15,321,062 / 14,699,497 / 9,658 / 193,698 |
| `sta_img_win` (6+512) | 4 | 13 | 15,451,859 / 14,699,774 / 9,964 / 324,291 |
| `sta_img_hi` (6+256) | 4 | 13 | 15,321,085 / 14,699,501 / 9,682 / 193,722 |
| `all` (7) | 4 | 13 | 15,451,894 / 14,699,794 / 9,988 / 324,315 |

- 5 条件とも match 4 件は `0x4bf600`・`0x50ab90`・`0x7850d0`・`0xb77200`。全件の verdict は `results/ld226_sta_img_stack.tsv`。
- RESET 差分の列は、対象 17 件の各 RESET で戻した byte 数 (`*.reset.json` の先頭 4 件)。RESET は対象 case の直前に送るため、各値は「その時点までに case が書き換えた量」で、snapshot からの累積ではない。
- 差分は wasm の関数を呼ばずに数えた値なので、getter 由来の byte は混ざらない (§2 の hi 区間 32 B)。
- 前版 (修正前の JS 版 `253902726`) からの verdict の変化は無い。`sta_img_hi` と `all` の match は 4 件のまま。
- 戻しの冪等性: 同じ wasm で `RESET 6,6,2,2,4,4` を連続で送ると、いずれも diff 0 (§2)。

## 4. 読み取り

- どの区間 (deep・win・hi) を sta_img に足しても、match 4 件は消えない。
- 「スタック復元 (`all`) で効果が消える」(前版 LD-226 の結論) は、この測定では再現しなかった (`all` = match 4)。前版の 0 件は、§0 の戻し処理の不具合に由来する。
- hi 区間は 32 B で実質空。スタックの区間は、この 17 件では効果を持たない。
- LD-126 §3 の stk/all の結果は、不具合版の reset で測られたもの。再測定まで結論は保留 (`REPORT_APPENDIX_LD126.md` 注記・#3384)。

## 5. 再現

```sh
export FL_WIN64_DIR=<[WIN64]>   # fl-win64 を展開したディレクトリ (extracted/ が直下)。docs/REFERENCES.md §4
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
