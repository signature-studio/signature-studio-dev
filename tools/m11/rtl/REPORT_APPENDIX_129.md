[付録] `REPORT.md` §7-4 の分割移動先 (#129)。本体の結論 1 行は `REPORT.md` §7-4 を参照。

### 7-4. レビュー指摘対応 (`ff28834`) の検証 (batch は再実行していない)

採点値を変える変更ではないため batch (m11 / flelift) は再実行せず、後処理だけをコミット済み `ff28834` で検証した
(初回 batch の jsonl は commit されていないので、`results/rtl_verdicts.tsv` の `va` + 各 route の verdict から `function.va` / `verdict` だけの jsonl を復元して入力にした。
`rtl_compare.py` が読むのはこの 2 項目だけ)。GitHub Actions runner, 所要は `time`、load は終了時の 1 分平均 0.47:

| 検証 | 結果 |
|---|---|
| `rtl_range.py` (`B = pe.OPTIONAL_HEADER.ImageBase`; この PE は `0x400000`), 0.13 秒 | 2,958 クラス / 527 unit。`results/rtl_units.json` と `cmp` 一致、stdout も修正前と一致 (PASS) |
| `rtl_compare.py` を復元 jsonl (1,172 VA) で再生成, 0.03 秒 | `results/rtl_verdicts.tsv` は `cmp` 一致 (PASS)。`results/rtl_compare.md` は先頭 1 行 (`自動生成: <cmd>`) の追加のみで、本体は修正前と一致。再実行しても `cmp` 一致 |
| 帯フィルタ: 帯外を含む実 batch (snapshot の `batch_closure.jsonl` 7,421 関数 × 2 route) | 修正前は 7,421 関数をそのまま採点 (計 m11 2273/2892/2256・x64c 4182/741/2498)。修正後は帯外 6,249 を除外して 1,172 関数 (この snapshot の run での計 m11 574/427/171・x64c 540/116/516。§2 の表とは別 run の値で、比較には使わない) |
| 帯フィルタのネガコン: 復元 jsonl に `0x400fff` / `0x456e97` / `0x456e98` / `0x545a90` / `0x1000000` を追加 | 両 route 採点あり 1,177 → 1,173 (帯内は `0x456e97` のみ。上端 `0x456e98` は排他)。TSV の差分は `0x456e97` の 1 行だけ |
| `negctl.sh` (復元 jsonl): `_UStrAsg 0x4133f0` の x64c を mismatch に書換え | x64c 535/125/512 → 534/126/512、TSV 差分 1 行 (PASS) |

VA/RVA 変換の ImageBase 化は、`ImageBase` が `0x400000` の PE では出力が変わらないことの確認までで、別 ImageBase の PE での動作は確認していない (該当 PE が無い)。
