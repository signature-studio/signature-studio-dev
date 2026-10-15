# Massive X MX-6 (#1123): vectorcall 独自規約と MSVC EH funclet の静的解析

- 解析日: 2026-10-14 / 担当: `tools/targets/massivex/dsp/` (生成物は repo 外 `$RUNNER_TEMP`・gitignore 対象は触らない)
- 素材: `plugins-massivex` の `Native Instruments Massive X v1.7.1.exe` を repo 内の既存パーサ
  (`tools/targets/massivex/scripts/parse_setup_headers.py` → `extract_massivex.py <exe> <work> key`) で展開。
  `Massive X.vst3` = 95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca` (REPORT §0 の記録値と一致)。
- 前回 run の「素材を展開できない」停止は誤り (innoextract のみで判断していた)。本 run は既存パーサで展開済み。
- 測定 commit (コードを変えた最後の commit) = **fbc9971f**。再現: `bash tools/targets/massivex/dsp/mx6_e2e.sh` (`MX_PE` で PE を指定)。

## 0. 結論 (先出し)

1. **vectorcall (受入 1・U3)**: 入口 (pdata 始点) の関数で、入口から書かれる前に xmm4/xmm5 を読むものは **0 件**
   (seeds 566 件・1-round closure 604 件)。独自規約 (5 番目以降の vector/HVA 引数) を持つ入口関数は検出されず。
   ただし **xmm0〜3 だけの vectorcall は Win64 と区別できず判定不能** (pdata 始点で各 17 件を保留・§2 限界)。
2. **chained .pdata (受入 2・U4)**: 1 本目の .pdata 全体 (entry 187,060 件・§3) のうち UNW_FLAG_CHAININFO は **62,526 件 (33.4%・分子と分母は同じ範囲)**。
   2 本目 (158,952 B) は census の対象外 (U4b)。入口 seeds の pdata 始点 566 件には chained 子は **0 件**。EH handler を持つ入口関数は 248 件
   (`__CxxFrameHandler3` 247 / `__CxxFrameHandler4` 1)。
3. **funclet 一覧 (受入 2)**: FH3 の FuncInfo (x64 RVA 形) から catch 本体と cleanup action の funclet RVA を取ると、
   seeds 由来 **533 件** (pdata 始点 529)・1-round 由来を含む和集合 **537 件**。
4. **#228 同型判定 (受入 3)**: **同型あり**。funclet 537 件のうち 1-round CFG closure に入るものは **0 件**、
   seeds にも 0 件。`.text` 全体の生バイトの E8/E9 走査 (命令境界を見ない) で funclet を指す一致候補は **4 件のみ** (直接参照とは未確認 → U4d)。
   残りは unwind 経由 (EH dispatch) でしか到達しない code で、CFG 降下 (x64c の closure) からは見えない。
   #228 (ICALL-2) の「landing pad は CFG 非到達」と同じ型。
5. **独立再計算・NC (受入 4)**: 合成バイト列の selftest 5 件 PASS (正例 3・負例 2)。線形走査 (CFG を使わない) の
   xmm4/5 参照関数数は 183 (seeds) / 1,296 (1-round) で、本体の上限と整合 (livein ⊆ anyref を全件で確認)。
   ただし線形側も命令の読み書き集合 (`effects()`) と逆アセンブラを本体と共有するため、CFG 非依存の上限確認に限り、独立な検証ではない。
   感度: PE 上の非 begin 入口 302 件で livein 検出が発火 (検出器が実バイトで動くことの確認)。

## 1. 実測 (e2e, 測定 commit fbc9971f)

| 工程 | 結果 |
|---|---|
| NC selftest (合成バイト列) | 5/5 PASS |
| RTTI + 入口面 | seeds 567 / 1-round 3,226 (`dsp/REPORT.md` §2 注の e2e 再現値。同注の mx_closure.py 実測 3,227 とは 1 件違う) / pdata 186,960 (`mx_entry_surface.py` が .text 範囲と `e <= t_hi` で絞った数。§3 の 187,060 は絞らない 1 本目の全 entry で、差 100) |
| vectorcall 検出 | seeds: pdata 始点 livein45 = 0 / one-round: pdata 始点 livein45 = 0 |
| unwind census | 1 本目の .pdata 全体: entry 187,060 / chained 62,526 / EH 23,293 / 読取不能 160 |
| funclet | seeds 533 / 和集合 537 / 線形直接参照 4 |
| 判定 | PASS (pdata 始点の vectorcall livein 0 かつ整合 OK) |

- 所要 **28.0 s** (測定 commit fbc9971f・同一 PE)。load average: 0.31 0.37 0.36 → 0.54 0.42 0.37。
- 実行: `MX_PE='$RUNNER_TEMP/.../Massive X.vst3' MX6_WORK='$RUNNER_TEMP/massivex-mx6' bash tools/targets/massivex/dsp/mx6_e2e.sh` → exit 0。

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
本 run では未実装。→ [MX-33] (#3032) で扱う。
関数範囲外への直接 jmp は `analyze` で経路を打ち切る (`idx` に無い target は後続に入らない)。範囲外の読みは見えず、closure がその target を root に含むことに依存する。

## 3. unwind census (U4)

- 「1 本目の .pdata 全体」= `.pdata` section の先頭 (file 順) の全 entry (st≠0・e>st の 187,060 件)。2 本目 (158,952 B) は含まない (U4b)。以下の「全体」はこの範囲。

| 集合 | pdata 始点 | chained 子 (CHAININFO) | EH handler | 内訳 |
|---|--:|--:|--:|---|
| 1 本目 .pdata 全体 | 187,060 entry | 62,526 | 23,293 | FH3 14,381 / FH4 2,542 / `__C_specific_handler` 16 / IAT 外 (direct) 6,354 |
| seeds | 566 | **0** | 248 | FH3 247 / FH4 1 |
| 1-round | 604 | 1 | 256 | FH3 248 / FH4 5 / direct 3 |

- handler は `jmp [rip+X]` の thunk から IAT 名を引いた (`walk_imports`: pefile の import 表は 30 DLL で打ち切られるため手動で辿る)。
- 読取不能 160 件 (1 本目 .pdata 全体): `.pdata` の 2 本目の VirtualSize が `.xdata` の VA 範囲と重なる。読取は raw データを持つセクションを優先
  (`make_rva_reader`)。残り 160 件の原因は未確定 → [MX-33] (#3032)。

## 4. funclet と #228 同型判定 (U4・受入 2・3)

- 取得: FH3 の FuncInfo (`magic 0x19930520〜0x19930522`) → `maxState` の unwind map の action と、try block の
  handler 配列の `dispOfHandler` (x64 は RVA 形)。`funclets_fh3()` (`mx6_pdata_eh.py`)。
- 妥当性 (positive control): 取れた funclet 533 件中 **529 件が pdata 始点、529 件が pdata 範囲内**
  (残り 4 件は pdata 範囲外・原因未確定 → [MX-33] (#3032))。解析が無作為な番地を拾っていないことの確認。
- closure 判定: funclet は 1-round CFG closure に **0/537**、seeds に 0/537。
  `.text` 全体の生バイトの E8/E9 走査 (命令境界を見ない) で funclet を指す一致候補は **4 件**。直接参照とは断定せず、由来と到達は U4d で確認する (CFG で辿れない・unwind 経由が主と見ている)。
- 判定: **#228 と同型** (CFG 非到達の landing pad が unwind 情報からしか到達しない)。
  件数は FLEngine (#228 の 879 site) より小さいが、同じ欠陥類型として扱う。同型の既知例は #228 (ICALL-2) の landing pad (CFG 非到達)
  で、類型の記述は `tools/icall/REPORT.md` の類型表 D12 (Delphi landing pad 非到達・FLEngine 879 site) が正本。
  `docs/DEFECTS.md` の D12 は別の harness 欠陥 (ABI 毒入れ) で、landing pad の行は無い。
  `docs/DEFECTS.md` に横断行を足さない理由: 同型は D12 として記録済みで、同じ欠陥を二重に書かないため。MSVC 固有の差 (FH3 funclet の到達) は #3032 の確定後に判断する。

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
| U3a | xmm0〜3 のみの vectorcall (HVA / `__m128` の register 渡し) を Win64 と区別する判定 | seeds 17 / 1-round 17 (pdata 始点) が保留 | [MX-33] (#3032) |
| U3b | 間接 jmp テーブルの残り (seeds 12 / 1-round 14 の pdata 始点が過大近似のまま。解決器は MSVC の lea 形のみ) | 陰性の保守性は保つが精度は未確定 | [MX-33] (#3032) |
| U3c | 1-round の root 3,226 のうち解析できない 118 件 (先頭命令のデコード 0 件) の由来 | 118 件は vectorcall 判定の対象外 (陰性の結果は 3,108 関数の範囲に限る) | [MX-33] (#3032) |
| U4a | FH4 (`__CxxFrameHandler4`・符号化 FuncInfo) の funclet 未解析 (1 本目 .pdata 全体 2,542 entry・入口 1 / 1-round 5) | FH4 の landing pad が一覧に入らない | [MX-33] (#3032) |
| U4b | `.pdata` 2 本目 (158,952 B・`.xdata` と VA 重なり) が census の対象外・読取不能 160 件の原因未確定 | 1 本目 .pdata 全体の数値は下界 | [MX-33] (#3032) |
| U4c | IAT 外の handler (direct) 6,354 件 (1 本目 .pdata 全体) の同定 | 別 handler の EH 構造が未確認 | [MX-33] (#3032) |
| U4d | funclet を指す E8/E9 一致候補 4 件の由来 (命令境界を確認して、どの関数から来るか) と、深い closure での到達 | #228 同型の判定を closure 拡張で確定できない | **§8 で測定済み (MX-39 #3776)** |
| U4e | funclet の x64c closure への取り込み (#228 の landing pad 方式を MSVC に当てる実装) | 同型の欠陥が lift 出力に現れる (未修復) | **§8.4 で方式を記録 (MX-39 #3776)。実装は [MX-43] (子)** |

## 7. 検証 commit と差分 (docs/WORKFLOW.md §6)

- 測定 commit = **fbc9971f** (`dsp/scripts/mx6_*.py` と `dsp/mx6_e2e.sh` を最後に変えた commit)。
- `git diff fbc9971f HEAD -- tools/targets/massivex/dsp/scripts tools/targets/massivex/dsp/mx6_e2e.sh` は **0 行**
  (本 REPORT の commit は docs のみ。コードの変更は無い)。
- 検証: e2e は測定 commit fbc9971f で実行し PASS (§1)。差し戻し後の修正 run では `plugins-massivex` が無く PE を展開できず、e2e は再実行していない。NC selftest は修正後の HEAD で再実行し 5/5 PASS。

## 8. MX-39 (#3776): funclet の深い closure 到達・E8/E9 候補の由来・取り込み方式 (U4d・U4e)

- 測定 commit = **bb4ce18b2** (`dsp/mx39_e2e.sh` と `dsp/scripts/mx39_funclet_reach.py` を追加した commit)。再現: `MX_PE=<Massive X.vst3> MX6_WORK=<mx6 作業dir> bash tools/targets/massivex/dsp/mx39_e2e.sh` (前提: `mx6_e2e.sh` で RTTI json を作成済み)。
- 素材: `plugins-massivex` → `Native Instruments Massive X v1.7.1.exe` → `parse_setup_headers.py` / `extract_massivex.py` で `Massive X.vst3` (95,356,824 B、md5 `622993e7…`、§0 と一致)。展開先は repo 外 `$RUNNER_TEMP`。
- 実測 (e2e, bb4ce18b2): **所要 422 s**、load 1.00 0.94 0.83 (終了時)、exit 0。closure 2 本 (linear・flow) の固定点計算が大半 (flow 約 6.5 分)。

### 8.1 結論 (先出し)

1. **U4d(1) 由来**: `.text` の E8/E9 一致 (全 FH3 funclet 36,533 件が対象) は 213 件。命令境界で見ると **179 件は call/jmp rel32 (長さ 5、宛先一致)**、**34 件は別命令の途中** (NC: 境界判定で除外)。537 母数 (REPORT §4) に当たる **4 件は全て命令境界の call/jmp**。4 件の囲む関数 (pdata begin) は linear・flow いずれの closure にも入らず、由来は「closure 非到達の関数の中の直接辺」。
2. **U4d(2) 深い closure**: 2 round 以上で funclet は到達する (ただし少数)。537 母数では **2 件 (0x118c780・0x118d1f0) のみ**で、どちらも深さ 3 (元の入口は深さ 2)。残り 535 件は固定点でも到達しない。全 FH3 funclet 36,533 件では固定点で linear 119 件・flow 82 件のみ到達 (表 8.2)。
3. **U4e 取り込み**: §8.4 に方式を記録 (x64c の追加 root + #228 と同じ SjLj 形の呼出し)。実装は子 issue **[MX-43]**。

### 8.2 closure の深さ別の到達 (測定 commit bb4ce18b2)

| 集合 | round 0 | round 1 | round 2 | round 3 | 固定点 |
|---|--:|--:|--:|--:|--:|
| linear 入口数 | 567 | 3,227 | 12,973 | 59,522 | 472,313 (round 17) |
| flow 入口数 | 567 | 2,456 | 6,748 | 18,533 | 507,258 (round 34) |
| funclet 到達 (linear・36,533 中) | 0 | 1 | 9 | 44 | 119 |
| funclet 到達 (flow・36,533 中) | 0 | 1 | 5 | 9 | 82 |
| 537 母数の到達 (linear = flow) | 0 | 0 | 0 | 2 | 2 |

- 母数: funclet を持つ FH3 関数 13,525 / funclet 36,533 (`mx39_funclet_reach.py`)。537 母数 = round 1 の FH3 親の funclet (REPORT §4 と一致)。
- 上限・下限: linear は全域を decode する過大近似 (固定点の入口が pdata 関数数 186,960 を超える)。flow は制御フローで到達する命令だけの下限 (間接 jmp は未解決 `indirect_unres` を含む)。
- 棄却: FH3 FuncInfo 355 件は上限 (maxState > 0x1000 / nTry > 0x1000 / nCatch > 0x100) で棄却。537 母数は棄却の影響なし (537 を再現)。棄却の値の妥当性は未確認 (U4f)。

### 8.3 E8/E9 一致 4 件 (537 母数) の由来

| site (RVA) | 命令 | 宛先 funclet (親) | 囲む関数 | 囲む関数の closure 深さ | 宛先の到達 |
|---|---|---|---|---|---|
| 0x10c8beb | call | 0x1190b30 (0x1190ad0) | 0x10c8b40 (FH3 親) | なし (入口から flow で未到達 = EH 専用の block と見られる) | 未到達 |
| 0x1c9a51b | call | 0x118c780 (0x118c3c0) | 0x1c99c51 (非 FH3・非 funclet) | なし | 深さ 3 |
| 0x1c9afeb | call | 0x118d1f0 (0x118cee0) | 0x1c99c51 | なし | 深さ 3 |
| 0x10c6dab | jmp | 0x118ceb0 (0x118c940) | 0x10c6cb0 | なし | 未到達 |

- 4 件とも囲む関数は closure に入らず、宛先 2 件 (0x118c780・0x118d1f0) は別の直接辺 (深さ 2 の入口 0x1c9a1cd・0x1c9aa25 から) で深さ 3 に到達する。
- 境界の判定は linear 逆アセンブル (囲む関数の pdata begin から) と flow 到達 (begin から制御フロー) の両方で行った。

### 8.4 U4e: MSVC funclet の取り込み方式 (記録・実装は [MX-43])

- **方式**: #228 の landing pad 方式 (`tools/icall/landing/REPORT.md` §6・§8) を MSVC に当てる。Delphi と異なり MSVC の funclet は親範囲の外の独立 .pdata entry で、FH3 FuncInfo (`mx6_pdata_eh.funclets_fh3`) から RVA を取る。
  1. **x64c の追加 root**: FH3 funclet を追加入口として lift する (親の CFG に scope を取り込む処理 (landing §8-2①) は不要)。対象は固定点で flow 未到達の funclet (36,451 件)。
  2. **呼出し**: pad は関数として呼ぶ SjLj 形 (`@__lp_icall` / `@__lp_resume` 相当)。例外 runtime は FH3 FuncInfo の walk を移植する。
  3. **既到達の funclet** (flow 82 件) は通常 lift で足りるので pad 経路を重ねない (二重 lift を避ける)。
- **根拠**: MSVC funclet は FuncInfo (unwind action と catch handler) からしか到達しない (537 母数は直接辺 0 件、round 1 で 0 件)。SjLj 形は landing §6 の推奨と同じ。
- **未確認 (前提)**: MSVC funclet の呼出し ABI (unwinder が RDX に establisher frame を渡す形) は実機で未確認。landing §9-2 (OTT funclet の実行検証) と同じ未解決。
- **検証の要件 (子 issue)**: funclet 1 本以上の native vs wasm 通し一致 (landing §7 型)、既到達の 82 件と root 追加分の lift 件数を分けて報告。

### 8.5 未解決 (起票先)

| # | 未解決 | 影響 | 起票先 |
|---|---|---|---|
| U4f | FH3 FuncInfo 355 件の上限棄却 (maxState・nTry・nCatch) の妥当性 | 母数 36,533 の下界 | [MX-43] (子) |
| U4g | flow 到達 funclet の直接辺の元 82 件のうち 4 件 (FH3 親の関数) が funclet を通常フローで指す (ICF / tail-merge による共有か) | funclet と通常コードの境界 | [MX-43] (子) |
| U4h | 囲む関数 0x10c8b40 の EH 専用 block の位置 (親の pdata 範囲内か) | 親 pdata 範囲の定義 | [MX-43] (子) |
| U4i | MSVC funclet の呼出し ABI の実機確認 | §8.4 の前提 | [MX-43] (子) |

### 8.6 検証 (docs/WORKFLOW.md §6)

- 測定 commit = **bb4ce18b2**。`git diff bb4ce18b2 HEAD -- tools/targets/massivex/dsp/scripts tools/targets/massivex/dsp/mx39_e2e.sh` は本 REPORT の commit の後も **0 行** (docs のみ)。
- positive control: `mx6_e2e.sh` を HEAD で再実行し PASS (35 s、NC 5/5、seeds 567 / 1-round 3,226、funclet 537・直接参照 4 は §1 と一致)。
- NC: 境界判定の負例として E8/E9 一致 34 件 (別命令の途中) を除外。mx6 の合成バイト列 NC は 5/5 PASS (§5)。
