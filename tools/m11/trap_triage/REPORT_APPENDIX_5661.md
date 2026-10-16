# #5661 付録: 証拠表の行 159〜193 (35 件) の件ごとの判定

本付録が #5661 の判定の正本。結論は `REPORT_718.md` §4m に要約する。

## 1. 結果

- 母数 35 件 (証拠表 `strict_evidence.tsv` のデータ行 159〜193)。
- 真陽性 11 件: 行 178 (`function_8c5eb0`・既知の positive control)、行 168 (`function_821210`)、行 169 (`function_821550`)、行 181・182・184・186・187 (§8)、行 189 (`function_a9ece0`)、行 190 (`function_bb5fd0`)、行 191 (`function_c3c830`・§9)。うち 168・169 は #5685 (§6) で、181・182・184・186・187 は #5687 (§8) で、191 は #5725 (§9) で確定した。
- 偽陽性 1 件: 行 188 (`function_a97930`)。
- 確定 12 件 (真陽性 11・偽陽性 1)。保留 23 件 (母数 35 = 確定 12 + 保留 23)。保留の内訳は 159〜177 の 17 件 (§6.2) と 179・180・183・185・192・193 の 6 件 (§8・§9)。偽陽性率は母数 288 の判定が終わるまで書かない。

## 2. 測定

- 測定 commit: `f195a93a9` (origin/main)。本 PR はコードを変えない (REPORT と付録のみ)。
  `git diff f195a93a9 HEAD -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_ctx.py` = 0 行。
