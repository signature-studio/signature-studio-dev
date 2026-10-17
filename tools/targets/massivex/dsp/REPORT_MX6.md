# Massive X MX-6 (#1123): vectorcall 独自規約と MSVC EH funclet の静的解析

- 解析日: 2026-10-14 / 担当: `tools/targets/massivex/dsp/` (生成物は repo 外 `$RUNNER_TEMP`・gitignore 対象は触らない)
- 素材: `plugins-massivex` の `Native Instruments Massive X v1.7.1.exe` を repo 内の既存パーサ
  (`tools/targets/massivex/scripts/parse_setup_headers.py` → `extract_massivex.py <exe> <work> key`) で展開。
  `Massive X.vst3` = 95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca` (REPORT §0 の記録値と一致)。
- 前回 run の「素材を展開できない」停止は誤り (innoextract のみで判断していた)。本 run は既存パーサで展開済み。
- 最後に e2e を実測した commit = **62a3fda35** (コードを変えた最後の commit・PR #4781 の単一 commit。再現: `bash tools/targets/massivex/dsp/mx6_e2e.sh`・`MX_PE` で PE を指定)。実測の範囲は §1。
- **MX-41 の新版 (分類の関数化・ネガコンの入力書き換え・行ごとの独立照合) は 3afa6013d で実測済み** (付録 `REPORT_APPENDIX_MX6_HISTORY.md` A4)。旧版 5de22167f のネガコン値は取り消した (§3)。
- MX-41 (#3792・MX-38 の U4b) の追補: 素材は `plugins-massivex` を展開し直した (md5 `622993e7` 一致)。分類の全件表は `REPORT_APPENDIX_3792.md` (3afa6013d の出力と全項目一致)。
- main の FH4 固定部 (MX-42・§8) を取り込んだ。旧測定 (0dbf9a54d・51953f46d・fbc9971f) の表と記録は `REPORT_APPENDIX_MX6_HISTORY.md` に分割移動した (削除していない)。

## 0. 結論 (先出し)

1. **vectorcall (受入 1・U3)**: 入口 (pdata 始点) の関数で、入口から書かれる前に xmm4/xmm5 を読むものは **0 件**
   (seeds 566 件・1-round closure 604 件)。独自規約 (5 番目以降の vector/HVA 引数) を持つ入口関数は検出されず。
   ただし **xmm0〜3 だけの vectorcall は Win64 と区別できず判定不能** (pdata 始点で各 17 件を保留・§2 限界)。
2. **chained .pdata (受入 2・U4)**: 1 本目の .pdata 全体 (entry 187,060 件・§3) のうち UNW_FLAG_CHAININFO は **62,526 件 (33.4%・分子と分母は同じ範囲)**。
   2 本目 (VS 158,952 B・raw 6,144 B) は MX-41 で census に入れた (§3・509 件・chained 34・読取不能 0)。入口 seeds の pdata 始点 566 件には chained 子は **0 件**。EH handler を持つ入口関数は 248 件
   (`__CxxFrameHandler3` 247 / `__CxxFrameHandler4` 1)。
3. **読取不能 160 件 (MX-41・受入 1・4)**: reader の欠陥ではない。160 件は全て UnwindInfoAddress の値が画像外 (≥ SizeOfImage `0x6616000`)、どの section にも入らず raw も無い。
   pefile の独立解決でも同じ 160 件を読取不能と判定した (集合 160/160・行ごとの分類 160/160・`get_section_by_rva` の None 160/160。3afa6013d)。値の由来 (配布 PE の改変か、展開の誤りか) は未確定 → [MX-38] (#3775)。全件表は `REPORT_APPENDIX_3792.md`。
4. **funclet 一覧 (受入 2)**: FH3 の FuncInfo (x64 RVA 形) から catch 本体と cleanup action の funclet RVA を取ると、
   seeds 由来 **533 件** (pdata 始点 529)・1-round 由来を含む和集合 **537 件**。
5. **#228 同型判定 (受入 3)**: **同型あり**。funclet 537 件のうち 1-round CFG closure に入るものは **0 件**、
   seeds にも 0 件。`.text` 全体の生バイトの E8/E9 走査 (命令境界を見ない) で funclet を指す一致候補は **4 件のみ** (直接参照とは未確認 → U4d)。
   残りは unwind 経由 (EH dispatch) でしか到達しない code で、CFG 降下 (x64c の closure) からは見えない。
   #228 (ICALL-2) の「landing pad は CFG 非到達」と同じ型。
6. **独立再計算・NC (受入 4)**: 合成バイト列の selftest 5 件 PASS (正例 3・負例 2)。線形走査 (CFG を使わない) の
   xmm4/5 参照関数数は 183 (seeds) / 1,296 (1-round) で、本体の上限と整合 (livein ⊆ anyref を全件で確認)。
   ただし線形側も命令の読み書き集合 (`effects()`) と逆アセンブラを本体と共有するため、CFG 非依存の上限確認に限り、独立な検証ではない。
   感度: PE 上の非 begin 入口 302 件で livein 検出が発火 (検出器が実バイトで動くことの確認)。

## 1. 実測 (e2e, 測定 commit 62a3fda35)

- 測定 commit = **62a3fda35** (PR #4781 の単一 commit)。PR 作成 run の記録: `mx6_e2e.sh` 全 8 工程 PASS・exit 0・所要 **48 s** (`elapsed=48s`)・load average `0.15 0.31 0.17` → `0.63 0.42 0.22`。
  positive control は funclet 533 / pdata 始点 529、読取不能 160 (`out_of_image`)。
- 本 run (fix モード) では `plugins-massivex` が無く、62a3fda35 の e2e を再実行できなかった。上の値は PR 作成 run の記録であり、本 run で再測定した値ではない。工程ごとの詳細値は再取得できていない → 下の未解決 U1 (本 run で再確認できた範囲は §7)。
- 62a3fda35 の直前の工程別値 (3afa6013d の e2e 表) は `REPORT_APPENDIX_MX6_HISTORY.md` A4 に分割移動した。
- MX-41 の判定 (3afa6013d の実測・付録 A4): 1 本目 187,060 / chained 62,526 / EH 23,293 / 読取不能 160 (`out_of_image` 160)。2 本目 509 / 34 / 49 / 読取不能 0。独立再計算 (pefile): 読取不能の集合一致 (160 = 160)・行ごとの分類一致 160/160・ネガコン break +1・fix −1。
- 実行: `MX_PE='$RUNNER_TEMP/mx/work/extracted/VST3/Massive X.vst3' MX6_WORK='$RUNNER_TEMP/massivex-mx6' bash tools/targets/massivex/dsp/mx6_e2e.sh` → exit 0。
- 旧測定 (0dbf9a54d・51953f46d・fbc9971f) の表は `REPORT_APPENDIX_MX6_HISTORY.md` の A1・A2 に移した。

## 2. vectorcall 静的検出 (U3)

判定の定義: 入口からの CFG 上で must-def (全経路で書かれている集合) を取り、書かれていない xmm_k の読みを検出
(`dsp/scripts/mx6_vectorcall.py`)。Win64 の引数レジスタは xmm0〜3 のみなので、xmm4/5 の入口 livein は
独自規約の強い根拠になる。

| 集合 | 関数 | pdata 始点 | livein xmm4/5 (pdata 始点) | xmm0〜3 のみ (保留) | 解析 flow 未解決 (pdata 始点) | 線形 anyref 上限 |
|---|--:|--:|--:|--:|--:|--:|
| seeds (入口面) | 567 | 566 | **0** | 17 | 12 | 183 |
| 1-round closure (解析できた関数) | 3,108 | 604 | **0** | 17 | 14 | 1,296 |

- 入口数の差: 1-round の入口 (roots) は **3,226** (`mx_entry_surface.py` の `one_round_closure`)。上表の 3,108 は解析できた関数数で、差 **118** は `analyze()` が `None` を返した root の数 (`mx6_vectorcall.py` は `None` の root を `rows` に入れず飛ばす)。この除外経路はこれだけで、roots の重複は `set` で潰れ、seeds 567 は全件解析済み。`None` は先頭命令を capstone が 0 命令しかデコードできない root を指す。どの命令で止まるかの内訳は本 run では PE が無く未測定 → U3c。
- 1-round の livein xmm4/5 のうち 302 件は **pdata 始点でない途中アドレス**を入口にした結果 (途中の定義を見ないため)。
  pdata 始点の判定には使わない。PE 上の感度確認としてのみ扱う。
- 間接 jmp: MSVC の相対 int32 テーブル形 (`lea` 基底・`cmp` 境界・`movsxd`/`add`) を解決 (seeds 11 件・1-round 24 件)。
  解決できない間接 jmp は全命令への後続と見なす (過大近似。livein の偽陽性側にだけ誤差が出る。陰性結果は保守側)。
  途中の検討で 3 件の偽陽性 (switch 後続の過大近似による) を確認し、解決器を入れて消した。
- 呼出側の根拠: xmm4/5 が call 前に (経路上で) 書かれる直接 call は seeds 716 / 1-round 2,809 (`call_args`)。

**限界 (未解決)**: xmm0〜3 だけを使う vectorcall (HVA / `__m128` を xmm0〜3 に載せる形) は Win64 の float 引数と
区別できない。`__m128` の by-pointer (Win64) と by-register (vectorcall) の差は memory 参照の有無で見分けるが、
本 run では未実装。→ [MX-37] (#3774) で扱う。
関数範囲外への直接 jmp は `analyze` で経路を打ち切る (`idx` に無い target は後続に入らない)。範囲外の読みは見えず、closure がその target を root に含むことに依存する。

## 3. unwind census (U4)

- 「1 本目の .pdata 全体」= `.pdata` section の先頭 (file 順) の全 entry (st≠0・e>st・同じ st の重複を 1 件に畳んだ 187,060 件。行数は 187,093)。以下の「全体」はこの範囲。2 本目は下表の別行 (MX-41)。
- 除外行 (census に入らない行・`excluded_pdata1` / `excluded_pdata2`): 1 本目 33 件 (st==0 9・e≤st 23・同じ st の重複 1)、2 本目 3 件 (st==0 2・e≤st 1: st `0x6700E4E9`・offset `0x12B4`)。
  重複 1 組は st `0x039373E0`・e `0x039373FE` で、ui が `0x062F4A8C` (flags 0・EH なし) と `0x0620B39C` (flags 3・EH+UH) の 2 行。census は後の行を採るため、EH 件数 (23,293) はこの選択に依存する (先の行 (flags 0) を採れば EH は 1 件減り、chained 62,526 は両行とも CHAIN=0 のため変わらない)。由来は未確認 → [MX-38] (#3775)。

| 集合 | pdata 始点 | chained 子 (CHAININFO) | EH handler | 内訳 |
|---|--:|--:|--:|---|
| 1 本目 .pdata 全体 | 187,060 entry | 62,526 | 23,293 | FH3 14,381 / FH4 2,542 / `__C_specific_handler` 16 / IAT 外 (direct) 6,354 |
| 2 本目 .pdata 全体 (MX-41) | 509 entry | 34 | 49 | 全件 IAT 外 (direct) |
| seeds | 566 | **0** | 248 | FH3 247 / FH4 1 |
| 1-round | 604 | 1 | 256 | FH3 248 / FH4 5 / direct 3 |

- **2 本目 (MX-41・#3792)**: VS 158,952 B・raw 6,144 B。VS は `.xdata` の VA 範囲と重なる。census の条件は `e > st` (512 行中 509 件。除外 3 件は上の箇条)。
  読取は raw を持つ section を優先する (`make_rva_reader`) ので、2 本目の ui は raw から読める (reader は変更なし・読取不能 0)。
  PE の例外ディレクトリ (DataDirectory[3]) は 1 本目 (VA `0x5F50000`・size `0x224190`) だけを指し、2 本目は指さない。

- handler は `jmp [rip+X]` の thunk から IAT 名を引いた (`walk_imports`: pefile の import 表は 30 DLL で打ち切られるため手動で辿る)。
- **読取不能 160 件の分類 (MX-41・#3792・3afa6013d の実測・`mx41_pdata2_census.py`)**:

  | 分類 (UnwindInfoAddress の値) | 件数 |
  |---|--:|
  | 画像外 (≥ SizeOfImage `0x6616000`) | **160** |
  | どの section にも入らない (画像内) | 0 |
  | VirtualSize の zero 埋めだけ | 0 |
  | raw を持つ section の内側 | 0 |

  - 値の範囲は `0x17E6E86C`〜`0xEFC4E938`。欄の先頭バイトは **E8 が 148 件**、他は 12 件 (`38`×3・`e0`×2・`48`×2 ほか)。
    関数先頭 (st) の 1 バイトが `48` で始まるのは 128 件。その他の値は分類していない。
  - 分類は `zero_fill` (VirtualSize の zero 埋め)・`raw_zero` (raw 内で 4 バイトが 0)・`no_section`・`out_of_image` の 4 種。json `unreadable_by_class` に出す。実データで出たのは `out_of_image` の 1 種類 (160 件) だけ。`zero_fill`・`raw_zero`・`no_section` は実データで 0 件のため、その 3 分類の照合は実データでは検証されていない。実データでの照合は 1 分類 (`out_of_image`) だけで、「4 分類の照合」とは書かない。
  - **独立再計算 (受入 3)**: pefile の `get_section_by_rva` / `get_offset_from_rva` で行ごとの分類を求め、reader の分類と照合する (json `independent_pefile`: `unreadable_same_set`・`class_pefile`・`class_rows_match`・`flag_mismatch_readable`)。
    旧版 (5de22167f) では読取不能の集合の一致 (160 = 160・差 0) と、読める 186,900 件の flags (CHAIN / EH) の不一致 0 を確認した。行ごとの分類の照合 (160/160) と `get_section_by_rva` の全件 None (160/160) は 3afa6013d で実測した (旧版 0dbf9a54d でも同じ値)。
  - **ネガティブコントロール (受入 4)**: 新版は分類関数に入力 (`ents`) を渡し、入力を書き換えて再分類する。読める行 (CHAIN / EH でない最初の行) の ui を画像外の値 `0x49500DE8` に壊す → 件数の増減 (`negctl.break.delta`)。読取不能の最初の行 (`st` 昇順) の ui を、その手前で読める最後の行の ui に直す → 件数の増減 (`negctl.fix.delta`)。3afa6013d で実測 (旧版 0dbf9a54d と同じ値): `negctl.break` +1 (`st 000010d0`・ui `06186314` → `49500de8`・行は `out_of_image`)、`negctl.fix` −1 (`st 0002fac0`・ui `49500de8` → `0618ccd0`・行は除外)。
    旧版の「160 → 161」「160 → 159」は、摂動が入力を変えておらず (読取不能の ui をそのまま判定していた)、再現できない数値のため取り消す。
  - **結論**: 読取不能の原因は reader ではなく、1 本目 `.pdata` の UnwindInfoAddress 欄に入っている画像外の値 (3afa6013d の測定)。reader には直す箇所が無いため変更していない。
    値の由来 (配布 PE / repack 由来の改変か、展開 `extract_massivex.py` の誤りか) は未確定。隣接データとの一致は計算していない (推定で埋めない)。
    installer 内の MD5 は 125/125 件が一致しない既知事象 (`tools/targets/massivex/REPORT.md` §8.1) で、原本との照合はできていない → [MX-38] (#3775)。
  - 全 160 件の表 (st / e / ui / 所属 section / raw / 先頭バイト) は `REPORT_APPENDIX_3792.md`。
  - 1 本目の読取不能 160 件は zero 埋め (VirtualSize と raw の差) や section 境界の問題ではない (raw の外ではなく画像の外)。

## 4. funclet と #228 同型判定 (U4・受入 2・3)

- 取得: FH3 の FuncInfo (`magic 0x19930520〜0x19930522`) → `maxState` の unwind map の action と、try block の
  handler 配列の `dispOfHandler` (x64 は RVA 形)。`funclets_fh3()` (`mx6_pdata_eh.py`)。
- 妥当性 (positive control): 取れた funclet 533 件中 **529 件が pdata 始点、529 件が pdata 範囲内**
  (残り 4 件は pdata 範囲外・原因未確定 → [MX-38] (#3775))。解析が無作為な番地を拾っていないことの確認。
- closure 判定: funclet は 1-round CFG closure に **0/537**、seeds に 0/537。
  `.text` 全体の生バイトの E8/E9 走査 (命令境界を見ない) で funclet を指す一致候補は **4 件**。直接参照とは断定せず、由来と到達は U4d で確認する (CFG で辿れない・unwind 経由が主と見ている)。
- 判定: **#228 と同型** (CFG 非到達の landing pad が unwind 情報からしか到達しない)。
  件数は FLEngine (#228 の 879 site) より小さいが、同じ欠陥類型として扱う。同型の既知例は #228 (ICALL-2) の landing pad (CFG 非到達)
  で、類型の記述は `tools/icall/REPORT.md` の類型表 D12 (Delphi landing pad 非到達・FLEngine 879 site) が正本。
  `docs/DEFECTS.md` の D12 は別の harness 欠陥 (ABI 毒入れ) で、landing pad の行は無い。
  `docs/DEFECTS.md` に横断行を足さない理由: 同型は D12 として記録済みで、同じ欠陥を二重に書かないため。MSVC 固有の差 (FH3 funclet の到達) は #3776 (MX-39) の確定後に判断する。

## 5. 独立再計算・ネガティブコントロール (受入 4)

- 本体 (CFG must-def) と独立再計算 (線形走査で xmm4/5 を参照する関数の上限) を同じ入力で比較。
  `anyref` 183 (seeds) / 1,296 (1-round) で、線形側が本体の上限と整合。livein ⊆ anyref を全件で確認 (`consistency=True`)。
  ただし `livein ⊆ anyref` は同じ `effects()` を使うため構造上必ず真で、ここで確認したのは CFG 依存部分の上限関係に限る。独立な検証ではない。
- NC (合成バイト列・PE 不要・`mx6_vectorcall.py --selftest`):
  - pos `movaps xmm0,xmm4; ret` → livein [4] (期待どおり)
  - pos `addps xmm5,xmm1; ret` → livein [5]
  - neg `movaps xmm5,xmm1; addps xmm5,xmm1; ret` → livein なし (書いてから読む)
  - neg `pxor xmm4,xmm4 (idiom); movaps xmm0,xmm4; ret` → livein なし (XOR 同一レジスタは読みとしない)
  - pos `test rcx,rcx; je +3; movaps xmm4,xmm0; movaps xmm0,xmm4; ret` → livein [4] (分岐の片側だけ書く = maybe-undef)
  - 結果: **5/5 PASS**。

## 6. 未解決・限界 (起票先)

| # | 未解決 | 影響 | 起票先 |
|---|---|---|---|
| U1 | 62a3fda35 の工程別 e2e 値 (§1 の表) を本 run で再取得できない (`plugins-massivex` が無く、PR 作成 run の記録のみ)。直前の 3afa6013d の表は付録 A4 | 本文の 62a3fda35 の値は PR 作成 run の記録のみ。再測定で置き換える | [MX-38] (#3775) |
| U3a | xmm0〜3 のみの vectorcall (HVA / `__m128` の register 渡し) を Win64 と区別する判定 | seeds 17 / 1-round 17 (pdata 始点) が保留 | [MX-37] (#3774) |
| U3b | 間接 jmp テーブルの残り (解決できない jmp の形と件数は §10。seeds 12 / 1-round pdata 始点 14 が過大近似のまま) | 陰性の保守性は保つが精度は未確定 | [MX-37] (#3774)・由来の測定は §10 (MX-53 #4992) |
| U3c | 1-round の root 3,226 のうち解析できない 118 件 (先頭命令のデコード 0 件) の由来 → **§10 で測定** (呼び出し元の直接 call/jmp 命令は命令境界・着地点は含む関数の命令境界でない: pdata 内 112 件・pdata 外 6 件) | 118 件は vectorcall 判定の対象外 (陰性の結果は 3,108 関数の範囲に限る)。**なぜ命令境界でないかは未確定** | [MX-53] (#4992) |
| U4a | FH4 (`__CxxFrameHandler4`・符号化 FuncInfo) の funclet 未解析 (1 本目 .pdata 全体 2,542 entry・入口 1 / 1-round 5)。固定部は §8 で復号済み、可変長整数・table 中身が未了 | FH4 の landing pad が一覧に入らない | [MX-42] (#3807・親 #3791) |
| U4b | 1 本目の読取不能 160 件の由来 (UnwindInfoAddress が画像外・E8 始まり 148 件)。配布 PE の改変か展開の誤りかは未確定 (§3・`REPORT_APPENDIX_3792.md`)。2 本目の census は MX-41 で済 | 1 本目 .pdata 全体の chained / EH 数値は 160 件を除いた下界 | [MX-38] (#3775) |
| U4c | IAT 外の handler (direct) 6,354 件 (1 本目 .pdata 全体) の同定。構造は測定済み: 相異なる handler 番地は 214 件・うち上位 2 番地 (`0x1cdd2c4` 5,066 件・`0x1ebf5f0` 952 件) で 6,018 件。上位 2 番地の先頭の call 先 (JSON `top_handlers` の `call_target`) (`0x29b993f`・`0x2b9bc90`) は、どちらも .pdata の関数入口ではなく含む関数の内側。命令境界の判定は `0x29b993f` が一致・`0x2b9bc90` が不一致 (含む関数の先頭からの線形走査。未確定)。**測定の出所**: 測定 commit 62a3fda35・入力 = `plugins-massivex` の `Massive X.vst3` (md5 `622993e7` 一致)・実行 `python3 tools/targets/massivex/dsp/scripts/mx38_direct_handler.py <PE> <out.json>`。`mx6_e2e.sh` は `mx38_direct_handler.py` を呼ばないため、この数値は **e2e 外の別スクリプトの実測** (§1 の e2e 値ではない)。 | 別 handler の EH 構造が未確認 | [MX-38] (#3775) |
| U4f | census から除外した行 36 件 (1 本目 33 = st==0 9・e≤st 23・同じ st の重複 1、2 本目 3 = st==0 2・e≤st 1) の由来と、同じ st の重複 1 組 (st `0x039373E0`) の選択 | 1 本目の EH 件数 23,293 は重複の選択に依存 (±1)。除外行は census の母数に入らない | [MX-38] (#3775) |
| U4d | funclet を指す E8/E9 一致候補 4 件の由来 (命令境界を確認して、どの関数から来るか) と、深い closure での到達 | #228 同型の判定を closure 拡張で確定できない | **`REPORT_APPENDIX_3776.md` §9 で測定済み (MX-39 #3776)** |
| U4e | funclet の x64c closure への取り込み (#228 の landing pad 方式を MSVC に当てる実装) | 同型の欠陥が lift 出力に現れる (未修復) | **受入 1 (root 追加・36,240 件 lift) は [MX-43] (#3838) で実測 (`REPORT_APPENDIX_3776.md` §9.7)。SjLj runtime は [MX-45] (#4161)、通し一致は [MX-46] (#4162)** |

## 7. 検証 commit と差分 (docs/WORKFLOW.md §6)

- 最後に e2e を実測した commit = **62a3fda35** (コードを変えた最後の commit・PR #4781 の単一 commit)。実測の範囲と限界は §1。
- 測定後のコード差分: `git diff 62a3fda35 HEAD -- tools/targets/massivex/dsp/scripts tools/targets/massivex/dsp/mx6_e2e.sh` の出力は 0 行 (docs/WORKFLOW.md §6)。
- 直前の測定 3afa6013d から 62a3fda35 までの、e2e が呼ぶスクリプトの差分: `mx33_xmm03.py` (工程 4) と `mx6_vectorcall.py` (返し値 `cfg` の追加のみ)。`git diff --stat 3afa6013d 62a3fda35 -- tools/targets/massivex/dsp/scripts tools/targets/massivex/dsp/mx6_e2e.sh` の全体は 11 files (+1112 −34・U4c の新規スクリプト `mx38_direct_handler.py` を含む)。3afa6013d の工程別値は付録 A4。
- 素材: `plugins-massivex` を `$RUNNER_TEMP/mx` に展開 (`tar --zstd -xf`) → `parse_setup_headers.py <exe> <work>` → `extract_massivex.py <exe> <work> key` で `Massive X.vst3` (95,356,824 B・md5 `622993e76565f49c094063a2b717d6ca` 一致)。展開 125 件の md5-ok 0/125 は既知事象 (`tools/targets/massivex/REPORT.md` §8.1)。
- PR #4781 の run で実行したもの: 62a3fda35 の e2e (§1 の値)・`pr-lint.sh`。本 fix run (62a3fda35 → 修正 commit) では `plugins-massivex` が無く e2e を再実行していない。`bash -n` と `mx38_direct_handler.py` の `python3 -m py_compile` のみ実行。

## 8. FH4 FuncInfo4 の固定部 (U4a・#3791 部分)

- 測定 commit = **3afa6013d** (step 8/8 の値の出典。`mx6_fh4.py` は 3afa6013d から 62a3fda35 まで変更なし)。`scripts/mx6_fh4.py` は 81573d876 で追加し、51953f46d 以後は 62e3aefbe で非挙動の編集のみ (付録 `REPORT_APPENDIX_MX6_HISTORY.md` の A3)。再現: `bash tools/targets/massivex/dsp/mx6_e2e.sh` (step 8/8)。
- 構造の出典: MSVC 公式記事 "Making C++ Exception Handling Smaller On x64" (C++ Team Blog, 2019-03-07, https://devblogs.microsoft.com/cppblog/making-cpp-exception-handling-smaller-x64/) の FuncInfo4 定義 (`ehdata4_export.h` の抜粋)。
  header 1 byte の bit は LSB から isCatch / isSeparated / BBT / UnwindMap / TryBlockMap / EHs / NoExcept / reserved。
  bbtFlags (可変長・BBT のとき)、dispUnwindMap (UnwindMap のとき)、dispTryBlockMap (TryBlockMap のとき)、dispIPtoStateMap (常に)、dispFrame (可変長・isCatch のとき・末尾) の順。
  記事は整数の符号化と各 table の中身を書いていない (→ 未解決)。
- 実測 (`.pdata` 1 本目の FH4 entry 2,542 件・`mx6_fh4.py`・3afa6013d の e2e step 8 で再現):

| 項目 | 結果 |
|---|--:|
| FH4 entry / 相異なる FuncInfo (fi) | 2,542 / 2,117 (425 件は他と fi を共有) |
| header bit の組 (件数) | UnwindMap,EHs 2,094 / UnwindMap,EHs,NoExcept 154 / UnwindMap,TryBlockMap 119 / EHs,NoExcept 100 / UnwindMap,TryBlockMap,EHs 47 / isCatch,UnwindMap,TryBlockMap 10 / isCatch,UnwindMap,EHs,NoExcept 8 / UnwindMap,TryBlockMap,EHs,NoExcept 6 / isCatch,UnwindMap,EHs 4 |
| BBT が立つ entry | 0 件 (固定部の位置は全件で決まる) |
| dispIPtoStateMap (UnwindMap・TryBlockMap なしの 100 件) | fi+5 (直後) 99 件・他所 1 件 |
| dispUnwindMap | fi+9 (直後) 1,489 件・前方 35 件・後方または共有 918 件 |
| 固定部のポインタが画像外 | **2 件** (fi `0x64cbbe0`・`0x659b6e0`、header `0x28`、dispUnwindMap = `0xa0d2a1e9`・`0xadda9ce9`)。原因未確定 → [MX-42] (#3807) |

- NC (`mx6_fh4.py --selftest`): 3/3 PASS。(a) 正例: 既知の 2 件以外が全て通る。(b) 負例: 問題の無い 1 件の dispIPtoStateMap を 0 に壊すと `dispIPtoStateMap_outside_image` で FAIL。(c) 負例: BBT ビットを立てた合成ヘッダは固定部未解決として扱われる (位置を推測しない)。
- 実行: `MX_PE='$RUNNER_TEMP/mx/work/extracted/VST3/Massive X.vst3' MX6_WORK='$RUNNER_TEMP/massivex-mx6' bash tools/targets/massivex/dsp/mx6_e2e.sh` → exit 0 (測定 commit 3afa6013d・所要と load は §1)。
- 素材: `plugins-massivex` の `Native Instruments Massive X v1.7.1.exe` を展開し既存パーサで `Massive X.vst3` = 95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca` (§0 の記録値と一致)。
- 未解決 (起票先): 可変長整数の符号化、unwind map / try map / IP-to-state map の中身、funclet RVA の全数取り出し、独立再計算、2 件の画像外ポインタ → [MX-42] (#3807・親 #3791)。
- 検証差分 (docs/WORKFLOW.md §6): 測定 commit 62a3fda35 より後のコード差分は §7 のとおり (0 行)。

### 8.1 可変長整数 (compressed int) の符号化 (MX-48・#4787)

- 一次資料: `ehdata4_export.h` の公開写し (trcrsired/windows-msvc-sysroot `include/ehdata4_export.h`)。`ReadUnsigned` と `getNETencoded` の規則を `scripts/mx6_fh4_cint.py` に移植。先頭 byte の下位 4 bit で長さ L を決め、値は LE(bytes[pb:pb+L]) >> L (L=5 は flag 0x0F で、後続 4 byte の LE32)。pb は前から L 進める。`s_negLengthTab` と一致。
- 測定 commit = **3239e912d** (`scripts/mx6_fh4_cint.py` の追加のみ。素材 `plugins-massivex` の `Massive X.vst3` md5 `622993e7` 一致)。再現: `python3 scripts/mx6_fh4_cint.py --selftest` と `python3 scripts/mx6_fh4_cint.py "$PE" "$RUNNER_TEMP/fh4_cint.json"`。所要 3.6 秒・load 0.13→0.20。

| 項目 | 結果 |
|---|--:|
| NC (往復 20,014 値・連続読み 500 値・表との一致) | 3/3 PASS |
| FH4 entry / 相異なる fi | 2,542 / 2,117 |
| 固定部が読めない entry (既知の画像外 2 件) | 2 |
| UnwindMap entry (5,621 件・nextOffset の戻り先が state -1 (buffer 前) か entry 先頭) | 不整合 0 |
| TryBlockMap entry (185 件・tryLow ≤ tryHigh ≤ catchHigh) | 不整合 0 |
| IPtoStateMap entry (9,850 件) | 11 行 (fi 10 件・entry 数 1〜70) が関数範囲外 |

- IP map の 11 行は、2 本目以降の entry が関数長を超える (値が数千万から 4 億台)。fi 0x62ef3b0 は 2 行が共有する。確認した 4 件 (fi 0x6257284・0x62ef3b0・0x630bcc8・0x639080c) では dispIPtoStateMap が fi+9 または fi+27 にあり、funclet の範囲とずれている。残り 6 件は未確認。符号化の誤りとは断定できない (表の位置の割当て・別関数との共有の可能性)。**未解決**。
- 受入 1 の判定: 符号化そのものは一次資料どおり復号し、unwind / try は全件整合。IP map の 11 行を切り分けるまで「確定」とは書かない → `Refs #4787`。

## 9. MX-39 (#3776): 付録へ分割移動

MX-39 の深い closure 到達・E8/E9 候補の由来・MSVC funclet の取り込み方式 (U4d・U4e) の節 (§9) は付録 `REPORT_APPENDIX_3776.md` §9 にある (250 行上限のため分割移動)。

## 10. U3b / U3c の由来 (MX-53 #4992・受入 5)

- 測定 commit = **9d1672f57** (コードを変えた最後の commit。測定はこの commit のコードで実施)。実行: `bash tools/targets/massivex/dsp/mx6_e2e.sh` (step 9/9・`mx6_origin_u3.py`)。素材 `plugins-massivex` の `Massive X.vst3` md5 `622993e7` 一致。
- U3c (解析できない root 118 件): `mx6_vectorcall.analyze()` は先頭から 0 命令しかデコードできない root を捨てる (`n == 0`)。この 118 件は 1-round root 3,226 件の内訳で、seeds (567) には 0 件。

  | 項目 | 件数 |
  |---|--:|
  | root (1-round・相異なる) | 3,226 |
  | 先頭からのデコードが 0 命令 (= analyze が捨てる) | **118** |
  | うち、seeds の pdata 関数内の直接 call/jmp (E8/E9) の着地点 | **118** |
  | うち、その直接 call/jmp 命令が出所関数の線形デコードの命令境界 | **118** |
  | うち、.pdata 関数の内側 (含む関数の先頭からの線形デコードで命令境界か) | 112 (うち命令境界は 0 件・根拠は json の `boundary_in_containing_fn`。e2e の判定 `ok` には含めていない) |
  | うち、どの .pdata 関数にも含まれない | 6 |

  - 判別力の確認 (NC): 同じ含む関数内で、デコードできた 3,036 root のうち境界に当たるのは 1,613 件。「含む関数の境界でない」だけでは 118 件を分けられない。分けているのは「先頭からデコードできない」と「直接 call の着地点である」の組。
  - 例: `0x35b2` は `c7 48 89 d3 ...`。`c7 /1` は 64 bit で不正形のため、capstone はここで 0 命令を返す。`0x35b2` は `0x1f10` の `call 0x209d` の着地点で、`0x1f10` の call 命令 `0x209d` は命令境界。
  - **未確定**: 直接 call の着地点が命令の途中になるのは、正しい lift では通常起きない形。考えられるのは (a) 配布 PE 側の不整合 (U4b・MX-38 と同じ型) (b) call の rel32 を別の base で解釈した (c) 線形デコードの同期ずれ (出所関数の先頭からの走査が、その関数の真の命令列と一致しない)。 (a)〜(c) を区別する測定は本 run では行っていない → 起票先 [MX-38] (#3775)。

- U3b (間接 jmp の残り): `mx6_vectorcall.jt_targets` が解決できない jmp を含む関数 (= analyze の `unknown_flow`)。

  | 集合 | unknown_flow 関数 | うち pdata 始点 | jmp の形 (件数) |
  |---|--:|--:|---|
  | seeds | 12 | 12 | `reg_no_table` 9・`mem_indirect` 3 |
  | 1-round | 53 | 14 | `reg_no_table` 40・`mem_indirect` 27・`table_shape_unmatched` 6 |

  - `reg_no_table` (レジスタ経由の tail jmp・vtable 呼出し) と `mem_indirect` (`jmp [rax+N]` 等の vtable 末尾) は、テーブル形ではない。解決器の対象外。
  - `table_shape_unmatched` (6 件・1-round のみ) は、近傍に `movsxd` と `add` があるが解決器の形に合わない。switch の別形と見られる。未確定の形のため、件数だけを記録する。
  - seeds の pdata 始点の unknown_flow 12 件は、`mx6_vectorcall` の 12 件 (`unknown_flow=12`) と一致する。

- 判定への影響: U3c の 118 件は解析対象外のまま (陰性の結果は 3,108 関数の範囲に限る)。U3b の 53 件 (1-round) は過大近似側に残るため、livein の陰性の保守性は保たれる (精度は未確定)。
- 検証差分 (docs/WORKFLOW.md §6): 測定 commit 9d1672f57 から HEAD までのコード差分 `git diff 9d1672f57 HEAD -- tools/targets/massivex/dsp/scripts tools/targets/massivex/dsp/mx6_e2e.sh` は 0 行 (測定時点のコードと一致)。`mx6_origin_u3.py` と `mx6_e2e.sh` (step 9 の追加・番号 /8→/9) は測定 commit 9d1672f57 で入っている。既存 step 1〜8 の値は変えていない。
