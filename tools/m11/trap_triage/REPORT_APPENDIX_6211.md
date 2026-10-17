# #6211: 証拠表の行 224・225 (母数 2) の件ごとの判定 (真陽性 0・偽陽性 0・保留 2)

本付録が #6211 の判定の正本。結論は `REPORT_718.md` §4n の要約行に載せる。判定の基準は `REPORT_APPENDIX_5751.md` §2 と同じ (構造判定・到達性は範囲外)。

## 1. 結果

- 母数 2 (証拠表 `strict_evidence.tsv` のデータ行 224・225。ヘッダを除く 1 始まり)。
- 真陽性 0、偽陽性 0、保留 2 (224・225)。
- 保留の理由: 機械語と IR で count 源の参照段数が一致しない (§3・§4)。構造判定の前提 (同じ G・同じ段数) を満たさないため、確定できない。
- 偽陽性率は母数 288 の判定が終わるまで書かない。

## 2. 入力と再現

- 素材: `oc_artifacts: fl-win64 work-m11 work-liftdiff`。`work-m11` → `tools/m11/work/`、`fl-win64` → `tools/m11/work/fl/extracted/` (`block00031_PE.bin` のみ展開)。
- 入力 IR: `tools/m11/work/boot_final.ll` (19,787,837 B・sha256 `69c774de…`。REPORT_718 §4a・§4f と一致)。
- 入力 PE: `block00031_PE.bin` (22,227,016 B)。
- 再現 (foreground):
  - `scan_guard.py <IR> --pe <PE> --report work/strict.json`: 4.0 s で strict 288。
  - `strict_evidence.py <IR> --pe <PE> --report work/strict.json --out work/strict_evidence_6211.tsv`: 12.0 s で TSV 288 行 (ヘッダ除く)。
  - `judge_ctx.py <IR> work/strict_evidence_6211.tsv <PE> 224 225`: rc 0 (122 行)。
  - 機械語の全体: `LD_M11_PE=<PE> disasm_fn.py dce130` で関数 `function_dce130` を逆アセンブル。
- 測定 commit: `b912d309f` (origin/main 取り込み前の HEAD)。判定に使ったコード (`tools/m11/guard699/`・`tools/m11/ldfix/ldmach.py`・`tools/m11/trap_triage/strict_evidence.py`・`judge_ctx.py`) は `git diff b912d309f origin/main -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_ctx.py` = 0 行。
- 作業ファイルは `tools/m11/work/` (gitignore・未コミット)。

## 3. 件ごとの判定

判定基準は `REPORT_APPENDIX_5751.md` §2 と同じ。真陽性 (構造) の条件は次の 3 つ。(a) 機械語の jcc の count 源と IR の loop 先頭の counter が、同じ G (同じ参照段数・幅) から来る。(b) IR の loop 先頭に入口判定が無い。(c) IR の末尾が後判定 (do-while)。

| 行 | 関数 | jcc → 脱出先 / L | 判定 | 理由 |
|---|---|---|---|---|
| 224 | function_dce130 | dce20a → dce27d / dce213 | 保留 | 機械語: `dce1f3` `mov rcx,[rip+0x81401e]` (.data 0x15E2218 = 一つ目の参照 P) → `dce1fa` `mov rcx,[rcx]` (P の指す先 Q) → `dce1fd` `mov r14d,[rcx+0x10]`。count = r14d + 1 は **2 段の参照 (`[[slot]]+0x10`)**。IR B=dce1ea: `%49` = `load i32 [0x11E2218]` (スロットを 1 段だけ読む) → `%51` = `%50`+16 → `%53` = `load i32 [%51]` (`r14.0` へ)。IR は `[slot]+16` で、機械語の `[[slot]]+16` と段数が違う。(b)・(c) は満たす (L=dce213 に入口判定無し・末尾 `%72` = r14.0 − 1 の後判定) |
| 225 | function_dce130 | dce2e4 → dce32d / dce2ed | 保留 | 機械語: `dce2bc`〜`dce2c6` `mov rax,[rip+0x813f55]` → `mov rax,[rax]` → `mov eax,[rax+0x10]` (eax = count 源)。`[[slot]]+0x10` の 2 段。IR B=dce2bc: `%90` = `load i32 [0x11E2218]` → `%93` = `inttoptr(sext(%90)+16)` → `%94` = `load i32 [%93]`。224 と同じく段数が 1 段少ない (`[slot]+16`)。ecx = 0 (`dce2d6` `xor ecx,ecx`) は機械語で確認。(b)・(c) は満たす |

## 4. 保留の根拠 (段数の差)

- 両件の count 源は、機械語・IR とも `.data` の同じスロット `0x15E2218` (IR 表記は `0x11E2218`、ImageBase `0x400000` の差) を指す。PE の `.data` の値は `c8af6b0100000000` (qword)。
- 機械語は、このスロットの qword (P) をさらに 1 段読み (`[P]`)、その先の `+0x10` を読む。IR は、スロットを `load i32` で 1 段だけ読み、その下位 32 bit を基底にして `+16` を読む。IR の値 = `[low32(P)+16]`、機械語の値 = `[[P]+0x10]` で、同じ値として結べない。
- この段数の差が lift 段の欠陥 (中間の `mov rcx,[rcx]` が IR で落ちた) か、IR の読み方の誤りか、機械語の別の意味かは未確定。判断は PM (`REPORT_718` §4n の 228・229 と同じ扱い)。
- 「count = 0 で IR が本体を回り、機械語は脱出先へ直行する」は、count 源が同じ値であることを前提にする。段数が違うなら IR の count はこの式で決まらないため、真陽性 (構造) とは書けない。偽陽性とも書けない (機械語の jcc が機械語だけでは決まらない)。

## 5. 範囲

- 判定の入力は work-m11 の IR に限る。現 main の `m11_e2e.sh --full` 出力では未確認。
- 段数の差の原因の切り分けは範囲外 (lift 段の欠陥か IR の読み方か)。
- `m11_ov.c`・`docs/DEFECTS.md`・`guard699/`・`ldmach.py` は変更していない。
