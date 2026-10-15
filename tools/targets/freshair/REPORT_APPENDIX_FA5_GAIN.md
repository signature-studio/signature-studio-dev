# Fresh Air REPORT §11 (FA-5 #52) 付録: Gain の meter・ramp 照合 (§A3-3〜§A3-5)

- 本体: [REPORT.md](REPORT.md) §11。親付録: [REPORT_APPENDIX_FA5.md](REPORT_APPENDIX_FA5.md) §A3。本書は 250 行上限のため、親付録の §A3-3〜§A3-5 を無変更で分割移動した (内容は削除していない)。

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
