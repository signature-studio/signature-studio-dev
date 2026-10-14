# MX-16 (#1833) .pdata 無し入口の「次の入口まで」近似の置換 (試行と棄却)

- 親: #1626 (MX-14) / 本件: #1833 (MX-16)。前段の実測は `REPORT_MX14.md`。
- 素材: `plugins-massivex` → `scripts/parse_setup_headers.py` → `scripts/extract_massivex.py <exe> work key` → `work/extracted/VST3/Massive X.vst3` (95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca`、MX-14 と一致)。

## 1. 残件の内訳 (測定 commit `787bb17e`・closure 472,313 入口)

| 区分 | 入口数 |
|---|--:|
| `.pdata` begin そのもの | 5,950 |
| 含まれる `.pdata` 関数あり (begin ではない) | 448,977 |
| 含まれる `.pdata` 関数なし (「次の入口まで」の近似) | 17,386 |

- 「次の入口まで」区間の合計: 2,128,567 B。
- 同じ入口を「次の `.pdata` begin まで」で切った場合の合計: 53,737,264 B。
- 次の `.pdata` begin が次の入口より手前になる入口は 8,716 件。

## 2. 試行: 「次の `.pdata` begin で切る」(棄却)

含まれる `.pdata` 関数が無い入口の区間を `min(次の入口, 次の .pdata begin)` にした。

| 指標 | 旧 (`787bb17e`) | 試行 |
|---|--:|--:|
| closure 入口数 | 472,313 | 417,309 |
| うち .pdata begin | 5,950 | 5,203 |
| closure の .pdata 担当バイト | 1,592,431 | 1,427,612 |
| InitDll closure 関数 | 430,763 | 3 |
| GetPluginFactory closure 関数 | 430,927 | 367,484 |

棄却理由 (不健全): `InitDll` の closure が 430,763 → 3 に縮んだ。原因は入口 `0x37d7e` (.pdata 無し) で、次の .pdata begin が `0x37d80` (2 B 後) にあるため区間が 2 B に切られ、旧版で辿れていた callee `0x383a2` / `0x6cb32` / `0x8a31f` が消えたこと。.pdata の begin が「区間内に別の関数の先頭がある」ことを示すだけで、この入口の関数末尾を示すわけではない。したがってこの切り方は closure を過小評価し、closure 指標の縮小は見かけ上のものである。コードは `dsp/scripts/mx_closure.py` を含め main から変更していない (試行は revert 済み・closure 再計算で旧版と一致を確認)。

## 3. 検証 (測定 commit `787bb17e`・コード変更なし)

- **e2e (`bash dsp/e2e.sh`・n=1)**: rc 0 / `OK elapsed=43s` / load 0.65 0.67 0.32 → 0.87 0.72 0.36。
- **closure (`dsp/scripts/mx_closure.py`・旧)**: 472,313 入口 / .pdata 5,950 / 1,592,431 B (MX-14 と一致)。実行 19 s。
- **negctl (`bash dsp/negctl.sh`)**: NC1 insns 3118 unsup 67 / NC2 insns 4575 unsup 746 / NC3 insns 31 unsup 0 → 3 件とも FAIL<期待>。
- **鮮度 (WORKFLOW §6)**: 測定 commit 以降、`git diff 787bb17e HEAD -- tools/targets/massivex/dsp/` はこの REPORT のみ。

## 4. 結論と残件

- 受入 1 (「次の入口まで」近似を実 unwind/境界に置換) は未達。.pdata の境界だけでは 17,386 件の関数末尾は決まらない。
- 必要なのは、.pdata 無し入口の末尾を code 側から決める方法 (ret/jmp 境界の解析など)。これは MX-13 (code/data 区別を入れた再帰降下) と同じ層の問題。
- 受入 2 は本 REPORT の §1・§2 で達成 (置換前後の実測)。受入 3 は §3 で維持を確認。
