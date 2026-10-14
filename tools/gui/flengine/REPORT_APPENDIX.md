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

## 7. WIN-4 (#2715): CreateFruityInstance の closure 取込と呼出し (部分達成)

既知類型との関係: 該当 DEFECTS 行なし。新規の sigfix 欠陥 1 件 (§7-3, 行案あり)。検証起点は origin/main `26f90ada` (本 PR の base)。

**測定 commit `5f9d7cbd`** (コードを変えた最後の commit。`02c9fbda` は lift と probe の追加)。その後の commit は文書のみ。
差分の証跡 (WORKFLOW §6): `git diff 5f9d7cbd HEAD -- tools/gui/flengine tools/m11 ':!*.md' ':!*/results/*'` の出力は 0 行。`*.md` を含めた差分は `REPORT.md` と `REPORT_APPENDIX.md` の 2 件のみ (`--name-only`)。

### 7-1. 受入条件の状態 (元の #2715 の 8 項目)

本 PR の範囲は縮小後の #2715 (1・2 の到達・4・7)。残りは子 issue へ移した。

| 受入 | 状態 | 根拠・行き先 |
|---|---|---|
| 1 closure の実測と seed 追加 | 達成 | §7-2 |
| 2 glue 経由で `CreateFruityInstance` を呼ぶ | 呼出しの到達まで達成。完了は未達 | §7-4。完了 → #2880 [WIN-11] |
| 3 Run ループ (S22) の Worker 置換 | 未着手 | → #2904 [WIN-12] |
| 4 観測の REPORT | 達成 | §7-4・§7-5 |
| 5 shim の追加 | 0 件 (止まりは未実装 API ではない) | §7-5。条件付きの追加は #2880 |
| 6 `open()` の trace | 未着手 | → #2905 [WIN-13] |
| 7 既存 gate の回帰なし | 達成 (本 PR による新規の回帰は無い) | §7-6。既存 FAIL は main 祖先でも同型 (§6j) |
| 8 #174 の証跡 | 未達 | → #2904 [WIN-12] (窓の実登録を経た生成) |

### 7-2. closure 測定 (`gf_seed_closure.py`)

seed = `0x1375990` (PE export `CreateFruityInstance`、`.pdata` の大きさ 3,213 B)。call/jmp 即値の閉包は 6,591 関数 / 1,965,676 B。
現 IR (`tools/m11/work/boot_final3.ll`) に既にあるのは 4,520 関数、閉包外は **2,071 関数 / 761,038 B**。
`grep -c 1375990 tools/m11/work/boot_final3.ll` = 0 (lift の label 無し)。
再現: `python3 tools/gui/flengine/gf_seed_closure.py --pe <PE> --ir tools/m11/work/boot_final3.ll --seed 0x1375990 --json-out <json> --ranges-out <ranges>`

### 7-3. lift と IR 生成

| 手順 | 結果 (実測) |
|---|---|
| `m11_lift.sh work/boot_ranges_cfi.txt boot7 780` | rc 0・**3 分 24 秒**・`boot7.lift.ll` 222,014 行。RetDec は 0x1375990 を export 名 `@CreateFruityInstance` で出力 |
| `m11_gen_ir2.sh` (boot7 を CH に追加) | rc 0・**1 分 21 秒**・`boot_final.ll` 707,524 行、define 9,531 (取込前 7,422) |
| `m11_build.sh` (1 回目) | rc 1: `work/boot_final3.ll:78502: invalid cast opcode for cast from 'i32' to 'i8'` |
| 同 (修正後) | rc 0・35.7 秒・wasm-ld signature mismatch 0 / undefined 0 |

