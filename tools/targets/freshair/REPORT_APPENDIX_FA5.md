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

## §A4. `value` 17 件の内訳 (`ks_rdata_detail.py`, #52 残件)

- 再現: `ks_rdata_detail.py <HeartCore.core_64> <SlateCore.core_64> rdata_class.json share.json` (`ks_identity.sh` と `ks_rdata_class.py` の出力を入力にする)。素材は `work-liftlib-targets` のみ (`SlateCore.core_64`・`HeartCore.core_64` を含む)。
- 実測 (2 回実行で byte 一致、EXIT=0): 内容が違う組は 44 組 (うち text 2、非 text 42。`pairs` の値)。非 text の 42 組について 32 B の参照先を 8 B 語に分けた結果は次のとおり (語数。`text_ref` は参照数)。

| 区分 | SC | KH | 判定の定義 |
|---|---|---|---|
| `text_ref` | 2 | 2 | 印字可能 ASCII を含む参照 (文字列断片) |
| `rva32` | 75 | 74 | 上位 32 bit が 0 で、下位 32 bit がいずれかのセクションの [VirtualAddress, +VirtualSize) 内の語 (RVA 候補。セクション範囲内に入る整数定数は区別していない。0x1000 未満は除外) |
| `abs` | 3 | 5 | image 範囲の 8 B 絶対アドレス (`ptr` 判定の対象) |
| `dbl` | 73 | 75 | それ以外 (倍精度・整数定数など) |

- 読み: `rva32` は「RVA の候補」であって、RVA と確認した値ではない。セクション範囲に入る小さな整数定数が混じりうるため、件数は上限として読む。`dbl` 語は定数の差の候補だが、本節では位置ごとの対応を取っていない。文字列断片は 2 件ずつ。
- 判定: `value` 17 件の中身が定数値の差か配置差かは、この集計からは決まらない (未確認)。`ptr` 判定 (8 B 絶対アドレスのみ) では 32 bit の RVA を拾えないので、`value` と `ptr` の境界は下限でしか決まらない。
- 未解決: `dbl` 語が同一位置で bit 一致するかの対応付け。`rva32` 候補が RVA か定数かの確認と、RVA 差分による正規化。起票先 → #52 (本 issue の残件)。

## §A5. `value` 17 件の語単位切り分け (`ks_rdata_value.py`, #52 残件 ②)

- 再現: `ks_rdata_class.py` の出力 `rdata_class.json` を入力に `python3 ks_rdata_value.py <HeartCore.core_64> <SlateCore.core_64> rdata_class.json share.json out.json` (uv で pefile/numpy/capstone)。素材は `work-liftlib-targets`。
- 方法: `value` 17 関数の rip 参照 (32 B) を 8 B 語で対にし、差分語を分類。`rva_off_*` は「SC 語が指すセクション内 RVA の 16 B」を KH 側と比べる。
- 前提の訂正: 旧 §A4 の `rva32` (セクション範囲内の整数) は、RVA ポインタなのか定数なのかを区別していなかった。本節の定義: **RVA 候補** = 上位 32 bit が 0 で、いずれかのセクション範囲に入る値 (RVA か定数かは未判定)。`layout` / `target_eq` / `rva_off_*` の対象は、そのうち `.rdata` 内を指すもの (両側とも `.rdata` に解決される組) に限る。
- 本節の分類は RVA 候補の「指す先」を見るだけで、値が RVA であることは確認していない。
- 測定 commit: `115debea` (最後にコードを変えた commit。RVA 候補を `.rdata` に限定し `sec_hits` を追加)。`ks_identity.sh` と `ks_rdata_value.py` は同じ commit で再実行。コード差分の証跡 `git diff 115debea HEAD -- tools/targets/freshair/*.py tools/targets/freshair/*.sh` は **0 行** (差分は本節の文書のみ)。
- 実測 (測定 commit `115debea`。HEAD `d148d08a` まで `tools/targets/freshair/*.py` / `*.sh` の差分 0 行。`ks_identity.sh` EXIT=0、54.6 s、load 0.38 (nproc=4)。`ks_rdata_value.py` 2 回実行で stdout・JSON とも byte 一致、EXIT=0、0.68 s real × 2、load 0.43): 下記の数値が本 PR の正本。
  `{"abs_vs_const": 8, "dbl": 13, "fn_value_differs": 17, "int": 23, "rva_off_absent": 72, "text": 23}`
  - `abs_` 接頭辞は、片側以上が ImageBase〜SizeOfImage の 8 B 絶対アドレスである組。`abs_vs_const` 8 語は、片側だけが絶対アドレスで、もう片側が `.rdata` に解決できない定数。
  - `layout` 0 件・`target_eq` 0 件・`abs_layout` 0 件・`abs_target_eq` 0 件 (配置差で説明できる語は無い)。
  - `sec_hits` (語の解決先セクション件数): SC `.rdata` rva 74 / abs 2、SC `.text` rva 1 / abs 1、KH `.rdata` rva 74 / abs 5。
  - **限定前後の比較** (限定前 = `1b3a1b33` の `ks_rdata_value.py`、限定後 = `115debea` 以降。同じ入力 `rdata_class.json` と `share.json` で実行): 全バケットの件数は before / after とも同一 (`abs_vs_const` 8・`dbl` 13・`int` 23・`text` 23・`rva_off_absent` 72)。`sec_hits` は限定後だけの出力のため、before 側は未計測 (件数の差は 0 件と読める)。
  - **`.text` を指す RVA 候補 1 語の行き先**: SC `0x18105b380` (値 `0x776f70` = 文字列断片 "pow")。KH 側 `0x686e697300776f70` は KH 側の解決先がセクション外のため `.rdata` 対にならず、`is_text` で `text` に入る。限定前も同じ経路 (`sy` が None → `text`) で、`rva_off_*` には入っていなかった。同じ入力で `.rdata` 限定の前後とも `text` 側。
  - `rva_off_absent` 72 語は、「RVA 候補の指す 16 B が KH の `.rdata` の全バイト位置のどこにも無い」件数 (`rva_off_found` 0 / 72)。RVA か定数かは未判定のため、「内容が違う」の確定ではなく、参照先の内容差の下限として読む。
  - `int` 23 / `dbl` 13 / `text` 23 は、差分語のうち RVA 候補・絶対アドレスでないもの (整数・倍精度・文字列断片)。
