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
2. **chained .pdata (受入 2・U4)**: PE 全体 187,060 entry のうち UNW_FLAG_CHAININFO は **62,526 件 (33.4%)**。
   入口 seeds の pdata 始点 566 件には chained 子は **0 件**。EH handler を持つ入口関数は 248 件
   (`__CxxFrameHandler3` 247 / `__CxxFrameHandler4` 1)。
3. **funclet 一覧 (受入 2)**: FH3 の FuncInfo (x64 RVA 形) から catch 本体と cleanup action の funclet RVA を取ると、
   seeds 由来 **533 件** (pdata 始点 529)・1-round 由来を含む和集合 **537 件**。
4. **#228 同型判定 (受入 3)**: **同型あり**。funclet 537 件のうち 1-round CFG closure に入るものは **0 件**、
   seeds にも 0 件。`.text` 全体の線形 E8/E9 走査でも funclet への直接 call/jmp は **4 件のみ**。
   残りは unwind 経由 (EH dispatch) でしか到達しない code で、CFG 降下 (x64c の closure) からは見えない。
   #228 (ICALL-2) の「landing pad は CFG 非到達」と同じ型。
5. **独立再計算・NC (受入 4)**: 合成バイト列の selftest 5 件 PASS (正例 3・負例 2)。線形 (CFG 非依存) の
   xmm4/5 参照関数数は 183 (seeds) / 1,296 (1-round) で、本体の上限として整合 (livein ⊆ anyref を全件で確認)。
   感度: PE 上の非 begin 入口 302 件で livein 検出が発火 (検出器が実バイトで動くことの確認)。

## 1. 実測 (e2e, HEAD fbc9971f)

| 工程 | 結果 |
|---|---|
| NC selftest (合成バイト列) | 5/5 PASS |
| RTTI + 入口面 | seeds 567 / 1-round 3,226 / pdata 186,960 (REPORT §2 の再現値と一致) |
| vectorcall 検出 | seeds: pdata 始点 livein45 = 0 / one-round: pdata 始点 livein45 = 0 |
| unwind census | PE: pdata 187,060 / chained 62,526 / EH 23,293 / 読取不能 160 |
| funclet | seeds 533 / 和集合 537 / 線形直接参照 4 |
| 判定 | PASS (pdata 始点の vectorcall livein 0 かつ整合 OK) |

- 所要 **28.0 s** (HEAD fbc9971f・同一 PE)。load average: 0.31 0.37 0.36 → 0.54 0.42 0.37。
- 実行: `MX_PE='$RUNNER_TEMP/.../Massive X.vst3' MX6_WORK='$RUNNER_TEMP/massivex-mx6' bash tools/targets/massivex/dsp/mx6_e2e.sh` → exit 0。

## 2. vectorcall 静的検出 (U3)

判定の定義: 入口からの CFG 上で must-def (全経路で書かれている集合) を取り、書かれていない xmm_k の読みを検出
(`dsp/scripts/mx6_vectorcall.py`)。Win64 の引数レジスタは xmm0〜3 のみなので、xmm4/5 の入口 livein は
独自規約の強い根拠になる。

| 集合 | 関数 | pdata 始点 | livein xmm4/5 (pdata 始点) | xmm0〜3 のみ (保留) | 解析 flow 未解決 (pdata 始点) | 線形 anyref 上限 |
|---|--:|--:|--:|--:|--:|--:|
| seeds (入口面) | 567 | 566 | **0** | 17 | 12 | 183 |
| 1-round closure | 3,108 | 604 | **0** | 17 | 14 | 1,296 |

- 1-round の livein xmm4/5 のうち 302 件は **pdata 始点でない途中アドレス**を入口にした結果 (途中の定義を見ないため)。
  pdata 始点の判定には使わない。PE 上の感度確認としてのみ扱う。
- 間接 jmp: MSVC の相対 int32 テーブル形 (`lea` 基底・`cmp` 境界・`movsxd`/`add`) を解決 (seeds 11 件・1-round 24 件)。
  解決できない間接 jmp は全命令への後続と見なす (過大近似。livein の偽陽性側にだけ誤差が出る。陰性結果は保守側)。
  途中の検討で 3 件の偽陽性 (switch 後続の過大近似による) を確認し、解決器を入れて消した。
- 呼出側の根拠: xmm4/5 が call 前に (経路上で) 書かれる直接 call は seeds 716 / 1-round 2,809 (`call_args`)。

**限界 (未解決)**: xmm0〜3 だけを使う vectorcall (HVA / `__m128` を xmm0〜3 に載せる形) は Win64 の float 引数と
区別できない。`__m128` の by-pointer (Win64) と by-register (vectorcall) の差は memory 参照の有無で見分けるが、
本 run では未実装。→ [MX-33] で扱う。

