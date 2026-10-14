# MX-14 (#1626) leaf 境界の実 unwind 化と closure 変化の定量化

- 親: #1488 (MX-10) / 起票: #1626 (MX-14)。本ファイルは #1626 の実測。
- 素材: `plugins-massivex` (installer `.exe`) → `scripts/parse_setup_headers.py` → `scripts/extract_massivex.py <exe> work key` → `work/extracted/VST3/Massive X.vst3` (95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca`、REPORT_MX5 §5 と一致)。
- 計測スクリプト: `dsp/scripts/mx_closure.py` (closure)、`dsp/e2e.sh` (e2e)、`dsp/negctl.sh` (negctl)。

## 1. 変更内容と置換前後の closure

変更 (測定 commit `0db657e6`): `.pdata` に begin が無い入口 (`fsz` に無いもの) の区間を、含まれる `.pdata` 関数の end で切る。含まれる関数が無い入口は従来どおり「次の入口まで」。あわせて各ラウンドの `sorted(entries)` を 1 回に減らした (旧版は入口ごとに再ソートし、入口 67 万件で 15 分の timeout を超えた。出力は同一)。

| 指標 | 旧 (`7e665077`) | 新 (`0db657e6`) |
|---|--:|--:|
| closure 入口数 | 669,225 | 472,313 |
| うち .pdata begin | 8,248 | 5,950 |
| closure の .pdata 担当バイト | 2,208,727 | 1,592,431 |
| GetPluginFactory closure 関数 | 644,290 | 430,927 |
| InitDll closure 関数 | 643,451 | 430,763 |
| factoriesListGetter closure 関数 | 644,511 | 431,799 |
| VST3-entry-surface(all) closure 関数 | 669,225 | 472,313 |
| ExitDll closure 関数 | 2 | 2 |

- 同一 commit の closure を 2 回実行し、`pe` 欄を除いて一致 (再現性を確認)。
- target 判定 (negctl の unsup 件数) は変化なし (下記 §3)。

## 2. 残件

- 含まれる `.pdata` 関数が無い入口の区間は、依然「次の入口まで」の近似。受入 1 は未達。
- 残りの置換は子 issue #1833 (MX-16) へ。

## 3. 検証

- **測定 commit**: `0db657e6` (`fix(massivex): cut non-begin leaf at containing pdata end; hoist sort in closure (Refs #1626)`)。
- **e2e (`bash dsp/e2e.sh`・測定 commit・n=1)**: rc 0 / `OK elapsed=43s` / load 0.37 0.31 0.44 → 0.71 0.41 0.47。
- **e2e (同・ベースライン 7e665077)**: rc 0 / `OK elapsed=42s` / load 0.23 0.24 0.15 → 0.61 0.34 0.19。
- **negctl (`bash dsp/negctl.sh`・測定 commit)**: NC1 unsup 67 / NC2 unsup 746 / NC3 insns 31 unsup 0 → 3 件とも FAIL<期待>。
- **closure の実行時間**: 旧版は 15 分で timeout (rc 124・round 3 で打ち切り)。sort 修正版は base 34 s、新版 22 s。
- **鮮度 (WORKFLOW §6)**: `git diff 7e665077 HEAD -- tools/targets/massivex/dsp/` の差分は `scripts/mx_closure.py` のみ (本 REPORT は測定後に追加)。
