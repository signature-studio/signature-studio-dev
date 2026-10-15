# REPORT_APPENDIX_3353 (WIN-22 #3353)

親 #3245 の子。(1) boot の init 1675 (`function_1266a60` → `function_423940` = `InitializeCriticalSection(0x12bd390)`) への到達を計装で実測する。(2) CreateFruityInstance の閉包 (boot7) を IR に取り込み、`cfi_probe.mjs` が `EnterCriticalSection` を越えるかを記録する。
既知類型との関係: 該当なし (新規の lift 欠陥類型は観測していない)。

## 1. 結論 (測定版: #3245 の head `8bc881c4d` + 本 PR の `6a17a3c47`)

- boot は完走する (`dllmain_done` True・`boot_threw` / `boot_failfast` なし・`units_run` 109・`init_count` 111)。LoadImageW の実装 (#3245) を入れた boot は trap せず DllMain を抜ける。
- 受入 1 (init 1675 への到達): **届かない**。boot 中に `InitializeCriticalSection(0x12bd390)` が呼ばれない (`CS-INIT` 11 件、`0x12bd390` は 0 件。`CS-DEL` 0 件)。boot は完走するため trap 位置は無い。届かない理由は未特定 (起票先 [WIN-26])。
- 受入 2 (`EnterCriticalSection` を越えるか): **越えない**。`_CreateFruityInstance` は export され呼べるが、`EnterCriticalSection(0x12bd390)` で `[shim] CS-MISS key=0x12bd390` → abort。CS 0x12bd390 が未登録のため (1 の結果から直接の原因)。
- 前版 (基点 `9ceb420d4`・LoadImageW は STUB で boot が init 111 で fail-fast) で見えた `function_412e40` の OOB は、この測定では出ない。boot が完走した状態では観測されなかった。

## 2. 受入条件の状態 (#3353)

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1 boot の 1675 到達を計装で実測。届かなければ trap 位置を REPORT に書く | 未達 (届かない。計装で実測)。trap 位置は無し (boot は完走) | §3-2。起票先 [WIN-26] |
| 2 boot7 閉包を取り込み、`cfi_probe` が `EnterCriticalSection` を越えるか記録。越えなければ次の停止点を記録 | 達成 (越えない。次の停止点は `EnterCriticalSection(0x12bd390)` の CS-MISS) | §3-3 |

## 3. 実測 (測定版: 1 組の commit・1 run の記録)

### 3-0. 測定版と再現

- 基点: `origin/3245-loadimagew-shim` の `8bc881c4d` (LoadImageW 実装を含む #3245)。
- その上に本 PR の `tools/gui/flengine/cfi_boot7.sh` (`6a17a3c47`) と `cfi_probe.mjs` (`a5c242555` と同一) をコピーした一時 worktree で測定した。commit していない (本 PR の diff に LoadImageW は入らない)。
- 手順 (環境変数は `<...>` で置く):
  1. `git worktree add --detach <dir> origin/3245-loadimagew-shim`
  2. `<dir>` に `cfi_boot7.sh` と `cfi_probe.mjs` を本 PR の版からコピーする (commit しない)。
  3. `tar --zstd -xf <artifacts>/work-m11.tar.zst -C <dir>` (展開の top は `tools/m11/work/`)。fl-win64 は `FL_WIN64_DIR=<展開先>` に展開する。
  4. `cd <dir>/tools/m11 && FL_WIN64_DIR=<展開先> bash m11_wndseed.sh` (`work/boot6.lift.ll` を作る。work-m11 には無い)。
  5. `cd <dir> && FL_WIN64_DIR=<展開先> EMSDK_ENV=<[EMSDK] の emsdk_env.sh> RETDEC=<[RETDEC] の bin/retdec-decompiler> PATH=<その bin>:$PATH bash tools/gui/flengine/cfi_boot7.sh` (rc 0。出力は `tools/gui/work/flengine/res/`)。
  6. CS 行の抜き出し (§3-2): `tools/shim/src/sync.c` の `InitializeCriticalSectionAndSpinCount` と `DeleteCriticalSection` の先頭に `fprintf(stderr, "[shim] CS-INIT/CS-DEL key=0x%x\n", ...)` を足した一時版 (commit しない) で `diag/build_g2.sh` を再 build する。`cfi_probe.mjs` の `errs_tail` を `CS-(INIT|DEL|MISS)` で抜く (標準の `errs_tail` は末尾 12 行だけで、CS 行が落ちるため)。

| 実行 (1 run・同じ組) | 値 |
|---|---|
| 手順 4 (`m11_wndseed.sh`) | 01:26:44 → 01:29:07 UTC (143 秒)・rc 0 |
| 手順 5 (`cfi_boot7.sh`) | 01:29:14 → 01:32:59 UTC (225 秒)・rc 0・出力 `closure new functions: 1133` |
| load (`/proc/loadavg` 1 分値) | 手順 5 の開始 `0.90` → 終了 `1.32` (4 core) |
| 手順 6 (CS 計装 build + probe) | build 01:36:05 → 01:36:19 UTC (14 秒)・probe rc 0 |

### 3-1. boot (`boot_b7.json`・手順 5)

| 項目 | 値 |
|---|---|
| `dllmain_done` | True |
| `boot_threw` / `boot_failfast` | None / None |
| `units_run` / `init_count` | 109 / 111 |
| GUI-REACH | reached 24・IMPL 24・STUB 0 (`CreateWindowExW` は IMPL 1 回) |
| `failfast_count` / `icall_miss` | 0 / 7 |

boot7 の有無による差: boot の経路は boot7 を含まない既定の IR と同じ。3245 の B1 (`REPORT_APPENDIX_3245.md` §3: units 109 / init 111 / dllmain True) と一致する。boot7 は boot の結果を変えない。

### 3-2. init 1675 の到達 (受入 1・手順 6)

- 計装: 診断 build の shim で `InitializeCriticalSection` (`InitializeCriticalSectionAndSpinCount` を経由) と `DeleteCriticalSection` の呼出しを記録した。boot と CFI の呼出しを全部含む。
- 結果: `CS-INIT` 11 件 (key は全て `0x12bd390` 以外)。`0x12bd390` の `CS-INIT` は 0 件。`CS-DEL` は 0 件。
- 判定: init 1675 の `InitializeCriticalSection(0x12bd390)` は boot で呼ばれない。boot は完走するので trap 位置は無い。
- 届かない理由は未特定 (`init_count` 111 と init 列の行番号 1675 の対応も未確認)。[WIN-26] で扱う。

### 3-3. CreateFruityInstance (`cfi_b7.json`・boot7 込み・手順 5)

| 項目 | 値 |
|---|---|
| `CreateFruityInstance(0xC0, 0xEDE95A, host, &iface)` | returned false・`Aborted(native code called abort())` |
| 直接の停止 | `[shim] CS-MISS key=0x12bd390` → `shim_unimplemented("EnterCriticalSection (未初期化/未登録)")` |
| JS スタック (関数名・`-g2` 診断 build) | `EnterCriticalSection` ← `function_4232e0` ← `function_1265690` ← `CreateFruityInstance` ← `_CreateFruityInstance` |
| `iface` | 0x0 (未設定) |
| boot7 無し (3245 head・`results/cfi_probe_3245.json`) | `mod._CreateFruityInstance is not a function` |

`function_4232e0` は `REPORT_APPENDIX_3077.md` が挙げた `CS 0x12bd390` の呼出元 VA と一致する。
判定: `EnterCriticalSection` を越えない。次の停止点は `EnterCriticalSection(0x12bd390)` の CS-MISS。

## 4. 考察 (推定を含む)

- CS-MISS の直接の原因は、CS 0x12bd390 が登録されていないこと (§3-2 の実測)。その登録 (init 1675) が boot で実行されないことによる。
- 前版の `function_412e40` の OOB は、LoadImageW の fail-fast で boot が途中停止した後の部分状態で起きたものと考えられる (推定)。完走した boot では出ないことが実測と整合する。
- 1675 に届かない理由 (boot の init 列が 111 で止まっているのか、別の経路か) は未確認 (推定の材料: `init_count` が前版と 3245 の両方で 111)。[WIN-26] で計装する。
- 旧版の `cfi_noboot` (boot を外した診断コピー) は再現手順をコミットしていないため、§4 の根拠から外した。

## 5. ネガティブコントロール

- 5-1 (boot7 無し): §3-3 の表 (3245 head は `_CreateFruityInstance is not a function`)。boot7 の取込で export されることを示す。
- 5-2 (IR の m11 pass 未通過): 本 run では再実行していない。IR は `m11_gen_ir2.sh` と `m11_build.sh` を通す必要がある (`docs/WORKFLOW.md` §11)。

## 6. 製品 KPI (起動・ウィンドウ)

- FLEngine 起動の通過 unit 数 / init: 前 (boot7 無し・3245 head) 109 / 111 → 後 (boot7 有り・本 run) 109 / 111。
- 最初のウィンドウ: 前 (3245 head の e2e・`REPORT_APPENDIX_3245.md` §3) は窓 P4/P5 PASS。後 (本 run) は boot 中に `CreateWindowExW` が IMPL で 1 回呼ばれる。CFI 経由の経路は CS-MISS で止まり、CFI 経由のウィンドウ作成には届かない。
- 動かしていないもの: 実 FL の製品起動。e2e.sh (窓 P4/P5 の判定)。

## 7. 検証範囲・範囲外

- 検証: 測定版 (§3-0) での `cfi_boot7.sh` の完走 1 回 (rc 0)。CS 計装 build と probe の 1 回 (計装は一時版で commit していない)。
- e2e.sh は未実行。`e2e.sh` は `cfi_probe.mjs` を参照しない (`grep -n cfi_probe tools/gui/flengine/e2e.sh` は 0 件)。
- main 上の値は測っていない。PR の基点 `9ceb420d4` から main で `tools/m11`・`tools/shim` が 21 ファイル進んでいる。ここに書く数値は 3245 head 上の結論で、main の数値ではない。
- 範囲外: init 1675 に届かない原因 (→ [WIN-26])。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| init 1675 (`InitializeCriticalSection(0x12bd390)`) に boot が届かない原因 (受入 1) | CS 0x12bd390 が未登録 → CFI が `EnterCriticalSection` で abort | [WIN-26] (本 PR は `Refs #3353`) |
| boot7 込みの e2e (JUDGE・S1) は未測定 | 既定の CI は boot7 を含まない | #3354 の merge 後に再測定 (子 issue は起票しない) |
| main 上の boot・CFI は未測定 | 本結論は 3245 head 上 | #3354 の merge 後に main で再測定 (子 issue は起票しない) |
