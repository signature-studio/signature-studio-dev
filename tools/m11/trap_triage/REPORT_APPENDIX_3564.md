# #3564: strict 候補の残り (証拠表の行 36〜66 のうち保留 6 件・単独 15 件) の件ごと判定

本付録は `REPORT_718.md` §4i の全文。結論は §4i にある。

## 1. 測定と入力

- 測定 commit: `6d12e53f1` (`judge_src.py` を追加した commit。判定に使ったコードの正本)。`git diff 6d12e53f1 HEAD -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_ctx.py` = 0 行。`judge_src.py` は `6d12e53f1` で追加されたもので、以後の差分は docstring の 1 行 (REPORT_718 §4h → §4i) だけ。`4517825a2` 以前の判定コードも同一 (`git diff 03df83be4 4517825a2 -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_ctx.py` = 0 行)。本 PR は `tools/m11/trap_triage/judge_src.py` (新規)・`negctl_3564.py` (新規) と本付録・REPORT_718 §4i・DOC_MAP の行を足すだけ。
- 入力 (`435960297` での実測。本 run は `boot_final.ll` が `$ARTIFACTS_DIR` に無く IR 側を再実行していない): `work-m11` の `boot_final.ll` (19,787,837 B・sha256 `69c774de…`)、`fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。`scan_guard.py --report` で fn 6969・jcc 25618・dropped 1380・strict 288 (§3 と一致)、`strict_evidence.py` で TSV 288 行。TSV と strict.json は `tools/m11/work/judge_3564/` (gitignore・未コミット)。
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
- 行 37: #3499 は真陽性 (注 1 は N=0x40 で『実害未確認』)。本付録 §8.1 で、jcc は機械語の命令列だけで不成立 (偽陽性) と確認した。#3571 側の判定を直す必要がある。
- 行 40: 行 41 と同じ K (0x11e2218) の 3 段。#3499 の『段数 2 vs 3 の不一致を注に書き、真陽性とする』は、本付録 §8.2 の機構 (M1) で保留とするべき。#3571 側で再確認が要る。

## 6. 再現

```sh
python3 tools/m11/guard699/scan_guard.py <IR> --pe <PE> --report strict.json
python3 tools/m11/trap_triage/strict_evidence.py <IR> --pe <PE> --report strict.json --out strict_evidence.tsv
python3 tools/m11/trap_triage/judge_src.py <IR> function_12b5450 --pe <PE> --jcc 12b5479 --n 10
python3 tools/m11/trap_triage/judge_src.py <IR> function_12b5450 12b54af 12b5482 --mx 12
python3 tools/m11/trap_triage/judge_src.py <IR> function_1280530 --pe <PE> --jcc 1285e80 --n 6
python3 tools/m11/trap_triage/negctl_3564.py <PE>
```

- 検証範囲: 行 39〜66 の 21 件の IR ブロックと機械語の命令列。到達性 (count = 0 が実行時に起きるか) は範囲外で、真陽性は構造判定。
- 判定は work-m11 の IR に限る (現 main の `m11_e2e.sh --full` 出力では未確認。`docs/WORKFLOW.md` §11 は work-m11 を survey の基準に使わないとする)。
- `guard699/`・`ldfix/`・`m11_ov.c`・RetDec 本体は変更していない。

## 7. ネガティブコントロール (機械語側・本 run で実測)

- 測定: `negctl_3564.py` を commit `dd5faa039` で実行 (`fl-win64` の `block00031_PE.bin`・22,227,016 B)。機械語は PE から直接逆アセンブルして count 源 (G・オフセット・幅・段数) を抽出し、§3 の記録値 (IR 側) と照合する。
- IR 側は `boot_final.ll` が無いため再取得していない。照合の相手は §3 の記録値 (`435960297` の判定の転記)。本節が示すのは「照合器が 1 項目のずれで不一致を出すこと」で、IR 側の正しさは示さない。
- 抽出・照合 (出力の要約。全文は `python3 negctl_3564.py <PE>` の標準出力):

| 行 | 抽出 (機械語) | 記録 (IR 側) | 照合 | 1 項目ずつ壊した結果 (G/callee+8・オフセット 0x10⇄0x14・幅 32→16・段数+1) |
|---|---|---|---|---|
| 51 | G `0x12bd510`・+0x10・32・段数 2 | 同じ | 一致 | 4 件すべて不一致 (val・off・width・stages) |
| 56 | G `0x153fc08`・+0x14・32・段数 2 | 同じ | 一致 | 4 件すべて不一致 (val・off・width・stages) |
| 64 | call `0x12f9ed0`・オフセット無し・32・段数 1 | 同じ | 一致 | 3 件不一致 (val・width・stages)。オフセットは対象外 |
| 41 | G `0x11e2218`・+0x10・32・**段数 3** | 段数 2 | **不一致 (stages)** | 実際の段数の不一致。§3 の保留理由 (段数) と一致 |

- 結果: 壊した 11 件 (対象外 1 件を除く) はすべて不一致 (FAIL)。件 41 は壊さなくても段数の不一致が出る (§3 の保留理由と同じ)。
- 件 64 の経路: `12cb758: call 0x12f9ed0` → `12cb75f: mov ebx, eax` (count) → `12cb766: cmp eax, ebx` → `12cb76b: jg`。抽出は `mov ebx, eax` の元である `call` を取る。抽出規則は `negctl_3564.py` の `count_src` が正本。

## 8. 本 run の追加判定 (run 2): 行 37 の実害と保留 8 件の機構

- 測定 commit: `28b96a18c` (`frame_ops_3564.py` の追加 commit)。以後、判定に使ったコード (`tools/m11/guard699/`・`tools/m11/ldfix/ldmach.py`・`tools/m11/trap_triage/strict_evidence.py`・`judge_src.py`・`judge_ctx.py`) は変更していない (main (`abf0981f7`) の取り込み `2f8c8dccf` 後も、同じパスの `git diff 28b96a18c HEAD` は 0 行)。
- 入力: `work/boot_final.ll` (main の checkout 側 `tools/m11/work/`・gitignore・sha256 `69c774de…`・19,787,837 B)、`block00031_PE.bin` (`fl-win64` の `extracted/`・22,227,016 B。`tar --zstd -xf fl-win64.tar.zst extracted/block00031_PE.bin` で取得)。`scan_guard.py --report` で fn 6969・jcc 25618・dropped 1380・strict 288、`strict_evidence.py` で TSV 288 行 (§3 と一致)。

### 8.1 行 37 (`function_125da90`・jcc `125e022` → `125e06d`): 偽陽性・実害なし

- 機械語: `125e00d: mov esi,[rbp+0xac]` → `125e013: sub esi,1` → `125e016: mov [rbp+0xb8],eax` (eax = 0) → `125e01c: cmp [rbp+0xb8],esi` → `125e022: jg 125e06d`。jcc は `0 > [rbp+0xac] − 1` のとき成立する。
- `[rbp+0xac]` への書込み: `125df0d: mov dword [rbp+0xac], 0x40` の 1 箇所だけ (`frame_ops_3564.py <IR> function_125da90 <PE> "rbp \+ 0xac\]"` の出力)。残りは読出し (`div` 125df3a・`mov` 125df53・125e00d・125e06e・125e07a)。
- 別名の確認: 関数内の `lea` (rbp 相対) は 37 個。書込み後の 125df0d〜125e022 に、0xac を指す番地は無い。`lea` の番地は `rbp+0xc0` 以上 (`[rbp+0xc0]`・`[rax+rbp+0xc0]` 等)。IR の frame base (`%stack_var_-16920` = rbp+0) の派生は `%152 = %53 + 192` (= rbp+0xc0) だけ。負の添字による別名は未確認。
- ネガティブコントロール (fix run で実測): `frame_ops_3564.py` の `rbp \+ 0xa4\]` は既知の書込み `125df07` を含む 7 件を出し、照合器は書込みを拾う。`rbp \+ 0xa[0-9a-f]\]` (rbp+0xa0〜0xaf の全アクセス) は 17 件で、すべて dword (0xa4・0xa8・0xac)。0xac にかかるのは `[rbp+0xac]` の dword 6 件だけで、0xa4・0xa8 の dword (4 byte) は 0xac に届かない。別幅のアクセスは無い。
- 結論: `[rbp+0xac]` = 0x40 は定数で、esi = 63。`0 > 63` は偽で jcc は**機械語の命令列だけで不成立**。IR の L (`125e034`) は入口判定を持たず、`exitcond` (`count == 64`) で 64 回回る。機械語も 0〜63 の 64 回で一致する。
- 判定: **偽陽性** (jcc 不成立)。実害なし (IR の本体の回数は機械語と一致)。§4j 注 1 の『N=0x40。実害未確認』は、この確認で解消した。§4j の表の『真陽性』は PR #3571 側の判定で、本付録は変えない (§5 参照)。

### 8.2 保留 8 件の機構 (機械語と IR の count 源の比較)

機構の名前 (本節だけの用語):
- **M1 (段数)**: 機械語は K (= 機械語の `rip` 相対の番地 − 0x400000) を qword で読み、その先を 1 段以上 deref する。IR は K を 1 回だけ読む (または 1 段少ない)。`ldfix/REPORT_2794.md` の類型 (2 段 deref が 1 段に潰れる) と同型かは未確認 (下の注 2)。
- **M2 (幅)**: 機械語は K を qword (ポインタ) で読む。IR は同じ K を `i32` で読み、その下位 32 bit を番地に使う。
- **M3 (入口判定の幅)**: 行 39 の L の入口判定だけが、機械語と幅が違う (下表)。

| 行 | 関数 | 機械語の count 源 (実測) | IR の count 源 | 機構 | 判定 |
|---|---|---|---|---|---|
| 39 | function_1274260 | `mov rcx,[rbx+0x9c]; mov r14d,[rcx+0x10]` (qword P → dword P+16) | B: `load i64 [arg1+156]` = P → `load i32 [P+16]` (count は一致)。L の入口: `load i64 [P+16]` と `icmp ult` | M3。加えて偽側: IR `1274316` は `function_47a250` 呼出し、機械語 T `127433e` は `function_47b3e0` 呼出し (別経路) | 保留 |
| 41 | function_127bc80 | `mov rcx,[rip+X]; mov rcx,[rcx]; mov edi,[rcx+0x10]` (K → P → dword P+16、3 段) | `load i32 @K` → sext → +16 → `load i32` (2 段) | M1 + M2 (K の幅) | 保留 |
| 40 (#3499) | function_127bc80 | 41 と同じ 3 段 (`mov rcx,[rip+X]; mov rcx,[rcx]; mov edi,[rcx+0x10]`) | 同じ K (`load i32 @K`) | M1 | 保留 (#3571 の判定の再確認が要る) |
| 42 | function_127cea0 | `mov rax,[rip+X]` (qword P) → `sub esi,[rax]` (dword P) | `load i32 @K` を count に使う (1 段) | M1 | 保留 |
| 47 | function_12a75e0 | `mov rcx,[rip+X]; mov rcx,[rcx]; mov r14d,[rcx+0x10]` (3 段) | `load i32 @K` → sext → +16 (2 段) | M1 + M2 | 保留 |
| 57 | function_12ca640 | `mov rcx,[rip+X]` (qword P) → `mov r13d,[rcx+0x14]` | `load i32 @K` → sext → +20 → `load i32` | M2 | 保留 |
| 59 | function_12cab20 | `mov rcx,[rip+X]` (qword P) → `mov edi,[rcx+0x14]` | 同 K (`load i32`) → sext → +20 | M2 | 保留 |
| 61 | function_12cab20 | `mov rcx,[rip+X]` (qword P) → `mov esi,[rcx+0x14]` | 同 K (`load i32`) → sext → +20 | M2 | 保留 |
| 65 | function_12cb680 | `mov rcx,[rip+X]` (qword P) → `mov esi,[rcx]` (dword P) | `load i32 @K` (`align 8`) を count に使う (1 段) | M1 | 保留 |

- 対応の確認 (IR 側の K の読み方。件数は §8.4 のコマンドで出した): K = 18752024 (41・47・40) は IR で `load i32` が 269 箇所で、他の型は無い。K = 22281208 (57・59・61) は `load i32` が 11 箇所で、他の型は無い。K = 18751896 (42) は `load i32` 31 箇所・`load ptr` (qword) 3 箇所・`load i16` 1 箇所。K = 18742616 (65) は `load i32` 3 箇所・`load ptr` 1 箇所。`load i64` は保留 8 件の 4 つの K のどれにも無い。K は i32 でも ptr でも読まれるので、『K だけが i32 で読まれる』とは言えない。真陽性の G は `load i64` で読まれる (19649808 = 13 箇所・22281224 = 12 箇所・22281256 = 5 箇所)。行 42 の『IR は 1 段』は、count 源の `%11 = load i32` (`function_127cea0`・`%18 = sub i32 %5, %11`) に限って言う。
- 行 39 の L の入口判定 (M3): IR は `index` (sext i32) と `load i64 [P+16]` を `ult` で比べ、機械語は `esi` (index) と `dword [P+16] − 1` を `jg` (符号付き) で比べる。P+16 の上位 4 byte (dword の隣の値) は静的な PE からは確定できない (P はヒープ) ため、同値は作れない。
- 行 40・41 の参照経路差 (§4j 注 2) の対応: 機械語は K から 3 段 (`mov rcx,[rip+X]; mov rcx,[rcx]; mov edi,[rcx+0x10]`。§4j 注 2 の『2 段 deref』は、rip 相対の K の読みを除いて数えた値で、3 回のメモリ読みは同じ)、IR は K を 1 回読むだけ (127bc80 の段数の差: 機械語 3 段・IR 2 段。本 PR の観測)。番地のずれではない (K = X − 0x400000 は全件で一致)。K = 0x11e2218 は `ldfix/REPORT_2794.md` の site #1 (`function_1003c20`) と同じ K だが、型 (段数) が同じとは確認していない。`ldfix/REPORT_2940.md` §2・§3 は、その site #1 の読みの欠落を『分岐の欠落 (lift 段)』と確定している (不成立側 block が IR に無い)。よって site #1 は 2 段 deref の潰れの類型ではない。行 40・41 は『K の共有だけ。型は未確認』とし、REPORT_2794 の類型名は借りない。#2940 (LD-141) は close 済み。同 REPORT の未特定は 128c320 だけで、子 #3612 に移してある。

### 8.3 判定の結論と限界

- 21 件の判定 (§3) は変えない。本節は保留 8 件の**理由**を機構で特定した (保留の理由が『段数』『幅』『偽側の経路』の 3 型のどれかに入ることを、機械語の実測で確認)。
- 保留 8 件の SSA 同値 (受入条件の 1 項目目) は**未達**。機械語側の count 源は実測したが、IR の K の読みが機械語と一致しないため、『同じ値』を結ぶ前に count 源の欠落・幅の誤りが先に出た。SSA 追跡は行っていない。
- 機構 M1・M2 の欠陥類型 (`docs/DEFECTS.md` の ID) は付けない (`ldfix/REPORT_2794.md` と同じく、ID は PM 判断)。
- 保留 8 件を真陽性・偽陽性に確定するには、IR 側の K の読みが機械語と一致する版 (ldfix 適用後・現 main の `m11_e2e.sh --full` 出力) で count 源を取り直す必要がある。`work-m11` の IR はこの比較の基準には使えない (`docs/WORKFLOW.md` §11)。

### 8.4 再現

```sh
python3 tools/m11/trap_triage/frame_ops_3564.py <IR> function_125da90 <PE> "rbp \+ 0xac\]"
python3 tools/m11/trap_triage/judge_src.py <IR> function_125da90 --pe <PE> --jcc 125e022 --n 14
python3 tools/m11/trap_triage/judge_src.py <IR> function_12a75e0 --pe <PE> --jcc 12a760d --n 6
python3 tools/m11/trap_triage/judge_src.py <IR> function_12ca640 --pe <PE> --jcc 12ca666 --n 12
python3 tools/m11/trap_triage/judge_src.py <IR> function_1274260 --pe <PE> --jcc 12742fa --n 12
python3 tools/m11/trap_triage/frame_ops_3564.py <IR> function_125da90 <PE> "rbp \+ 0xa4\]"
python3 tools/m11/trap_triage/judge_src.py <IR> function_127cea0 --pe <PE> --jcc 127cf07 --n 8
python3 tools/m11/trap_triage/judge_src.py <IR> function_127cea0 127cf0e 127cf60 --mx 12
grep -oE "load [a-z0-9]+, ptr inttoptr \(i64 (18752024|22281208|18751896|18742616) to ptr" <IR> | sort | uniq -c
```

- §8.2 の件数 (IR 側・`grep` の出力): 18752024 = `load i32` 269 のみ。22281208 = `load i32` 11 のみ。18751896 = `load i32` 31・`load ptr` 3・`load i16` 1。18742616 = `load i32` 3・`load ptr` 1。
- 行 42 の機械語 (`--jcc 127cf07`): `127cec8: mov rax,[rip+X]` (qword) → `127ced1: sub esi,[rax]` (dword) で esi = arg − dword[*X] (2 段)。IR 側 (`127cf0e` = ループ先頭) は count 源の `%20 = load i32` (ループ本体) と脱出先 `127cf60` の `%41 = load i32` を出す。ループ先頭の `%20` は本付録の count 源の表 (§8.2) の対象外で、段数は未照合。
