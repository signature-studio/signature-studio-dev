# MX-5 (#1122) .pdata chained 分割と leaf 境界近似の定量化

- 親: #266 / 起票: #1122 (MX-5)。本ファイルは #1122 の 1 run 分の実測。
- 素材: `plugins-massivex` → `work/extracted/VST3/Massive X.vst3` (95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca`、REPORT §11.1 と一致)。
- 計測スクリプト: `dsp/scripts/mx_pdata_quant.py` (e2e.sh の step 5/5)。

## 1. 今 run で達成した範囲 (受入 2・3 の計測部分)

受入条件のうち、本 run は **受入 2 (chained の実測) と受入 3 (leaf 近似の定量化)** の計測のみ。
受入 1・4 は未着手、受入 2 の「扱いの決定と実装」・受入 3 の「実 unwind への置換」は未達 (§4 の子 issue)。

## 2. 実測値 (.pdata 全数・1 回目 e2e 実行)

| 指標 | 値 | 意味 |
|---|--:|---|
| .pdata entry 総数 | 187,084 | `.pdata` の Misc_VirtualSize / 12 (テーブル 2,245,008 B = 187,084 × 12) |
| .text 内かつ e>b の entry | 186,961 | 旧 REPORT の 186,960 とは 1 件差 (下記 注 1) |
| **chained: begin == 直前 entry の end** | **70,489** | issue 本文の「70,533 件」とは 44 件差 (下記 注 2) |
| UNWIND_INFO に CHAININFO (Flags & 4) | 66,837 | 親 RUNTIME_FUNCTION を持つ entry |
| 親 entry が .pdata 内に実在 | 62,651 | |
| うち 親の (begin,end) が完全一致 | 62,498 | 残り 153 は親 begin は在るが end が不一致 |
| CHAININFO 付きだが親が .pdata に無い | 4,186 | 親 RVA が pdata 外 (未解決) |
| leaf 近似 (次 begin まで) = pdata end | 70,489 | 近似が正しいのは 37.7% (chained と一致) |
| leaf 近似 > pdata end (過大評価) | 116,460 | 過大評価の総バイト 2,618,866 B (= valid 186,961 entry の Σ(end−begin) 58,062,810 B の 4.51%・下記 注 3) |
| leaf 近似 < pdata end (過小評価) | 12 | |

len ヒストグラム (256 B 刻み): 0〜255 B が 143,802 件、4 KiB 以上が 2,581 件。

注 1: 旧 REPORT (§4 / §9) の 186,960 との 1 件差の原因は未確認 (本計測は `.text` 内 VA の条件・e>b で数える)。
注 2: 70,533 は issue 起票時の値。今回の e>b・.text 内条件での実測は 70,489。差 44 件の原因 (旧 CAB-263 の集計条件) は未確認。
注 3: 計測定義。`mx_pdata_quant.py` は valid entry (e>b・.text 内・e<=.text 末尾) を **begin で並べ替えた後**、直前 entry の end と次 begin を比べる (生の .pdata の並び順は使わない)。分母は `dsp/scripts/mx_pdata_denom.py` (本 fix run・素材 `plugins-massivex` の PE 上で実測) の値で、次の 2 通り:
  - valid 186,961 entry の Σ(end−begin) = **58,062,810 B** (本文の 4.51% の分母)
  - 同じ valid を begin で一意化 (186,960 関数) した Σ(end−begin) = **58,062,780 B**
  - 差 30 B は begin `0x39373e0` に (begin, end) が同一の entry が 2 件あるため (end `0x39373fe`・長さ 30 B・unwind RVA は 0x62f4a8c と 0x620b39c で別)。
  - 過大評価の割合: 2,618,866 / 58,062,810 = 4.51% (一意化の分母でも 4.51%)。.pdata テーブル本体 (2,245,008 B) は分母ではない。`dsp/REPORT.md` §4 の 58,062,780 B は一意化後の値。

## 3. 解釈

- CHAININFO の件数 (66,837 / 62,651 / 4,186) は全 valid entry 基準。chained entry (70,489) 基準の内訳は本 run では未集計 (次の子 issue で出す)。
- (begin,end) が親と完全一致する 62,498 件は、CHAININFO の親を使えば束ねられる候補。ただし chained 判定と CHAININFO の重なりは未計測。
- 親が pdata 外の 4,186 件と、親 begin は在るが end 不一致の 153 件は、この計測だけでは親を確定できない。
- leaf 近似は 116,460 件で pdata end より長い (過大評価 2,618,866 B)。`mx_closure.py` の区間は「次の入口まで」なので、closure のバイト数と target 判定へ与える影響は未測定 (U5)。

## 4. 未解決・起票先 (本 run の残り)

| 残件 | 受入 | 起票先 |
|---|---|---|
| chained の扱い (CHAININFO 親に束ねる規則) の決定と実装 | 2 | 子 issue (MX-8 = #1321) |
| 4,186 件の pdata 外親・153 件の end 不一致の解決 | 2 | 子 issue (MX-8 = #1321) |
| leaf 境界を実 unwind / 境界に置換 (過大評価 116,460 件の解消) | 3 | 子 issue (MX-8 = #1321) |
| code/data 区別 (jump table・文字列窓) を入れた再帰降下 と round 推移 | 1 | 子 issue (MX-8 = #1321) |
| process 起点 closure の確定値 | 4 | #266 (U1 process slot 同定) に依存。依存明記で未解決 |

## 5. 検証

- **測定 commit (実行時間)**: `0bcdcd15` (本 fix の検証 HEAD。素材 `plugins-massivex` を `$HOME/artifacts` から展開し `parse_setup_headers.py` → `extract_massivex.py key` で PE を再抽出、md5 `622993e7…` / 95,356,824 B を確認)。
- **実行時間 (n=3・`bash dsp/e2e.sh`・全回 rc 0・head `0bcdcd15`)**:

  | run | elapsed | load 開始 | load 終了 |
  |---|--:|---|---|
  | 1 | 34 s | 0.85 0.37 0.14 | 0.99 0.46 0.18 |
  | 2 | 33 s | 0.99 0.46 0.18 | 0.99 0.52 0.21 |
  | 3 | 33 s | 0.91 0.51 0.21 | 0.95 0.56 0.24 |

  min–max: **33–34 s** (n=3)。
- **旧記録 (現 head と非再現)**: PR 本文の 34 s / load 0.09 0.36 0.25 → 0.50 0.43 0.28 (`tools/targets/massivex/dsp/e2e.sh` と記載)、旧 REPORT の 31 s / load 0.23 0.47 0.26 → 0.57 0.53 0.28 (`dsp/e2e.sh`)。いずれも測定 commit と実行コマンドの記録が不完全で、判定の根拠にしない。今回の n=3 は現 head で取得した値。
- **鮮度 (WORKFLOW §6)**: 測定 commit (コード差分の最終 commit) = `375fc6ac`。検証 HEAD `0bcdcd15` までの差分:
  `git diff 375fc6ac 0bcdcd15 -- tools/targets/massivex/dsp` の全文 (2 files, 14 insertions / 11 deletions):

  ```diff
diff --git a/tools/targets/massivex/dsp/REPORT_MX5.md b/tools/targets/massivex/dsp/REPORT_MX5.md
index 6e50cd54..521e2932 100644
--- a/tools/targets/massivex/dsp/REPORT_MX5.md
+++ b/tools/targets/massivex/dsp/REPORT_MX5.md
@@ -13,7 +13,7 @@
 
 | 指標 | 値 | 意味 |
 |---|--:|---|
-| .pdata entry 総数 | 187,084 | `.pdata` の Misc_VirtualSize / 12 |
+| .pdata entry 総数 | 187,084 | `.pdata` の Misc_VirtualSize / 12 (テーブル 2,245,008 B = 187,084 × 12) |
 | .text 内かつ e>b の entry | 186,961 | 旧 REPORT の 186,960 とは 1 件差 (下記 注 1) |
 | **chained: begin == 直前 entry の end** | **70,489** | issue 本文の「70,533 件」とは 44 件差 (下記 注 2) |
 | UNWIND_INFO に CHAININFO (Flags & 4) | 66,837 | 親 RUNTIME_FUNCTION を持つ entry |
@@ -21,13 +21,14 @@
 | うち 親の (begin,end) が完全一致 | 62,498 | 残り 153 は親 begin は在るが end が不一致 |
 | CHAININFO 付きだが親が .pdata に無い | 4,186 | 親 RVA が pdata 外 (未解決) |
 | leaf 近似 (次 begin まで) = pdata end | 70,489 | 近似が正しいのは 37.7% (chained と一致) |
-| leaf 近似 > pdata end (過大評価) | 116,460 | 過大評価の総バイト 2,618,866 B (= .pdata 総 58,062,780 B の 4.5%) |
+| leaf 近似 > pdata end (過大評価) | 116,460 | 過大評価の総バイト 2,618,866 B (= 関数範囲合計 58,062,780 B の 4.5%・下記 注 3) |
 | leaf 近似 < pdata end (過小評価) | 12 | |
 
 len ヒストグラム (256 B 刻み): 0〜255 B が 143,802 件、4 KiB 以上が 2,581 件。
 
 注 1: 旧 REPORT (§4 / §9) の 186,960 との 1 件差の原因は未確認 (本計測は `.text` 内 VA の条件・e>b で数える)。
 注 2: 70,533 は issue 起票時の値。今回の e>b・.text 内条件での実測は 70,489。差 44 件の原因 (旧 CAB-263 の集計条件) は未確認。
+注 3: 計測定義。`mx_pdata_quant.py` は valid entry (e>b・.text 内・e<=.text 末尾) を **begin で並べ替えた後**、直前 entry の end と次 begin を比べる (生の .pdata の並び順は使わない)。4.5% の分母 58,062,780 B は `dsp/REPORT.md` §4 が「.pdata バイト」と記す値 (.text の 96.4%) を引用したもので、.pdata テーブル本体 (2,245,008 B) ではない。分母の定義 (関数範囲の合計か) は本 run では再計算しておらず、素材なしのため未検証。
 
 ## 3. 解釈
 
@@ -40,14 +41,16 @@ len ヒストグラム (256 B 刻み): 0〜255 B が 143,802 件、4 KiB 以上
 
 | 残件 | 受入 | 起票先 |
 |---|---|---|
-| chained の扱い (CHAININFO 親に束ねる規則) の決定と実装 | 2 | 子 issue (MX-8) |
-| 4,186 件の pdata 外親・153 件の end 不一致の解決 | 2 | 子 issue (MX-8) |
-| leaf 境界を実 unwind / 境界に置換 (過大評価 116,460 件の解消) | 3 | 子 issue (MX-8) |
-| code/data 区別 (jump table・文字列窓) を入れた再帰降下 と round 推移 | 1 | 子 issue (MX-8) |
+| chained の扱い (CHAININFO 親に束ねる規則) の決定と実装 | 2 | 子 issue (MX-8 = #1321) |
+| 4,186 件の pdata 外親・153 件の end 不一致の解決 | 2 | 子 issue (MX-8 = #1321) |
+| leaf 境界を実 unwind / 境界に置換 (過大評価 116,460 件の解消) | 3 | 子 issue (MX-8 = #1321) |
+| code/data 区別 (jump table・文字列窓) を入れた再帰降下 と round 推移 | 1 | 子 issue (MX-8 = #1321) |
 | process 起点 closure の確定値 | 4 | #266 (U1 process slot 同定) に依存。依存明記で未解決 |
 
 ## 5. 検証
 
-- クリーン HEAD (`origin/main` 起点の worktree `ws-1122`) で `bash dsp/e2e.sh` → rc 0 / 31 s / load 0.23 0.47 0.26 → 0.57 0.53 0.28。
+- 実行記録の出典 (未統一・要再測定): 実装 run の記録は PR 本文 (34 s / load 0.09 0.36 0.25 → 0.50 0.43 0.28 / `tools/targets/massivex/dsp/e2e.sh`) と本ファイルの旧記載 (31 s / load 0.23 0.47 0.26 → 0.57 0.53 0.28 / `dsp/e2e.sh`) で食い違う。どちらが実測かを示す run ログが本 fix run からは取得できず、素材 `plugins-massivex` も無いため再測定していない。n≥3 の min–max レンジは未取得。
+- 測定 commit: 375fc6ac (e2e.sh step 5/5 を含むコード差分の最終 commit)。
+- 差分 (`git diff 375fc6ac ec0a3237 -- tools/targets/massivex/dsp`): REPORT_MX5.md 16 行 (+/−)・e2e.sh 8 行 (+/−)、合計 13 insertions / 11 deletions。e2e.sh の差分は `echo "== n/4"` → `echo "== n/5"` の表示文字列のみで、計算・入出力は不変。REPORT の差分は数値の定義・注記・出典の文言のみ。実測値 (表 §2) は変えていない。
 - `bash dsp/negctl.sh` → NC1 FAIL<期待> (unsup 67 vs 基準 48,612) / NC2 FAIL<期待> (unsup 746) / NC3 FAIL<期待> (unsup 0) 。
 - 計測は `.pdata` 解析のみで closure は変えていない。受入 5 の「negctl 3 件 FAIL」は既存の 3 件が満たす (本 run の変更は e2e.sh 末尾の step 5/5 追加のみ)。
diff --git a/tools/targets/massivex/dsp/e2e.sh b/tools/targets/massivex/dsp/e2e.sh
index 720198eb..7cc41be9 100755
--- a/tools/targets/massivex/dsp/e2e.sh
+++ b/tools/targets/massivex/dsp/e2e.sh
@@ -18,13 +18,13 @@ mkdir -p "$W"
 L0="$(cut -d' ' -f1-3 /proc/loadavg)"
 
 T0=$(date +%s)
-echo "== 1/4 RTTI + vtable 抽出"
+echo "== 1/5 RTTI + vtable 抽出"
 python3 "$DSP/scripts/mx_rtti.py" "$PE" "$W/rtti_vtables.json" 2>&1 | sed 's/^/   /'
 
-echo "== 2/4 VST3 入口面 (exports + MassiveX*/Steinberg::Vst vtable slot)"
+echo "== 2/5 VST3 入口面 (exports + MassiveX*/Steinberg::Vst vtable slot)"
 python3 "$DSP/scripts/mx_entry_surface.py" "$PE" "$W/rtti_vtables.json" "$W/surface" | sed 's/^/   /'
 
-echo "== 3/4 x64c probe (未対応命令センサス, tools/flelift/x64c.py を読取実行)"
+echo "== 3/5 x64c probe (未対応命令センサス, tools/flelift/x64c.py を読取実行)"
 python3 - "$W" <<'PY'
 import json, sys
 W = sys.argv[1]
@@ -60,7 +60,7 @@ for k, v in g.most_common():
     print("   group %-14s %d sites" % (k, v))
 PY
 
-echo "== 4/4 独立再計算 (線形 E8/E9 バイトスキャン・別アルゴリズム)"
+echo "== 4/5 独立再計算 (線形 E8/E9 バイトスキャン・別アルゴリズム)"
 python3 "$DSP/scripts/mx_recount.py" "$PE" "$W/rtti_vtables.json" "$W/recount.json" | sed 's/^/   /'
 
 echo "== 5/5 .pdata chained 分割 + leaf 近似の定量化 (MX-5 受入 2・3)"
  ```
  差分は e2e.sh の表示文字列 (`n/4`→`n/5`) と REPORT の文言のみ。計算・入出力は不変。実測値 (表 §2) は変えていない。
- `bash dsp/negctl.sh` (head `0bcdcd15`) → NC1 FAIL<期待> (unsup 67 vs 基準 48,612) / NC2 FAIL<期待> (unsup 746) / NC3 FAIL<期待> (unsup 0)。
- 検証 HEAD と測定 commit の関係: 実測は `0bcdcd15` で取得。その後の HEAD (`5c965723` = main 取り込み + `mx_pdata_denom.py` 追加 + 本 REPORT 修正) について `git diff 0bcdcd15 HEAD -- tools/targets/massivex/dsp/e2e.sh tools/targets/massivex/dsp/negctl.sh tools/targets/massivex/dsp/scripts/mx_pdata_quant.py tools/flelift/x64c.py tools/shared/env.sh` は **0 行**。e2e の測定値は `0bcdcd15` のまま有効 (WORKFLOW §6)。
- 分母の実測: `python3 dsp/scripts/mx_pdata_denom.py <PE>` → valid 186,961 entry の Σ = 58,062,810 B / begin 一意化 186,960 関数の Σ = 58,062,780 B (差 30 B は重複 begin 1 件)。
- 計測は `.pdata` 解析のみで closure は変えていない。受入 5 の「negctl 3 件 FAIL」は既存の 3 件が満たす (本 run の変更は e2e.sh 末尾の step 5/5 追加のみ)。
