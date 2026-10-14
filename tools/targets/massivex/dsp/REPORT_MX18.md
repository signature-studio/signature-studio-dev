# MX-18 (#1879) .pdata 無し入口の区間末尾を code 側から決める試行 (棄却)

- 親: #1833 (MX-16) / 本件: #1879 (MX-18)。前段は `REPORT_MX16.md`・`REPORT_MX14.md`。
- 素材: `plugins-massivex` → `scripts/parse_setup_headers.py` → `scripts/extract_massivex.py <exe> work key` → `work/extracted/VST3/Massive X.vst3` (95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca`、MX-14・MX-16 と一致)。
- 測定 commit: `68534484` (main。コード変更は本 commit で追加しない・検証スクリプトのみ追加)。

## 1. 試行 (code 側の末尾)

.pdata 無し入口 `e` の区間末尾を、`e` から分岐を辿って到達できる命令の末尾 (最大) で切る。
- 辿る: fall-through、`jcc`/`jmp` の即値先 (`.text` 内・thunk 外)。`ret`/`int3`/`ud2`/`hlt` で止める。
- 間接 jmp・`.text` 外・解読失敗のときは従来どおり「次の入口まで」に戻す。
- 結果は `min(次の入口, 到達末尾)`。

## 2. closure 測定 (測定 commit `68534484`)

| 指標 | 旧 (main) | 試行 |
|---|--:|--:|
| closure 入口数 | 472,313 | 420,859 |
| うち .pdata 関数 | 5,950 | 5,062 |
| closure の .pdata 担当バイト | 1,592,431 | 1,413,172 |
| InitDll closure 関数 | 430,763 | 368,099 |
| GetPluginFactory closure 関数 | 430,927 | 368,627 |
| factoriesListGetter closure 関数 | 431,799 | 368,909 |
| ExitDll closure 関数 | 2 | 2 |

- 旧版の再現: 472,313 / 5,950 / 1,592,431 / InitDll 430,763 / GetPluginFactory 430,927 で MX-16 §1 と一致。
- 試行の closure は**不健全な値**であり、採用しない (§3)。

## 3. 健全性の検証 (`dsp/scripts/mx_tail_check.py`)

真の末尾が分かる .pdata 関数 (186,960 件) に同じ到達末尾を当てた。

| 判定 | 関数数 |
|---|--:|
| 到達末尾 ≥ 真の末尾 (ok) | 162,628 |
| **到達末尾 < 真の末尾 (SHORT)** | **2,370** |
| 解読不能 (間接 jmp 等・unresolved) | 21,962 |

- SHORT は、間接 jmp (jump table) の先など、分岐を辿っても到達できない部分を末尾が切ることを示す。例: `0xba4f0` (真 458 B / 到達 0x1c1 = 449 B)、`0x115a40` (真 389 B / 到達 0x98)。
- 試行 closure が旧版より小さいのは、SHORT による過小評価 (`InitDll` 430,763 → 368,099) であり、closure の縮小ではない。MX-16 §2 で棄却した「次の .pdata begin」と同じ原因。
- 結論: 到達末尾は .pdata 無し入口の末尾の上界にも下界にもならず、採用不可。

## 4. 検証 (測定 commit `68534484`・コード変更なし)

- **e2e (`bash dsp/e2e.sh`・n=1)**: rc 0 / `OK elapsed=43s` / load 0.28 0.30 0.15 → 0.63 0.39 0.19。
- **negctl (`bash dsp/negctl.sh`)**: NC1 insns 3118 unsup 67 / NC2 insns 4575 unsup 746 / NC3 insns 31 unsup 0 → 3 件とも FAIL<期待>。

## 5. 結論と残件

- 受入 1 (.pdata 無し入口の末尾を code 側で決める) は**未達**。健全な末尾には jump table 先と文字列窓の code/data 区別が要り、MX-13 (#1625) と MX-25 (#1913) の範囲。
- 受入 2 は §2 で達成 (置換前後の closure 実測)。受入 3 は §4 で維持を確認。
- 試行コードは本 commit に含めない (SHORT のため棄却)。再試行するなら `mx_tail_check.py` の SHORT が 0 件になることを先に確かめる。