- 原因: `call i64 @function_6bc010(i64 %48, ptr null)` の callee は i8 引数。`m11_post.py` の `_conv` が ptr→i8 を `zext i32 → i8` で作っていた (狭い型への zext は無効 IR)。`trunc` に修正。
- **`_conv` の変更の効き方 (推定。実測は未実施)**: 変更されたのは、旧版が狭い型へ無効な `zext` を出していた枝だけ。clang はこの IR を拒否する (上の 1 回目の build 失敗)。したがって旧版で build が通った入力では、この枝は通っていないはずで、出力は変わらないと推定する。ただし同一入力での実測は本 run で行っていない (§7-7)。
- **`i1`・`i16` の使われ方 (minor m1)**: 本 PR で観測した使用は i8 (`function_6bc010` の引数) のみ。`i1` (trunc = 下位 1 bit) を非 0 判定に使う箇所は boot7 で確認していない。`icmp ne` への変更は測定値を変えるため本 PR では行わない。
- **define 増分 2,109 (minor m2)**: 9,531 − 7,422 = 2,109。閉包外 2,071 と `@CreateFruityInstance` 1 で 2,072 件。残り 37 件の内訳は未切り分け (RetDec の補助 define と推定。`boot7.lift.ll` が本 run に無く確認不可)。また 7,422 は §7-7 の通り本 run で同じ IR を再現できないため、2,109 を boot7 だけの寄与とは断定しない。
- DEFECTS 行案: 症状=clang が invalid cast で止まる / 根本原因=sigfix の ptr→narrow 変換が zext / 検出信号=`invalid cast opcode` / 修復=trunc (`m11_post.py` `_conv`)。

### 7-4. 呼出し (`cfi_probe.mjs`)

- 手順: DllMain attach (`_m11_boot_enter(0,1)`) → THostInstance (0x38 B) を wasm の malloc に作る (+0 ダミー vtable、+8=1、+0xc=0、+0x18=ANSI `"FL Studio"` のポインタ、+0x30=cmdline 0x8000 B) → `_CreateFruityInstance(0xC0, 0xEDE95A, host, &iface)`。
- 結果: `boot_enter` は trap `unreachable` (`boot_threw`)。`CreateFruityInstance` は `[shim] FAIL-FAST: unimplemented Win32 API: EnterCriticalSection (未初期化/未登録)` の後に `abort()` (1 ms)。`iface` は 0 のまま。GUI-REACH は `LoadStringW` ×3 のみ。
- 止まった地点: `EnterCriticalSection` の呼出元 VA は未特定 (IR 中の `call void @EnterCriticalSection` は 4 箇所)。この CS は `InitializeCriticalSection` で登録されていない (または別アドレス) と読める。→ #2880。

### 7-5. shim に足すべき API

0 件。`EnterCriticalSection` は `tools/shim/src/sync.c:255` に実装済みで、止まりは「登録表に無い CS への lookup 失敗」(未実装 API ではない)。原因は lift 側の CS 初期化経路の欠落の可能性があり、#2880 で切り分ける。

### 7-6. 既存 gate (`bash tools/gui/flengine/e2e.sh`)

| 実行 (測定 commit `5f9d7cbd`・foreground・各 1 回) | rc | 所要 | judge | S1 (soft vs base) |
|---|---|---|---|---|
| boot7 あり | 1 | 543 s (load 1.05 1.00 0.78) | 13/14 | `870/1/47/24/0` vs `872/1/47/22/0` (unit 304・555 が base ok → soft OOB) |
| boot7 なし (CI と同じ素材構成) | 1 | 473 s (load 1.05 1.01 0.88) | 13/14 | `872/1/47/22/0` vs `870/1/47/24/0` (同じ 2 unit が逆向き) |

- 残り 13 gate は PASS (L1 0/0/0・A1 193=193・B1 units_run 52 = base・R1・R2・S2・P1〜P5・W1)。ネガコン 9 件は期待どおり FAIL。`selftest` は boot7 ありの run で 506 passed / 0 failed。
- **S1 の FAIL は main でも同型で再現済み (既存の FAIL)**: 測定 commit `60932d35` (origin/main `26f90ada` の祖先。`git merge-base --is-ancestor 60932d35 26f90ada` で確認) の `bash tools/gui/flengine/e2e.sh` は rc 1・judge 13/14・S1 `870/1/47/24/0` (base `867/1/47/27/0`) (§6j)。本 PR の boot7 run と soft 値が同じ。よって本 PR による新規の回帰は確認されず (既存の FAIL の再現)。
- 符号の入れ替わり (boot7 の有無で 304・555 の base/soft が逆になる) は順序依存 (REPORT §5-6 と同型) と読む (推定)。
- `boot_threw` は `unreachable` (旧 REPORT §5-1 は `memory access out of bounds`)。boot7 なしの run でも同じ値のため、本 PR の追加 IR に起因するとは言えない。要因は未切り分け。
- survey の reach は `RegisterClassW` ×1〜2 / `CreateWindowExW` ×1〜2 (`survey_ff.json` / `survey_soft.json`)。旧 REPORT §1 の「RegisterClassW 自然到達 0」と異なる。差の原因は未切り分け。

