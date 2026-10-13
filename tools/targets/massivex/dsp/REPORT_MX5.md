# MX-5 (#1122) .pdata chained 分割と leaf 境界近似の定量化

- 親: #266 / 起票: #1122 (MX-5)。本ファイルは #1122 の実測。
- 素材: `plugins-massivex` → `work/extracted/VST3/Massive X.vst3` (95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca`、REPORT §11.1 と一致)。
- 計測スクリプト: `dsp/scripts/mx_pdata_quant.py` (e2e.sh の step 5/5)。

## 1. 今 run で達成した範囲 (受入 2・3 の計測部分)

受入条件のうち、本 run は **受入 2 (chained の実測) と受入 3 (leaf 近似の定量化)** の計測のみ。
受入 1・4 は未着手、受入 2 の「扱いの決定と実装」・受入 3 の「実 unwind への置換」は未達 (§4 の子 issue)。

## 2. 実測値 (.pdata 全数・測定 commit `93eab8d7`)

| 指標 | 値 | 意味 |
|---|--:|---|
| .pdata entry 総数 | 187,084 | `.pdata` の Misc_VirtualSize / 12 (テーブル 2,245,008 B = 187,084 × 12) |
| .text 内かつ e>b の entry | 186,961 | valid (下記 注 1) |
| **chained: begin == 直前 entry の end** | **70,489** | issue 本文の「70,533 件」とは 44 件差 (下記 注 2) |
| UNWIND_INFO の RVA が section 1 つに一意に解決 | 167,541 | 残り 19,420 件は解決不能 (下記 注 4) |
| うち UNWIND_INFO に CHAININFO (Flags & 4) | 62,516 | 一意解決のみで数える。別経路 (pefile の offset 解決 + `.pdata` 直読み、`mx_pdata_quant.py` 非依存) でも 62,516 を再現 |
| うち 親 entry が valid .pdata 内に実在 | 62,498 | 親の (begin,end) が完全一致 も 62,498 (差 0) |
| 親が valid 外 (= 62,516 − 62,498) | 18 | うち全 pdata 内に在るのが 7 件・pdata 外が 11 件 (全 pdata 内の親一致 62,505 は作業用の別経路確認) |
| leaf 近似 (次 begin まで) = pdata end | 70,489 | 近似が正しいのは 37.7% (chained と一致) |
| leaf 近似 > pdata end (過大評価) | 116,460 | 過大評価の総バイト 2,618,866 B (= valid 186,961 entry の Σ(end−begin) 58,062,810 B の 4.51%・下記 注 3) |
| leaf 近似 < pdata end (過小評価) | 12 | |

len ヒストグラム (256 B 刻み): 0〜255 B が 143,802 件、4 KiB 以上が 2,581 件。

注 1: 旧 REPORT の 186,960 との 1 件差の原因は未確認。本計測は `.text` 内 VA・e>b・e<=.text 末尾で数える。
注 2: 70,533 は issue 起票時の値。今回の条件での実測は 70,489。差 44 件の原因 (旧 CAB-263 の集計条件) は未確認。
注 3: 計測定義。`mx_pdata_quant.py` は valid entry を **begin で並べ替えた後**、直前 entry の end と次 begin を比べる (生の .pdata の並び順は使わない)。分母は `dsp/scripts/mx_pdata_denom.py` の実測で、次の 2 通り:
  - valid 186,961 entry の Σ(end−begin) = **58,062,810 B** (本文の 4.51% の分母)
  - 同じ valid を begin で一意化 (186,960 関数) した Σ(end−begin) = **58,062,780 B**
  - 差 30 B は begin `0x39373e0` に (begin, end) が同一の entry が 2 件あるため (end `0x39373fe`・長さ 30 B・unwind RVA は 0x62f4a8c と 0x620b39c で別)。
  - 過大評価の割合は 2,618,866 / 58,062,810 = 4.51% (一意化の分母でも 4.51%)。.pdata テーブル本体 (2,245,008 B) は分母ではない。
注 4: **section 重なりの事実 (計測の前提)**: この PE の section 表で `.qtmimed` (VA 0x6178000・VirtualSize 208,361) が `.xdata` (VA 0x6186000〜) と VA 範囲で重なり、2 本目の `.pdata` (VA 0x6176000) とも重なる。UNWIND_INFO の RVA が複数 section に当たる entry がある。
  - RVA 解決規則: VirtualSize の範囲 `[VA, VA+VirtualSize)` に当たる section がちょうど 1 つのときだけ解決し、file offset = `PointerToRawData + (RVA − VA)`。0 件・2 件以上は解決不能として読まない。
  - 件数: 1 件 167,541 / 2 件 2,554 / 3 件 16,706 / 0 件 160 (合計 186,961)。
  - 旧版 (先頭一致の section を使う) は CHAININFO 66,837 と出していたが、これは重なり部分を別 section から読んだ値で、旧 REPORT の 66,837 / 62,651 / 4,186 / 153 は規則の欠陥による誤りとして撤回する。
  - 検算: 作業用の別経路 (`work/overlap_probe.py`・`work/parent_probe.py`、gitignore 対象) でも、一意解決 167,541 件の CHAININFO 62,516、親 valid 内 62,498・全 pdata 内 62,505 を再現。

## 3. 解釈

- CHAININFO (62,516) は一意に解決できた entry のみの件数。解決不能 19,420 件の中の CHAININFO は未確定 (規則上は数えない)。
- 親が一致する 62,498 件は、CHAININFO の親を使えば束ねられる候補。chained 判定 (70,489) との重なりは未計測。
- leaf 近似は 116,460 件で pdata end より長い (過大評価 2,618,866 B)。`mx_closure.py` の区間は「次の入口まで」なので、closure のバイト数と target 判定へ与える影響は未測定 (U5)。

## 4. 未解決・起票先 (本 run の残り)

| 残件 | 受入 | 起票先 |
|---|---|---|
| chained の扱い (CHAININFO 親に束ねる規則) の決定と実装 | 2 | 子 issue (MX-8 = #1321) |
| 解決不能 19,420 件 (section 重なり) の UNWIND_INFO の正しい読み方、親 18 件の解決 | 2 | 子 issue (MX-8 = #1321) |
| leaf 境界を実 unwind / 境界に置換 (過大評価 116,460 件の解消) | 3 | 子 issue (MX-8 = #1321) |
| code/data 区別 (jump table・文字列窓) を入れた再帰降下 と round 推移 | 1 | 子 issue (MX-8 = #1321) |
| process 起点 closure の確定値 | 4 | #266 (U1 process slot 同定) に依存。依存明記で未解決 |

## 5. 検証

- **測定 commit (コードを変えた最後の commit)**: `93eab8d7` (`fix(massivex): resolve UNWIND_INFO RVA only when unique section hit (#1122)`)。以後の commit は REPORT のみ。
- **素材**: `plugins-massivex` を `$RUNNER_TEMP/mx` に展開 → `scripts/parse_setup_headers.py` → `scripts/extract_massivex.py <exe> work key` で `work/extracted/VST3/Massive X.vst3` を再抽出。md5 `622993e7…` / 95,356,824 B (一致)。
- **実行時間 (`bash dsp/e2e.sh`・測定 commit `93eab8d7`・n=3・全回 rc 0)**:

  | run | elapsed | load 開始 | load 終了 |
  |---|--:|---|---|
  | 1 | 30 s | 0.33 0.31 0.14 | 0.60 0.37 0.17 |
  | 2 | 30 s | 0.55 0.37 0.17 | 0.73 0.43 0.20 |
  | 3 | 30 s | 0.73 0.43 0.20 | 0.84 0.49 0.22 |

  min–max: **30–30 s** (n=3)。load は連続実行で上がっている (run 間の負荷累積)。所要時間は参考値。
  - 以前の記録 (PR 本文 34 s・旧 REPORT 31 s・`0bcdcd15` での 33–34 s) は旧版の step 5 で測ったもので、現 commit の値とは比較しない。
- **step 5/5 の出力 (run 1)**: chained 70,489 / 解決 1 件 167,541・CHAININFO 62,516 / 親 valid 内 62,498 (完全一致 62,498) / 過大評価 116,460 件・2,618,866 B / 過小評価 12。
- **negctl (`bash dsp/negctl.sh`・同 commit)**: NC1 unsup 67 / NC2 unsup 746 / NC3 unsup 0 → 3 件とも FAIL<期待>。
- **鮮度 (WORKFLOW §6)**: `git diff 93eab8d7 HEAD -- tools/targets/massivex/dsp/e2e.sh tools/targets/massivex/dsp/negctl.sh tools/targets/massivex/dsp/scripts/mx_pdata_quant.py tools/flelift/x64c.py tools/shared/env.sh` は **0 行**。測定値は測定 commit のまま有効。
- 分母: `python3 dsp/scripts/mx_pdata_denom.py <PE>` → valid 186,961 の Σ = 58,062,810 B / begin 一意化 186,960 の Σ = 58,062,780 B。
- 計測は `.pdata` 解析のみで closure は変えていない。受入 5 の「negctl 3 件 FAIL」は既存の 3 件が満たす。
