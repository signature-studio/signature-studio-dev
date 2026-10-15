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

## §A4・§A5. `value` 17 件の内訳・語単位切り分け

- 本文 (`ks_rdata_detail.py`・`ks_rdata_value.py`、#52 残件) は [REPORT_APPENDIX_FA5_VALUE.md](REPORT_APPENDIX_FA5_VALUE.md) §A4・§A5 へ分割移動 (250 行上限のため、無変更)。

## §A3. Gain の意味同一性 (native ⇄ native 差分, REPORT §11-2 ① の実施)

- 再現: `bash tools/targets/freshair/ks_semantic_gain.sh 200 7` (`SC_CORE`/`KH_CORE` で素材パスを指定可)。ハーネス: `ks_semantic_gain.c` (両側とも実機機械語を ImageBase に敷設し ms_abi で直接実行)、比較: `ks_semantic_gain_cmp.py`、ulp 分布: `ks_semantic_gain_ulp.py <sc.txt> <kh.txt>`。丸め形の単体テスト: `ks_ramp_form.c` (`cc -O1 -ffp-contract=off`)。
- 入力: 同一の乱数列 (seed 7) から 200 case を生成。`n` は 0〜128、`mode` 0/1、`first` 0/1、`dl`/`dr` 0/1、`v`/`q28`/`a`/`b`/`cur` は通常値と特殊値 (0・非正規数・±4) の混合。
- 比較対象: L 出力・R 出力・self state (0x38 B)。通知件数 (vector push 数) は SC が `end-begin` のバイト数、KH が要素数のため `/4` で揃えて比較。
- 結果 (コミット `da2398e0` で再現、EXIT=0、0.171 s real、load 0.25→0.25、nproc=4。`cmp.json` の実出力):
  `{"cases": 200, "bit_exact_LRS": 127, "mismatch_L": 73, "mismatch_R": 73, "mismatch_S": 48, "notify_count_mismatch": 0}`
  - 同一 L/R/state: **127 / 200**。通知件数の不一致: **0 / 200**。
  - L 不一致 73 / R 不一致 73 / state 不一致 48。
  - 不一致は全て `first=0` (ramp 継続経路) に出る。`first=1` の 101 件は全て一致。`first=0` は 26 件一致・73 件不一致 (実測、`first` 別の集計)。
  - 旧版 (126/200, L/R 74) は解析バグによる誤り。`n=0` の case (C109) は L/R が空で、通知件数が L 欄にずれて読まれていた。C 側で L/R を `-` で出し、比較側は 11 トークン固定 + assert で読むよう修正した (`da2398e0`)。
  - state の不一致位置は 3 箇所 (0x38 B 基準の 16・36・52 B = `cur` (0x74 ⇄ SC 0xac)・meter L (0x88 ⇄ 0xc0)・meter R (0x98 ⇄ 0xd4))。
  - 差の大きさ (ulp 距離、`ks_semantic_gain_ulp.py`、コミット時点の実測): 不一致 73 件の case 内最大 ulp 距離は、1 が 9 件・2 が 28 件・3 が 5 件・4 が 3 件・5 が 2 件・6 が 2 件・7 が 2 件・8 が 3 件・10 以上が 19 件。符号反転は 0 件。**「1 ulp 程度」とは言えない** (前版の記述を訂正)。例: case 6 の L[1] は SC 1.5502195358 / KH 1.5502196550 (1 ulp 級)。
- 係数の確認 (計算): ramp の傾き `1/n` は両側で一致 (`divss` 1.0 / (float)n = KH 0x1813a9da0 の 1.0f と同値)。
- 切り分け (実測, `da2398e0`): `pos` (KH 0x64 / SC 0x9c) を 0 に固定 (`POS0=1`) しても `bit_exact_LRS` は 127 のまま (L/R 不一致 73・state 不一致 48 も不変)。`pos` は原因ではない。
- **未特定**: `first=0` の ramp 継続で `cur` の更新式が両側で同じ丸め順か。逆アセンブルでは KH は `addss`→`mulss`→`subss`→`mulss`→`addss` の順、SC は `addss` (cnt+1) → `mulss` (t=cnt*coef) → `subss`/`mulss`/`addss` の順で、式の形は対応するが、丸めの順 (`(1-t)*a + t*b` の a/b 参照) は未照合。
- **丸め形の単体テスト** (`ks_ramp_form.c`、`cc -O1 -ffp-contract=off`、1.09 s real。出力 `{"samples": 64516694, "differ": 18434252}`): KH の `cur = a + (b-a)*t` と SC の `cur = (1-t)*a + t*b` は数学的に等価だが、float32 では **18,434,252 / 64,516,694 サンプル (28.6%) で 1 ulp ずれる** (実測)。ramp の丸め形の違いだけで bit 不一致が出ることを確認した。
- 追加の切り分け (実測): 不一致 case の ulp 分布は広く、10 ulp 以上が 19 件ある。ramp 丸め形の単体差 (28.6%) だけでは、実機の 73 件の差を説明できない。`ramp` の丸めは一因だが主因とは断定できない。
- 判定: **意味同一ではない (bit 一致しない) ことを実測で確定。** 差の原因は未特定。ramp 式が説明するのは一部だけと見られ、SC 側の `cnt` / meter 経路の未照合が残る。
- 起票先: 残りの切り分け (SC の `cnt`・meter 経路の照合) → #52 (本 issue の残件)。

### §A3-2. FA-18 の切り分け (#1264, 実測)

- 結果数値は §A3 の同一実行 (`a3af6a7a`、`ks_semantic_gain.sh 200 7`) を参照。本節の数値は §A3 の内訳に対する追加集計のみ。
- state 0x38 B の不一致フィールド (73 件中): `m1` 28 件・`m2` 35 件・`cur` 18 件 (`pos`・`inc`・`a`・`b`・`c1`・`c2` は 0 件)。
- **`cur` の差 (18 件) は丸め形で説明できる**: case 11 (n=1・mode=0・first=0) は `a=1.5263482332229614`・`b=0.09984630346298218` で、KH の `a+(b-a)*t` (t=1) は 0.0998462438583374 で、SC の `(1-t)*a+t*b` の 0.09984630346298218 より **8 ulp 下** (float32 単体の実測)。
- **meter (`m1`・`m2`) の差は `cur` と独立に出る**: `cur` が一致する case でも 30 件で meter がずれる (`m1` 18・`m2` 21 件)。ulp 分布は 1:23・2:13・4:1・10+:2。case 3 は `cur` も L/R 末尾も一致し、`m1` 8.336935043334961 (SC) / 8.336935997009277 (KH) のみ違う。
- したがって**主因は meter 経路 (`m1`/`m2` の更新式)** と読めるが、meter の更新式の逆アセンブル照合は本 run で未実施。
- 判定: 受入条件 1 (主因特定) は**部分達成** (`cur` 丸め形は確定、meter は未特定)。受入条件 2 (200/200 bit 一致) は**未達**。受入条件 3 (Gain 以外への拡大判定) は**未決定**。
- 起票先: meter 経路の逆アセンブル照合と主因の確定 → #1467 [FA-20]。bit 一致化と Gain 以外への拡大判定 → #1264 の残件 (#52 配下)。

### §A3-3. meter (m1・m2) 更新式の照合 (#1467 FA-20, 実測)

- 測定 commit: `87fd84b7` (コードを変えた最後の commit は `e532b06a`。`git diff e532b06a 87fd84b7 -- tools/targets/freshair/*.c tools/targets/freshair/*.py tools/targets/freshair/*.sh` は 0 行)。`37c8193d` の時点では漸化式を計算しておらず、実機の数値は持たない。`e532b06a` でハーネスに SC/KH 両側の `M<i>` 行 (実行前 m1/c1/m2/c2、`METER_DUMP=1`) を追加し、`ks_meter_replay.py` に再計算を実装した (stdout は不変)。
- 再現: `cc -O1 -ffp-contract=off -o h tools/targets/freshair/ks_semantic_gain.c -lm` → `METER_DUMP=1 ./h sc <SlateCore> 200 7 > sc.txt 2> sc_m.txt`・`METER_DUMP=1 ./h kh <HeartCore> 200 7 > kh.txt 2> kh_m.txt` → `python3 ks_meter_replay.py sc.txt kh.txt sc_m.txt kh_m.txt`。逆アセンブルは capstone 5.0.7 (SC 0x180afe090・KH 0x1804b0380 の先頭 900 命令)。
- 素材: `work-liftlib-targets` (`tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64`・`tools/targets/kilohearts/work/winpkg/HeartCore.core_64`)。`fl-win64` には含まれない (`tar --zstd -tf` で確認)。
- 実測 (測定 commit `87fd84b7`、素材 `work-liftlib-targets`、`cc -O1 -ffp-contract=off -Wall` 警告 0、実行直前の load 0.37〜0.43): `./h sc` 0.019 s real・`./h kh` 0.024 s real。
  - `ks_meter_replay.py` = `{"cases_n_gt0": 199, "m1_mismatch": 28, "m2_mismatch": 35, "cur_equal": 181, "meter_mismatch_with_cur_equal": 30, "m1_mismatch_with_L_identical": 0, "m2_mismatch_with_R_identical": 0, "L_identical": 126, "R_identical": 126, "recalc_SC": {"n": 199, "ok": 199, "bad_cases": []}, "recalc_KH": {"n": 199, "ok": 199, "bad_cases": []}}`
  - `ks_semantic_gain_cmp.py` = `{"cases": 200, "bit_exact_LRS": 127, "mismatch_L": 73, "mismatch_R": 73, "mismatch_S": 48, "notify_count_mismatch": 0}` (§A3 と一致)。
  - `cases_n_gt0: 199` は case C109 (`n=0`) の 1 件が対象外のため (`recalc_SC` / `recalc_KH` の `n` も 199)。
- meter 更新式 (両側同形): ループ内で `m = (s*s - m)*c + m` (`mulss` → `subss` → `mulss` → `addss`)。対応 (SC = KH + 0x38): m1 `0x88`⇄`0xc0`・c1 `0x84`⇄`0xbc`、m2 `0x98`⇄`0xd0`・c2 `0x94`⇄`0xcc`。SC `0x180afe1b4`〜`0x180afe1e2`、KH `0x1804b04a1`〜`0x1804b04f2`。
- 初期値 (m1・m2・c1・c2) は 200/200 一致。
- 出力 L/R から同じ式を float32 で再計算して自側の state (m1 `0x88`・m2 `0x98`) と比べる (`ks_meter_replay.py` の `recalc_SC` / `recalc_KH`): **SC 199/199・KH 199/199 で一致** (上記の実測)。式は両側で実行後 state を再現する。
- 合成データでの動作確認 (実機ではない): 既知の m から式で作った state を入れると一致 1/1、1 ケースに 1e-6 のずれを入れると不一致 1/1 と判定される (`replay` の判定が機能することのみを確認)。
- meter 不一致 (state 比較): m1 28 件・m2 35 件。`ks_meter_replay.py` の内訳: `m1_mismatch_with_L_identical` 0・`m2_mismatch_with_R_identical` 0。つまり meter 不一致は全て対応する出力チャネル (L/R) の不一致と同じ case に出る。
- `cur` 一致かつ meter 不一致 30 件 (§A3-2 の 30 件と同じ) は、全て L/R 出力の差からの伝播として説明できる。
- L 差の内訳: `cur` 不一致 18 件・`cur` 一致 55 件 (`cur` が一致するのに L が違う case がある)。
- 例 case 3: 出力 L の index 2 のみが 1 ulp ずれ (SC -0.4080760180950165 / KH -0.4080759882926941)、以降の差は同じ起点から伝播。
- **判定 (受入条件 1 は未達)**: meter 更新式は SC/KH で同一で、実機で再計算が 199/199 一致した。ずれる式は **meter 更新式には見つからなかった**。meter 差は L/R 差の伝播で、式そのものの差ではない。
- 未確定: L 差の起点。`cur` の逐次値 (ramp の丸め順) の bit 単位照合が未了。harness は逐次 `cur` を出力しないため、そのままでは確定できない。起票先 → #1617 [FA-23] (ramp 逐次値のダンプと照合)。
- 受入条件 3 (本節の追記) は満たす。受入条件 2 (単体再現で 30 件を説明) は「meter 式は同一・30 件は L/R 伝播」まで。L 差の起点の説明は未了 (#1617)。

### §A3-4. ramp の逐次 cur 照合と L 差の起点 (#1617 FA-23, 実測)

- 再現: `bash tools/targets/freshair/ks_cur_trace.sh 200 7` (1 コマンド。既定実行・probe 実行・照合・集計を行う。素材は `work-liftlib-targets`)。
- 方法: `ks_semantic_gain.c` に `CUR_PROBE=1` を足した。入力 L を全サンプル 1.0 にすると L 出力が逐次 cur そのもの (`1.0 * cur` は厳密)。既定実行 (`CUR_PROBE` 無し) の stdout は変更前と **byte 一致** (SC/KH とも `cmp` で確認)。probe の stderr に入力 L (`I<idx>`) と、ramp の係数・端点 (SC `coef`/`A`/`B`、KH `inc`/`a`/`b`) を出す。
- 検算: probe の cur に入力 L を掛けた値が既定 L と **全 case で bit 一致** (SC/KH とも。違えば照合を止める)。
- 式 (機械語から読んだ形。`ks_cur_trace.py` の docstring): KH `cur = a + (b-a)*t` (`t = pos*inc`)、SC `cur = (1-t)*a + t*b` (`t = pos*coef`)。`pos` は両側で case 開始時 0。float32 で各演算を丸める。
- 実測 (測定 commit: `53c6cfe9`。`git diff 53c6cfe9 HEAD -- tools/targets/freshair/` は 0 行。`ks_cur_trace.sh 200 7` を 3 回実行: 0.54 / 0.56 / 0.55 s real、load 0.04〜0.08、nproc=4。既定 stdout は `CUR_PROBE` 無しで変更前の sc/kh と byte 一致):

| 群 | L 同一・cur 同一 | L 差・cur 差 | L 差・cur 同一 |
|---|---|---|---|
| `first=0` (98 件) | 25 | **73** | **0** |
| `first=1` (101 件) | 101 | 0 | 0 |

  - 逐次 cur が一致しない case は 73 件、その全てで L も一致しない (逆向きの不一致は 0 件)。`first=0` 98 件の中で cur と L が 1:1 に対応する。
  - L 差が最初に出るサンプル番号 (0 始まり): 0 が 15 件・1 が 10 件・2 が 15 件・3 が 6 件・4 が 2 件・5 が 8 件・6 が 6 件・7 が 3 件・8 が 3 件・9 以上が 5 件。**全 73 件が `first=0` の ramp 途中で最初に出る** (最終 cur ではなく逐次の差)。
  - 旧集計との関係: 最終 cur (state の 0x74) で数えると一致 181 件・うち L 差 55 件 (再現済み: 73 件の L 差のうち 18 件が最終 cur 差)。これは **逐次 cur を見ていない集計**で、「cur が一致するのに L が違う 55 件」という §A3-3 の記述は、この集計の誤読だった。L 差 73 件は全て逐次 cur の差で説明できる。**§A3-3 の「L 差 55 件 (cur 一致)」の記述は本節で訂正する。**
  - 検算 (ネガティブコントロール): SC 側の cur を 1 ulp 下げると KH 形と一致する (case 3 の sample 2: SC `3f9fcb2a` → 下げると KH `3f9fcb29` と一致。`True`)。未変更の SC 形は KH と全サンプルで不一致 (`False`)。判定は感度を持つ。
- **反実仮想 (主結果)**: SC の入力 (`coef`・`A`・`B`) は KH の `inc`・`a`・`b` と bit 一致している (`coef_inc_bits` 等、73 件全件)。この入力に **KH の丸め形 `a + (b-a)*t` を当てると、first=0 の 98 件全てで probe の cur と既定 L が一致** する (`KH form == KH probe cur` 98/98、`KH form → L == KH 既定 L` 98/98)。つまり L 差の起点は **ramp の丸め形 (`(1-t)*a + t*b` と `a + (b-a)*t`) の違いだけ** で説明できる。
- 同じ入力に SC 形を当てた場合と KH 形を当てた場合の一致は first=0 の 25 件だけ。残り 73 件が丸め形の違いで 1 ulp 以上ずれる (L 差 73 件と一致)。
- `ks_ramp_form.c` (単体、§A3) の 28.6% (丸め形だけの差の出現率) と整合する。本節は、その丸め形の差が **実機の L 差 73 件の全ての起点** になることを、case ごとに確かめたもの。
- 判定 (受入条件 1・2・3 の達成): 受入条件 1 (harness の逐次 cur 出力): **達成** (`CUR_PROBE=1`、既定 stdout は不変)。受入条件 2 (L が最初に違うサンプルで丸め順を照合し、ずれる式を特定): **達成** (ramp の cur 式。SC `(1-t)*a+t*b` が KH `a+(b-a)*t` と異なる)。受入条件 3 (特定した式の単体再現と件数): **達成** (反実仮想 98/98・単体形 25/98 一致、73 件が丸め形由来)。
- 限界: (a) 「丸め形が差の原因」は **機械語の式形の照合と bit 一致する入力での反実仮想** による。ソースは持たないため、SC 側の式が元の数式で何を意図したかは未確認。(b) 逆アセンブルの式形読みは capstone 5.0.7 による (SC `0x180afe160`〜`0x180afe1ea`、KH `0x1804b0460`〜`0x1804b04e6`)。(c) L 差 73 件の全てが `first=0`・ramp 途中の差で、meter 経路 (§A3-3) はこの起点から伝播している。

#### 未解決 (本 issue の範囲外)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| SC の ramp 式 `(1-t)*a+t*b` を、ソースと照らして意図する式かを確認する | 「SC が誤り」と断定はしていない。どちらが正しい式かは未確定 | #1264 (FA-18 の bit 一致化判定) |
| 200/200 bit 一致 (§A3-2 の未達) | Gain の意味同一性の判定 | #1264 |

### §A3-5. 丸め形だけを差し替えたモデルで L・R・state を再現 (#52 ①・#1264 受入 2, 実測)

- 測定 commit: `76862382` (コードを変えた最後の commit。追加: `ks_gain_model.py`、`ks_semantic_gain.c` の `IN_DUMP=1` (stderr のみ。既定 stdout は byte 一致)、`ks_semantic_gain.sh` の 1 行追加)。
- 再現: `SC_CORE`・`KH_CORE` に `work-liftlib-targets` の SlateCore.core_64・HeartCore.core_64 を指定して `bash tools/targets/freshair/ks_semantic_gain.sh 200 7` (1 コマンド。出力 `model.json`)。
- 方法: 実行後 state の ramp 端点 (coef・A・B・cur) は、両側で bit 一致することを確認した上で使う (`nonform_state_fields_sc_vs_kh` 200/200)。harness の入力 `inc`・`a`・`b` は実行中に native 側で再計算されるため、実行前の値は使えない。
  - ramp の丸め形だけを入れ替える。SC 形 `(1-t)*A + t*B`、KH 形 `A + (B-A)*t` (t = pos·coef、pos を 1 ずつ増やす。float32 の各演算を丸める)。first=1 は実行後 cur の一定値。
  - L = in·cur、R = in·cur。m1 は L に c1 を、m2 は R に c2 を順に適用 (`m = (s*s-m)*c+m`)。state は実行後の 0x38 B のうち cur・m1・m2 の 3 箇所だけをモデル値に置き換えて比べる。
- 結果 (測定 commit `76862382`、EXIT=0、0.625 s real、実行前後の uptime で load average 0.05 (1 分値)・0.17 (5 分値)、nproc=4。2 回実行で `sc.txt`・`kh.txt`・`cmp.json`・`ulp.json`・`model.json` の md5 一致):

| モデルの比較 | L・R・m1・m2 一致 (n>0 の 199 件) | 実行後 state を含む LRS 一致 (200 件) |
|---|---|---|
| 検証: SC 形 × SC 入力 → SC native | 199/199 | 200/200 |
| 検証: KH 形 × KH 入力 → KH native | 199/199 | 200/200 |
| **反実仮想: KH 形 × SC 入力 → KH native** | **199/199** | **200/200** |
| 負例: SC 形 × SC 入力 → KH native | 126/199 | 127/200 |

- 入力の一致: 実行前の入力 (L・R・state) は harness が両側に同じ乱数を与えるため構成上 SC/KH 同一 (`input_same_sc_kh_cases` 200/200)。実測として確かめたのは、丸め形以外の実行後 state フィールドが 200/200 で一致すること (`nonform_state_fields_sc_vs_kh`) である。
- 読み: 同じ端点・同じゲイン適用・同じメーター式で、差は ramp 補間の丸め形 (`(1-t)*A + t*B` と `A + (B-A)*t`) だけ。この 1 点を KH 形に換えたモデルは、SC 入力から KH native の L・R・state 全 200 case を再現する。負例は SC 形のままでは 127/200 にとどまり、判定は感度を持つ。
- 限界: (a) SC の機械語そのものは差し替えていない。モデルは Python の再実装で、両側の native を 200/200 で再現することを確かめた上での反実仮想である。機械語の ramp 命令を置き換えた native での確認は未実施。(b) どちらの丸め形が元のソースの意図かは未確定。「SC が誤り」とは言えない。(c) 結論は本入力 (seed 7、200 case) の Gain に限る。他の snapin への拡大は未検証。
- 判定 (#1264 受入 2): モデル上では **達成** (主因 = ramp 丸め形の 1 点で、取り除くと 200/200)。native での確認と受入 3 (Gain 以外への拡大) は未了。

#### 未解決 (本節の範囲外)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 機械語の ramp 命令を KH 形に置き換えた native で 200/200 を確認する | 反実仮想がモデル上の結果にとどまる | #52 (残件) |
| SC の ramp 丸め形がソースの意図か | 「どちらが正しい式か」は未確定 | #52 (残件) |
| Gain 以外の snapin への同じ差分実行の拡大 (#1264 受入 3) | ①の意味同一性は Gain の 1 件のみで判定 | #52 (残件) |

- Gain 以外の判定 (#2739): 判定基準 (§1) と ID 一致 37 組の振り分け (§3) は [REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md)。新規の差分実行は 0 件。Compressor・Filter の差分は #3506・#3507 へ。

### §A3-6. 機械語の ramp を KH 形に置換した native で 200 case を比較 (#2736, 実測)

- 測定 commit: `fbfec952c` (追加: `ks_ramp_kh_patch.py`・`ks_ramp_kh_native.sh`)。`git diff fbfec952c HEAD -- tools/targets/freshair/*.py tools/targets/freshair/*.sh` は 0 行。
- 再現: `SC_CORE=<SlateCore.core_64> KH_CORE=<HeartCore.core_64> bash tools/targets/freshair/ks_ramp_kh_native.sh 200 7` (素材パスは環境変数で必ず指定。未指定は exit 2)。出力は `work/ks_ramp_kh/` (gitignore)。
- 置換の設計 (`ks_ramp_kh_patch.py`、元 SC の逆アセンブル実測):
  - 元の ramp (VA `0x180afe160`〜`0x180afe1a0`、65 B) は `cur = (1-t)*A + t*B` (t = pos*coef)。
  - 置換後 (66 B、10 命令): `pos+1` → `t = pos*inc` → `B-A` → `(B-A)*t` → `+A` → `cur` 保存。KH (`0x1804b0460`〜) の演算順に一致。`(B-A)*t` と `t*(B-A)` は float32 で同値。
  - 1 B 増えるため、直前の nop を 14 B → 13 B に詰めて `0x180afe152`〜`0x180afe1a0` の 79 B を保ち、ループ頭を `0x180afe15f` に寄せる。`0x180afe1a1` の `mov rax,[rdx]` は不変。
  - back-edge `jl` (`0x180afe21b`) の rel32 を `3fffffff` → `3effffff` (`0x180afe15f` へ)。`0x180afe160` への他の分岐は無い (`0x180afe090`〜`0x180afe400` の分岐を走査して確認)。
  - 書き込み前に元バイトを assert (一致しなければ dst を作らず exit 1)。元 SC は変えない。
  - 差分: `cmp -l` で 56 B (領域内 55 B + jl の rel32 の 1 B)。逆アセンブルで置換後の命令列を目視確認 (`0x180afe15f`〜`0x180afe1a1`、末尾 `jl 0x180afe15f`)。
- 結果 (2 回実行で `sc_patched.txt`・`kh.txt`・`cmp_patched.json`・`sc_orig.txt`・`cmp_orig.json` が byte 一致。stderr 0 B):

| 比較 | bit_exact_LRS | mismatch_L | mismatch_R | mismatch_S | notify_count_mismatch |
|---|---|---|---|---|---|
| control: 元 SC × KH | 127 / 200 | 73 | 73 | 48 | 0 |
| patched: 置換 SC × KH | **200 / 200** | **0** | **0** | **0** | 0 |

  - control は §A3 の 127/200 と一致。ulp (`ks_semantic_gain_ulp.py`): control の不一致 73 件は §A3 と同じ分布 (1:9・2:28・3:5・4:3・5:2・6:2・7:2・8:3・10 以上:19、符号反転 0)。patched は不一致 0 件。
  - 実行: 1 回目 1.630 s・2 回目 1.523 s (`date +%s.%N` の差、`cc` と Python を含む)。load (uptime の 1 分値) 0.19→0.19 と 0.16→0.16、nproc=4。
- 判定: 受入 1 (置換 native の作成) **達成** (元 SC から 56 B の差分の複製を作り、逆アセンブルで命令列を確認)。受入 2 (200 case で L・R・実行後 state の一致) **達成** (patched 200/200、control 127/200)。受入 3 (本節の追記) **達成**。
- 置換範囲 (Issue #2736 の受入 1 は `0x180afe160`〜`0x180afe1ea`、本節は `0x180afe160`〜`0x180afe1a0` に縮めた。根拠は元 SC の `objdump -d -M intel` の実測): ramp の計算と保存は `0x180afe160`〜`0x180afe1a0` (65 B) に収まる。`0x160`〜`0x178` が pos の加算と保存、`0x179` が `t = pos*coef`、`0x181`〜`0x198` が `cur = (1-t)*A + t*B`、`0x199`〜`0x1a0` が `movss [rbx+0xac],xmm0` (cur の保存)。`0x180afe1a1`〜`0x180afe1ea` は cur の値を作らず、cur を読む側である: `0x1a1`〜`0x1b3` が L 出力 (`mulss xmm1,xmm0` で in_L·cur を作って保存)、`0x1b4`〜`0x1d7` が meter m1 の更新 (§A3-3 と同式)、`0x1d8`〜`0x1ef` が R 出力 (`0x1e2` の `mulss xmm1,[rbx+0xac]` で cur を state から読む)。`0x1ea` は R の保存命令の先頭。置換で cur の値を決めるのは `0x160`〜`0x1a0` だけで、`0x1a1`〜`0x1ef` は置換前後で 1 B も変わらない (`cmp -l` の差分は `0x180afe156`〜`0x180afe21d` の 56 B に限られ、`0x1a1`〜`0x1ef` の差分は 0 B)。
- 限界: (a) 結論は seed 7・200 case・Gain 1 件に限る。(b) SC の式 `(1-t)*A + t*B` が元ソースの意図かは未確定。「SC が誤り」とは言わない。(c) Gain 以外への拡大は未検証。

#### 未解決 (本節の範囲外)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| SC の ramp 式 `(1-t)*A + t*B` がソースの意図かの確認 | 「どちらが正しい式か」は未確定 | #52 (残件) |
| Gain 以外の snapin への同じ置換・差分実行の拡大 (#1264 受入 3) | ①の判定は Gain 1 件のみ | #52 (残件) |

### §A5-2. value 17 件の位置対応・再配置・指す先の切り分け (#2024, 実測)

- 測定 commit: `2ca41218` (追加した 3 本のスクリプトを含む commit。`git diff 2ca41218 HEAD -- tools/targets/freshair` は 0 行)。
- 再現: `ks_identity.sh` → `ks_rdata_class.py` → `ks_rdata_value.py` (§A5 と同じ入力)。追加で `ks_rdata_value_pos.py` (位置対応)・`ks_rdata_reloc_check.py` (DIR64 再配置)・`ks_rdata_rva_target.py` (RVA 候補の指す先)。素材は `plugins-kilohearts` (Windows installer の `windows.zip` から `HeartCore.core_64`) と `plugins-freshair` (`fetch.sh` で `SlateCore.core_64`)。
- 入力の再現: `ks_rdata_value.py` は §A5 と同一の `{"abs_vs_const": 8, "dbl": 13, "fn_value_differs": 17, "int": 23, "rva_off_absent": 72, "text": 23}` を再現した (EXIT=0、0.77 s real)。
- 位置対応 (`ks_rdata_value_pos.py`、value 17 関数の 32 B × 対。8 B 語 736 組): `same` 597・`rva_pair` 72・`dbl_pair` 14・`other` 29・`text` 24。
  - `dbl_pair` 14 組は全て同符号で、ulp 差が **16 以上** (丸め差ではない)。関数別は `0x181040d20` 2・`0x181049d40` 4・`0x18104a270` 8。一致は 0 件。
  - `rva_pair` 72 組の RVA delta (`sc_off - kh_off`) は 27 種類に散る。最頻は `-0x133640e` の 18 件で、単一の配置ずれでは説明できない。
- 再配置 (`ks_rdata_reloc_check.py`、DIR64 対象の RVA 集合。SC 32,376 件・KH 380,327 件): 参照スロット 736 語のうち SC 再配置対象 **3 語**・KH **5 語**。RVA 候補は、絶対ポインタとして再配置されていない。
  - ただし DIR64 でない 32 bit の RVA テーブルは、この検査では区別できない。RVA か整数定数かは未判定。
- RVA 候補の指す先 (`ks_rdata_rva_target.py`、先頭 8 B): `rva_pair` 72 組は **72 / 72 で不一致** (`target8_ne`)。うち差が 256 未満の組は 27 件 (整数の近い値)。
- 判定 (受入 4 件に対応):
  - 受入 1 (RVA か定数か): **部分達成**。絶対ポインタではない (再配置 3+5 語のみ) ことは示したが、RVA テーブルと整数定数の区別は未了。
  - 受入 2 (dbl の位置対応・件数): **達成**。同位置の dbl 対 14 件、全て不一致 (ulp 16 以上)。
  - 受入 3 (REPORT 追記): 本節で達成。
  - 受入 4 (定数値の差か配置差か): **定数値の差が支持される**。配置差なら指す先の 8 B が揃うはずだが 72 / 72 で不一致、dbl も同位置で一致しない。ただし指す先の 8 B しか見ておらず、さらにポインタを辿る先は未追跡。「意味が違う」の根拠ではない (§A5 の読みを維持)。

#### 未解決 (#2024 の範囲外・残件)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ~~RVA 候補 72 組が RVA テーブルか整数定数か~~ | §A5-3 で解消 (72 組とも整数定数側。RVA テーブルは 0 組) | — |
| 指す先の 8 B 以降・さらに先のポインタの追跡 | 受入 4 の「定数値の差」判定の下限 | #52 (残件) |
| `other` 29 組の中身 (abs と RVA の混在など) | 件数の内訳が未確定 | #52 (残件) |

### §A5-3. RVA 候補 72 組の指す先の切り分け (#2052, 実測)

- 測定 commit: `590206da` (`ks_rdata_rva_table.py` を追加した commit)。`590206da` から本 fix までの `ks_rdata_rva_table.py` の差分は `--sensitivity` モードの追加のみで、`main()` (RVA 候補の分類経路) は不変。
- 再現: `ks_identity.sh` → `ks_rdata_class.py` → `ks_rdata_value.py` (§A5 と同じ入力) → `python3 ks_rdata_rva_table.py <HeartCore.core_64> <SlateCore.core_64> rdata_class.json out.json`。素材は `plugins-kilohearts` (`HeartCore.core_64`) と `plugins-freshair` (`SlateCore.core_64`)。
- 方法: `rva_pair` 72 組 (§A5-2) の各組について、指す先の 32 B を dword 単位で読み、先頭から RVA dword (上位 32 bit が 0・セクション範囲内) の連続長 `run` を数える (最大 16)。`run >= 2` を RVA テーブル、それ未満を整数定数とした。
- 結果 (測定 commit `590206da`、`ks_rdata_rva_table.py` の JSON を 2 回実行で byte 一致、EXIT=0、0.27 s real、load 0.13、nproc=4):

| 指標 | 件数 |
|---|---|
| `rva_pair` (RVA 候補の組) | 72 |
| SC 側の指す先で `run = 0` | **72 / 72** |
| KH 側の指す先で `run = 0` | **72 / 72** |
| RVA テーブルと判定された組 | **0** |
| 整数定数と判定された組 | 72 (指す先の 8 B: 一致 0・不一致 72) |

- 感度の確認 (陽性対照・同じ分類器): HEAD (`fa810810`) の `--sensitivity` を fl-win64 の installer exe (`flstudio_win64_26.1.7.5653.exe`、`$ARTIFACTS_DIR/fl-win64.tar.zst` から展開) に対して実行した実出力:
  `{"blocks": 196, "path": "flstudio_win64_26.1.7.5653.exe", "run0": 148, "run1": 7, "run>=2": 41}` (EXIT=0、0.26 s real、load 0.87)。`run>=2` が 0 でないので、分類器は RVA 列を検出できる (0 件は検出不能の結果ではない)。
  - 再現: `python3 ks_rdata_rva_table.py --sensitivity <PE>` (`sensitivity()` は `rva_run` と同じ判定で `.rdata` を 32 B 境界ごとに 3 区分する)。
  - 注記: この陽性対照は installer exe の `.rdata` (196 ブロック) に対するもので、plugin の `HeartCore.core_64` ではない。対象が小さいため検出力の上限の目安にはならない。
  - 未再現: 測定 commit `590206da` には `sensitivity()` が無く、その時点で KH `.rdata` を 3 区分した手段は記録されていない。過去の数値 (`run = 0` 599,263・`run = 1` 49,084・`run >= 2` 33,479 ブロック) は出所不明の ad hoc 計測として扱い、HEAD で再現していない (`plugins-kilohearts` が `$ARTIFACTS_DIR` に無い)。判定の根拠には用いない。
- 関数別 (value 17 件): `rva_pair` を持つ関数は 7 件 (`0x18100ca28` 15・`0x18100cc50` 12・`0x18103d218` 23・`0x18103d47c` 12・`0x180f9e540` 2・`0x18105aec8` 4・`0x18105bb90` 4 の合計 72)。残り 10 件は `rva_pair` が 0。
- 併せて §A5-2 の語単位結果と突き合わせると、72 組の SC 側 16 B は全て KH の `.rdata` 内に存在しない (`rva_off_absent` 72)。

判定:
- 受入 1 (RVA テーブルか整数定数かの切り分け): **達成**。72 組は全て RVA テーブルではない (指す先の先頭 dword が RVA でない)。整数定数側に分類。
- 受入 2 (RVA 差分で正規化した上で value 17 件を再判定): **達成 (正規化不要と判定)**。RVA テーブルでないため、配置差の正規化を適用する対象が無い。正規化なしの再判定は 17 件とも `value_differs` のまま。この再判定は §A5-2 の結果をそのまま引用しており、`RVA 対象なし` のため §A5-2 の判定を据え置く (新たな再計算は行っていない)。
- 受入 3 (本節の追記): 本節で達成。

判定の限界:
- 「指す先の先頭 dword が RVA でない」は、指す先が RVA テーブルでないことの十分条件ではない。指す先が RVA でない整数・浮動小数・文字列の混在である可能性を排除しない (`text` 語が含まれる関数がある)。
- `rva_off_absent` 72 組は、配置差では説明できないことを示す。ただし指す先の内部をさらに辿る (ポインタの先) ことは未追跡。§A5-2 の「定数値の差」判定の下限のまま。
- 分類器は 32 bit RVA 列だけを見る。指す先が 8 B 絶対ポインタの表である場合は RVA 列として検出されず整数定数側に入るため、「整数定数」の判定は絶対ポインタ表を排除しない。

#### 未解決 (#2052 の範囲外)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 指す先の 16 B 以降・さらに先のポインタを追跡する | §A5-2 受入 4 の「定数値の差」判定の下限を上げる | #52 (残件) |
| `other` 29 組・`dbl` 14 組の値の差の意味 | value 17 件の実質的な差の原因は未特定 | #52 (残件) |
