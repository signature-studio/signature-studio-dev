# flengine REPORT 付録

`REPORT.md` の行数上限 (250 行・`docs/DOC_MAP.md` §1) を超えないよう、本付録へ分割移動した節。内容は削除していない。

## 6i. S1 (soft) の unit 304/555 調査 (#1442 / GUI-21)

**測定 commit `719f1c43`。実行コードは現 HEAD と同一** (`git diff 719f1c43 HEAD -- tools/gui tools/m11 tools/shim tools/shared ':!*/results/*' ':!*.md'` が 0 行。差分は `tools/gui/flengine/REPORT*.md` の文書のみ)。

実行: `EMSDK_ENV=[EMSDK]/emsdk_env.sh RETDEC=[RETDEC]/bin/retdec-decompiler FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/gui/flengine/e2e.sh` (foreground・1 回・runner 4 vCPU・直列)。
素材: `fl-win64` (`$RUNNER_TEMP/fl-win64`)・`work-m11` (`tools/m11/work/` に展開)・`toolchain-emsdk` (`[EMSDK]`)・`toolchain-retdec` (`[RETDEC]`)・`x86_64-w64-mingw32-gcc` (`[APT-MINGW]`)。

| 実行 (測定 commit `719f1c43`) | rc | 所要 | load (開始→終了) | 結果 |
|---|---|---|---|---|
| `bash tools/gui/flengine/e2e.sh` | **1** | 388 s (e2e 内計測)・6 分 28 秒 (`time`) | 0.85 → 1.08 | judge **13/14**。FAIL は S1 のみ `870/1/47/24/0` (base `867/1/47/27/0`)。他 13 gate PASS: R1 (first `LoadStringW`)、R2 (reached 33 ≥ 19・missing=[])、S2、P1 (`RegisterClassW=3`)、P2〜P5 (P4 hwnd `0x110000f`・P5 `0x110000e`)、W1 (11 / 8)、L1・A1・B1 (units 52)。ネガコン N1〜N9 は期待どおり FAIL。selftest 506 passed / 0 failed |

