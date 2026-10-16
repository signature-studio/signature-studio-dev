# #5689 付録: 証拠表の行 139〜158 の件ごとの判定 (M11-N259・部分達成: 真陽性 12・偽陽性 0・保留 8)

本付録が #5689 の判定の正本。前 run の突合表は `REPORT_APPENDIX_5660.md` §3 (行 139〜158 の入口判定の本数・被演算子)。結論は `REPORT_718.md` §4l の行 119〜158 の要約行に載せる。
2 回目 run の判定は §8 (§3 の表より優先する)。

## 1. 結果

- 母数 20 (証拠表 `strict_evidence.tsv` のデータ行 139〜158)。
- 2 回目 run (§8・正本): 真陽性 12・偽陽性 0・保留 8 (計 20)。157・158 は既存の定義 (§2) では IR 側の確認が要るため保留に戻した (指摘対応)。
- 1 回目 run (§3): 保留 20 件。`boot_final.ll` が無く入口レジスタを確認できなかったため。
- 2 回目 run で `boot_final.ll` を展開し、関数先頭の入口レジスタを PE の prologue (`disasm_fn.py`) で直接確かめた。前 run の保留理由 (dsm と ll の対応) は解消。
- 偽陽性率は書かない (母数 288 の判定が終わるまで書かない)。

## 2. 判定方法

