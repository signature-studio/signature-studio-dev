# #5689 付録: 証拠表の行 139〜158 の件ごとの判定 (M11-N259・部分達成: 判定 0 件・保留 20)

本付録が #5689 の判定の正本。前 run の突合表は `REPORT_APPENDIX_5660.md` §3 (行 139〜158 の入口判定の本数・被演算子)。結論は `REPORT_718.md` §4l の行 119〜158 の要約行に載せる。

## 1. 結果

- 母数 20 (証拠表 `strict_evidence.tsv` のデータ行 139〜158)。
- 確定 0 件 (真陽性 0・偽陽性 0)、**保留 20 件**。
- 140・141・143 は前版で真陽性としたが、根拠の関数先頭の入口レジスタ確認が `work/boot1.drc.dsm` (`boot_final.ll` とは別ビルド) に依るため、確定できず保留に戻した。`work-m11` の `boot_final.ll` はこの run の素材に無く、dsm と ll の対応を確かめられなかった。
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

## 7. 判定方法と入力 (REPORT_718 §4l から移動)

- 判定方法: 機械語 (`objdump` の逆アセンブル) の jcc 直前の被演算子の count 源を、IR の同じ load 連鎖 (段数・幅) と突合する。入口判定の有無と脱出先の一致を見る。判定は手で行い、スクリプトでは判定しない (`judge_ctx.py` は文脈ダンプのみ)。
- 入力: `work-m11` の `boot_final.ll` (sha256 `69c774de…`。`597757f4…` の系統は未使用)・`fl-win64` の `block00031_PE.bin`。scan 288・TSV 288 行を再現。

`oc_artifacts: fl-win64 work-m11` が要る。`work-m11` は `tools/m11/work/` (リポジトリ直下で展開する。tar 内のパスが `tools/m11/work/...` なので)、`fl-win64` は `$RUNNER_TEMP/fl-win64/extracted/` に展開する (いずれも gitignore)。
