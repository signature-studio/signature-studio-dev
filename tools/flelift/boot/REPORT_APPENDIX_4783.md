# REPORT_APPENDIX_4783 — 既定変更の影響の実測 (#4783)

> 分割移動元: `REPORT_APPENDIX_672.md` §D (main 取り込み時に 250 行上限を超えるため移動。内容は変えていない・見出し番号 §D / D-n はそのまま)。

## §D. 既定変更の影響の実測 (#4783・受入 1〜3)

> 測定 commit: `b60025c7d` (本 PR の HEAD・`origin/main` `02a31c7cd` 取り込み後・分割移動後)。
> 素材: `fl-win64` (`flstudio_win64_26.1.7.5653`)・`toolchain-emsdk` 6.0.12 (上流 `emsdk install 6.0.12`・`[EMSDK]` の既定位置は runner に無い)。lift は `fle6_measure.sh` の経路で `FLE_EXTRA_ROOTS=` (root 無し)、clang は `FLE_SHARDS=8`。
> 実測環境: 4 vCPU・load 0.6〜2.0。各 run n = 1。
> 注: 旧版の本節 (測定 commit `8aa9c0289`・mode 0 を既定とした値) は head で再測定した値に置き換えた。`FLE_IPP` 未指定の既定は main 側 (#672) で mode 3 になっているため、既定経路の値は mode 3 で書く。

### D-1 結論 (先出し)

- **既定経路 (`FLE_IPP` 未指定 = mode 3) の boot: units 895・`exit` (halt0 0)**。GetMem 3,680 / FreeMem 1,499・IPP `ptr_15F34A0` = 0x7f10001c (ok)。最初のウィンドウ無し (変化なし)。
- **ネガコン (`FLE_IPP=0`): units 209・`unlifted` (0x6a7b70)**。旧既定 (mode 0) の値。GetMem 1,890 / FreeMem 776・IPP ptr 0。
- **受入 1 (survey 942 unit・既定経路): 未達 (mode 3 の survey が測定できない)**。mode 0 の survey は測定できた (D-2)。mode 3 の survey は `InitContext.InitTable == 0` で `survey` が error になり、942 の functional 判定は得られていない (D-2・子 issue)。
- **受入 2 (ILTools native 読込): 未達**。wine では DLL が読めず実測できなかった (D-3)。native の成否は推定のまま。
- **受入 3 (他経路): 一部**。`boot_e2e.sh` 本体は plain の 1 TU clang が RSS cap (11,000MB) を超えて build できず未実行。strict / nosx は旧測定 commit の値のみで、head では未再測定 = 未確認 (D-4。受入 3 の結論には使わない)。
- 製品 KPI (起動・既定経路): 既定 units 895 (変更前の既定 mode 3 と同値)・ネガコン 209。最初のウィンドウ: 無し。本 PR 自身のコード変更は `merge_survey.py` のみで、起動経路は変えていない。

### D-2 survey (受入 1)

`survey_drive.sh 150 20` (1 セグメント・約 10 s)。正本は `results/survey_4810_mode0.json` の `survey.byCls` (mode 0)。mode 3 の error 記録は `results/survey_4810_mode3_error.json`。boot 結果は `results/boot_summary_s4810_default.json` (既定 mode 3) と `results/boot_summary_s4810_negctl.json` (`FLE_IPP=0`)。

| mode (head `b60025c7d`) | 結果 | 備考 |
|---|---|---|
| 0 (`FLE_IPP=0` = 旧既定) | ok 893 / empty 46 / unlifted 2 / noproc 1 (合計 942)・halt0 0 | unlifted = unit 280・659 (`0x6a7b70`)。unit 895 (`0x976da0`) は ok |
| 3 (既定 = `FLE_IPP` 未指定) | **測定不能**: `survey = {error: "InitContext.InitTable == 0"}` | boot-only (`fle6_measure.sh` default) は units 895 まで進む。survey 経路だけ `_InitLib` 後の状態が揃わない (子 issue) |

- 参考 (旧 `8aa9c0289` 測定の mode 0 = ok 892 / unlifted 3 (895 を含む)): head では unit 895 が ok で、値が一致しない。差分の原因は未切り分け (子 issue)。
- `merge_survey.py` の `covered` は jsonl に書かれない empty / noproc を数えないため、`results/survey.json` は 942 網羅を示さない。この集計の不整合は本 PR では直さず、子 issue に起票する (D-6)。
- boot 単独: `FLE_IPP=0` = units 209・GetMem 1,890 / FreeMem 776。既定 (mode 3) = units 895・GetMem 3,680 / FreeMem 1,499。

### D-3 ILTools native 読込 (受入 2): 未達

- 素材の `ILTools_x64.dll` (`block24347_PE.bin`・PE32+ x64 DLL・export 6 本・DllMain あり) を `tools/flelift/boot/iltools_native_probe.c` (`LoadLibraryW(L"ILTools")` → `GetProcAddress("CreateCursorFromFont")`) で wine64 9.0 (`/usr/lib/wine/wine64`) から実行した。
  - (a) ファイル名 `ILTools_x64.dll`: `LoadLibraryW` = NULL・err=126 (モジュール未検出)。`ILTools` は拡張子補完で `ILTools.dll` を探すため、この名前では見つからない。
  - (b) `ILTools.dll` に改名: `LoadLibraryW` = NULL・err=1114 (`ERROR_DLL_INIT_FAILED`)。wine のログは DllMain の GUI 依存 (ウィンドウ・ディスプレイドライバ) を示す。
  - (c) (b) + Xvfb: 120 s で timeout (rc=124)。DllMain から戻らない。
- **判定: native 読込は未実測** (wine の GUI 依存で偽陰性の可能性が高く、native の結論にできない)。
- 参考 (推定・未検証): boot は `LoadLibraryW(L"ILTools")` を呼ぶ (`0x815edc`)。素材の DLL 名は `ILTools_x64.dll` で、拡張子補完の `ILTools.dll` とは一致しない。このため native の既定探索でも見つからない可能性がある。mode 3 の前提「native は読めて非 0」は、この点を含めて未確定。

### D-4 他経路 (受入 3)

> 注: 本表は旧測定 commit `8aa9c0289` の値。head では未再測定のため **未確認 (head 未再測定)**。受入 3 の結論には使わない。

| 経路 | 結果 | 備考 |
|---|---|---|
| `boot_e2e.sh` (全 variant・`--fast`) | **未実行** | plain の `fle_lifted.c` を 1 TU で clang → peak 11,380〜11,458MB > cap 11,000MB で停止。`FLE_SHARDS=8` でも同じ (`boot_e2e.sh` の `cc()` は shard しない)。既存スクリプトの制約で本 PR の変更ではない (子 issue) |
| strict (`build.sh strict`・8 shard) | build OK (mismatch 0 / undefined 0 / dup 0) | mode 0: units 93・`soft` 停止・rc 0 / mode 3: units 93・`soft` 停止・rc 3 (ptr 判定 NG) |
| nosx (`build.sh nosx`) | build OK | mode 0 / 3 とも units 0・`exit` (rc 0 / rc 3)。mode 3 で `FLE_IPP` の shim を持たないため前進しない |
| trace / chk | 未実行 | 時間上限 |

- strict の mode 3 で rc=3 は `FLEBOOT_IPP_CHECK` の判定 NG (`ptr_15F34A0` が 0x7f10001c 以外) による。mode 3 の入力の正しさは strict では確認できていない。

### D-5 既定の影響 (まとめ)

- 既定 (mode 3) の boot-only は units 895 まで進み、ネガコン (`FLE_IPP=0`) の units 209 より先に進む。ただし mode 3 の survey は測定できていない (D-2) ため、942 unit の functional 判定は既定経路では未確認。
- ILTools の native 読込は未確定 (D-3)。『mode 3 が正しい入力』とは言えない。既定化は main 側 (#672) で決定済みで、本 PR はその既定を変えない。

### D-6 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ILTools native 読込 (受入 2) の実測。wine の GUI 依存で不可 | mode 3 の入力の正しさ | #4853 [FLE-30] |
| mode 3 の survey が `InitContext.InitTable == 0` で測定不能 (受入 1 の既定経路) | 既定経路の 942 functional 判定が無い | #4854 [FLE-31] |
| `boot_e2e.sh` の 1 TU clang の RSS cap 超過 (受入 3 の一部) | `boot_e2e.sh` 全 variant が build 不能 | #4855 [FLE-32] |
| `merge_survey.py` の covered が empty / noproc を数えない | `results/survey.json` の集計が 942 網羅を示さない | #4855 [FLE-32] (同じ子に含める) |
| strict mode 3 の ptr 判定 NG (rc 3) | mode 3 の strict 経路の正しさ | PM 判断 (`pm-decision`) |

### D-7 再現

```sh
# 素材: fl-win64 (展開先は FL_WIN64_DIR)・toolchain-emsdk 6.0.12 (SS_EMSDK_ENV)
FL_WIN64_DIR=... SS_EMSDK_ENV=... FLE_EXTRA_ROOTS= FLE_BOOT_TAG=s4810 FLE_BOOT_RUNS="default negctl" bash tools/flelift/boot/fle6_measure.sh   # lift 80 s + clang 99 s + boot 10 s × 2
FLE_IPP=0 FL_WIN64_DIR=... bash tools/flelift/boot/survey_drive.sh 150 20     # mode 0 (旧既定・ネガコン) → 正本 results/survey_4810_mode0.json
FL_WIN64_DIR=... bash tools/flelift/boot/survey_drive.sh 150 20               # mode 3 (既定) → InitTable == 0 で error (D-2)・正本 results/survey_4810_mode3_error.json
FLE_SHARDS=8 FLE_BOOT_WORK=$PWD/tools/flelift/work/boot FL_WIN64_DIR=... bash tools/flelift/boot/build.sh strict
x86_64-w64-mingw32-gcc -O0 -o probe.exe tools/flelift/boot/iltools_native_probe.c && /usr/lib/wine/wine64 probe.exe   # D-3
```
