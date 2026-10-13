# Fresh Air REPORT §11 (FA-5) 付録: 最大値の基準と `.rdata` 分類の詳細

- 本体: [REPORT.md](REPORT.md) §11 (#52)。本書は 250 行上限のため、§11 の詳細を無変更で分割移動した (内容は削除していない)。
- 再現: `bash tools/targets/freshair/ks_identity.sh [outdir]` (`ks_rdata_class.py` は §A2 参照)。

## §A1. 最大値の基準 (REPORT §11-1 の補足)

- REPORT §11-1 の「最大 Compressor 0.436・Gain 0.475」は、process 候補 37 件のうち **TapeStop (M 1.000・9 B の stub) と HostProxy (M 0.750・41 B)** を除いた中での最大。両者は実体の小さい関数で、類似度が高くても process 比較の代表にならないため除外した。
- 全 37 件の最大は TapeStop 1.000 → HostProxy 0.750 → Gain 0.475 の順 (`ident.json` の `process_pair.ratio_M`)。

## §A2. `.rdata` 不一致 20 関数の分類 (REPORT §11-3 の詳細)

`ks_closure_share.py` の `differ_vas` (20 関数) について、rip 相対で参照する `.rdata` 先頭 16 B の参照列を SC/KH で対にして分類した (再現: `ks_rdata_class.py <KH> <SC> <share.json> <out.json>`)。

| 分類 | 件数 | 判定の定義 |
|---|---|---|
| `value` | 17 | 参照数は同じで、内容の違う参照のうち **image 範囲の絶対アドレスを含まない** もの |
| `ptr` | 3 | 内容の違う参照に image 範囲 (`base`〜`img_hi`) 内の 8 B 値を含むもの |
| `count` / `order` | 0 / 0 | — |

- **未確定**: `value` 17 件は「定数値の差」とは断定できない。差分語 (計 70 語、`value` 側も含む) を抽出すると、ASCII 文字列 (`0x7420726f74636576` = "vector t" 等 = 文字列リテラルの断片) や、上位 32 bit が 0 の値 (例 `0x3b3f5000000000`・`0xf880d000000000`) が混じる。`value` の 17 件は「文字列リテラル (型名・メッセージ) の断片」か「定数テーブルの別要素」の可能性がある。どちらかの切り分けは未実施。
- 注: `ptr` 判定 (`has_abs_ptr`) は 8 B 整列の値だけを見るため、差分が 4 B 境界にずれた場合は取りこぼす。分類は下限。
- `ptr` 3 件 (`0x180cb5ef0`・`0x18100ca5c`・`0x181066558`) は、参照先が配置差に依存する絶対アドレスを含むため、定数差ではなく配置差由来と読むのが妥当 (これも未検証)。
- したがって「定数が違う関数がある」は事実だが、「意味が違う」の根拠にはならない。意味同一性は REPORT §11-2 ① の差分実行で判定する (未実施)。
- 起票先: ① の意味同一性と `value` 17 件の中身 → #52 (本 issue の残件)。

## §A3. Gain の意味同一性 (native ⇄ native 差分, REPORT §11-2 ① の実施)

- 再現: `bash tools/targets/freshair/ks_semantic_gain.sh 200 7` (`SC_CORE`/`KH_CORE` で素材パスを指定可)。ハーネス: `ks_semantic_gain.c` (両側とも実機機械語を ImageBase に敷設し ms_abi で直接実行)、比較: `ks_semantic_gain_cmp.py`。
- 入力: 同一の乱数列 (seed 7) から 200 case を生成。`n` は 0〜128、`mode` 0/1、`first` 0/1、`dl`/`dr` 0/1、`v`/`q28`/`a`/`b`/`cur` は通常値と特殊値 (0・非正規数・±4) の混合。
- 比較対象: L 出力・R 出力・self state (0x38 B)。通知件数 (vector push 数) は SC が `end-begin` のバイト数、KH が要素数のため `/4` で揃えて比較。
- 結果 (コミット済み HEAD で再現、EXIT=0、0.16 s、load 0.00→0.10):
  - 同一 L/R/state: **126 / 200**。通知件数の不一致: **0 / 200**。
  - L 不一致 74 / R 不一致 74 / state 不一致 48。
  - 不一致は全て `first=0` (ramp 継続経路) に出る。`first=1` の 101 件は全て一致 (実測)。
  - state の不一致位置は 3 箇所 (0x38 B 基準の 16・36・52 B = `cur` (0x74 ⇄ SC 0xac)・meter L (0x88 ⇄ 0xc0)・meter R (0x98 ⇄ 0xd4))。
  - 差は 1 ulp 程度 (例 case 6 の L[1]: SC 1.5502195358 / KH 1.5502196550)。
- 係数の確認 (計算): ramp の傾き `1/n` は両側で一致 (`divss` 1.0 / (float)n = KH 0x1813a9da0 の 1.0f と同値)。
- 切り分け (実測): `pos` (KH 0x64 / SC 0x9c) を 0 に固定しても結果は不変 (126/200 のまま)。`pos` は原因ではない。
- **未特定**: `first=0` の ramp 継続で `cur` の更新式が両側で同じ丸め順か。逆アセンブルでは KH は `addss`→`mulss`→`subss`→`mulss`→`addss` の順、SC は `addss` (cnt+1) → `mulss` (t=cnt*coef) → `subss`/`mulss`/`addss` の順で、式の形は対応するが、丸めの順 (`(1-t)*a + t*b` の a/b 参照) は未照合。
- 判定: **意味同一ではない (bit 一致しない) ことを実測で確定。ただし差は 1 ulp 級で、ramp 式の丸め順の違いか、ハーネスの入力差 (SC の `cnt` 初期化) かは未切り分け。** 未切り分けのため、「意味が違う」とは結論しない。
- 起票先: 差の原因の切り分け (ramp 継続経路の丸め順・SC `cnt` の意味) → #52 (本 issue の残件)。
