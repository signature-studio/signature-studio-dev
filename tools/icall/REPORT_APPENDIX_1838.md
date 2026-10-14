# icall #1838 (ICALL-41): CHAININFO 断片による Fresh Air 関数範囲の伸長

REPORT §15 から参照。修正の本体は `tools/icall/prep_targets.py` の `chain_parents` / `chain_end` (`chained=True` の時だけ適用)。

## 1. 原因 (issue #1838 の調査結果)

`1803de190` は PE の `.pdata` で 3 断片に分かれる (`190-1b7` 親、`1b7-20d`・`20d-260` は CHAININFO の hot/cold 断片で親を参照)。
`fa_ranges.txt` は先頭の RUNTIME_FUNCTION (`190-1b7`) だけを RetDec に渡していたため、`je` の飛び先と call が範囲外になり、IR は分岐・call 0 の未初期化戻り値になった。

## 2. 修正の条件 (#1884 差し戻しへの対応)

- 断片の UNWIND_INFO 末尾の親 RUNTIME_FUNCTION (`chain_parents`) が `va` 本人の断片だけを辿る。親が別関数なら伸ばさない。
- 伸ばした範囲に、親の断片以外の関数開始 VA (`img.bounds`) が入る場合は伸ばさない。
- 境界条件は `tools/icall/tests/test_chain_end.py` (PE 不要・4 件) で固定。

## 3. 実測の状態

| 項目 | 状態 |
|---|---|
| `test_chain_end.py` (合成データ・境界 4 条件) | PASS 4/4 (本 HEAD で実行) |
| `chain_ranges_diff.py` (実 PE で伸長件数・他 VA 跨ぎの有無) | **未実行**。Fresh Air の `SlateCore.core_64` と `clo_freshair_all.json` が本 run の素材 (`fl-win64`) に無い |
| 伸長 12 件の一覧 (`1803b5500` `1803de190` `18040c950` `180829930` `180829c20` `180c97f20` `180c98240` `180c99430` `180ca1480` `180da4030` `180da5f20` `180da6720`) | 前回 `3cdf8cf3` の測定。今回の親同一性チェック後の再確認は**未実施** |
| `chained=False` で `1803de190` が br 0・call 0 のまま | 前回 `3cdf8cf3` の旧ロジックでの値。今回の `chained=False` 経路は変更していない (`chain_end` は `chained=True` の時だけ呼ばれる) ため、同じ結果が期待されるが、実測は未実施 |
| roundtrip (`work/rt_fa1838`、前回 `3cdf8cf3`) | 前回の値 (`1803de190` br 0→8 call 4→8 等)。今回の修正後は未実施 |
| `call_lost` (audit) | 6 → 6 (前回値) |
| sweep (`fa_sweep.sh 8 60`) | 未実施 (子 #1886) |

## 4. 再現手順 (素材 `work-icall` + `plugins-freshair` が必要)

```sh
python3 tools/icall/tests/test_chain_end.py                                  # PE 不要
python3 tools/icall/chain_ranges_diff.py "<SlateCore.core_64>" "<clo_freshair_all.json>"
```

`chain_ranges_diff.py` は範囲の差分 (`chained=False` と `True`)・伸長件数・伸長後の範囲に他関数の開始 VA が入るかを出す。`leak` が 1 件でもあれば FAIL。
