# #3564: strict 候補の残り (証拠表の行 36〜66 のうち保留 6 件・単独 15 件) の件ごと判定

本付録は `REPORT_718.md` §4h の全文。結論は §4h にある。

## 1. 測定と入力

- 測定 commit: `4517825a2` (origin/main)。`git diff 03df83be4 4517825a2 -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_ctx.py` = 0 行。本 PR は `tools/m11/trap_triage/judge_src.py` (新規) と本付録・REPORT_718 §4h・DOC_MAP の行を足すだけ。
- 入力 (本 run で実測): `work-m11` の `boot_final.ll` (19,787,837 B・sha256 `69c774de…`)、`fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。`scan_guard.py --report` で fn 6969・jcc 25618・dropped 1380・strict 288 (§3 と一致)、`strict_evidence.py` で TSV 288 行。TSV と strict.json は `tools/m11/work/judge_3564/` (gitignore・未コミット)。
- 対象: 保留 6 件 (行 39・42・43・47・63・65) と単独 15 件 (行 41・51〜62・64・66)。#3499 の 10 件 (行 36〜38・40・44〜46・48〜50) は PR #3571 (未 merge) の判定で、本付録の対象外。

## 2. 判定方法

1. 機械語: jcc の直前で count (ループ回数の元) を読む命令を取る。`judge_src.py <IR> <fn> --pe <PE> --jcc <A>` は RIP 相対の参照先を IR の絶対アドレス (次命令 + disp − 0x400000) に直して出す。この変換は行 51〜55 の G = 19649808 (`0x12bd510`) が IR の `inttoptr` と一致することで確かめた。
2. IR: `judge_src.py <IR> <fn> <VA>...` で B (帰属ブロック)・L (ループ先頭)・join (ループ末尾の判定)・T (脱出先) を出す。count の源 (`inttoptr` の G と +オフセット・幅) と、入口判定の有無、末尾の判定が後判定 (do-while) かを見る。
3. 2 つの照合を独立に取る。(a) 機械語の count 源と IR の count 源が、同じ G・同じ段数・同じ幅か。(b) 機械語が jcc で T へ直行する条件 (count ≤ 0) で、IR が本体を回るか。
- 注: 受入条件の「SSA で同じ値に結ぶ」は行っていない。reg2mem の store/load を遡らず、count の源 (メモリ読み出しの G・オフセット・幅・段数) の照合で代替した。(a) は同値の必要条件に当たるが十分条件ではない。(a) の一致は「同じメモリ位置を同じ幅で読んでいる」ことまでしか示さない。
- 真陽性 (構造): (a) が一致し、IR に入口の count 判定が無く、count = 0 で IR が本体を 1 回以上回る。機械語は T へ直行する。
- 偽陽性: jcc の条件が機械語の命令列だけで成立しない。
- 保留: (a) の段数・幅・戻り値が一致しない、または偽側の行き先が T と別経路で同値とは言えない。

## 3. 行ごとの判定

| 行 | 関数 | jcc → T | 判定 | 根拠 |
|---|---|---|---|---|
| 39 | function_1274260 | 12742fa → 127433e | 保留 | IR の L `1274303` に入口判定 `icmp ult index, count` があり、機械語の guard と同値。しかし偽側は `1274316` (`function_47a250` 呼出し) で、機械語は count ≤ 0 で T へ直行する。47a250 の戻り値 (`%42` 相当) の性質が未確認 |
| 41 | function_127bc80 | 127be05 → 127beaf | 保留 | 機械語の count は `mov rcx,[G]; mov rcx,[rcx]; mov edi,[rcx+0x10]` (G = 18752024、3 段)。IR は `load i32 @18752024` → `sext` → `+16` (2 段)。同一値を確定できない。#3499 の「単独」真陽性は段数の照合を経ていない |
| 42 | function_127cea0 | 127cf07 → 127cf60 | 保留 | 機械語の count は `esi = arg − i32[*G]` (G = 18751896) で、arg と `*G` の 2 段。IR の L の回数 (B の `%19` の結果) と同一性を未照合 |
| 43 | function_1280530 | 1285e80 → 1285ebc | 偽陽性 | 機械語 `1285e3c: mov ebx, 0x1f4` の後、1285e80 まで ebx への書込みが無い (呼出し先は rbx を保存)。`cmp ecx(0), edi(500)` で `0 > 500` は不成立で、jcc は機械語の命令列だけで決まる。IR の定数 501 は機械語の `ebx+1` (`sub edi,eax; add edi,1`) と一致 |
| 47 | function_12a75e0 | 12a760d → 12a7685 | 保留 | 機械語の count は `mov rcx,[G]; mov rcx,[rcx]; mov r14d,[rcx+0x10]` (G = 18752024、3 段)。IR は `load i32 @G` を sext して +16 (2 段)。41 と同じ形。IR の `%0` (i32 の G) は B の基底と L の fe8bb0 引数に使われる |
| 51 | function_12b52e0 | 12b52fa → 12b5329 | 真陽性 | (a) 機械語 `mov rcx,[G=19649808]; mov esi,[rcx+0x10]`、IR `load i64 @19649808; +16; load i32` (一致)。(b) L `12b5301` に入口判定無し。末尾 `(rsi−1 mod 2^32) ≠ 0` で継続 (後判定)。count = 0 で IR は本体を 1 回回り、継続判定は −1 ≠ 0 で真 |
| 52 | function_12b5390 | 12b53aa → 12b53d9 | 真陽性 | 51 と同型。G = 19649808 一致、後判定 `12b53b1` |
| 53 | function_12b53f0 | 12b540a → 12b5439 | 真陽性 | 51 と同型。G = 19649808 一致、後判定 `12b5411` |
| 54 | function_12b5450 | 12b5479 → 12b54bc | 真陽性 | (a) 機械語 `mov rcx,[G=19649808]; mov r14d,[rcx+0x10]`、IR `load i64 @19649808; +16`。(b) join `12b54af` で `r14−1 ≠ 0` の後判定 (`%24`)。count = 0 で L `12b5482` が 1 回走る |
| 55 | function_12b54d0 | 12b54ec → 12b5536 | 真陽性 | (a) G = 19649808 一致 (`mov edi,[rcx+0x10]`)。(b) `12b552c` で `rdi−1 ≠ 0` の後判定 (`%25`)。count = 0 で本体が回る |
| 56 | function_12ca540 | 12ca5cd → 12ca629 | 真陽性 | (a) 機械語 `mov rcx,[G=22281224]; mov r13d,[rcx+0x14]`、IR `load i64 @22281224; +20; load i32` (一致)。(b) join `12ca61d` で `r13−1 ≠ 0` の後判定 (`%44`) |
| 57 | function_12ca640 | 12ca666 → 12ca73e | 保留 | 機械語は `mov rcx,[G=22281208]` (qword) の後 `[rcx+0x14]`。IR は `load i32 @22281208` を `sext` して `+20`。幅が一致しない (IR の 32bit 読みは、上位 32bit が 0 という仮定が要る)。L は入口判定を持たず、末尾の判定も未確認 |
| 58 | function_12ca770 | 12ca79a → 12caaaf | 真陽性 | (a) G = 22281224 (qword、+0x14 i32) 一致。(b) join `12caa99` で `r13−1 ≠ 0` の後判定 (`%148`) |
| 59 | function_12cab20 | 12cad0f → 12cad72 | 保留 | 57 と同じ G = 22281208。機械語は qword、IR は i32 の読み。幅の不一致 |
| 60 | function_12cab20 | 12cad89 → 12cae48 | 真陽性 | (a) 機械語 `mov rcx,[G=22281256]; mov ebx,[rcx+0x10]`、IR `load i64 @22281256; +16; load i32` (一致)。(b) join `12cae11` で `rbx−1 ≠ 0` の後判定 (`%144`)。count = 0 で L `12cad94` が回る |
| 61 | function_12cab20 | 12cadcb → 12cae11 | 保留 | 57・59 と同じ G = 22281208 の幅不一致 |
| 62 | function_12cab20 | 12caeec → 12cafaf | 真陽性 | (a) 機械語 `mov rcx,[G=22281224]; mov edi,[rcx+0x14]`、IR `load i64 @22281224; +20 (%167); load i32` (一致)。(b) join `12caf9b` で `rdi−1 ≠ 0` の後判定 (`%228`) |
| 63 | function_12cab20 | 12caf23 → 12caf7d | 真陽性 | (a) 機械語 `call 0x663d80` の戻り値を `mov rbx,rax` で持ち、`mov ecx,[rbx+0x10]` (count)。IR は同じ call `%164` に `+16` (`%170`→`%171`) して i32 を読む (一致)。(b) join `12caf6d` で `rcx−1 ≠ 0` の後判定 (`%209`)。count = 0 で L `12caf2a` が 1 回走る |
| 64 | function_12cb680 | 12cb76b → 12cb796 | 真陽性 | (a) count は `call 0x12f9ed0` の戻り値の低 32bit (機械語 `mov ebx,eax`)。IR は同じ call `%47` の戻り値を `+2^32` して保持し、L で `and 0xffffffff`。(b) L 末尾 `(rbx−1) mod 2^32 ≠ 0` で継続 (後判定 `%57`)。count = 0 で IR は本体を回る |
| 65 | function_12cb680 | 12cb803 → 12cb8a9 | 保留 | 機械語は `mov rcx,[G=18742616]; mov esi,[rcx]` (G の内容をポインタとして 1 段読む)。IR は `load i32 @18742616` (G を直接読む)。段数が一致しない。IR 側の読み方が lift の欠陥の疑い (未確定) |
| 66 | function_12cb680 | 12cbb59 → 12cbb9f | 真陽性 | 64 と同じ call の戻り値 (`mov ebx,eax`)。(b) join `12cbb8f` で `rbx−1 ≠ 0` の後判定 (`%214`)。L `12cbb60` は入口判定 (count) を持たない |

## 4. 集計

- 母数 (本付録の対象) 21 件: 真陽性 12 (51・52・53・54・55・56・58・60・62・63・64・66)、偽陽性 1 (43)、保留 8 (39・41・42・47・57・59・61・65)。
- 保留 6 件 (39・42・43・47・63・65): 真陽性 1 (63)、偽陽性 1 (43)、保留 4 (39・42・47・65)。
- 単独 15 件 (41・51〜62・64・66): 真陽性 11、保留 4 (41・57・59・61)。単独の 11 件は #3499 の IR 構造の判定に、本付録の (a) 段数・幅の照合を 2 系統目として加えた。
- 偽陽性率は母数 288 のうち判定が終わるまで書かない。

## 5. #3499 との食い違い (PR #3571・未 merge。本 PR は変えない)

- 行 41: #3499 は単独真陽性。本付録は段数が一致しないため保留 (機械語 3 段、IR 2 段)。
- 行 40: #3499 は「直接確認・真陽性」とし、同じ注で段数 (機械語 3 段、IR 2 段) の不一致を書いている。本付録の基準では同値を確定できないため、#3571 側で再確認が要る。
- 行 46: #3499 は 3 段の一致を書いている。本付録では未確認 (機械語側の 3 段の読み出しを IR と突き合わせていない)。

## 6. 再現

```sh
python3 tools/m11/guard699/scan_guard.py <IR> --pe <PE> --report strict.json
python3 tools/m11/trap_triage/strict_evidence.py <IR> --pe <PE> --report strict.json --out strict_evidence.tsv
python3 tools/m11/trap_triage/judge_src.py <IR> function_12b5450 --pe <PE> --jcc 12b5479 --n 10
python3 tools/m11/trap_triage/judge_src.py <IR> function_12b5450 12b54af 12b5482 --mx 12
python3 tools/m11/trap_triage/judge_src.py <IR> function_1280530 --pe <PE> --jcc 1285e80 --n 6
```

- 検証範囲: 行 39〜66 の 21 件の IR ブロックと機械語の命令列。到達性 (count = 0 が実行時に起きるか) は範囲外で、真陽性は構造判定。
- `guard699/`・`ldfix/`・`m11_ov.c`・RetDec 本体は変更していない。
