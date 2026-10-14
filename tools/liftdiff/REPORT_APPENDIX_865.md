# 付録: liftdiff LD-18 (#865) — trace_head 外 27 件の到達確認・OOB 他の最上位 frame 集計

> **正本**: `tools/liftdiff/REPORT.md` (結論・§7 未解決)。本書は LD-18 (#865) の新規節。
> `REPORT_APPENDIX.md` は 250 行上限 (`docs/DOC_MAP.md` §1) のため増やさず、本書に別置きした (参照 1 文のみ `REPORT_APPENDIX.md` §9)。

### 27 件の到達確認 (LD-18 / #865、実測)

入力リストは `tests/extract_414ad0_27.py` で batch jsonl から生成する (`work/m11_414ad0_27/list.txt`、gitignore)。
`tests/rerun_414ad0_27.sh` で 27 件を `trace_head=200` (`-v`) で単体再走 → `tests/oob_414ad0_27.py` → `results/m11_oob_414ad0_27.md`。
**26 / 27 件が wasm trace に 0x414ad0 を含み、最上位 frame も全 26 件が function_414ad0** (= 到達)。
残り 1 件: 0x6525b0 は最上位 frame が function_4133f0 (414ad0 無し)。
> **#1588 訂正**: 0x66ea90 を「再走で trap せず」としたのは `oob_414ad0_27.py` が `both_fault` (native fault かつ wasm trap) を `NO_TRAP:` と表示した誤読。生成元で `both_fault` も trap として集計するよう直し、0x66ea90 は再走で wasm OOB trap (最上位 `function_414ad0`) を再現する。詳細は `tools/m11/trap_triage/REPORT_1588.md` §2・§6。

### OOB 他の最上位 frame 集計 (LD-18、`tests/oob_top_frames.py` → `results/m11_oob_top_frames.md`)

- **対象の定義 (件数 239)**: `tests/oob_top_frames.py`。batch jsonl の**全行**について、最初の `wasm_trap` case の `wasm_detail` に `memory access out of bounds` を含むもの。`va` での重複排除はしておらず、TSV の tags による絞り込みも無い。
- **件数 222 (§8 の TSV)**: `tests/triage_wasm_trap.py`。verdicts TSV の tags に wasm_trap を含む 578 関数を対象とし、`va` で dict に詰めた jsonl から、最初の wasm_trap case の `trap_kind` が oob・`wasm_status` が badjson でない関数。
- **差 17 の要因 (コード上の差分。件数の内訳は未実測)**: (a) triage は TSV の wasm_trap 集合で絞る (jsonl のみの wasm_trap 関数 71 件は対象外)、(b) triage は `wasm_status=badjson` を oob から除く、(c) jsonl に同一 `va` の行が複数あれば triage は畳む。どの要因が何件かは `work/` が無く未確認。

上位 5 種は function_414ad0 68・__asm_rep_movsq_memcpy 13・function_412e40 12・function_4133f0 11・function_1062930 11。
IR 分類は候補のみ (`inttoptr %arg` 経由の deref の有無)。機械語との突合・単体再走はしていないため**原因は未確定**。