### 7-7. boot7 なし run の IR・結果と main 記録の差 (「既定の挙動は変わらない」は未検証)

本 PR の `results/` の値 (boot7 なし run で再生成された後に残った値) は、main の記録と次のとおり異なる。

| 対象 | main の記録 | 本 PR の値 |
|---|---|---|
| `results/ir_sha256.txt` `boot_final.ll` | `69c774…` | `7bf7a2…` |
| `results/ir_sha256.txt` `boot_final3.ll` | `010451…` | `c763f8…` |
| `results/probe.json` `gui_shared_ptr` | `271677696` | `271679808` |
| `results/baseline_boot.json` `wasm_size` | `6913292` | `6914481` |
| `results/baseline_survey.json` | `867/…/27` | `870/…/24` |

- 確認できたこと: `m11_gen_ir2.sh` の boot7 行は `work/boot7.lift.ll` がある時だけ CH に加わる (`[ -f ... ] &&`)。boot7 あり・なしの e2e は、どちらも judge 13/14 を返した (§7-6)。
- **確認できていないこと**: boot7 なしの IR が main と同一であること。上の差は、(a) 素材 (`work-m11`) の差、(b) `_conv` の変更 (§7-3 の推定で、旧版が build を通す入力では枝に入らないはず)、のどちらかで生じたが、切り分けていない。
- 最小の確認: 同じ素材 (`work-m11`) で main (`26f90ada`) と head の `tools/m11` をそれぞれ用意し、boot7 なしで `m11_gen_ir2.sh` を実行して `boot_final.ll` の sha256 と差分行数を比べる。**本 run は `$ARTIFACTS_DIR` に `fl-win64.tar.zst` しか無く、`tools/m11/work/` も無いため未実施。** 「既定の挙動は変わらない」の記述は撤回した。
- 起票先: PR 本文の未解決表のみ (再測定。素材 `work-m11` を要する)。

### 7-8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `CreateFruityInstance` の経路で登録されていない CS に `EnterCriticalSection` (§7-4) | 呼出しの完了と S12 以降に届かない | #2880 [WIN-11] (`親: #2715`) |
| Run ループ (S22) の Worker 置換と、窓の実登録を経た生成 (受入 3・8) | 窓は未生成 | #2904 [WIN-12] (`親: #2715`) |
| `open()` 相当の呼出しの trace (受入 6) | asset 集合が未取得 | #2905 [WIN-13] (`親: #2715`) |
| boot7 なし run の IR・結果が main 記録と異なる (§7-7) | 「既定の IR は変わらない」は未検証 | PR 本文の未解決表のみ (再測定) |
| define 増分の内訳 37 件 (§7-3 m2) | boot7 の寄与の断定ができない | PR 本文の未解決表のみ (再測定) |
| S1 の順序依存: unit 304・555・923 (base と soft の OOB の向き) | flengine e2e judge 13/14 (main 同型) | #1426 (OPEN) |
| S1 の順序依存: unit 101・291・296 (base のみ trap) | 同上 | #1635 (OPEN、Refs #1442) |
| boot の trap 種別 (OOB → unreachable) と survey の RegisterClassW 値 (0 → 1〜2) の差 | 旧 REPORT との整合 | PR 本文の未解決表のみ (切り分けは再測定) |

## 8. WIN-13 (#2905): CreateFruityInstance 起動中の open 系呼出しの trace

既知類型との関係: 該当なし (trace の追加のみ。lift の変換は変えていない)。
測定 commit: `37cc1097` (コードの最後の commit)。後続の commit は本節の正の対照スクリプト・結果 JSON・本文の追加のみ (`git diff 37cc1097 HEAD -- tools/shim tools/gui/flengine/cfi_probe.mjs` の出力は `tools/gui/flengine/cfi_probe.mjs` 以外の差分 0 を確認する)。

### 8-1. 仕組み (`tools/shim/src/file.c`・wasm のみ)

CreateFileW の 1 呼出し = printErr の 1 行 `SHIMOPEN {json}`。json は `op`・`path` (Win パス)・`ok`・`w`・`err` (GetLastError)・`access`・`disp`・`caller`・`frames`。
`caller` は JS スタックの最初の `function_<VA>` (lift 関数名)。native ビルドでは何も出さない。
`cfi_probe.mjs --trace-out <jsonl>` が行を JSONL に集める。`op`・`path`・`ok`・`w` は assettrace の trace 形式 v1 と同じ (`tools/startup/assettrace/assettrace.mjs` にそのまま読める)。