- 入力: `work-m11` の `boot_final.ll` (19,787,837 B・sha256 `69c774de…`。REPORT の記録と一致)、`fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。
- 実行 (foreground・各 1 回): `scan_guard.py --report` 4.3 s (strict 288)、`strict_evidence.py` 13.0 s (TSV 288 行)、`judge_ctx.py <IR> <TSV> <PE> 159 193` (rc 0・2,330 行の文脈ダンプ)。
- 件数の数え直し (`ir_loop_head_icmp` 列・行 159〜193): 0 件 2 / 1 件 12 / 2 件 18 / 3 件 1 / 5 件 1 / 6 件 1 (計 35)。
  本 run は 35 件の範囲だけを数え直した。旧記録 (§4c・行 99〜193 の 95 件の内訳) とは範囲が違うため照合していない。
- 判定方法: 機械語 (`ldmach` の逆アセンブル) の jcc 直前の cmp 被演算子と、count 源 (`[reg+off]` の load・関数戻り値) を、IR の同じ load 連鎖 (段数・幅・オフセット) と突合する。入口判定の有無と脱出先の一致を見る。判定は手で行い、スクリプトでは判定しない。
- 引数対応 (Win64): `arg1`=rcx、`arg3`=r8、`arg4`=r9 を、関数先頭の命令と IR の使い方の両方で確認した (`function_a96d40`・`function_bb5fd0`・`function_821210`・`function_a968f0` の先頭命令)。

## 3. 件ごとの判定

(本表は #5661 時点の判定。現在の判定は §1 の件数と §8・§9 の表が正本。#5685 で 168・169、#5687 で 181・182・184・186・187 を確定し、#5725 で 191 を確定した。)

| 行 | 関数 | jcc → 脱出先 / L | 判定 | 理由 |
|---|---|---|---|---|
| 159 | function_78b010 | 78b251 → 78b301 / 78b25c | 保留 | 機械語の count は `call 5281a0` の戻り値 −1。IR の L の判定は `call 40fe90` の結果で、count 源との対応が未確認 |
| 160 | function_78b010 | 78b417 → 78b449 / 78b41e | 保留 | 機械語の count は `[[rbp+0x80]+0x10]`−1。IR の B (78b402) の `%143` (load i32 `%72`) との同一性が未確認 |
| 161 | function_78b4f0 | 78b61e → 78b686 / 78b625 | 保留 | 機械語の被演算子は `ecx`=0 と `esi`=`eax`−1。IR の L の判定は `icmp eq %44,0` (関数戻り値) で、入口 count との対応が未確認 |
| 162 | function_78c110 | 78c88b → 78f9ae / 78c89c | 保留 | 機械語の count は `call [rax+0x28]` の戻り値 −1。IR の L の `icmp` は `stack_var_-1128` の 0 判定で、count 源との対応が未確認 |
| 163 | function_78c110 | 78cde7 → 78ceba / 78cdf2 | 保留 | 機械語の count は `[[[rbp+0x30]+0x57c]+0x10]`−1。IR の B の `%292` (load `%112`+16) との同一性が未確認 |
| 164 | function_7a0b50 | 7a0ba2 → 7a0be7 / 7a0ba9 | 保留 | 機械語の count は min(`ecx`, `rax`) の結果。IR の B の `%9` (`spec.select`+1) との対応は未確認 |
| 165 | function_80e040 | 80e094 → 80e133 / 80e09f | 保留 | 機械語は `[rip+…]` の 2 段 load、IR は `load [18762880]` の 1 段。rip 先アドレスの一致が未確認 |
| 166 | function_81a710 | 81a9b5 → 81aa57 / 81a9c0 | 保留 | 機械語の count は `call [rax+0x28]` の戻り値。IR の B の count 源 (`%69`) との対応が未確認 |
| 167 | function_81a710 | 81aac4 → 81ab19 / 81aacb | 保留 | 機械語の count は `call [rax+0x28]`。IR の B の `%93` (load `%91`) との同一性が未確認 |
| 168 | function_821210 | 821226 → 821253 / 82122d | 真陽性 (構造) | count は `[arg1+16]` で IR の B の `%4` と一致 (§6.1)。L の `icmp eq %15,0` は要素の null 判定で count 判定ではない。#5685 で確定 |
| 169 | function_821550 | 821571 → 8216db / 82157e | 真陽性 (構造) | count は `[arg1+16]` (IR の B の `%2`) と一致。L の判定は `icmp eq %12, arg2` (要素比較)。#5685 で確定 (§6.1) |
| 170 | function_824460 | 8244f0 → 82462a / 8244fb | 保留 | count は `call 611430` の戻り値。機械語の引数 `[rsp+0x28]` と IR の `arg1` の対応が未確認 |
| 171 | function_825fc0 | 8260a1 → 82616e / 8260ae | 保留 | count は `[[rsi+0x370]+0x10]`−1 。IR の L の判定は `call 81fed0` の戻り値で、対応が未確認 |
| 172 | function_8261a0 | 82682d → 8268a0 / 826836 | 保留 | count は `[[rbp+0x80]+8]`−1。IR の B の `%284` (load `%282`+8) との同一性が未確認 |
| 173 | function_8261a0 | 8269cf → 826aef / 8269dc | 保留 | count は `ebx`−1。IR の L の判定が複合 `icmp` (`%or.cond40`) で、count 源との対応が未確認 |
| 174 | function_8261a0 | 826b4d → 826c58 / 826b58 | 保留 | count は `[rbp+0xa4]` (機械語の 1 段 load)。IR の L の判定は `call 424660` の結果で、対応が未確認 |
| 175 | function_85dfb0 | 85dfea → 85e026 / 85dff3 | 保留 | 機械語の count は `call 8657d0` の戻り値。IR の B の `%8` (`call 8657d0`) との同一性が未確認 |
| 176 | function_867540 | 867569 → 8675a5 / 867572 | 保留 | count は `call 8657d0`。IR の L の exit は `call 865020` の結果で、count 判定の対応が未確認 |
| 177 | function_86b300 | 86b31e → 86b380 / 86b325 | 保留 | count は `call 865850`。IR の B の `%2` と同じ callee だが、機械語は `[rip+…]` 経由で引数の一致が未確認 |
| 178 | function_8c5eb0 | 8c5f18 → 8c6066 / 8c5f23 | 真陽性 | count = `[[rbp+0x58]+0x14]`。IR の B の `%7`・`%9` (offset 20) と一致。B → L の直接分岐で、入口の count 判定が IR に無い (`switch` のみ)。既知の positive control と一致 |
| 179 | function_8d0580 | 8d05ec → 8d066a / 8d05f5 | 保留 | count は `call 8cfb90` の戻り値 −1。IR の B の `%7` (`call 8cfb90`) と一致するが、`eax` の符号拡張と L の `%16` の対応が未確認 |
| 180 | function_8e6150 | 8e6237 → 8e63b6 / 8e6248 | 保留 | count は `call [rax+0x28]` の戻り値 −1。IR の L の判定は `call 4150d0` の結果で、対応が未確認 |
| 181 | function_92d9d0 | 92da0e → 92da78 / 92da17 | 保留 | count は `[[rdx+rcx*8+0x3c]+0x10]`。IR の B の `%13`/`%16` の段数は一致するが、機械語の `rdx` と IR の `arg1` の対応が未確認 |
| 182 | function_9cef00 | 9cef21 → 9cef57 / 9cef2a | 保留 | count は `[[rip+…]+0x10]`。IR の B の `%0` (load `[19241064]`) と rip 先アドレスの一致が未確認 |
| 183 | function_a96620 | a9672f → a96899 / a9673a | 保留 | count は `[[rbp+0x38]+0x18]`。IR の L の判定は `icmp eq %54,0` (ポインタ) と `icmp sgt` の複合で、count 源との対応が未確認 |
| 184 | function_a968f0 | a96988 → a96a4c / a96995 | 保留 | count は `[[rbp+0x20]+0xb0]+0x18`−1。IR の B の `%25`・`%28` (`[arg1+176]`+24) と段数は一致するが、機械語の `rbp+0x20` と `arg1` の対応が未確認 |
| 185 | function_a968f0 | a96a7e → a96adf / a96a85 | 保留 | 184 と同じ count 源。IR の B の `%96` と L の `%98` の対応が未確認 |
| 186 | function_a96b10 | a96cc0 → a96d07 / a96cc9 | 保留 | count は `[[rbp+0xb0]+0x18]`−1。IR の L の count 源 (`%r13.0`) の同一性が未確認 |
| 187 | function_a96d40 | a96d80 → a96db6 / a96d89 | 保留 | count は `[[rbx+0x50]+0x90]`の 2 段 load。IR の B の `%12`・`%15` (段数 3) との対応が未確認 |
| 188 | function_a97930 | a97a90 → a9812e / a97a96 | **偽陽性** | `a97a77` で `[rbp+0xc4]`=3 を書いた直後に `a97a89` の `cmp` があり、その間に分岐の着地点が無い (`jcc` の着地点は `a97a61`・`a97a38`・`a98128` のみ)。よって `jle` は常に不成立 |
| 189 | function_a9ece0 | a9ecf6 → a9ed11 / a9ecff | **真陽性** (構造) | count は `r8d` (`arg3`=r8)。IR の B は `store arg3 → r8.0` で直接 L に入り、L には入口判定が無い (L の判定は末尾の `icmp eq`)。機械語は count=0 で `a9ed11` へ抜ける。到達性 (count=0 の実行時到達) は未測定 |
| 190 | function_bb5fd0 | bb5ff2 → bb601d / bb5ffb | **真陽性** (構造) | count は `[[arg1+928]+16]` (`rbx`=`rcx`=`arg1`、`0x3a0`=928)。IR の B の `%2`・`%5` と一致。B → L の直接分岐で入口判定が無い。機械語は count=0 で `bb601d` へ抜ける。到達性は未測定 |
| 191 | function_c3c830 | c3c8c8 → c3c907 / c3c8da | 保留 | count は `[rbp+0xa8]`。IR の L の count 源 (`stack_var_-88`) と一致する根拠が未確認 |
| 192 | function_c3c830 | c3c94a → c3c972 / c3c951 | 保留 | count は `[[rbp+0x68]+0x10]`−1。IR の B の `%17` (load `%4`+16) と段数は一致するが、`rbp+0x68` と `%4` の対応が未確認 |
| 193 | function_c3efe0 | c3f020 → c3f04f / c3f027 | 保留 | count は `[[rbx+0x10]+0x10]`。IR の B の `%11` (`arg1`+16) との対応は、`rbx` = `arg1` の確認が要る |

## 4. 保留 23 件の未解決 (#5661 時点の 31 件から #5685 で 168・169、#5687 で 181・182・184・186・187、#5725 で 191 を除いた)

- 型: count 源の段数・オフセットは IR と一致するが、機械語のベースレジスタ (`rbp+…`・`rip+…`・`rbx`) と IR の SSA 値 (`arg1`・load 先) の同一性が未確認 (159・160・163・165・177・185・192・193 ほか)。
- 型: count 源が関数戻り値 (`call 8657d0`・`call 865850`・`call [rax+0x28]` ほか) で、IR の同じ callee の引数の一致が未確認 (166・167・175・176・180)。8cfb90 の引数の同一性が未確認 (179: 機械語は仮想呼び出し `call [rax+0x30]` の戻り値 `rsi` を渡し、IR は `%arg2` を渡す)。
- 型: count 源が stack 変数 (`[rbp+0xa8]` 等) で、store/load の追跡が未了 (191 は #5725 で確定 (§9) のため未解決から外す)。
- 起票先: #5661 (本 issue・Refs)。子 issue は新規に起票しない (判定だけの残作業のため。規約上の『未解決の追跡』に当たる)。

## 5. 再現

```sh
cd tools/m11
python3 guard699/scan_guard.py work/boot_final.ll --pe <block00031_PE.bin> --report work/strict_5661.json
python3 trap_triage/strict_evidence.py work/boot_final.ll --pe <block00031_PE.bin> --report work/strict_5661.json --out work/strict_evidence_5661.tsv
python3 trap_triage/judge_ctx.py work/boot_final.ll work/strict_evidence_5661.tsv <block00031_PE.bin> 159 193
```

- 入力は `oc_artifacts: fl-win64 work-m11` で展開する (`tools/m11/work/` 配下・gitignore)。
- 出力の文脈ダンプは `tools/m11/work/judge_5661.txt` (gitignore・未コミット)。

## 6. #5685 (行 159〜177・母数 19 件): 確定 2 件・保留 17 件

- 測定 commit: `739b46e2d` (origin/main)。本 PR はコードを変えない。`git diff 739b46e2d HEAD -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py tools/m11/trap_triage/` = 0 行。
- 入力: `work-m11` の `boot_final.ll` (19,787,837 B・sha256 `69c774de…`・§4a と一致)、`fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。
- 実行 (foreground・各 1 回): `scan_guard.py --report` 4.3 s (strict 288)、`strict_evidence.py` 12.1 s (TSV 288 行)、`judge_ctx.py <IR> <TSV> <PE> 159 177` rc 0 (1,237 行の文脈ダンプ)。
- 件数の数え直し (`ir_loop_head_icmp` 列・行 159〜177): 0 件 0 / 1 件 9 / 2 件 8 / 5 件 1 / 6 件 1 (計 19)。付録 §2 の 35 件の内訳とは範囲が違う。
- 判定母数 19、確定 2 (真陽性 2・偽陽性 0)、保留 17。偽陽性率は書かない。

