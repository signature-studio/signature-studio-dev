# REPORT_APPENDIX_5437 — rewrite 行 2 件の窓確認 (#5437 / CI-220)

親: #4973 (CI-202, PR なしで終了・分割元)。本付録は `REPORT_3382.md` §9・§13 の rewrite 行のうち、窓で未確認だった 2 件の確認記録。`REPORT_3382.md` は 250 行で上限のため分割移動した。

## 1. 測定

- 測定 commit: `219677f85` (判定器の修正。`judge_copy_3382.py` のみ)。`219677f85` は main (`7306126a0`) の祖先で、`git diff 219677f85 HEAD -- tools/m11/ldfix` は 0 行。
- 素材: `fl-win64` の `extracted/block00031_PE.bin` (`$RUNNER_TEMP/fl-win64` 展開先。`REPORT_3382.md` §1 と同じ指紋)、IR は `tools/m11/work/boot_final3.ll` (`work-m11` 展開済み・gitignore)。
- scan: `scan_spill_deref_3328.py` → `COPY 49 関数 103 箇所` (3.95 s)。
- judge: `judge_copy_3382.py` → `ERR_BARE 15 / UNCLEAR 14 / REWRITE_NOARG 4 / ERR_CAND 47 / MISMATCH 13 / OK_ARGK 10` (`REPORT_3382.md` §13 の修正後の値と一致)。
- issue #5437 本文の検証値 `ERR_BARE 14 / ERR_CAND 57 / UNCLEAR 16 / MISMATCH 14 / OK_ARGK 2` は `REPORT_3382.md` §1 (§9 の補正前) の値で、現行コードの出力とは一致しない。現行の値は上記。

## 2. 窓の確認 (`show_site_2555.py`)

| 関数 | deref → call | 機械語 (窓) | IR (窓) | 判定 |
|---|---|---|---|---|
| 0x43adf0 | 0x43ae29 → 0x43ae32 (`4399e0`・argpos 2) | entry `mov rsi,r8` (rsi = arg3)。0x43ae29 `mov rcx,[rsi]` → 0x43ae2c `mov rdx,rcx` → 0x43ae2f `mov rcx,rax` → call。第 2 引数 (argpos 2) は `*arg3` | `%16 = call @function_4399e0(%13, %15)`。`%15 = load(%14)`・`%14 = inttoptr %rsi.0.reload`・`%rsi.0.reload` は `%rsi.0.reg2mem` 経由で `%arg3` を store/load | **一致** (窓で確認。機械語の `*arg3` と IR の `arg3` 由来 load が同じ argpos 2) |
| 0x439f90 | 0x43a0e7 → 0x43a0fa (`409c80`・argpos 3) | 0x43a0e7 `mov r8,[rbx]` → 0x43a0ea `sub r8,rdi` → 0x43a0ed `sar r8,1` → 0x43a0f3 `adc r8,0` → 0x43a0f7 `add r8,r8` → call。argpos 3 の値は計算値 (`*argK` ではない) | 関数内に `@function_409c80` の呼出しが 0 件 (IR 対応無し) | **判定不能** (値が `*argK` でなく、IR 側にも対応 call が無い。`REWRITE_NOARG` の判定を支持) |

## 3. 検収との関係

- 受入条件 1 (0x439f90・0x43adf0 の `rewrite_va` を窓で確かめる): 両件とも窓で確認した (§2)。
- 受入条件 2 (判定件数を REPORT_3382 の追記に書く): 件数は §1 の judge 出力。窓の 2 件の結論は §2。
- 残件: `REPORT_3382.md` §10・§11 の ERR_CAND 判定不能 44 件と保留 1 件、§6 の未解決 (子 #4961・#4993) は本件の範囲外。
