# MX-50 (#4198) 親 18 件の RUNTIME_FUNCTION 解決 (部分・未達)

- 親: #1810 (MX-15) / 起票: #4198 (MX-50)。本ファイルは #4198 の実測。
- 素材: `plugins-massivex` (`$ARTIFACTS_DIR/plugins-massivex.tar.zst`) → インストーラ `Native Instruments Massive X v1.7.1.exe` を `scripts/parse_setup_headers.py` → `scripts/extract_massivex.py <exe> work key` で `Massive X.vst3` (95,356,824 B、md5 `622993e76565f49c094063a2b717d6ca`、REPORT_MX10 §4 と一致)。
  - 展開先: 前版の記録は `work/extracted/VST3/...` とだけ書いており、実際の所在は確認できていない。再現時は `tools/targets/massivex/work/extracted/VST3/Massive X.vst3` (`dsp/e2e.sh` の既定 `MX_PE`) に置くか、`MX_PE` で指定する。`work/` は gitignore 対象で commit しない。
- 計測スクリプト: `dsp/scripts/mx_unres_residual_4198.py` (#4198 で新規。main の `mx_unres_residual.py` (MX-15) とは別ファイル)。

## 1. 受入の達成状況

| 受入 | 状態 |
|---|---|
| 1 親 18 件の所在ごとに解決規則を決めて実測 | **未達**。所在の再現は REPORT_MX5 と一致せず (§3)、規則は未確定 |
| 2 解決不能の理由を分類して REPORT に残す | **未達** (受入 1 の結果に依存) |
| 3 e2e PASS・negctl 3 件 FAIL<期待> | **未達**。本 run では未実施 (素材 `plugins-massivex` が `$ARTIFACTS_DIR` に無く実行不能) |

## 2. 測定 (`mx_unres_residual_4198.py`)

- 測定 commit: `c2b976d75` (スクリプトと本節の数値が初めて入った commit)。本 run では PE が無く再実行していないため、本節の数値は未再検証。
- valid entry のうち UNWIND_INFO が section 1 つに一意に解決: 167,541
- うち CHAININFO (Flags & 4): 62,516 (REPORT_MX5 §2 と一致)
- 親が `.pdata` 先頭セクションの valid に完全一致で無い: **18 参照 / 13 種類の親**
  - 参照数の内訳: `pdata_out/text_in` 16、`pdata_out/text_out` 2 (親 (begin,end) を先頭 `.pdata` で判定)

## 3. 食い違い (読み方の疑い・未確定)

- REPORT_MX5 §2 は同じ 18 件について「全 pdata 内 7 件・pdata 外 11 件」と記す。今回の計測では、
  **13 種類の親の全てが、先頭の `.pdata` にも 2 本目の `.pdata` (`0x6176000`) にも完全一致で無い**。内訳は再現しなかった。
- 18 件の UNWIND_INFO はすべて `.xdata` (`0x6186000` 以降・`.text` の外) の中にある。その読み方で得た親の (begin,end) は、`.text` の範囲外の値を含む (例 `0x984f20e8`)。
  UNWIND_INFO の読み方が誤っている可能性が高い。ただし、これは未検証の推定である。
- 原因候補: (a) 親の読み方 (`.xdata` の UNWIND_INFO の CountOfCodes の扱い・先頭バイトの偏り)、(b) REPORT_MX5 の計測条件との差。
  どちらかを確定するには、REPORT_MX5 の計測コードを読んで条件を揃え、素材で再実行する必要がある。

## 4. 検証

- 本 run の検証: 素材 `plugins-massivex` が無く、`mx_unres_residual_4198.py`・`e2e.sh`・`negctl.sh`・`mx_unres_probe.py` は実行していない。
- 前版の本文と本節に書いた e2e (rc 0 / `OK elapsed=30s`)・negctl (NC1 unsup 5 / NC2 unsup 292 / NC3 insns 31 unsup 0)・probe (valid 186,961 / 解決不能 19,420 / 整合候補 0・2・3 件 = 160・7,274・64) は、出所 (実行 commit・PE の所在・実行ログ) を確認できないため取り下げる。
  probe の値が REPORT_MX10 §2 と一致するという記述は REPORT_MX10 側の記録との比較であり、本件での再測定ではない。
- 測定 commit から HEAD までの差分: `git diff c2b976d75 HEAD -- tools/targets/massivex/dsp/scripts/mx_unres_residual_4198.py` は 0 行 (スクリプト不変)。

## 5. 未解決 (起票先)

| 残件 | 影響 | 起票先 |
|---|---|---|
| 親 18 件の所在の再現 (REPORT_MX5 の 7/11 と今回の 0/18 の差。UNWIND_INFO 読み方の疑い・未確定) | 受入 1・2 が書けない | 本 issue #4198 (Refs・未達) |
| 解決規則の確定と受入 3 の e2e・negctl 再実行 (要 `plugins-massivex`) | 受入 1〜3 | #4198 (Refs・未達) |