### 6.1 確定 (真陽性・構造判定)

| 行 | 関数 | jcc → 脱出先 / L | 判定 | 理由 |
|---|---|---|---|---|
| 168 | function_821210 | 821226 → 821253 / 82122d | 真陽性 (構造) | 機械語: 関数先頭で `mov rbx, rcx` (rcx = arg1) の後に `edi = [rbx+0x10]−1`、`esi = 0`、`cmp esi, edi`、`jg 821253`。count=0 で脱出する。IR: B の `%4 = load [arg1+16]` が同じ count 源 (段数 1・幅 i32)。L の入口判定は要素 null の `icmp eq %15, 0` (`%16`) で count 判定ではない。末尾の `%22` は `i32` の 0 判定で後判定 (do-while)。count=0 のとき IR は本体を 1 回実行し、`%20` が `0xFFFFFFFF` になって `trunc` 後も 0 にならず、loop を抜けない。機械語は count=0 で `821253` へ直行する。count=0 の実行時到達は未測定。 |
| 169 | function_821550 | 821571 → 8216db / 82157e | 真陽性 (構造) | 機械語: 先頭の `mov r9d, [rcx+0x10]` (rcx = arg1。`rcx` はそれまで書き換えられない)、`r9d = count−1`、`cmp eax, r9d`、`jg 8216db`。IR: B の `%2 = load [arg1+16]` が count 源 (`%0 = arg1+16`) で一致。L の判定は要素比較 `icmp eq %12, arg2` で、count の入口判定ではない。末尾 8216cb の `%75 = r9−1` が `trunc` で 0 かを見る後判定で、count=0 では loop を抜けない。到達性は未測定。 |

