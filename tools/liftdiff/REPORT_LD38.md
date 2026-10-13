# liftdiff LD-38 (#1193) — ret=i128 39 関数の戻り経路の確認 (部分達成)

> 親 #976 (LD-24) の子。分割の正本は [`REPORT_LD24.md`](REPORT_LD24.md) §3。
> 既知類型との関係: 該当なし (lift の silent miscompile ではなく、case 生成と署名型の問題)。

## 1. 結論

- **i128 戻り関数の戻り経路は rax:rdx ではない可能性が高い**。機械語 (RetDec dsm) の `ret` 直前を見ると、
  xmm0 を使う経路が多く、rdx で返す関数は 0 件だった。IR の `i128` 型付けは実際の戻り値と合わない可能性がある。
- したがって受入条件「rdx を取得して `cmp_ret` で比較」は、この 39 関数に対しては**前提が未確定**。
  実装の前に戻り経路の確定が要る (下記 §4)。**コード変更は本 run では行わなかった**。

## 2. 署名内訳の照合 (実測・LD-24 の未検証表を確定)

`tools/liftdiff/results/m11_closure_verdicts.tsv` の `unexec_reason == unsupported_sig` は **50 行**、
すべて `work/m11_ldfix/sigs.json` に存在 (欠落 0)。ret=`i128` は **39 行**。内訳 (ret, params) は
LD-24 §1 の表と一致した (21 / 8 / 8 / 7 / 1 / 1 / 1 / 1 / 1 / 1、計 50)。

- 集計コマンド: `python3` で TSV の `unsupported_sig` 行を `sigs.json` に引く (本 REPORT の作業手順。TSV の `name` 列で結合)。
- 分母・除外: 分母は closure の判定 TSV 全行。除外なし。

## 3. 機械語の戻り経路 (実測)

`tests/ld38_ret_convention.py` が `work/m11/boot0.drc.dsm` 等の逆アセンブルを読み、各関数の `ret` 直前 3 行を判定。
出力: `work/ld38_ret_convention.txt`。

| 判定 | 関数数 | 意味 |
|---|---|---|
| xmm0 | 24 | 戻り値が浮動小数 (IR の i128 は誤り) |
| other | 14 | rax のみ・sret 等。目視確認が要る |
| no_ret | 1 | dsm 内に ret が無い |
| rax_rdx | 0 | rdx で返す関数は無い |

- ヒューリスティック (ret 直前 3 行の文字列) のため、**確定値ではない**。`other` 14 件と `no_ret` 1 件は未確認。
- 別手順 (ret 直前 3 行を見る一時スクリプト) では xmm0 19 件・other 12 件・ret 無し 8 件となり、スクリプトと件数が一致しない。
  差の原因 (ret 行の取り方・dsm の関数境界) は未切り分け。rax_rdx は両方式で 0 件。件数は確定値ではない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `other` 14 件・`no_ret` 1 件の戻り経路の目視確定 | 受入条件「rdx 比較」の対象が確定しない | #1193 (本 issue・次 run) |
| i128 戻り型の IR 誤型付けの有無 (xmm0 24 件) | 署名型の修正が要る可能性 | #976 の残件 (PM 判断) |
| rdx 取得・`cmp_ret` 拡張・e2e (`--m11-only`) の実測 | 未着手 (前提 §1 が未確定) | #1193 (本 issue・次 run) |
