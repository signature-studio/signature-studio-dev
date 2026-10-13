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
- 前提の訂正: 旧 §A4 の `rva32` (セクション範囲内の整数) は、RVA ポインタなのか定数なのかを区別していなかった。本節の検査では、差分語は RVA として扱えるものだけを対象にした。
- 測定 commit: `1b3a1b33` (最後にコードを変えた commit)。`ks_identity.sh` と `ks_rdata_value.py` を `d67052f9` でも再実行し、同じ数値 (以後 docs のみの commit で HEAD は進むが、コード差分は 0 のまま)。コード差分の証跡 `git diff 1b3a1b33 HEAD -- tools/targets/freshair/*.py tools/targets/freshair/*.sh` は **0 行** (差分は本節の文書のみ)。
- 実測 (2 回実行で byte 一致、EXIT=0。`ks_rdata_value.py` 0.73〜0.75 s、`ks_identity.sh` 51.9 s、load 0.36〜0.74 (nproc=4)): 下記の数値が本 PR の正本。
  `{"abs_vs_const": 8, "dbl": 13, "fn_value_differs": 17, "int": 23, "rva_off_absent": 72, "text": 23}`
  - `abs_` 接頭辞は、片側以上が ImageBase〜SizeOfImage の 8 B 絶対アドレスである組。`abs_vs_const` 8 語は、片側だけが絶対アドレスで、もう片側が RVA として解決できない定数。
  - `layout` 0 件・`target_eq` 0 件・`abs_layout` 0 件・`abs_target_eq` 0 件 (配置差で説明できる語は無い)。
  - RVA 候補 72 語 (すべて `.rdata` を指す) は、SC が指す 16 B が KH の `.rdata` の全バイト位置のどこにも無い (`rva_off_absent` 72 / 72、`rva_off_found` 0)。
  - `int` 23 / `dbl` 13 / `text` 23 は、差分語のうち RVA 候補・絶対アドレスでないもの (整数・倍精度・文字列断片)。
- 読み: `value` 17 件は「配置がずれただけ」とは言えず、RVA 候補の指す先の 16 B が KH 側に無い。参照先がさらにポインタを含む場合は未追跡 (下限)。`dbl` 13 / `int` 23 が同一位置の定数差か、そもそも対応しない語の組み合わせかは未確定。
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