- 168・169 の確定の範囲: 同じ count 源の同一性は、関数先頭の命令 (rbx・rcx = arg1) と IR の `arg1` の対応で確認した。back-edge の `rsi`・`rdi`・`r9` の更新式は本文で読んだ。
- 到達性 (count=0 の実行時到達) は未測定。判定基準は付録 §4 (#3564) と同じ構造判定。

### 6.2 保留 17 件 (残件)

- 保留: 159・160・161・162・163・164・165・166・167・170・171・172・173・174・175・176・177。
- 型: (a) count 源が `[rbp+…]` のスロット経由で、スロットが `arg1` を保存しているかの確認が未了 (160・163・172・173・174・171 ほか)。(b) count 源が関数戻り値 (`call 5281a0`・`call 8657d0`・`call 865850`・`call [rax+0x28]`・`call 611430`・`call 50aa70` ほか)で、IR の同じ callee と引数の一致が未了 (159・162・165・166・167・170・175・176・177)。(c) 機械語が `[rip+…]` 経由で、IR の定数アドレスとの一致が未了 (165・177)。(d) 機械語の被演算子が stack 変数 (`[rbp+0x7c]`・`[rbp+0x4c]`・`[rbp+0x5c]`・`[rbp+0x6c]`・`[rbp+0x8c]`・`[rbp+0xa4]`) で、store/load の追跡が未了 (159・162・163・164・173・174)。
- 注: 行 173 の L の判定は複合 `icmp` (`%or.cond40`) で、count 源との対応が未確認。行 164・170 は機械語の count が `min` や戻り値の合成で、IR の `spec.select`・`call` 結果との同一性が未確認。
- 起票先: #5661 (`[M11-N253]`・open。行 159〜193 を担当)。残り 17 件は既存の open issue で追跡し、新しい子 issue は切らない (重複のため)。

## 7. 範囲 (REPORT_718.md §7 の正本)

- 本付録の変更は `REPORT_APPENDIX_5661.md` の §1・§4・§6 の文言と件数の修正だけ (#5685)。`tools/m11/guard699/`・`tools/m11/ldfix/ldmach.py`・`tools/m11/trap_triage/` のコードは変更していない。
- 20 MiB 超の blob: 追加なし。

## 8. #5687: 保留 12 件 (行 179〜187・191〜193) の件ごとの判定

- 母数 12 件。真陽性 (構造) 5・偽陽性 0・保留 7 (179・180・183・185・191・192・193)。判定件数は 5 + 0 = 5 / 12 (確定)。(run 1 で確定 5 (181・182・184・186・187)。run 2 で 179 を真陽性にしたが、run 3 で保留に戻した。)
- 注 (#5725): 本節の 191 (保留) は §9 で確定に変更した。§9 の確定後の件数は真陽性 6・保留 6、判定件数 6 / 12 (§1 の件数と一致)。
- 行 188〜190 は §3 で確定済みのため対象外。
- 測定 commit: `739b46e2d` (origin/main)。コードは変えていない。`git diff 739b46e2d HEAD -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_ctx.py` = 0 行 (本 PR は付録のみ)。
- 入力: `work-m11` の `boot_final.ll` (sha256 `69c774de…`、記録と一致)・`fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。
- 実行 (foreground・各 1 回): `scan_guard.py` 4.8 s (strict 288)、`strict_evidence.py` 15.2 s (TSV 288 行)、`judge_ctx.py <IR> <TSV> <PE> 179 193` (rc 0・1,034 行の文脈ダンプ)。
- 件数の数え直し (`ir_loop_head_icmp` 列・行 179〜193 の 15 行): 0 件 1 (行 185) / 1 件 3 (181・188・193) / 2 件 10 (180・182〜184・186・187・189〜192) / 3 件 1 (179)。
- 判定方法: 機械語の jcc 直前の cmp 被演算子の count 源を、IR の同じ load 連鎖 (ベース・段数・オフセット・幅) と突合する。ベースは関数先頭の命令 (`mov [rbp+x], rcx` 等) で引数 (`arg1`=rcx 等) と対応づけた。`rip` 先は PE の VA と IR のアドレスの差 (イメージ基底 `0x400000`) で換算した。入口判定の有無と脱出先の一致を見る。判定は手で行い、スクリプトでは判定しない。
- 真陽性 (構造) の基準は §4k と同じ: count 源が同一で、IR に count の入口判定が無く、末尾が後判定 (do-while) なら、count = 0 で IR は本体を 1 回回るが機械語は脱出先へ直行する。count = 0 の到達性は未測定。

| 行 | 関数 | jcc → 脱出先 / L | 判定 | 理由 |
|---|---|---|---|---|
| 179 | function_8d0580 | 8d05ec → 8d066a / 8d05f5 | 保留 | count は `call 8cfb90` の戻り値 `ret` −1 (`r8d`)。8cfb90 の引数が一致しない: 機械語は `8d05cd` の仮想呼び出し `call [rax+0x30]` の戻り値 `rsi` を `8d05d9` で `rcx` に渡す (`mov rcx, rsi; call 8cfb90`)。IR の `%7 = call 8cfb90(%arg2)` (335867) は `%arg2` を渡し、IR に `call [rax+0x30]` に当たる呼び出しが無い。IR の本体は `[arg2+24]` を読み、機械語は `[rsi+0x18]` を読むため、対象の同一性が未確認。`ret = 0` の挙動は保留の注記: IR は末尾 `%40` の後判定で約 2^32 回回り、機械語は `8d066a` へ飛ばす。`ret = 0` の実行時到達は未測定。IR の定義 (`%7`・`%8`・`%40`・入口 `br 8d05f5`) の読みは確認済み |
| 180 | function_8e6150 | 8e6237 → 8e63b6 / 8e6248 | 保留 | count は間接呼び出し `call [rax+0x28]` の戻り値 −1 (`[rbp+0x24]`)。IR 側で `[rbp+0x24]` 相当の値 (`%stack_var_-132`) の store 元と、機械語の間接呼び出しの戻り値との対応を確認できていない |
| 181 | function_92d9d0 | 92da0e → 92da78 / 92da17 | 真陽性 (構造) | count = `[[[arg1+0x78]*8+arg1+0x3c]+0x10]` の i32 (`rdx`=`arg1` は先頭の `mov [rsp+0x28],rcx`)。IR の B `%5`〜`%16` (+120・×8・+60・+16、i32) と段数・幅・オフセットが一致。L の `icmp ult %23,%26` は index と qword の境界判定で count 判定ではない。L から T への直接の脱出は無く、T (92da78) の preds は `92da4d` (内側) と末尾 `92da6c` の 2 件。入口判定は無い |
| 182 | function_9cef00 | 9cef21 → 9cef57 / 9cef2a | 真陽性 (構造) | count = `[[rip+0xc8a954]+0x10]` の i32。`rip` 先 VA `0x1659868` は IR のアドレス `19241064` (`0x1259868`) に当たる (基底差 `0x400000`)。IR の `%0 = load [19241064]`、`%3 = load i32 [%0+16]` と一致。L に入口判定無し、末尾 `%22` が後判定 |
| 183 | function_a96620 | a9672f → a96899 / a9673a | 保留 | count は `[[rbp+0x38]+0x18]` (2 段)。IR の L は入口で `rbx > stack_var_-1356 ∨ (関数戻り値 %54 == 0)` の分岐 (`or.cond`) を持ち、count 源 (`%48`) との同一性を確認できていない |
| 184 | function_a968f0 | a96988 → a96a4c / a96995 | 真陽性 (構造) | count = `[[arg1+0xb0]+0x18]` の i32 (`[rbp+0x20]`=`arg1` は `mov [rbp+0x20],rcx`)。IR の B `%11`〜`%28` (+176・+24、i32) と一致。L に入口判定無し、末尾 `%77` が後判定。T=`a96a4c` の preds は末尾 `a96a37` のみ |
| 185 | function_a968f0 | a96a7e → a96adf / a96a85 | 保留 | count の chain は 184 と同じ (B `%92`〜`%94` で一致)。ただし IR の L に count==0 の入口分岐 `br %cf.1 → a96abf` (`cf.1 = icmp eq %94,0`) があり、真陽性の基準「入口判定無し」を満たさない。`a96abf` は `rdi−1` を経由して `a96a85` へ戻る経路を持つ。count = 0 の挙動は未追跡。到達性未測定 |
| 186 | function_a96b10 | a96cc0 → a96d07 / a96cc9 | 真陽性 (構造) | count = `[arg1+0x18]` の i32 (`[rbp+0xb0]`=`arg1` は `mov [rbp+0xb0],rcx`、`mov rcx,[rbp+0xb0]; mov r13d,[rcx+0x18]`)。IR の `%16`〜`%99` (arg1+24、i32) と一致。機械語・IR とも `call a968f0` の後で読む。L に入口判定無し、末尾 `%121` が後判定 |
| 187 | function_a96d40 | a96d80 → a96db6 / a96d89 | 真陽性 (構造) | count = `byte [[[arg1+0x50]+0x90]+0x1c]+0x74]` (`rbx`=`rcx`=`arg1`)。IR の B `%7`〜`%18` (+80・+144・+28・+116、i8) と一致。L に入口判定無し、末尾 `%29` が後判定。T の preds は `a96d89` のみ |
| 191 | function_c3c830 | c3c8c8 → c3c907 / c3c8da | 保留 (§9 で確定に変更) | count = `[rbp+0xa8]` = エントリの `r9` (`arg4`)。機械語は count<0 で c3c907 (post-loop の `call 50a830`) へ抜ける。IR の P `%7 = icmp slt (arg4+1) 1` は同じ条件で `c3c923` へ直接抜け、`call 50a830` を飛ばす。脱出先が一致しない。到達性は未確認 |
| 192 | function_c3c830 | c3c94a → c3c972 / c3c951 | 保留 | count = `[[rbp+0x68]+0x10]`−1。`[rbp+0x68]` は `call 40f9e0` の戻り値。機械語は第 1 引数に `[rip+…]` の値 (load) を渡すが、IR の `%4 = call 40f9e0(ptrtoint 826304, …)` は定数アドレスを渡す。引数の形が一致せず、戻り値の同一性を確認できていない |
| 193 | function_c3efe0 | c3f020 → c3f04f / c3f027 | 保留 | count = `[[rbx+0x10]+0x10]` (`rbx`=`arg1`)。IR の B `%11`〜`%15` と一致する。ただし機械語は非 null 経路で `call [rsi+0x10]` (c3f00d) を経てから count を読むのに対し、IR の P→B (c3f010) にはこの呼び出しが無い。呼び出しが count 源を書き換えないことを確認できていない |

- run 3 (保留 6 件の再判定・新規確定 0 件): 保留 6 件 (180・183・185・191・192・193) の型と未解決点は次のとおり。
  - 180: count 源は `call [rax+0x28]` の戻り値 −1。IR の B (`8e620b`) の count store は `load [%4]` 由来で、間接呼び出しが無い。同一性は未確認。
  - 183: IR の L (`a9673a`) に入口判定 `or.cond = (rbx > stack_var_-1356) ∨ load[+640]==0` があり、真陽性の基準を満たさない。
  - 185: IR の L に count==0 の分岐 `cf.1 = icmp eq %94,0` がある。その経路 `a96abf` は `rdi−1` を 32 bit で見るだけで脱出せず、`a96a85` へ戻る (`rdi=0` なら `0xFFFFFFFF` で非 0 のため)。機械語は count=0 で `a96adf` へ直行する。count=0 の実行時到達は未測定。
  - 191: count 源は `[rbp+0xa8]`=`arg4`。IR の P (`c3c830`) に `icmp slt (arg4+1) 1` の入口判定があり、count<0 で `c3c923` へ直接抜ける。機械語の脱出先 `c3c907` (IR の T で `call 50a830` を行う) と呼び出し列が一致しない。
  - 192: count 源は `[[rbp+0x68]+0x10]`−1。機械語の `c3c92e` の間接呼び出し `call [rip+0xa7ba2c]` に対応する IR の call が、脱出前の B (`c3c923`) に無い。
  - 193: count 源は段数・オフセットが IR の `[[arg1+16]+16]` と一致する。ただし `rbx = arg1` の確認は未了。機械語は `c3f00d` の `call [rsi+0x10]` を経てから count を読むが、IR の P→B (`c3f010`) にその呼び出しが無い。
- 注: 185 の count=0 経路 (wrap して本体へ戻る) は IR の構造から読めるが、実行時の到達は未測定。入口判定の有無の基準 (§4k) に従い、確定にはしない。
- 偽陽性率は母数 288 の判定が終わるまで書かない。
- run 3 で 179 を保留に戻した。理由: 8cfb90 の引数が IR の `%arg2` と機械語の仮想呼び出し結果 (`rsi`) で一致しない。IR が `call [rax+0x30]` を欠く。レビュー (round 3) の指摘を受けた。
- 未解決 (保留 7 件: 179・180・183・185・191・192・193): 起票先は #5687 (本 issue・Refs。判定だけの残作業のため子 issue は新規に起票しない)。
- 素材: `oc_artifacts: fl-win64 work-m11` で取得した run (run 3) で、`boot_final.ll` (sha256 `69c774de…`) と `block00031_PE.bin` (22,227,016 B) を読んだ。上記 179 の機械語と IR の行番号はこの run の読み。
- 再現: 本節の §5 と同じ手順。`disasm_fn.py` の既定 PE パスは環境に合わせて `LD_M11_PE=<block00031_PE.bin>` で指定する。

## 9. #5725: 行 191〜193 (母数 3 件) の件ごとの判定

- 母数 3 件 (行 191・192・193)。確定 1 (真陽性 (構造) 1・偽陽性 0)、保留 2 (192・193)。判定件数は 1 / 3。§8 の 191 (保留) を本節で確定に変える (下記 191 の理由)。
- 測定 commit: `95883aa04` (origin/main)。本節はコードを変えていない。`git diff 95883aa04 HEAD -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_ctx.py tools/m11/trap_triage/disasm_fn.py` = 0 行。
- 入力: `work-m11` の `boot_final.ll` (sha256 `69c774de…`・19,787,837 B)、`fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。
- 実行 (foreground・各 1 回): `scan_guard.py` rc 0 (strict 288)、`strict_evidence.py` 288 行、`judge_ctx.py <IR> <TSV> <PE> 191 193` rc 0 (167 行の文脈ダンプ)、`disasm_fn.py c3c830 efe0` (機械語)。
- 件数の数え直し (`ir_loop_head_icmp` 列・行 179〜193 の 15 行): 0 件 1 (185) / 1 件 3 (181・188・193) / 2 件 10 (180・182〜184・186・187・189〜192) / 3 件 1 (179)。§8 の内訳と一致 (修正なし)。
- 判定方法: 機械語 (`disasm_fn.py`) の jcc 直前の cmp 被演算子と count 源を、IR の同じ load 連鎖と突合する。(a) 引数: `arg1`=rcx、`arg4`=r9 を関数先頭の `mov [rbp+x], rcx/r9` で対応づけた。(b) `[rip+…]` 先の値は PE から読んで IR の定数と照合した。(c) 機械語の間接呼び出しは、呼び出し先のアドレスがファイルのどの節に入るかで静的に決まるかを見た。判定は手で行い、スクリプトでは判定しない。

| 行 | 関数 | jcc → 脱出先 / L | 判定 | 理由 |
|---|---|---|---|---|
| 191 | function_c3c830 | c3c8c8 → c3c907 / c3c8da | **真陽性 (構造)** | count 源は `[rbp+0xa8]` (= entry の `r9`=`arg4`。書き込みは `c3c85a` の 1 回のみ)。機械語の入口判定は 2 つ。`c3c89b` の `jle c3c923` (64 bit の `arg4+1 ≤ 0`) は IR の P の `icmp slt (arg4+1) 1` → `c3c923` と一致する。問題の `c3c8c8` は 32 bit の `cmp 0, ebx` (ebx = low32(arg4)) で、負なら `c3c907` (post-loop の `call 50a830`) へ直行する。IR の P→B→L は入口で 32 bit 判定を持たず、B `c3c8a1` は L `c3c8da` へ無条件に入る。末尾は L の後判定 (`icmp eq trunc(%11),0`)。c3c8c8 に届くのは arg4+1 ≥ 1 の場合だけなので、差が出るのは arg4 ≥ 0 かつ low32(arg4) < 0 (arg4 mod 2^32 ∈ [2^31, 2^32)) の場合。この範囲で、機械語は本体を 0 回、IR は low32(arg4+1) 回回る。回数は未計算。到達性 (該当する arg4 の実行時到達) は未測定 |
| 192 | function_c3c830 | c3c94a → c3c972 / c3c951 | 保留 | count 源の同一性は確定: `[rbp+0x68]` = `call 40f9e0(rcx=[rip-0x772d71] → VA 0x4c9af8 の値 0x4c9bc0 = IR の定数 826304, dl=1)` = IR の `%4`。count は `[%4+0x10]`−1 で一致する。未解決は `c3c92e` の `call [rip+0xa7ba2c]` (間接呼び出し): IR の B (`c3c923`) に対応する call が無い。呼び出し先のスロットは RVA 0x12b8360 (`.bss` 内・raw 0 バイト) で、ファイルからは静的に決まらない。この呼び出しが `[%4+0x10]` を書き換えないことを確認できていない。count = 0 の挙動 (機械語は c3c972 へ直行、IR は本体を回る) は 191 と同型で、到達性は未測定 |
| 193 | function_c3efe0 | c3f020 → c3f04f / c3f027 | 保留 | count 源は `[[rbx+0x10]+0x10]`。`rbx = rcx = arg1` (`c3efe7`) で、IR の B `%10`〜`%15` と段数・オフセット・幅が一致する。未解決は `c3f00d` の `call [rsi+0x10]` (仮想呼び出し、`rsi` = `[[arg1+0x24]]`): IR の P→B (`c3f010`) に対応する呼び出しが無い。呼び出し先は実行時のオブジェクトの vtable で決まり、ファイルからは確定できない。この呼び出しが `[arg1+0x10]` の先の count を書き換えないことを確認できていない。count = 0 の挙動 (機械語は `c3f04f` へ直行、IR は回る) は 192 と同型で、到達性は未測定 |

- 未解決 (保留 2 件: 192・193): 両件の未解決は「間接呼び出し先が実行時にしか決まらない」点。静的な判定は打ち切り、件数の追加はしない。起票先は #5725 (本 issue・Refs)。子 issue は新規に起票しない (判定だけの残作業のため)。
- 191 の確定の範囲: 真陽性の根拠は脱出の不一致 (32 bit 判定) で、到達性 (low32(arg4) < 0 の実行時到達) は未測定。count の範囲を測らずに真陽性とする根拠は、構造上の差だけである。
- 191 の基準の当てはめ: §4k の『IR に count の入口判定が無い』は、IR の P の入口判定 (64 bit の `icmp slt (arg4+1) 1`) が機械語の 32 bit の `cmp 0, ebx` (c3c8c8) と同じ条件ではないため満たす。§8 (run 3) は脱出先の一致だけを見て、この 32 bit 判定の有無を基準に当てはめていなかった。
- 注: 本節の判定は §8 の 191 (保留) を覆す。§8 の件数 (5/12) は本節で 6/12 (確定 6・真陽性 6・偽陽性 0)。
