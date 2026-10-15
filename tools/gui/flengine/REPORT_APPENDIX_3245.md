# REPORT 付録 — WIN-19 (#3245): LoadImageW の shim 実装と boot 停止点の実測

測定 commit: `2c7f14fe5` (`fix(gui): LoadImageW の ID 制限の記述を LoadIconW/LoadCursorW と揃える`。コードを変えた最後の commit)。PR 本文の HEAD はこの後に results の commit だけを積む (§6)。素材: [WIN64] (fl-win64 26.1.7.5653)、[EMSDK]、[RETDEC] (v5.0)、work-m11。

## 1. 結論

| 受入条件 | 結果 (測定 `2c7f14fe5`) |
|---|---|
| 1. LoadImageW を IMAGE_BITMAP / IMAGE_ICON / IMAGE_CURSOR の仕様で実装、native selftest 追加 | **達成**。selftest `512 passed, 0 failed` (変更前 506) |
| 2. e2e B1 PASS・JUDGE 14/14 | **未達**。B1 PASS (base と一致)。JUDGE 13/14 (S1 のみ FAIL)。S1 の原因は未特定 (#3352) |
| 3. boot が init 1675 (`InitializeCriticalSection(0x12bd390)`) に到達したか | **head では未計測** (§4。head の boot は完了するため前提が変わった。#3353) |
| 4. `cfi_probe.mjs` が `EnterCriticalSection` を越えるか | **越えない**。`_CreateFruityInstance` 未 export で停止 (head で再測定。§5。#3353) |

## 2. 実装 (`tools/gui/src/gui_core.c` の `LoadImageW`)

- 観測した実呼出し (survey の unit 114、変更前の fail-fast 直前に一時出力で採取。計装は削除済み): `LoadImageW(hinst=0x0, name=0x7F86, type=2 (IMAGE_CURSOR), cx=32, cy=32, load=0x8000 (LR_SHARED))`。`0x7F86` は IDC_SIZEALL。
- IMAGE_BITMAP (0): `LoadBitmapW(hinst, name)` へ委譲。`cx`/`cy` が 0 でなければ `GetObjectW` の実寸と比較し、不一致は fail-fast (拡縮は未実装)。
- IMAGE_ICON (1) / IMAGE_CURSOR (2): `hinst != 0` (module 資源。RT_GROUP_ICON の decode は未実装) は fail-fast。`hinst == 0` は `LoadIconW(0,name)` / `LoadCursorW(0,name)` へ委譲 (擬似ハンドル、既定寸 32x32)。`name` の ID 制限は無い (LoadIconW / LoadCursorW と同じ既存挙動)。`cx`/`cy` が 0 か 32 以外は fail-fast。
- `LR_SHARED` (0x8000) と `LR_DEFAULTSIZE` (0x40) は無視する (擬似ハンドルは既に共有で、既定寸が 32x32 のため)。それ以外の load フラグ、文字列名 (`name >= 0x10000`)、未知の type は fail-fast。
- fail-fast メッセージは `hinst / name / type / cx / cy / load` を全て含む (`liw_fail`)。

## 3. e2e 実測 (測定 commit `2c7f14fe5`)

- 実行: `bash tools/gui/flengine/e2e.sh` (foreground)。476 s、load 開始 `0.47 0.39 0.17` → 完了 `1.14 1.01 0.58`、rc 1 (JUDGE 13/14、S1 のみ FAIL)。
- 素材: fl-win64 を `$RUNNER_TEMP/fl-win64` に、work-m11 を `tools/m11/work/` に展開。EMSDK_ENV と RETDEC は runner の `/opt` を使用。

| 項目 | 結果 |
|---|---|
| B1 boot parity | PASS: units_run 109 (base 109) / dllmain_done True / threw None (base None) / GetMem 761 FreeMem 24 / icall_miss 7 |
| units_run / init_count | 109 / 111 (base 109 / 111) |
| R1 最初の GUI API | PASS: LoadStringW (IMPL) calls=3、reached 24 |
| 窓 (P4 TApplication / P5 TLightweightLayeredControl) | PASS: hwnd 0x1100013 / 0x1100012 |
| R2 survey reach floor | PASS: reached 33 (floor 19) |
| S1 survey parity (soft) | **FAIL**: ok/noproc/miss/trap/clobber = 873/1/47/21/0 (base 871/1/47/23/0)。ok +2 / trap -2 の unit 単位の原因は未特定 (#3352) |
| S2 soft が ff 以上に fail-fast しない | PASS (ff fail-fast APIs=[]、soft STUB APIs=[]) |
| L1 link / A1 adapters | PASS / declare 193 adapter 193 impl 174 stub 19 |
| W1 WNDCLASS scan / P1〜P5 | PASS (WNDCLASS 11、最終 IR 外 0) |
| 4b `__pe_image` parity | PASS (P1/P2 LB=0 と LB=0x10000、N1〜N3) |
| native selftest | 512 passed, 0 failed |
| ネガティブコントロール N1〜N9 | 9/9 期待どおり FAIL / 非 0 |

- 取り込み前 (`ad5b4da3`) の base は boot が `unreachable` で units_run 52 / init 54 で停止していた。取り込み後 (`1bb44ab66` 以降) は base も boot が完了する (109 / 111)。変化の原因は main 側の `tools/m11`・`tools/shared` の変更で、本 PR の shim ではない (base が同値に変わったため)。

## 4. boot の init 1675 到達 (受入条件 3)

- head (`2c7f14fe5`) では**未計測**。取り込み後の boot は完了する (`dllmain_done True` / `boot_threw None`) ため、`unreachable` 停止を前提にした旧計装の結論は head に当てはまらない。
- 履歴: `ad5b4da3` 時点で `InitializeCriticalSection` の計装 (gitignore の検証コピーのみ。repo には残っていない) を行い、boot 中に `0x12bd390` は出なかった。
- 再測定は #3353 [WIN-22] で行う (head で関数 `function_1266a60` → `function_423940` の到達を計装で確認)。

## 5. cfi_probe.mjs (受入条件 4)

- head で再実行 (`node tools/gui/flengine/cfi_probe.mjs --out tools/gui/flengine/results/cfi_probe_3245.json`): `boot = {ok: true}` (`dllmain_done`)、`call = {returned: false, err: "mod._CreateFruityInstance is not a function"}`。`EnterCriticalSection` には届かない。`boot.err` が `[object Object]` なのは、boot の例外が Error でなく `String(e)` で整形されるため (`cfi_probe.mjs` 22 行目)。判断には影響しない。整形は未修正で #3353 で扱う。
- 停止点: `_CreateFruityInstance` が export されていない。現素材の `boot_final.ll` / `boot_final3.ll` に `@CreateFruityInstance` の定義が無い (head で grep 0 件)。e2e.sh は IR に定義がある時だけ export する。
- 次の停止点: boot7 (CreateFruityInstance の closure 取込, WIN-4 #2715) を含む IR の再生成 (素材側)。#3353 で扱う。

## 6. 差分 (測定 commit 以降のコード差分)

- `git diff 2c7f14fe5 HEAD -- tools/gui/src tools/gui/test tools/m11 tools/shared`: **出力 0 行** (測定 commit 以降は `results/*.json`・`IMPORTS.md`・本 REPORT・PR 本文の差分だけ)。
- `e2e.sh` 再実行で変わったのは `results/baseline_boot.json` の 1 行 (`classes.file` の絶対パスを `tools/m11` 相対の `work/ptrclass/classes.json` に直した (`m11_ptrcheck.mjs`)。他の結果ファイルは前回と同一)。
