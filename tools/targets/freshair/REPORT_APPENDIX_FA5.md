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
| RVA 候補 72 組が RVA テーブルか整数定数か | 受入 1 の残り。配置差の補正 (RVA 差分正規化) ができない | #52 (残件) |
| 指す先の 8 B 以降・さらに先のポインタの追跡 | 受入 4 の「定数値の差」判定の下限 | #52 (残件) |
| `other` 29 組の中身 (abs と RVA の混在など) | 件数の内訳が未確定 | #52 (残件) |

### §A5-3. RVA 候補 72 組の指す先の切り分け (#2052, 実測)

- 測定 commit: `590206da` (`ks_rdata_rva_table.py` を追加した commit)。`git diff 590206da HEAD -- tools/targets/freshair` は 0 行 (本節の文書のみ)。
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

- 感度の確認 (陽性対照・同じ分類器): KH の `.rdata` を 32 B 境界で走査すると、`run = 0` 599,263 ブロック・`run = 1` 49,084・`run >= 2` 33,479 ブロック。つまり分類器は RVA 列を検出できる (0 件は検出不能の結果ではない)。
- 関数別 (value 17 件): `rva_pair` を持つ関数は 7 件 (`0x18100ca28` 15・`0x18100cc50` 12・`0x18103d218` 23・`0x18103d47c` 12・`0x180f9e540` 2・`0x18105aec8` 4・`0x18105bb90` 4 の合計 72)。残り 10 件は `rva_pair` が 0。
- 併せて §A5-2 の語単位結果と突き合わせると、72 組の SC 側 16 B は全て KH の `.rdata` 内に存在しない (`rva_off_absent` 72)。

判定:
- 受入 1 (RVA テーブルか整数定数かの切り分け): **達成**。72 組は全て RVA テーブルではない (指す先の先頭 dword が RVA でない)。整数定数側に分類。
- 受入 2 (RVA 差分で正規化した上で value 17 件を再判定): **達成 (正規化不要と判定)**。RVA テーブルでないため、配置差の正規化を適用する対象が無い。正規化なしの再判定は 17 件とも `value_differs` のまま (§A5-2 と同じ)。
- 受入 3 (本節の追記): 本節で達成。

判定の限界:
- 「指す先の先頭 dword が RVA でない」は、指す先が RVA テーブルでないことの十分条件ではない。指す先が RVA でない整数・浮動小数・文字列の混在である可能性を排除しない (`text` 語が含まれる関数がある)。
- `rva_off_absent` 72 組は、配置差では説明できないことを示す。ただし指す先の内部をさらに辿る (ポインタの先) ことは未追跡。§A5-2 の「定数値の差」判定の下限のまま。

#### 未解決 (#2052 の範囲外)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 指す先の 16 B 以降・さらに先のポインタを追跡する | §A5-2 受入 4 の「定数値の差」判定の下限を上げる | #52 (残件) |
| `other` 29 組・`dbl` 14 組の値の差の意味 | value 17 件の実質的な差の原因は未特定 | #52 (残件) |
