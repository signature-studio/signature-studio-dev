# MX-18 (#1879) .pdata 無し入口の区間末尾を code 側から決める試行 (棄却)

- 親: #1833 (MX-16) / 本件: #1879 (MX-18)。前段は `REPORT_MX16.md`・`REPORT_MX14.md`。
- 素材: `plugins-massivex` → `scripts/parse_setup_headers.py` → `scripts/extract_massivex.py <exe> work key` → `work/extracted/VST3/Massive X.vst3` (95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca`、MX-14・MX-16 と一致)。
- 測定 commit: `68534484` (§4 参照)。本 commit で追加するのは検証スクリプトと本ファイルのみ。

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

## 4. 検証

- **測定 commit `68534484`** (e2e・negctl の対象コード)。`be1df2ce` は同じコードで、dsp 配下の差分は本ファイルと `scripts/mx_tail_check.py` の追加のみ (`git diff 68534484 be1df2ce -- tools/targets/massivex/dsp/` で確認、既存コードの変更 0)。
- **main 取り込み後の差分** (`git diff 68534484 e810021a -- tools/targets/massivex/dsp/`): `REPORT_MX13.md` 108 行・`scripts/mx_closure.py` 66 行 (MODE 引数の追加)・`scripts/mx_flow_recheck.py` 41 行。差分は 0 ではないため、再測定の対象になる。
- **既定 `linear` の挙動は旧版と同じ**: `linear` の計算 (入口から次の入口までの線形 disasm・`begins` と `fsz` による末尾計算) は変更なし。変わるのは引数の追加・stderr の行形式・JSON への `mode` / `rounds_log` キーの追加のみ。
- **素材不足のため、今回の HEAD では e2e・negctl を再測定していない**。`$ARTIFACTS_DIR` に `plugins-massivex` が無く (`fl-win64.tar.zst` のみ)、`plugins-massivex` 展開後に再実行が必要。
- **e2e (`dsp/e2e.sh`): 未測定**。`$ARTIFACTS_DIR` (`/home/runner/artifacts`) に `plugins-massivex` が無く (`fl-win64.tar.zst` のみ)、PE が展開できないため実行していない。出所不明の旧 e2e 値 (`elapsed` / load) は削除した (git 履歴 `9d661e3d` 以前に残る)。
- **negctl (`bash dsp/negctl.sh`): 未測定**。同じく PE が無いため未実行。
- **closure (§2) の測定 commit は `68534484`**。検証 HEAD (`9d661e3d` の後続 commit) では再測定していない。差分の証跡 (`git diff 68534484 HEAD -- tools/targets/massivex/dsp/scripts/`):
  - `git diff --stat`: `scripts/mx_closure.py` 66 行 (+/-)・`scripts/mx_flow_recheck.py` 41 行・`scripts/mx_tail_check.py` 82 行 (追加のみ)。`REPORT_MX13.md` 108 行 (追加のみ)。
  - 全 diff は 259 行で、`git diff 68534484 HEAD -- tools/targets/massivex/dsp/scripts/ | sha256sum` = `8128fd61c79e8d880cbc3328cbcefcea09437116ef04a863c9cc667488904cc9`。
  - `mx_closure.py` の差分は (a) `MODE` 第 4 引数の追加 (既定 `linear`・assert で `linear|flow` のみ)、(b) `flow()` の追加 (`MODE == 'flow'` の時だけ呼ぶ)、(c) 重複していた `begins = sorted(fsz)` の 1 行削除、(d) `rlog` / `mode` の JSON キー追加。既定 `linear` の経路は、入口から次の入口までの線形 disasm と `begins`/`fsz` の末尾計算が旧版と同じ (コード読みと `py_compile` のみ確認。実行は未実施)。
- **closure の HEAD 再測定は未実施** (PE 不在)。受入 2 の §2 の値は測定 commit `68534484` のものとして読むこと。

## 5. 結論と残件

- 受入 1 (.pdata 無し入口の末尾を code 側で決める) は**未達**。健全な末尾には jump table 先と文字列窓の code/data 区別が要り、MX-13 (#1625) と MX-25 (#1913) の範囲。
- 受入 2 は §2 で達成 (置換前後の closure 実測)。受入 3 は §4 で維持を確認。
- 試行コードは本 commit に含めない (SHORT のため棄却)。再試行するなら `mx_tail_check.py` の SHORT が 0 件になることを先に確かめる。