- **base の値について**: 旧版の本文・REPORT にあった base `872/1/47/22/0` は測定 commit `549e6817` 時点の値で、現 HEAD では同じ build の再測定が `867/1/47/27/0` になる。判定は現 HEAD の値 (base `867/1/47/27/0`) で揃える。
- **build の重複解消 (現状)**: `tools/gui/flengine/build.sh` の user32 改名 (`-DEnumDisplayMonitors=m11_win_…` `-DGetMonitorInfoW=m11_win_…`) は現 HEAD にまだ残っている (`origin/main` には無い)。`tools/m11/m11_win.c` 側は `97db5a58` (main) で `EnumDisplayMonitors` / `GetMonitorInfoW` を `weak` 化済み。現在は両方が効いており、どちらか片方だけでも重複は解消する。旧記述の「改名を削除した」は誤り。
- **S2 判定式の変更 (`8a6dcf4b`、main 取り込み済み・本 PR では不変)**: 旧式は「ff の fail-fast API は soft で STUB 必須」 (`ffu <= stub_soft and not (...)`)。新式は「soft で fail-fast が増えないこと」 (`sfu <= ffu and ffu <= (stub_soft | sfu)`)。`git diff 8a6dcf4b HEAD -- tools/gui/flengine/judge.py` の S2 行は差分 0。現 HEAD の実測では旧式・新式とも PASS (ff fail-fast `LoadImageW` 1 unit、soft fail-fast 0、soft STUB `LoadImageW`)。判定結果は変わらない。
- **unit 別の突き合わせ** (測定 commit `549e6817` の時点): base を同 build で `GF_SURVEY_UNITS` 付きで取り直し、差は **101 (base `trap halt0->longjmp` / soft `ok`)、291 と 296 (base `trap oob` / soft `ok`)** の 3 unit のみ。方向は全て base→soft の trap 解消。
- **304 と 555 は base・soft の両方が `memory access out of bounds`** (base 側も ok ではない)。923 も両方 OOB。issue 本文の「base は ok」は現 main の測定と合わない。GUI 結合による新規 trap ではない。
- **304/555 の真因 (受入条件 1)**: 未達。`[M11-N91]` (#1426・OPEN: OOB 直前の tbl/cnt/obj の実値採取と obj の生成元特定) と #714 (`function_535c2e` 系) の既存調査にある。本 run では wasm の local を読む計測を入れていない。
- **#1275 系統の判定 (受入条件 2)**: 同系統ではない。#1275 (`tools/m11/trap_triage/REPORT_1275.md`) の 304/555 は **ClassCreate ON 時の abort** (`function_535c2e` の未定義 closure 外)。本 e2e は ClassCreate OFF (既定) で、304/555 は OFF でも OOB のまま。OFF の OOB は `function_535bf2` が先頭フレーム (REPORT_1275 §3 の OFF 行)。したがって OFF の OOB 原因は #1275 の abort とは別経路で、#1426 側。
- **S1 の残り (101/291/296)**: base 側だけ trap する 3 unit。survey の順序依存 (REPORT §5-6 の既知) か GUI 実装の差かは未切り分け。子 issue #1635 `[GUI-22]` で扱う。

未解決 (起票先付き): 受入条件 1 は #1426 (304/555/923 の OOB 実値採取)。S1 の 3 unit は #1635 `[GUI-22]`。現 HEAD の S1 FAIL (`870/1/47/24/0` vs `867/1/47/27/0`) は本 PR で解消しない (`Refs #1442`)。

## 6j. GetMonitorInfoW / EnumDisplayMonitors の重複定義 (#1559 / M11-N102)

**測定 commit `60932d35` (main)。実行コードの差分 0** (`git diff 60932d35 HEAD -- tools/gui tools/m11 tools/shim tools/shared ':!*/results/*' ':!*.md'` が 0 行)。

- **重複は現 HEAD で再現しない**。issue 本文の「`wasm-ld: duplicate symbol` で build 段停止」は `97db5a58` (`m11_win.c` の weak 化) と `549e6817` (`build.sh` の `-DEnumDisplayMonitors=m11_win_…` 改名) より前の記述。`tools/gui/flengine/build.sh` の link ログは `duplicate symbol: 0` (L1 link[ff] / link[soft] PASS)。
- **正とする定義 = GUI 側 (`tools/gui/src/gui_core_ext.inc` の `gui_impl_GetMonitorInfoW` / `gui_impl_EnumDisplayMonitors`)**。理由: `build.sh` が `m11_win.c` 側を `m11_win_*` に改名しており、`obj/win.o` の `m11_win_EnumDisplayMonitors` / `m11_win_GetMonitorInfoW` (weak) は link 上どこからも参照されない (`gen/exclude.txt` にも載る)。実際に使われるのは `gui/gui_adapt_w32.o` の `EnumDisplayMonitors` / `GetMonitorInfoW` → `gui_impl_*`。
  - 差分: `m11_win.c` 仮実装 = 1920x1080・monitor 1 件 (`0x10001`)・`GetMonitorInfoW` は `hMon == 0x10001` のみ受理・callback を 1 回呼ぶ。GUI 側 = `HMON_PRIMARY` (`0x7B000001`)・画面サイズは `gui_sh()` の `screen_w/h`・`MONITORINFOEXW` (cbSize 104) の `szDevice` 対応・`EnumDisplayMonitors` は `pclip` で矩形を交差。
  - 本 run の判定 (R2) は GUI 側の到達で PASS (下表)。`m11_win.c` の仮実装は不要になったが、削除は `tools/m11` の範囲で行うため本 PR では触らない。

| 実行 (測定 commit `60932d35`・foreground・各 1 回) | rc | 所要 | load (開始→終了) | 結果 |
|---|---|---|---|---|
| `bash tools/m11/ldfix/f4_e2e.sh` | **0** | 288 s | 0.95 → 1.10 | F1・F2・D1 (`RegisterClassW` 2→3・ret `0x0`→`0x110000f`)・D2・P1 (units 52/52・ok 870/870)・A1 ALL PASS。ネガコン N1〜N4 は期待どおり FAIL |
| `bash tools/gui/flengine/e2e.sh` | **1** | 371 s (e2e 内計測)・6 分 13 秒 (`time`) | 1.13 → 1.06 | judge **13/14**。FAIL は S1 のみ `870/1/47/24/0` (base `867/1/47/27/0`)。他 13 gate PASS: L1 (ff/soft とも `sigmismatch/undefined/duplicate = 0/0/0`)・A1 (193/193/173/20)・B1 (units 52)・R1 (first `LoadStringW`)・**R2 (reached 33 ≥ floor 19・`missing=[]`)**・S2・P1 (`RegisterClassW=3`)・P2〜P5・W1 (11 / 8)。ネガコン N1〜N9 は期待どおり FAIL。selftest 506 passed / 0 failed |

- **R2 再確認 (受入条件 4)**: 重複解消後の現 HEAD で `EnumDisplayMonitors` / `GetMonitorInfoW` を含む 33 API が到達し、floor 19 を満たす (`missing=[]`)。
- **S1 FAIL は本 issue の範囲外**: 304/555/923 の OOB と 101/291/296 の差は §6i (#1442) の既存未解決で、#1426・#1635 が扱う。

`results/baseline_survey.json`・`results/ir_sha256.txt` は上記 e2e 実行で再生成された値 (現 HEAD の base `867/1/47/27/0`・IR sha256 の更新) に揃えた。
