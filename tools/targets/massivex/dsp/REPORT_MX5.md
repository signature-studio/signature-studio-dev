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
| leaf 近似 > pdata end (過大評価) | 116,460 | 過大評価の総バイト 2,618,866 B (= 関数範囲合計 58,062,780 B の 4.5%・下記 注 3) |
| leaf 近似 < pdata end (過小評価) | 12 | |

len ヒストグラム (256 B 刻み): 0〜255 B が 143,802 件、4 KiB 以上が 2,581 件。

注 1: 旧 REPORT (§4 / §9) の 186,960 との 1 件差の原因は未確認 (本計測は `.text` 内 VA の条件・e>b で数える)。
注 2: 70,533 は issue 起票時の値。今回の e>b・.text 内条件での実測は 70,489。差 44 件の原因 (旧 CAB-263 の集計条件) は未確認。
注 3: 計測定義。`mx_pdata_quant.py` は valid entry (e>b・.text 内・e<=.text 末尾) を **begin で並べ替えた後**、直前 entry の end と次 begin を比べる (生の .pdata の並び順は使わない)。4.5% の分母 58,062,780 B は `dsp/REPORT.md` §4 が「.pdata バイト」と記す値 (.text の 96.4%) を引用したもので、.pdata テーブル本体 (2,245,008 B) ではない。分母の定義 (関数範囲の合計か) は本 run では再計算しておらず、素材なしのため未検証。

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

- 実行記録の出典 (未統一・要再測定): 実装 run の記録は PR 本文 (34 s / load 0.09 0.36 0.25 → 0.50 0.43 0.28 / `tools/targets/massivex/dsp/e2e.sh`) と本ファイルの旧記載 (31 s / load 0.23 0.47 0.26 → 0.57 0.53 0.28 / `dsp/e2e.sh`) で食い違う。どちらが実測かを示す run ログが本 fix run からは取得できず、素材 `plugins-massivex` も無いため再測定していない。n≥3 の min–max レンジは未取得。
- 測定 commit: 375fc6ac (e2e.sh step 5/5 を含むコード差分の最終 commit)。
- 差分 (`git diff 375fc6ac ec0a3237 -- tools/targets/massivex/dsp`): REPORT_MX5.md 16 行 (+/−)・e2e.sh 8 行 (+/−)、合計 13 insertions / 11 deletions。e2e.sh の差分は `echo "== n/4"` → `echo "== n/5"` の表示文字列のみで、計算・入出力は不変。REPORT の差分は数値の定義・注記・出典の文言のみ。実測値 (表 §2) は変えていない。
- `bash dsp/negctl.sh` → NC1 FAIL<期待> (unsup 67 vs 基準 48,612) / NC2 FAIL<期待> (unsup 746) / NC3 FAIL<期待> (unsup 0) 。
- 計測は `.pdata` 解析のみで closure は変えていない。受入 5 の「negctl 3 件 FAIL」は既存の 3 件が満たす (本 run の変更は e2e.sh 末尾の step 5/5 追加のみ)。
