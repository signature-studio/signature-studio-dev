# Fresh Air REPORT §11 (FA-5) 付録 (分割): `value` 17 件の内訳と語単位切り分け

- 本体: [REPORT.md](REPORT.md) §11・付録 [REPORT_APPENDIX_FA5.md](REPORT_APPENDIX_FA5.md)。本書は 250 行上限のため、FA5 の §A4・§A5 を無変更で分割移動した (内容は削除していない)。

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

