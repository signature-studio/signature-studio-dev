# liftdiff LD-38 (#1193) — ret=i128 39 関数の戻り経路の確認 (部分達成)

> 親 #976 (LD-24) の子。分割の正本は [`REPORT_LD24.md`](REPORT_LD24.md) §3。
> 既知類型との関係: 該当なし (lift の silent miscompile ではなく、case 生成と署名型の問題)。
> 後続: 本節の『推定』は [`REPORT_LD158.md`](REPORT_LD158.md) (LD-158 / #3470) で動的実測に置き換えた (xmm0 戻り 8 関数の署名修正を含む)。

## 1. 結論

- **i128 戻り関数の戻り経路は rax:rdx ではない可能性が高い** (推定)。機械語 (RetDec dsm) で rdx を戻り値として
  使う判定は、窓幅 3 でも窓幅 8 以上でも 0 件。xmm0 が `ret` 直前に出る関数は、窓幅 3 で 24 件、窓幅 8 以上で 38 件
  (§3b)。前回の `other` 14 件は窓幅 3 の取りこぼしで、xmm0 の戻り (double) と読むのが妥当 (推定)。
  IR の `i128` 型付けが実際の戻り値と合わない可能性がある (推定。未確定)。
- したがって受入条件「rdx を取得して `cmp_ret` で比較」は、この 39 関数に対しては**前提が未確定**。
  実装の前に戻り経路の確定が要る (下記 §4)。**コード変更は本 run では行わなかった**。

## 2. 署名内訳の照合 (実測・LD-24 の未検証表を確定)

`tools/liftdiff/results/m11_closure_verdicts.tsv` の `unexec_reason == unsupported_sig` は **50 行**、
すべて `work/m11_ldfix/sigs.json` に存在 (欠落 0)。ret=`i128` は **39 行**。

再現コマンド (`tools/liftdiff/` で実行。IR は `tools/m11/work/boot_final3.ll`、無ければ `bash tools/m11/m11_e2e.sh --full` で生成):

```
cd tools/liftdiff && python3 tests/ld24_sig_breakdown.py > work/ld24_sig_breakdown.md
```

実測出力 (rc 0・入力 50 件 / IR で解決 50 件 / 未解決 0 件):

| 署名形 (ret / params) | 関数数 | 振り分け |
|---|---|---|
| ret=`i128`, params=`i64` | 21 | #1193 |
| ret=`i128`, params=`なし` | 8 | #1193 |
| ret=`i64`, params=`i128` | 8 | #1194 |
| ret=`i128`, params=`i64,i64` | 7 | #1193 |
| ret=`i128`, params=`i128` | 1 | #1193 |
| ret=`i128`, params=`i64,i64,i64` | 1 | #1193 |
| ret=`i128`, params=`ptr,i64,i64` | 1 | #1193 |
| ret=`i64`, params=`i64,i128,i64` | 1 | #1194 |
| ret=`i64`, params=`i64,i64,i128` | 1 | #1194 |
| ret=`ptr`, params=`%tagPOINT` | 1 | #1194 |

集計: #1193 = 39 / #1194 = 11 / その他 = 0。

- 分母・除外: 分母は closure の判定 TSV 全行 (50 行)。除外なし。

## 3. 機械語の戻り経路 (実測)

`tests/ld38_ret_convention.py` が `tools/m11/work/*.dsm` の逆アセンブルを読み、各関数の `ret` 直前 3 行を判定。
再現コマンド (`tools/liftdiff/` で実行): `python3 tests/ld38_ret_convention.py > work/ld38_ret_convention.txt`
(実測 rc 0・`SUMMARY {'other': 14, 'xmm0': 24, 'no_ret': 1} total 39`)。

| 判定 | 関数数 | 判定規則 (ret 直前 3 行に出現する文字列による推定) |
|---|---|---|
| xmm0 | 24 | xmm0 が出現。戻り値が浮動小数の推定 (IR の i128 型付けが誤りの推定) |
| other | 14 | xmm0 も rdx も出現しない。rax のみ・sret 等の可能性。目視確認が要る |
| no_ret | 1 | dsm 内に ret が無い |
| rax_rdx | 0 | rdx が出現。rax:rdx で返す可能性 (判定規則上 0 件) |

- ヒューリスティック (ret 直前 3 行の文字列) のため、**確定値ではない**。`no_ret` 1 件は未確認。

### 3b. 窓幅感度 (実測・本 run)

`--window N` (既定 3) で ret 直前 N 行を見る。`cd tools/liftdiff && python3 tests/ld38_ret_convention.py --window N`

| 窓幅 | xmm0 | other | no_ret | rax_rdx | rc |
|---|---|---|---|---|---|
| 3 (既定) | 24 | 14 | 1 | 0 | 0 |
| 8 | 38 | 0 | 1 | 0 | 0 |
| 16 | 38 | 0 | 1 | 0 | 0 |

- 窓 3 で `other` だった 14 件は、窓 8 以上で全て `xmm0` に入る。例: `function_12657b0` (boot3.drc.dsm L1007869-1007874) は
  `movq qword ptr [rbp+0x30], xmm0` の後に `movq xmm0, qword ptr [rbp+0x30]` で戻り、`ret` の 5 行前に xmm0 がある。
- 窓幅を広げても `rax_rdx` は 0 件。「i128 を rax:rdx で返す関数」は本 39 件に 1 件も見つからなかった。
- 判定器のネガティブコントロール (`--control`) は 3/3 OK のまま。
- 注意: 窓が広いほど別の呼出し後の xmm0 を拾う可能性がある。本表は方向の確認であり、関数ごとの ABI 確定ではない。
  確定には呼出し元の戻り値利用を見る必要がある (未実施)。
- 判定器の検証 (ネガティブコントロール): `python3 tests/ld38_ret_convention.py --control` (実測 rc 0)。
  - `real xmm0 body` (実在 `function_cc32f0` の本体 3 行) → `xmm0` (期待どおり)
  - `xmm0 removed from real body` (同じ本体の xmm0 を rax に置換) → `other` (判定が変わる)
  - `ret line deleted` (同じ本体から ret 行を削除) → `no_ret` (判定が変わる)
  - 出力は `work/ld38_control.txt` (実測 3/3 OK)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 方式間の差 (別手順の一時スクリプトとの件数差) は未切り分け。本 REPORT の件数は本スクリプトの結果のみ | 件数の信頼性 | #1193 (本 issue・次 run) |
| `other` 14 件・`no_ret` 1 件の戻り経路の目視確定 | 受入条件「rdx 比較」の対象が確定しない | #1193 (本 issue・次 run) |
| i128 戻り型の IR 誤型付けの有無 (xmm0 24 件・推定) | 署名型の修正が要る可能性 | #976 の残件 (PM 判断) |
| rdx 取得・`cmp_ret` 拡張・e2e (`--m11-only`) の実測 | 未着手 (前提 §1 が未確定) | #1193 (本 issue・次 run) |