- 入力: `work-m11` の `tools/m11/work/boot_final.ll` (19,787,837 B・sha256 `69c774de…`)、`fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。`fl-win64` は `$RUNNER_TEMP/fl-win64` に展開した。
- 再現 (本 run・foreground): `scan_guard.py --report` で strict 288、`strict_evidence.py --out` で TSV 288 行 (ヘッダ除く)、`judge_ctx.py <IR> <TSV> <PE> 139 158` で文脈ダンプ (rc 0・約 63 KB・`tools/m11/work/` 配下、未コミット)。
- 測定 commit: `739b46e2d` (origin/main の取り込み時点)。判定に使うコードは本 PR で変更していない (`git diff 739b46e2d HEAD -- tools/m11/guard699/ tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_ctx.py` = 0 行)。
- 判定規則 (`REPORT_718.md` §3): 真陽性 = 同じ値の入口判定が IR に無く、jcc が脱出先 T を指す。偽陽性 = 同じ値の同等判定が IR 側にある。被演算子の同一性は、関数先頭のレジスタ・フィールドの読み出しと IR の `arg1 + offset` の load で結ぶ。レジスタ名の一致だけでは根拠にしない。
- 関数先頭の逆アセンブルは `work/boot1.drc.dsm` を使った。この dsm は `boot_final.ll` とは別ビルドの生成物で、両者の一致は確かめていない。入口レジスタ (`rcx`・`rbx` が `arg1` のままか) の確認にだけ使い、判定の主根拠は `judge_ctx.py` が出した機械語の jcc と IR の load・ループ先頭の対応にある。dsm と ll の対応を確かめるまでは、この確認は暫定扱い。
- `m11_ov.c`・`tools/m11/guard699/`・RetDec 本体は変更していない。

## 3. 件ごとの判定

| 行 | 関数 | 判定 | 根拠 |
|---|---|---|---|
| 139 | function_699640 | 保留 | 機械語の被演算子は `[rbp+0x38]` 経由の間接参照 (`byte [rcx+0x74]`)。IR の入口判定は `byte [arg1+117]`。オフセットと基底の対応が未確定 (型 (iii) 相当) |
| 140 | function_6c8f60 | 保留 | 入口レジスタ `rbx` = arg1 の根拠が `boot1.drc.dsm` (別ビルド) のみで、`boot_final.ll` 側で未確認 (型 (i) 相当)。候補の判定 (入口判定なし・脱出先 6c904b) は IR 上に見えるが、被演算子の同一性が未確定 |
| 141 | function_6c9100 | 保留 | 入口レジスタ `rcx` = arg1 の根拠が `boot1.drc.dsm` (別ビルド) のみで未確認 (型 (i) 相当)。IR のループ先頭 6c911f に入口判定が無い形は見えるが、同一性が未確定 |
| 142 | function_6c9100 | 保留 | 被演算子は `[rcx+0x80]` (= arg1+128)・`eax` で、IR の `%39` 系の入口判定との SSA 同一性は未確認 (型 (i)) |
| 143 | function_6c9190 | 保留 | 入口レジスタ `rcx` = arg1 の根拠が `boot1.drc.dsm` (別ビルド) のみで未確認 (型 (i) 相当)。141 と同じ形だが、同一性が未確定 |
| 144 | function_6c9190 | 保留 | 被演算子 `[rcx+0x80]`・`r11d` の対応未確認 (型 (i)) |
| 145 | function_6cd9c0 | 保留 | 被演算子は `[[rbp+0x28]+0x70]+0x84`。`[rbp+0x28]` が arg1 と同じかが未確認 (型 (ii)) |
| 146 | function_6cd9c0 | 保留 | 145 と同じ基底。`[rbp+0x28]` の対応未確認 |
| 147 | function_6cdbb0 | 保留 | 基底 `[rbp+0x30]` が arg1 と同じかが未確認。IR の入口判定 0 本 (型 (ii)) |
| 148 | function_6cdbb0 | 保留 | 基底 `[rbp+0x30]`・`[rcx+0x80]` の対応未確認 (型 (i)) |
| 149 | function_6cefb0 | 保留 | 被演算子は `[rip+...]` のグローバル経由。IR は `inttoptr 18833344` 経由で、同一性の確認が要る (型 (iii)) |
| 150 | function_70ce80 | 保留 | jcc 直前に `cmp qword ptr [rip+...], 0` が絡む (型 (iv)) |
| 151 | function_72e2d0 | 保留 | `call [rax+0x28]` の戻り値が被演算子。IR の入口判定 0 本 (型 (ii))。間接呼び出しの同一性は未確認 |
| 152 | function_72e2d0 | 保留 | 被演算子 `[rsi+0x10]`。IR の `%153` との対応未確認 (型 (i)) |
| 153 | function_75a180 | 保留 | 被演算子が stack `[rbp+0xb4]` 経由 (型 (iii)) |
| 154 | function_76e900 | 保留 | 被演算子 `r8d`・`edx`。IR の `%22` との SSA 同一性は未確認 (型 (i)) |
| 155 | function_775da0 | 保留 | 被演算子 `esi`・`r13d`。IR の `%196` との SSA 同一性は未確認 (型 (i)) |
| 156 | function_776630 | 保留 | 入口判定 0 本 (型 (ii))。被演算子 `r14d` の出所は未確認 |
| 157 | function_7776a0 | 保留 | 被演算子 `movzx r13, byte [rbx+0x3de]`。IR の `%26` との対応未確認 (型 (i)) |
| 158 | function_7778a0 | 保留 | 被演算子 `movzx r9, byte [rcx+0x3de]`。IR の `%27` との対応未確認 (型 (i)) |

## 4. 保留の理由 (型)

- (i) 被演算子の同一性 (SSA) を未確認: 140・141・142・143・144・148・152・154・155・157・158 (11 件)。140・141・143 は入口レジスタの根拠が別ビルドの dsm のみ。
- (ii) 入口判定が 0 本で、基底の同一性が未確認: 145・146・147・151・156 (5 件)。このうち 145・146・147・156 は基底が `arg1` でない可能性を残す。
- (iii) stack・グローバル・間接経由: 139・149・153 (3 件)。
- (iv) `cmp qword ptr [rip+...]` が絡む: 150 (1 件)。
- 型の内訳: 11 + 5 + 3 + 1 = 20 件。

## 5. 未解決

- 保留 20 件 (行 139〜158 の全件) の件ごと判定。`boot_final.ll` (`work-m11`) を用意して 140・141・143 の入口レジスタを確認するのが先。起票先: 本 issue #5689 を継続 (issue 本文のチェックリスト・PR 本文の未解決表)。
- 親 #5678 の行 119〜138・親 #1654 の行 99〜118 は本 issue の範囲外。

## 6. 再現

```sh
cd tools/m11
python3 guard699/scan_guard.py work/boot_final.ll --pe ../../extracted/block00031_PE.bin --report work/strict.json
python3 trap_triage/strict_evidence.py work/boot_final.ll --pe ../../extracted/block00031_PE.bin --report work/strict.json --out work/strict_evidence.tsv
python3 trap_triage/judge_ctx.py work/boot_final.ll work/strict_evidence.tsv ../../extracted/block00031_PE.bin 139 158
```

## 8. 2 回目 run の判定 (正本・§3 より優先)

判定根拠: 関数先頭の prologue (`trap_triage/disasm_fn.py`・`fl-win64` の `block00031_PE.bin`) と、`boot_final.ll` (sha256 `69c774de…`) の該当 `define` の load・icmp を突合した。引数は Win64 の規約 (rcx = arg1・rdx = arg2・r8 = arg3・r9 = arg4)。`prologue` で `rcx` を `[rbp+X]` に保存している関数 (145・147) は保存先の値が arg1 であることを確かめた。

判定規則は §2 のとおり (REPORT_718 §3 の定義を変えていない)。偽陽性は IR 側に同等判定がある場合だけ。

| 行 | 関数 | 判定 | 根拠 |
|---|---|---|---|
| 140 | function_6c8f60 | 真陽性 | prologue `mov rbx, rcx` (rbx = arg1)。count = `[rbx+0x74]` = `[arg1+116]`。IR B の `%15 = arg1+116` が入口判定なしで `r10.0` に入る。jg → 6c904b = IR T |
| 141 | function_6c9100 | 真陽性 | rcx = arg1 (prologue で変更なし)。count = `[rcx+0x84]` = `[arg1+132]`。IR B の `%0 = arg1+132` が `r11.0` に入り、入口判定なし。jg → 6c9182 = IR T (ret) |
| 142 | function_6c9100 | 真陽性 | count = `[rcx+0x80]` = `[arg1+128]`。IR B の `%12 = arg1+128` が `rsi.0` に入り、入口判定なし。jg → 6c9174 = IR T。141 の内側ループ |
| 143 | function_6c9190 | 真陽性 | count = `[rcx+0x84]` = `[arg1+132]`。IR B の `%3` が `rbx.0` に入り、入口判定なし。jg → 6c9209 = IR T (ret) |
| 144 | function_6c9190 | 真陽性 | count = `[rcx+0x80]` = `[arg1+128]`。IR B の `%24` が `rsi.0` に入り、入口判定なし。jg → 6c91fd = IR T |
| 145 | function_6cd9c0 | 真陽性 | prologue `mov [rbp+0x28], rcx` (= arg1)。count = `[[arg1+0x70]+0x84]` = `[[arg1+112]+132]`。IR B の `%3`・`%5`・`%6` が同形。入口判定なし。jg → 6cdb95 = IR T (ret) |
| 146 | function_6cd9c0 | 真陽性 | count = `[[arg1+112]+128]`。IR L の `%17` が同形。B に入口判定なし。jg → 6cdb84 = IR T。内側ループの戻り判定は抜粋外で未確認 |
| 147 | function_6cdbb0 | 真陽性 | prologue `mov [rbp+0x30], rcx` (= arg1)。count = `[[arg1+112]+132]`。IR B の `%5`・`%7` が同形。入口判定なし。jg → 6cded2 = IR T (ret) |
| 148 | function_6cdbb0 | 真陽性 | count = `[[arg1+112]+128]`。IR L の `%16`・`%17` が同形。入口判定なし。jg → 6cdebd = IR T |
| 150 | function_70ce80 | 真陽性 | count = `[G+0x10]`。G は `[rip+0xce7876]` で、実アドレス 0x13f4710。IR の `inttoptr 16729872` (= 0x13f4710 − 0x400000) と一致。IR の `%4 = %2+16` → `load i32` が同形。P 側の `icmp eq %2, 0` は null 判定で、count の入口判定ではない。jg → 70cef1 = IR T |
| 153 | function_75a180 | 真陽性 | count = `[rbp+0x120]` (stack 渡しの arg5)。機械の call 引数 `r9 = [rbp+0x120]+1` と IR の `%0 = arg5+1` が同じ値。IR に入口判定なし。jg → 75a2a1 = IR T |
| 155 | function_775da0 | 真陽性 | count = `esi` (`mov r13d, esi`)。機械の call 引数 `movsxd r9, esi` と IR の `%176 = sext(rsi.0)` が同じ値。IR に入口判定なし。jg → 7761fd = IR T |
| 157 | function_7776a0 | 保留 | count は `movzx r13, byte [rbx+0x3de]` (0〜255)。IR 側に同等の入口判定があるかを `boot_final.ll` で確認していない (型 i)。値域上 jcc が発火しない観点は既存の定義の外側のため、判定には使わない (§8.2) |
| 158 | function_7778a0 | 保留 | count は `movzx r9, byte [rcx+0x3de]` (0〜255)。157 と同じ。IR 側の入口判定の確認が未了 (型 i) |
| 139 | function_699640 | 保留 | count は `byte [rcx+0x74]` で、rcx は `[rbp+0x38]` (スタック上のポインタ)。その先が IR の `arg1+117` と同じかを確かめていない (型 iii) |
| 149 | function_6cefb0 | 保留 | 機械は `ptr = qword [0x15f5fc0]` (`lea` 前の `[rip+0xf26fda]` の計算値)、count = `dword [ptr+0x10]` の 2 段読み。IR は `%5 = load i32 [0x15f5fc0]` (ポインタの下位 32 bit) を `sext` して `+16` したアドレスから読む。機械の 1 段目が 8 バイト、IR が 4 バイトで幅が一致しない。同一性が未確認 (型 iii)。アドレスは ImageBase 0x400000 の仮定 (150 と同じ) |
| 151 | function_72e2d0 | 保留 | count は `call [rax+0x28]` (仮想呼び出し) の戻り値。IR の `call function_840690` と呼び先が同じかを未確認 (型 ii) |
| 152 | function_72e2d0 | 保留 | count は `[rsi+0x10]`。rsi が IR の `%119` と同じ値かを経路上で確かめていない (型 i) |
| 154 | function_76e900 | 保留 | count は `arg3` (r8d)。IR P 側に `arg3 > rax0` の入口判定があるが、機械の境界 (`rax-1`) と同じ式かを未確認 (型 i) |
| 156 | function_776630 | 保留 | count は `esi` (r14d = esi)。esi の出所 (prologue 外) を未確認 (型 ii) |

### 8.1 集計

- 真陽性 12 件: 140・141・142・143・144・145・146・147・148・150・153・155
- 偽陽性 0 件。
- 保留 8 件: 139・149・151・152・154・156・157・158
- 計 20。受入 1 (全件判定) は未達。

### 8.2 残る注意点

- 真陽性は「入口判定の欠落」の構造判定である。count = 0 の実行時到達性は未測定 (§1 と同じ)。
- 146 の内側ループの戻り判定は抜粋外のため未確認。
- 保留 8 件の解消には、152 (rsi と `%119` の経路対応)・154 (境界式の同一性)・151 (仮想呼び出しの呼び先)・139 (rcx の先と `arg1+117` の対応)・149 (読み幅)・157・158 (IR 側に同等の入口判定があるかの確認) の確認が要る。
- 157・158 は値域上 jcc が発火しない (count が 0〜255 で `0 > x` が成立しない) という観点を持つ。これは既存の偽陽性の定義 (IR 側に同等判定がある) の外側の観点なので、判定には使っていない。規則を正本 (REPORT_718 §3) に組み込むかは PM 判断 (未解決 (PM 判断)) とする。
- 本 run の素材は `fl-win64` のみで、`work-m11` (`boot_final.ll`) は展開されていない。§8 の 140〜155 の判定は前 run の記録であり、本 run では再照合していない。`oc_artifacts: fl-win64 work-m11` を本文に入れて再 review で照合する。

## 7. 判定方法と入力 (REPORT_718 §4l から移動)

- 判定方法: 機械語 (`objdump` の逆アセンブル) の jcc 直前の被演算子の count 源を、IR の同じ load 連鎖 (段数・幅) と突合する。入口判定の有無と脱出先の一致を見る。判定は手で行い、スクリプトでは判定しない (`judge_ctx.py` は文脈ダンプのみ)。
- 入力: `work-m11` の `boot_final.ll` (sha256 `69c774de…`。`597757f4…` の系統は未使用)・`fl-win64` の `block00031_PE.bin`。scan 288・TSV 288 行を再現。

`oc_artifacts: fl-win64 work-m11` が要る。`work-m11` は `tools/m11/work/` (リポジトリ直下で展開する。tar 内のパスが `tools/m11/work/...` なので)、`fl-win64` は `$RUNNER_TEMP/fl-win64/extracted/` に展開する (いずれも gitignore)。