## 3. unwind census (U4)

| 集合 | pdata 始点 | chained 子 (CHAININFO) | EH handler | 内訳 |
|---|--:|--:|--:|---|
| PE 全体 | 187,060 entry | 62,526 | 23,293 | FH3 14,381 / FH4 2,542 / `__C_specific_handler` 16 / IAT 外 (direct) 6,354 |
| seeds | 566 | **0** | 248 | FH3 247 / FH4 1 |
| 1-round | 604 | 1 | 256 | FH3 248 / FH4 5 / direct 3 |

- handler は `jmp [rip+X]` の thunk から IAT 名を引いた (`walk_imports`: pefile の import 表は 30 DLL で打ち切られるため手動で辿る)。
- 読取不能 160 件 (PE 全体): `.pdata` の 2 本目の VirtualSize が `.xdata` の VA 範囲と重なる。読取は raw データを持つセクションを優先
  (`make_rva_reader`)。残り 160 件の原因は未確定 → [MX-33]。

## 4. funclet と #228 同型判定 (U4・受入 2・3)

- 取得: FH3 の FuncInfo (`magic 0x19930520〜0x19930522`) → `maxState` の unwind map の action と、try block の
  handler 配列の `dispOfHandler` (x64 は RVA 形)。`funclets_fh3()` (`mx6_pdata_eh.py`)。
- 妥当性 (positive control): 取れた funclet 533 件中 **529 件が pdata 始点、529 件が pdata 範囲内**
  (残り 4 件は pdata 範囲外・原因未確定 → [MX-33])。解析が無作為な番地を拾っていないことの確認。
- closure 判定: funclet は 1-round CFG closure に **0/537**、seeds に 0/537。
  `.text` 全体の線形 E8/E9 走査で funclet への直接参照は **4 件** (CFG で辿れない・unwind 経由が主)。
- 判定: **#228 と同型** (CFG 非到達の landing pad が unwind 情報からしか到達しない)。
  件数は FLEngine (#228 の 879 site) より小さいが、同じ欠陥類型として扱う。既存の類型表 (DEFECTS.md の D12 は別の
  harness 欠陥) への新規行は、同型が既知 (#228) のため追加しない。

## 5. 独立再計算・ネガティブコントロール (受入 4)

- 本体 (CFG must-def) と独立再計算 (線形走査で xmm4/5 を参照する関数の上限) を同じ入力で比較。
  `anyref` 183 (seeds) / 1,296 (1-round) で、線形側が本体の上限として一致。livein ⊆ anyref を全件で確認 (`consistency=True`)。
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
| U3a | xmm0〜3 のみの vectorcall (HVA / `__m128` の register 渡し) を Win64 と区別する判定 | seeds 17 / 1-round 17 (pdata 始点) が保留 | [MX-33] |
| U3b | 間接 jmp テーブルの残り (seeds 12 / 1-round 14 の pdata 始点が過大近似のまま。解決器は MSVC の lea 形のみ) | 陰性の保守性は保つが精度は未確定 | [MX-33] |
| U4a | FH4 (`__CxxFrameHandler4`・符号化 FuncInfo) の funclet 未解析 (PE 全体 2,542 entry・入口 1 / 1-round 5) | FH4 の landing pad が一覧に入らない | [MX-33] |
| U4b | `.pdata` 2 本目 (158,952 B・`.xdata` と VA 重なり) が census の対象外・読取不能 160 件の原因未確定 | PE 全体の数値は下界 | [MX-33] |
| U4c | IAT 外の handler (direct) 6,354 件 (PE 全体) の同定 | 別 handler の EH 構造が未確認 | [MX-33] |
| U4d | funclet 直接参照 4 件の由来 (どの関数から来るか) と、深い closure での到達 | #228 同型の判定を closure 拡張で確定できない | [MX-33] |
| U4e | funclet の x64c closure への取り込み (#228 の landing pad 方式を MSVC に当てる実装) | 同型の欠陥が lift 出力に現れる (未修復) | [MX-33] |

## 7. 検証 commit と差分 (docs/WORKFLOW.md §6)

- 測定 commit = **fbc9971f** (`dsp/scripts/mx6_*.py` と `dsp/mx6_e2e.sh` を最後に変えた commit)。
- `git diff fbc9971f HEAD -- tools/targets/massivex/dsp/scripts tools/targets/massivex/dsp/mx6_e2e.sh` は **0 行**
  (本 REPORT の commit は docs のみ。コードの変更は無い)。
- 検証は HEAD (fbc9971f) で e2e を再実行して PASS を確認した (§1)。