- 読み: `value` 17 件は「配置がずれただけ」とは言えず、RVA 候補の指す先の 16 B が KH 側に無い (RVA か定数かは未判定)。参照先がさらにポインタを含む場合は未追跡 (下限)。`dbl` 13 / `int` 23 が同一位置の定数差か、そもそも対応しない語の組み合わせかは未確定。
- 判定: `value` 17 件は **配置差だけでは説明できない**。「内容が違う」の断定は下限としてのみ言える。「意味が違う」とは言えない (定数表や型テーブルの内容差の可能性)。意味同一性は #1264 (FA-18) の差分実行で判定する。
- 起票先: 残件の意味判定 → #1264 (FA-18)、`dbl`/`int` 対応付けは #52 残件。

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

- 測定 commit: `37c8193d` (ハーネスに `METER_DUMP=1` 時の stderr 出力と `ks_meter_replay.py` を追加。stdout は不変)。`git diff 37c8193d HEAD -- tools/targets/freshair/*.c tools/targets/freshair/*.py tools/targets/freshair/*.sh` は本節の commit までで 0 行。
- 再現: `cc -O1 -ffp-contract=off -o h tools/targets/freshair/ks_semantic_gain.c -lm` → `./h sc <SlateCore> 200 7 > sc.txt`・`./h kh <HeartCore> 200 7 > kh.txt` → `python3 ks_meter_replay.py sc.txt kh.txt`。逆アセンブルは capstone 5.0.7 (SC 0x180afe090・KH 0x1804b0380 の先頭 900 命令)。
- 実測 (`37c8193d`、nproc=4): ハーネス 2 本で 0.053 s real、load 0.08 (測定時)。`ks_semantic_gain_cmp.py` = `{"cases": 200, "bit_exact_LRS": 127, "mismatch_L": 73, "mismatch_R": 73, "mismatch_S": 48, "notify_count_mismatch": 0}` (§A3 と一致)。
- meter 更新式 (両側同形): ループ内で `m = (s*s - m)*c + m` (`mulss` → `subss` → `mulss` → `addss`)。対応 (SC = KH + 0x38): m1 `0x88`⇄`0xc0`・c1 `0x84`⇄`0xbc`、m2 `0x98`⇄`0xd0`・c2 `0x94`⇄`0xcc`。SC `0x180afe1b4`〜`0x180afe1e2`、KH `0x1804b04a1`〜`0x1804b04f2`。
- 初期値 (m1・m2・c1・c2) は 200/200 一致。
- 出力 L/R から同じ式を float32 で再計算すると、自側の state (m1 `0x88`・m2 `0x98`) と **SC 199/199・KH 199/199 で一致** (n>0 の case)。式が再現できる。
- meter 不一致 (state 比較): m1 28 件・m2 35 件。`ks_meter_replay.py` の内訳: `m1_mismatch_with_L_identical` 0・`m2_mismatch_with_R_identical` 0。つまり meter 不一致は全て対応する出力チャネル (L/R) の不一致と同じ case に出る。
- `cur` 一致かつ meter 不一致 30 件 (§A3-2 の 30 件と同じ) は、全て L/R 出力の差からの伝播として説明できる。
- L 差の内訳: `cur` 不一致 18 件・`cur` 一致 55 件 (`cur` が一致するのに L が違う case がある)。
- 例 case 3: 出力 L の index 2 のみが 1 ulp ずれ (SC -0.4080760180950165 / KH -0.4080759882926941)、以降の差は同じ起点から伝播。
- **判定 (受入条件 1 は未達)**: ずれる式は **meter 更新式には見つからなかった**。meter 差は L/R 差の伝播で、式そのものの差ではないと読む。
- 未確定: L 差の起点。`cur` の逐次値 (ramp の丸め順) の bit 単位照合が未了。harness は逐次 `cur` を出力しないため、そのままでは確定できない。起票先 → 子 issue (ramp 逐次値のダンプと照合)。
- 受入条件 3 (本節の追記) は本 commit で満たす。受入条件 2 (単体再現で 30 件を説明) は「meter 式は同一・30 件は L/R 伝播」まで。L 差の起点の説明は未了。