### 8-2. 正の対照 (`tools/gui/flengine/open_trace_posctl.mjs`)

存在しないパス `C:\nonexistent\x.txt` を `_CreateFileW(GENERIC_READ, OPEN_EXISTING)` で 1 回呼ぶ。
結果: `n_shimopen` 1・`ok` false・`err` 2 (ENOENT)・`w` false・`path` 一致。**PASS (exit 0)**。
`caller` は空。JS から直接呼んだため期待どおり。`frames` は `wasm-function[19797]:0x4f311d` のような index 表記で、**wasm に name section が無く `function_<VA>` が出ない** (→ §8-5)。

### 8-3. 実測: CreateFruityInstance の呼出し (`cfi_probe.mjs`・boot7 あり)

| 項目 | 結果 |
|---|---|
| `m11_boot_enter` | `unreachable` (WIN-4 §7-4 と同じ) |
| `CreateFruityInstance(0xC0, 0xEDE95A, host, &iface)` | `Aborted` (`[shim] FAIL-FAST: unimplemented Win32 API: EnterCriticalSection (未初期化/未登録)`)・1 ms |
| open 系呼出し (CreateFileW) | **0 件** (trace 0 行 = `tools/gui/flengine/results/cfi_probe_win13.json` の `open_trace`) |
| `icall_miss` / 到達 API | 5 / `LoadStringW` 1 件 (IMPL) |

止まった地点 (`EnterCriticalSection`) より前に、この経路がファイルを開くことは無かった。
よって実 FL の起動 asset 集合は、この経路では採れない。採れるのは #2880 の修復後になる (→ [WIN-15] #2965)。

### 8-4. 既存 gate (`bash tools/gui/flengine/e2e.sh`・測定 commit `37cc1097`)

| 項目 | 結果 |
|---|---|
| 所要 | 379 s (開始 load 0.77 0.70 0.52・終了 1.11 1.00 0.73・nproc 4) |
| judge | 13/14 (S1 FAIL のみ・既存) |
| S1 (soft) | `870/1/47/24/0` (base `872/1/47/22/0`)。§7-6 の boot7 あり run と同値 |
| B1 boot parity | PASS (units_run 52 = base 52) |
| R1・R2・P1〜P5・W1・A1・L1 | PASS (P4 TApplication 窓 `hwnd=0x110000f`・P5 `hwnd=0x110000e`) |
| ネガコン N1〜N9 | 9 件すべて期待どおり FAIL |
| selftest / pe_image parity | 506 passed 0 failed / PASS |

`results/*.json` は boot7 あり構成で再生成されたが commit しない。CI 構成 (boot7 なし) の記録 (S1 `872/22`) と値が違うため。
本節の数値が e2e の正の記録。

### 8-5. 未達と起票先

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 呼出元 VA (wasm function index → `function_<VA>`) | 受入 1 の「呼出元 VA」が未取得 | [WIN-14] #2964 |
| 実 trace の採取 (EnterCriticalSection 修復後)・asset 集合・実 FL との差 | 受入 2 未達。実 trace が 0 件 | [WIN-15] #2965 (依存 #2880) |
| shimx 側 (`tools/shimx`) は構造化 trace を出さない (未変更) | assettrace REPORT §4 の shimx 行は残る | PR 本文の未解決表のみ |

### 8-6. 検証 (実測)

| 項目 | 結果 |
|---|---|
| `bash tools/shim/test.sh` | exit 0 (18 s)・shim 53 API × MT/ST・全 PASS |
| `gcc -Wall -c tools/shim/src/file.c` (native) | 警告 0 |
| 再現 | `bash tools/gui/flengine/e2e.sh` / `node tools/gui/flengine/cfi_probe.mjs --out <json> --trace-out <jsonl>` / `node tools/gui/flengine/open_trace_posctl.mjs` |

## 9. WIN-11 (#2880): EnterCriticalSection の失敗 CS と初期化経路 (部分達成)

結論: fail-fast の CS は `0x12bd390` (実測・動的引数)。呼出元 VA と boot の trap 地点は未特定 (子 issue #3077 [WIN-16])。測定 commit `ae963e28`。実測と未解決の全文は [REPORT_APPENDIX_2880.md](REPORT_APPENDIX_2880.md)。
