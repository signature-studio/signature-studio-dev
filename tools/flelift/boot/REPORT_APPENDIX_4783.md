# REPORT_APPENDIX_4783 — 既定変更の影響の実測 (#4783)

> 分割移動元: `REPORT_APPENDIX_672.md` §D (main 取り込み時に 250 行上限を超えるため移動。内容は変えていない・見出し番号 §D / D-n はそのまま)。

## §D. 既定変更の影響の実測 (#4783・受入 1〜3)

> 測定 commit: `8aa9c0289` (origin/main)。本節のコードは main と同一 (測定のみ・`tools/flelift/boot/` のコード変更 0)。
> 素材: `fl-win64` (`flstudio_win64_26.1.7.5653`)・`toolchain-emsdk`。lift は `fle6_measure.sh` の既定経路 (`FLE_EXTRA_ROOTS=` = root 無し)、clang は `FLE_SHARDS=8`。
> 実測環境: 4 vCPU・load 0.9〜2.0。各 run n = 1。

### D-1 結論 (先出し)

- **受入 1 (survey 942 unit・既定経路): 実施済み**。mode 0 (既定 = `FLE_IPP` 未指定) は unlifted 3 件 (unit 280・659 = `0x6a7b70`、unit 895 = `0x976da0`)。mode 3 (#4758 後の既定に相当) は unlifted 0 件・ok 895。halt0 (exit) は両方 0。
- **受入 2 (ILTools native 読込): 未達**。wine では DLL が読めず実測できなかった (D-3)。native の成否は推定のまま。
- **受入 3 (他経路): 一部**。`boot_e2e.sh` 本体は plain の 1 TU clang が RSS cap (11,000MB) を超えて build できず未実行。strict / nosx は `build.sh` で build して実行した (D-4)。
- 製品 KPI (起動・既定経路): units 209 → **209 (変化なし・コード変更なし)**。最初のウィンドウ: 無し (変化なし)。

### D-2 survey (受入 1)

`survey_drive.sh 150 20` (1 セグメントで 9〜10 s で完了)。正本は `results/survey_4783_*.json` (`survey_seg_0.json` の survey 節)。

| mode | ok | empty | unlifted | noproc | halt0 | unlifted の内訳 | boot 停止 (units_run) |
|---|--:|--:|--:|--:|--:|---|---|
| 0 (既定・`FLE_IPP` 未指定) | 892 | 46 | **3** | 1 | 0 | unit 280・659 = `0x6a7b70` / unit 895 = `0x976da0` | unit 209 (`unlifted 0x6a7b70`) |
| 3 (ILT 擬似・#4758 後の既定) | 895 | 46 | **0** | 1 | 0 | なし | unit 851 (`unlifted 0x976da0`) |

- 合計 942 = 両 mode とも ok + empty + unlifted + noproc。`empty` 46 と `noproc` 1 (unit 941) は両 mode で同じ。
- 注: `merge_survey.py` の `covered` (895) は jsonl に書かれない empty / noproc を数えないため、`results/survey.json` の値は 942 網羅を示さない。正本は `survey_seg_0.json` の `survey.byCls`。この集計の不整合は本 PR では直さず、子 issue に起票する (D-6)。
- boot 単独 (`FLE_IPP` 0 / 3): mode 0 = units 209・GetMem 1,890 / FreeMem 776 (§1 の既定と一致)。mode 3 = units 851・GetMem 3,139 / FreeMem 1,490 (§B-3 と一致)。

### D-3 ILTools native 読込 (受入 2): 未達

- 素材の `ILTools_x64.dll` (`block24347_PE.bin`・PE32+ x64 DLL・export 6 本・DllMain あり) を `tools/flelift/boot/iltools_native_probe.c` (`LoadLibraryW(L"ILTools")` → `GetProcAddress("CreateCursorFromFont")`) で wine64 9.0 (`/usr/lib/wine/wine64`) から実行した。
  - (a) ファイル名 `ILTools_x64.dll`: `LoadLibraryW` = NULL・err=126 (モジュール未検出)。`ILTools` は拡張子補完で `ILTools.dll` を探すため、この名前では見つからない。
  - (b) `ILTools.dll` に改名: `LoadLibraryW` = NULL・err=1114 (`ERROR_DLL_INIT_FAILED`)。wine のログは DllMain の GUI 依存 (ウィンドウ・ディスプレイドライバ) を示す。
  - (c) (b) + Xvfb: 120 s で timeout (rc=124)。DllMain から戻らない。
- **判定: native 読込は未実測** (wine の GUI 依存で偽陰性の可能性が高く、native の結論にできない)。
- 参考 (推定・未検証): boot は `LoadLibraryW(L"ILTools")` を呼ぶ (`0x815edc`)。素材の DLL 名は `ILTools_x64.dll` で、拡張子補完の `ILTools.dll` とは一致しない。このため native の既定探索でも見つからない可能性がある。mode 3 の前提「native は読めて非 0」は、この点を含めて未確定。

### D-4 他経路 (受入 3)

| 経路 | 結果 | 備考 |
|---|---|---|
| `boot_e2e.sh` (全 variant・`--fast`) | **未実行** | plain の `fle_lifted.c` を 1 TU で clang → peak 11,380〜11,458MB > cap 11,000MB で停止。`FLE_SHARDS=8` でも同じ (`boot_e2e.sh` の `cc()` は shard しない)。既存スクリプトの制約で本 PR の変更ではない (子 issue) |
| strict (`build.sh strict`・8 shard) | build OK (mismatch 0 / undefined 0 / dup 0) | mode 0: units 93・`soft` 停止・rc 0 / mode 3: units 93・`soft` 停止・rc 3 (ptr 判定 NG) |
| nosx (`build.sh nosx`) | build OK | mode 0 / 3 とも units 0・`exit` (rc 0 / rc 3)。mode 3 で `FLE_IPP` の shim を持たないため前進しない |
| trace / chk | 未実行 | 時間上限 |

- strict の mode 3 で rc=3 は `FLEBOOT_IPP_CHECK` の判定 NG (`ptr_15F34A0` が 0x7f10001c 以外) による。mode 3 の入力の正しさは strict では確認できていない。

### D-5 既定の影響 (まとめ)

- 既定 (mode 0) の survey には unlifted が 3 件あり、そのうち 2 件 (unit 280・659) は `0x6a7b70` (fill コールバック・既知の blocklist)。unit 895 は `0x976da0` (mode 3 で既定 root 化した対象)。
- 既定を mode 3 にすると survey の unlifted は 0 件になるが、ILTools の native 読込が未確定 (D-3) のため、『mode 3 が正しい入力』とは言えない。既定化の判断は PM に任せる。

### D-6 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ILTools native 読込 (受入 2) の実測。wine の GUI 依存で不可 | mode 3 の入力の正しさ | 子 issue (D-7) |
| `boot_e2e.sh` の 1 TU clang の RSS cap 超過 (受入 3 の一部) | `boot_e2e.sh` 全 variant が build 不能 | 子 issue (D-7) |
| `merge_survey.py` の covered が empty / noproc を数えない | `results/survey.json` の集計が 942 網羅を示さない | 子 issue (D-7) |
| strict mode 3 の ptr 判定 NG (rc 3) | mode 3 の strict 経路の正しさ | 本 PR の範囲外 (D-5 の判断と併せて PM) |

### D-7 再現

```sh
# 素材: fl-win64 (展開先は FL_WIN64_DIR)・toolchain-emsdk (SS_EMSDK_ENV)
FL_WIN64_DIR=... FLE_EXTRA_ROOTS= FLE_BOOT_TAG=s4783 FLE_BOOT_RUNS="default" bash tools/flelift/boot/fle6_measure.sh   # lift 78 s + clang 92 s + boot 10 s
FL_WIN64_DIR=... bash tools/flelift/boot/survey_drive.sh 150 20                # mode 0 (既定) → results/survey_seg_0.json
FLE_IPP=3 FL_WIN64_DIR=... bash tools/flelift/boot/survey_drive.sh 150 20      # mode 3
FLE_SHARDS=8 FLE_BOOT_WORK=$PWD/tools/flelift/work/boot FL_WIN64_DIR=... bash tools/flelift/boot/build.sh strict
x86_64-w64-mingw32-gcc -O0 -o probe.exe tools/flelift/boot/iltools_native_probe.c && /usr/lib/wine/wine64 probe.exe   # D-3
```
