# Massive X MX-6 (#1123): vectorcall 独自規約と MSVC EH funclet の静的解析

- 解析日: 2026-10-14 / 担当: `tools/targets/massivex/dsp/` (生成物は repo 外 `$RUNNER_TEMP`・gitignore 対象は触らない)
- 素材: `plugins-massivex` の `Native Instruments Massive X v1.7.1.exe` を repo 内の既存パーサ
  (`tools/targets/massivex/scripts/parse_setup_headers.py` → `extract_massivex.py <exe> <work> key`) で展開。
  `Massive X.vst3` = 95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca` (REPORT §0 の記録値と一致)。
- 前回 run の「素材を展開できない」停止は誤り (innoextract のみで判断していた)。本 run は既存パーサで展開済み。
- 測定 commit = **51953f46d** (e2e の記録があるのはこの commit・§1a・§7)。その後に `mx6_fh4.py` の非挙動の編集 (docstring・未使用変数・`with`) と e2e の step 表記を入れた commit `62e3aefbe` がある。この commit の e2e 再測定は素材 (`plugins-massivex`) が無く本 run では未実施 (§7)。§1b は fbc9971f の旧測定 (参考・削除せず移動)。再現: `bash tools/targets/massivex/dsp/mx6_e2e.sh` (`MX_PE` で PE を指定)。

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

## 1. 実測 (e2e)

### 1a. 測定 commit 51953f46d (e2e 記録)

本 run では PE (`plugins-massivex`) が無く e2e を再実行していない。以下は 51953f46d の e2e 出力として PR #3815 本文に
記録された値。生ログは REPORT に残っていなかったため、記録が無い工程は「未記録」と書く (推定で埋めない)。

| step (`mx6_e2e.sh`) | 結果 |
|---|---|
| 1/8 NC selftest (合成バイト列・PE 不要) | 5/5 PASS (本 run で HEAD 上でも再確認: `mx6_vectorcall.py --selftest` rc=0) |
| 2/8 RTTI + 入口面 | 未記録 (seeds 567 / 1-round 3,226 は §0・§2 の値。51953f46d の出力としての照合は未了) |
| 3/8 vectorcall | xmm4/5 入口 livein = 0 (pdata 始点・記録) |
| 4/8 受入1 (MX-33) | 17 件 PASS (記録) |
| 5/8 .pdata census | chained 62,526 / EH 23,293 (記録) |
| 6/8 判定 | PASS (記録) |
| 7/8 positive control | funclet 533 / pdata 始点 529 (記録) |
| 8/8 FH4 固定部 | NC 3/3 PASS・entry 2,542 / fi 2,117・固定部 2,540 OK・画像外 2 件 (記録) |
| 所要・exit | exit 0・**43 s**・n=1・並列数 1 (単独直列実行)・load 0.02 0.16 0.18 → 0.57 0.29 0.22 |

### 1b. 参考: fbc9971f の旧測定 (5 step 構成・削除せず移動)

fbc9971f は 51953f46d の祖先だが、e2e の step 構成が違う (旧 5 step・`mx33_xmm03.py` 無し)。下表の値を 51953f46d の値として扱わない。

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
本 run では未実装。→ [MX-37] (#3774) で扱う。
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
  (`make_rva_reader`)。残り 160 件の原因は未確定 → [MX-38] (#3775)。

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
| U3a | xmm0〜3 のみの vectorcall (HVA / `__m128` の register 渡し) を Win64 と区別する判定 | seeds 17 / 1-round 17 (pdata 始点) が保留 | [MX-37] (#3774) |
| U3b | 間接 jmp テーブルの残り (seeds 12 / 1-round 14 の pdata 始点が過大近似のまま。解決器は MSVC の lea 形のみ) | 陰性の保守性は保つが精度は未確定 | [MX-37] (#3774) |
| U3c | 1-round の root 3,226 のうち解析できない 118 件 (先頭命令のデコード 0 件) の由来 | 118 件は vectorcall 判定の対象外 (陰性の結果は 3,108 関数の範囲に限る) | [MX-37] (#3774) |
| U4a | FH4 (`__CxxFrameHandler4`・符号化 FuncInfo) の funclet 未解析 (1 本目 .pdata 全体 2,542 entry・入口 1 / 1-round 5)。固定部は §8 で復号済み、可変長整数・table 中身が未了 | FH4 の landing pad が一覧に入らない | [MX-42] (#3807・親 #3791) |
| U4b | `.pdata` 2 本目 (158,952 B・`.xdata` と VA 重なり) が census の対象外・読取不能 160 件の原因未確定 | 1 本目 .pdata 全体の数値は下界 | [MX-38] (#3775) |
| U4c | IAT 外の handler (direct) 6,354 件 (1 本目 .pdata 全体) の同定 | 別 handler の EH 構造が未確認 | [MX-38] (#3775) |
| U4d | funclet を指す E8/E9 一致候補 4 件の由来 (命令境界を確認して、どの関数から来るか) と、深い closure での到達 | #228 同型の判定を closure 拡張で確定できない | [MX-39] (#3776) |
| U4e | funclet の x64c closure への取り込み (#228 の landing pad 方式を MSVC に当てる実装) | 同型の欠陥が lift 出力に現れる (未修復) | [MX-39] (#3776) |

## 7. 検証 commit と差分 (docs/WORKFLOW.md §6)

- 測定 commit = **51953f46d** (main 取り込み後の merge・e2e 記録の commit・§1a)。
- 測定後のコード差分: commit `62e3aefbe` (`mx6_fh4.py` の docstring・未使用変数・`with`、`mx6_e2e.sh` の step 表記 /7→/8 のラベル)。
  出力 (`git diff -U0 51953f46d HEAD -- tools/targets/massivex/dsp/scripts tools/targets/massivex/dsp/mx6_e2e.sh`・`index` 行は省略):

```diff
diff --git a/tools/targets/massivex/dsp/mx6_e2e.sh b/tools/targets/massivex/dsp/mx6_e2e.sh
--- a/tools/targets/massivex/dsp/mx6_e2e.sh
+++ b/tools/targets/massivex/dsp/mx6_e2e.sh
@@ -17 +17 @@ T0=$(date +%s)
-echo "== 1/7 NC: 合成バイト列の正例・負例 (PE 不要)"
+echo "== 1/8 NC: 合成バイト列の正例・負例 (PE 不要)"
@@ -20 +20 @@ python3 "$DSP/scripts/mx6_vectorcall.py" --selftest | sed 's/^/   /'
-echo "== 2/7 RTTI + VST3 入口面 (seeds 567 / 1-round closure)"
+echo "== 2/8 RTTI + VST3 入口面 (seeds 567 / 1-round closure)"
@@ -25 +25 @@ python3 "$DSP/scripts/mx_entry_surface.py" "$PE" "$W/rtti_vtables.json" "$W/surf
-echo "== 3/7 vectorcall 静的検出 (本体: CFG must-def / 独立再計算: 線形 anyref / 感度: 非 begin 入口)"
+echo "== 3/8 vectorcall 静的検出 (本体: CFG must-def / 独立再計算: 線形 anyref / 感度: 非 begin 入口)"
@@ -28 +28 @@ python3 "$DSP/scripts/mx6_vectorcall.py" "$PE" "$W/surface_seeds_x64c.json" "$W/
-echo "== 4/7 受入1 (MX-33 #3032): xmm0〜3 だけの入口 livein 保留 17 件の判定 (NC 9 件・独立再計算・感度)"
+echo "== 4/8 受入1 (MX-33 #3032): xmm0〜3 だけの入口 livein 保留 17 件の判定 (NC 9 件・独立再計算・感度)"
@@ -32 +32 @@ grep -v '^| ' "$W/xmm03.log" | sed 's/^/   /'
-echo "== 5/7 .pdata unwind census (CHAININFO / EH handler 名)"
+echo "== 5/8 .pdata unwind census (CHAININFO / EH handler 名)"
@@ -36 +36 @@ python3 "$DSP/scripts/mx6_pdata_eh.py" "$PE" "$W/surface_seeds_x64c.json" "$W/su
-echo "== 6/7 判定 (期待値: seeds と 1-round の pdata 始点で xmm4/5 入口 livein = 0 / 受入1 の内訳が 17 件)"
+echo "== 6/8 判定 (期待値: seeds と 1-round の pdata 始点で xmm4/5 入口 livein = 0 / 受入1 の内訳が 17 件)"
@@ -48 +48 @@ PY
-echo "== 7/7 positive control: funclet 数の固定値 (MX-6 測定値 seeds 533 / pdata 始点 529 が変わらないこと)"
+echo "== 7/8 positive control: funclet 数の固定値 (MX-6 測定値 seeds 533 / pdata 始点 529 が変わらないこと)"
diff --git a/tools/targets/massivex/dsp/scripts/mx6_fh4.py b/tools/targets/massivex/dsp/scripts/mx6_fh4.py
--- a/tools/targets/massivex/dsp/scripts/mx6_fh4.py
+++ b/tools/targets/massivex/dsp/scripts/mx6_fh4.py
@@ -59,3 +59,2 @@ def validate(rd, fi, in_image):
-    """固定部の検査 (独立した 3 条件): (a) 固定部が読める (BBT なし) (b) 各ポインタが画像内 (c) ポインタの順序が
-    構造の並び (dispUnwindMap < dispTryBlockMap < dispIPtoStateMap は必須ではないが、各ポインタは重ならない)。
-    戻り値は違反の list (空なら OK)。"""
+    """固定部の検査 (独立した 3 条件): (a) 固定部が読める (BBT なし) (b) 各ポインタが画像内 (c) 固定部のポインタ値が
+    互いに重複しない (同値の検出のみ。範囲の重なりは見ない)。戻り値は違反の list (空なら OK)。"""
@@ -68 +67 @@ def validate(rd, fi, in_image):
-    for n, (o, v) in f.items():
+    for n, (_, v) in f.items():
@@ -85 +84 @@ def image_checker(pe):
-def fh4_entries(pe, data, rd):
+def fh4_entries(pe, rd):
@@ -117 +116,2 @@ def census(pe_path):
-    data = open(pe_path, 'rb').read()
+    with open(pe_path, 'rb') as fp:
+        data = fp.read()
@@ -120 +120 @@ def census(pe_path):
-    base, rows = fh4_entries(pe, data, rd)
+    base, rows = fh4_entries(pe, rd)
@@ -149 +149,3 @@ def census(pe_path):
-KNOWN_OPEN = 2  # 画像外の dispUnwindMap を持つ 2 件 (原因未確定・REPORT_MX6 §8)
+# 画像外の dispUnwindMap を持つ 2 件 (原因未確定・REPORT_MX6 §8)。解消すると正例が FAIL するので、
+# 解消したら KNOWN_OPEN と REPORT_MX6 §8 を同じ commit で更新する。
+KNOWN_OPEN = 2
```

- 再測定 (未了): commit `62e3aefbe` の e2e は本 run で PE が無く未実行。HEAD で再確認したのは PE 不要の step 1 のみ (`mx6_vectorcall.py --selftest` 5/5 PASS・rc=0)。
  `mx6_fh4.py` は旧版との AST 比較で、差分が docstring・未使用変数の削除・`with` 化だけであることを確認 (挙動は変えない)。
  step 8 の selftest と census は PE が必要で未実行。素材を付けた review run で照合する。
- 検証 (測定 commit 51953f46d の記録): e2e 全件 PASS・exit 0 (§1a)。NC selftest は step 1 (5/5)・step 4 (9/9)・step 8 (3/3) すべて PASS (記録)。

## 8. FH4 FuncInfo4 の固定部 (U4a・#3791 部分)

- 測定 commit = **51953f46d** (記録)。`scripts/mx6_fh4.py` は 81573d876 で追加し、51953f46d 以後は 62e3aefbe で非挙動の編集のみ (§7)。再現: `bash tools/targets/massivex/dsp/mx6_e2e.sh` (step 8/8)。
- 構造の出典: MSVC 公式記事 "Making C++ Exception Handling Smaller On x64" (C++ Team Blog, 2019-03-07, https://devblogs.microsoft.com/cppblog/making-cpp-exception-handling-smaller-x64/) の FuncInfo4 定義 (`ehdata4_export.h` の抜粋)。
  header 1 byte の bit は LSB から isCatch / isSeparated / BBT / UnwindMap / TryBlockMap / EHs / NoExcept / reserved。
  bbtFlags (可変長・BBT のとき)、dispUnwindMap (UnwindMap のとき)、dispTryBlockMap (TryBlockMap のとき)、dispIPtoStateMap (常に)、dispFrame (可変長・isCatch のとき・末尾) の順。
  記事は整数の符号化と各 table の中身を書いていない (→ 未解決)。
- 実測 (`.pdata` 1 本目の FH4 entry 2,542 件・`mx6_fh4.py`):

| 項目 | 結果 |
|---|--:|
| FH4 entry / 相異なる FuncInfo (fi) | 2,542 / 2,117 (425 件は他と fi を共有) |
| header bit の組 (件数) | UnwindMap,EHs 2,094 / UnwindMap,EHs,NoExcept 154 / UnwindMap,TryBlockMap 119 / EHs,NoExcept 100 / UnwindMap,TryBlockMap,EHs 47 / isCatch,UnwindMap,TryBlockMap 10 / isCatch,UnwindMap,EHs,NoExcept 8 / UnwindMap,TryBlockMap,EHs,NoExcept 6 / isCatch,UnwindMap,EHs 4 |
| BBT が立つ entry | 0 件 (固定部の位置は全件で決まる) |
| dispIPtoStateMap (UnwindMap・TryBlockMap なしの 100 件) | fi+5 (直後) 99 件・他所 1 件 |
| dispUnwindMap | fi+9 (直後) 1,489 件・前方 35 件・後方または共有 918 件 |
| 固定部のポインタが画像外 | **2 件** (fi `0x64cbbe0`・`0x659b6e0`、header `0x28`、dispUnwindMap = `0xa0d2a1e9`・`0xadda9ce9`)。原因未確定 → [MX-42] (#3807) |

- NC (`mx6_fh4.py --selftest`): 3/3 PASS。(a) 正例: 既知の 2 件以外が全て通る。(b) 負例: 問題の無い 1 件の dispIPtoStateMap を 0 に壊すと `dispIPtoStateMap_outside_image` で FAIL。(c) 負例: BBT ビットを立てた合成ヘッダは固定部未解決として扱われる (位置を推測しない)。
- 実行: `MX_PE='$RUNNER_TEMP/mx/work/extracted/VST3/Massive X.vst3' MX6_WORK='$RUNNER_TEMP/massivex-mx6' bash tools/targets/massivex/dsp/mx6_e2e.sh` → exit 0 (測定 commit 51953f46d・記録。§1a)。所要 **43 s** (n=1・並列数 1・単独直列実行。load average 0.02 0.16 0.18 → 0.57 0.29 0.22)。
- 素材: `plugins-massivex` の `Native Instruments Massive X v1.7.1.exe` を展開し既存パーサで `Massive X.vst3` = 95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca` (§0 の記録値と一致)。
- 未解決 (起票先): 可変長整数の符号化、unwind map / try map / IP-to-state map の中身、funclet RVA の全数取り出し、独立再計算、2 件の画像外ポインタ → [MX-42] (#3807・親 #3791)。
- 検証差分 (docs/WORKFLOW.md §6): 測定後のコード差分は §7 の出力のとおり (`62e3aefbe`・非挙動)。
