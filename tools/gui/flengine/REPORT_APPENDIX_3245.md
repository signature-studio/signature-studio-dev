# REPORT 付録 — WIN-19 (#3245): LoadImageW の shim 実装と boot 停止点の実測

測定 commit: `ad5b4da3` (`feat(gui): implement LoadImageW`)。比較元: `c6eca3e1` (`origin/main`)。素材: [WIN64] (fl-win64 26.1.7.5653)、[EMSDK]、[RETDEC] (toolchain-retdec)。

## 1. 結論

| 受入条件 | 結果 |
|---|---|
| 1. LoadImageW を IMAGE_BITMAP / IMAGE_ICON / IMAGE_CURSOR の仕様で実装、native selftest 追加 | **達成**。selftest `512 passed, 0 failed` (変更前 506) |
| 2. e2e B1 PASS・JUDGE 14/14 | **未達**。B1 は変更前から PASS (§3)。JUDGE は 13/14 のまま (S1 FAIL, 前後で同値) |
| 3. boot が init 1675 (`InitializeCriticalSection(0x12bd390)`) に到達したか | **未到達** (boot 実行で CS-INIT `0x12bd390` が出ない, §4) |
| 4. `cfi_probe.mjs` が `EnterCriticalSection` を越えるか | **越えない**。`_CreateFruityInstance` の呼出し前で停止 (§5) |

## 2. 実装 (`tools/gui/src/gui_core.c` の `LoadImageW`)

- 観測した実呼出し (survey の unit 114, 変更前の fail-fast 直前に一時出力で採取。計装は削除済み): `LoadImageW(hinst=0x0, name=0x7F86, type=2 (IMAGE_CURSOR), cx=32, cy=32, load=0x8000 (LR_SHARED))`。`0x7F86` は IDC_SIZEALL。
- IMAGE_BITMAP (0): `LoadBitmapW(hinst, name)` へ委譲。`cx`/`cy` が 0 でなければ `GetObjectW` の実寸と比較し、不一致は fail-fast (拡縮は未実装)。
- IMAGE_ICON (1) / IMAGE_CURSOR (2): `hinst != 0` (module 資源。RT_GROUP_ICON の decode は未実装) は fail-fast。`hinst == 0` の標準 OIC_/IDC_ は `LoadIconW(0,name)` / `LoadCursorW(0,name)` (擬似ハンドル、既定寸 32x32)。`cx`/`cy` が 0 か 32 以外は fail-fast。
- `LR_SHARED` (0x8000) と `LR_DEFAULTSIZE` (0x40) は無視してよい根拠: 擬似ハンドルは既に共有で、既定寸が 32x32 のため。それ以外の load フラグ、文字列名 (`name >= 0x10000`)、未知の type は fail-fast のまま。
- fail-fast メッセージは `hinst / name / type / cx / cy / load` を全て含む (`liw_fail`)。0 の黙殺はしない。

## 3. e2e 実測 (変更前 = `c6eca3e1`、変更後 = `ad5b4da3`)

| 項目 | 変更前 `c6eca3e1` | 変更後 `ad5b4da3` |
|---|---|---|
| e2e 完了 (done 行) | 480 s, load 1.09 0.99 0.60, exit 1 | 482 s, load 1.26 1.01 0.75, exit 1 |
| JUDGE | 13/14 (S1 FAIL) | 13/14 (S1 FAIL) |
| L1 / A1 | PASS / impl 173, stub 20 | PASS / impl 174, stub 19 |
| B1 boot parity | PASS (units_run 52 = base 52, dllmain_done False, threw unreachable = base) | PASS (同左) |
| units_run / init_count | 52 / 54 | 52 / 54 |
| dllmain_done | False | False |
| 最初の GUI API | LoadStringW (IMPL) | LoadStringW (IMPL) |
| 窓 (P4 TApplication / P5 TLightweightLayeredControl) | hwnd 0x110000f / 0x110000e | hwnd 0x110000f / 0x110000e |
| R2 survey reach floor | reached 33 (floor 19) | reached 33 (floor 19) |
| S1 survey parity (soft) | FAIL ok/noproc/miss/trap/clobber = 872/1/47/22/0 (base 870/1/47/24/0) | FAIL 同値 |
| S2 soft/ff fail-fast | ff `LoadImageW` 1 unit / soft STUB `LoadImageW` | ff なし / soft なし |
| native selftest | 506 passed, 0 failed | 512 passed, 0 failed |
| ネガコン N1〜N9 | 9/9 期待どおり FAIL | 9/9 期待どおり FAIL |

- JUDGE 14/14 に届かない理由は S1 のみ。S1 は LoadImageW の変更で値が動かない (soft では変更前も STUB が 0 を返して同じ unit が ok になっていた)。S1 の差 (base より ok +2, trap -2) は既存の課題で、§6d / 付録 §6i の調査対象。
- B1 は変更前から PASS。B1 の判定式は base との一致のみで `dllmain_done` の真偽は要求しない (base も False)。issue 本文の「B1 FAIL」は当該 commit では再現しなかった。

## 4. 受入条件 3: boot の init 1675 到達 (計装)

- 計装: gitignore 対象の検証コピー `tools/gui/work/flengine/tree/shim/src/sync.c` の `InitializeCriticalSection` 先頭に `fprintf(stderr, "CS-INIT key=0x%x\n", ...)` を一時挿入して `build.sh` を再ビルド、`node run.mjs` (boot 既定) を 1 回実行。repo には残っていない (`git status` で確認)。
- 実測: boot 中の `InitializeCriticalSection` は 3 回 (`key=0x11eaf00`, `0x11f0800`, `0x10c63a50`)。`0x12bd390` は**出ない**。
- 結論: function_423940 (= `InitializeCriticalSection(0x12bd390)`) は boot 実行で未到達。boot は `unreachable` trap で止まる (`boot_threw`)。
- 限界: init 1675 の index と function_1266a60 そのものは計装していない。実測できたのは、boot 実行で `InitializeCriticalSection(0x12bd390)` の呼出しが無いことだけ。

## 5. 受入条件 4: cfi_probe.mjs

- `node tools/gui/flengine/cfi_probe.mjs --out tools/gui/flengine/results/cfi_probe_3245.json` の結果: `boot = {ok: false, err: unreachable}`、`call = {returned: false, err: "mod._CreateFruityInstance is not a function"}`。`EnterCriticalSection` には到達しない。
- 停止点: `_CreateFruityInstance` が export されていない。現素材の `boot_final.ll` / `boot_final3.ll` に `@CreateFruityInstance` の定義が無く (grep 0 件)、e2e.sh は IR に定義がある時だけ export する。次の停止点は boot7 (CreateFruityInstance の closure 取込, WIN-4 #2715) を含む IR の再生成 (素材側)。boot 自体は `unreachable` で先に止まる (§4)。

## 6. 差分 (測定 commit 以降の GUI コード変更)

- `git diff --stat c6eca3e1 ad5b4da3 -- tools/gui`: `IMPORTS.md` 8 行、`exports.txt` 1 行、`src/gui_core.c` +26、`test/selftest_p1.inc` +11、`results/*.json` (e2e 生成物)。
- `git diff ad5b4da3 HEAD -- tools/gui/src tools/gui/test`: 差分 0 (本付録と `REPORT.md` の追記だけが後続 commit)。
