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

### §A3-3〜§A3-5 (分割移動)

- meter (§A3-3)・ramp の逐次 cur (§A3-4)・丸め形モデル (§A3-5) は [REPORT_APPENDIX_FA5_GAIN.md](REPORT_APPENDIX_FA5_GAIN.md) に無変更で移動した (250 行上限)。判定の要点は §A3 と本付録 §A3-2 の表を参照。

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

### §A5-4. value 17 件の差分語の 3 分類と参照元の用途 (#2743 FA-35, 実測)

- 測定 commit: `f1693b5b3` (コードを変えた最後の commit。`ks_rdata_deep.py` の追加)。`git diff f1693b5b3 HEAD -- tools/targets/freshair/*.py tools/targets/freshair/*.sh` は **0 行** (以降の差分は本付録と DOC_MAP のみ)。
- 再現: 素材 `work-liftlib-targets` (`tools/targets/{freshair,kilohearts}/work/` に展開) で `SLATECORE`・`HEARTCORE` を指定して `bash tools/targets/freshair/ks_identity.sh <dir>` (`ident.json`) → `ks_rdata_class.py` → `ks_rdata_value.py` → `ks_rdata_value_pos.py` → `python3 tools/targets/freshair/ks_rdata_deep.py <HeartCore.core_64> <SlateCore.core_64> rdata_class.json ident.json deep.json 64 3`。
- 実測 (測定 commit `f1693b5b3`): `ks_rdata_deep.py` 2 回実行で stdout・JSON とも byte 一致、0.80 s real × 2、load avg (1 分) 0.01、nproc=4。前段の `ks_identity.sh` は 54.8 s real・EXIT 0 (§A5-2 と同じ入力、`value` 17 件・差分語 139 を再現)。
- 差分語 139 (`pos`: rva_pair 72・dbl_pair 14・other 29・text 24) を、指す先 64 B (8 語)・深さ 3 で判定した結果:

| 分類 | 件数 | 内訳 |
|---|---|---|
| 定数値の差 | 58 | dbl 10・int 19・text 24・text_mixed 5 |
| 参照先の内容差 | 72 | 葉は全 72 語が text_mixed (下記) |
| 配置差 | 0 | — |
| 分類不能 | 9 | ptr_vs_const 9 (片側だけポインタ候補・もう片側は定数) |

- 感度: 指す先 16・32・64・128 B (深さ 3) と深さ 1・2・3・4 (64 B) の 7 条件で件数は上表と同一。
- `pos` との対応: rva_pair 72 → 参照先の内容差 72 / dbl_pair 14 → 定数 dbl 10・text_mixed 3・分類不能 1 / other 29 → 定数 int 19・text_mixed 2・分類不能 8 / text 24 → 定数 text 24。
- **参照先の内容差 72 語**: 指す先の印字可能文字列 (3 字以上) の集合を比べると、SC/KH で一致 2 件・不一致 70 件 (`content_strings`)。不一致例 `0x180f9e540`: SC は `GetCurrentThreadId`・`GetModuleFileNameW`・`GetModuleHandleExW`、KH は `GetCurrentThreadId`・`WaitForSingleObjectEx`・`CreateEventA`。差は DSP の定数ではなく、参照される Windows API 名の表の差と読める (表の出所・関数名は未確認)。
- **定数値の差 (dbl 10・int 19 など)**: 語が出るのは Filter 単独 closure の 3 関数 (`0x181040d20`・`0x181049d40`・`0x18104a270`) が中心。SC 側の倍精度は π/2 (`0x3ff921fb54442d18`・切り詰め `0x3ff921fb54400000`)・`6.08e-11`・DBL_MAX・0.0 で、同位置の KH 側は 0.0・0.499・1/720 (`0x3f56c16c16c16c17`)・整数 `0x200000001`・ポインタ候補。同位置の対応が同じ定数表の同じ要素かは確認していない (配置が違う可能性)。
- **配置差 0 件**: ポインタ同士の指す先が語単位で再帰的に一致した語は 0 件 (感度 7 条件すべて)。配置差で説明できる語は無い。
- **分類不能 9 語**: 片側の RVA 候補 (例 `0x286e5c8`・`0x18118fcf0`) と、もう片側の定数の組。RVA か定数かを区別する情報が無いため未確定。

#### 用途の照合 (`usage` in `ks_rdata_deep.py`)

- 方法: 4 root (FreshAir・Gain・Filter・Compressor) の vtable 全 slot からの direct call/jmp 到達 (`ks_closure_share.closure`) と、process 対応 (`ident.json`)・直接呼び出し元で照合。間接 call は辿らない (下限)。

| 用途 (静的な照合) | 関数 (SC VA) | 差分語: dbl_pair / other / 参照先の内容差 |
|---|---|---|
| Filter 単独 closure の数学補助 (process 本体ではない) | `0x181040d20`・`0x181049d40`・`0x18104a270` | 14 / 21 / 0 (+ `0x18105c480` の text 3) |
| FreshAir 単独 closure | `0x1803b3fc0`・`0x1803b5b60`・`0x180cbd860`・`0x180f9e540`・`0x18100cf60`・`0x181011058`・`0x18103d218`・`0x18103d47c` | 0 / 8 / 37 |
| 4 closure 共有 | `0x18100ca28`・`0x18100cc50`・`0x18105aec8`・`0x18105bb90` | 0 / 0 / 35 |
| 3 closure 共有 (Gain・Filter・Compressor) | `0x18105b380` | text 4 |

- process 本体・vtable slot の直接一致: 0 件。process 本体を直接呼ぶ関数: 0 件。
- 読み: dbl 14 組は全て Filter 単独 closure の 3 関数に入り、Gain・Compressor の closure には入らない (共通 lib ではない)。other 29 組は 21 組が同じ Filter の 3 関数、8 組が FreshAir 単独 closure。Gain・Compressor の process は差分語の参照元に現れない。数学的な用途 (三角関数系の定数) は定数の形からの推定で、関数名・ソースは未確認。

#### 受入の判定

- 受入 1 (3 分類・未分類の数と理由): **達成**。139 語を 58 / 72 / 0 / 9 に分類。未分類 9 語は理由 (ptr_vs_const) を記録。
- 受入 2 (other 29・dbl 14 の用途照合): **達成** (静的照合)。process 本体は 0 件、Filter 単独の数学補助 3 関数に集中。
- 受入 3 (§A5-4 の実測追記・測定 commit・再現手順): **達成** (本節)。

#### 限界

- 3 分類は指す先の 64 B と深さ 3 で判定。窓・深さを変えても件数は不変だが、葉の意味 (API 名の表の出所) は読めていない。
- 「RVA 候補」は `sec_of` (32 bit の値がセクション範囲に入るか) による。RVA か整数定数かは未判定のため、定数値の差 (int 19) と分類不能 9 は境界が未確定。
- 用途は静的な direct call 到達と既存 process 対応による。間接 call (vtable 経由) は追えない。

#### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 分類不能 9 語の RVA か定数かの判定 | 定数値の差と分類不能の境界 | #52 (残件) |
| 参照先の API 名表の差の出所 (どの import 表か・なぜ違うか) | 参照先の内容差 72 語の解釈 | #52 (残件) |
| Filter 単独 3 関数の用途 (数学 lib か) の逆アセンブル照合・間接 call 到達 | 用途照合の確度 (現状は定数と直接呼び出しからの推定) | #52 (残件) |
