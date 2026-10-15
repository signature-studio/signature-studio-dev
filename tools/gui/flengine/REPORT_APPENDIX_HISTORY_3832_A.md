# flengine 付録 (#3832 分割移動): REPORT.md §6b〜§6d・§6i の全文

本文書は `REPORT.md` の 250 行上限のため、§6b〜§6d・§6i を行を削らず移したもの (Git 履歴に残す)。本体からの参照は `REPORT.md` §6b の注記を見ること。

## 6b. WNDCLASS 静的実体の WNDPROC を closure に加える (#565 / M11-N20)

**判定: 受入条件 3 つとも達成**。PE の `.data` から WNDCLASS 静的実体を走査し (`tools/m11/m11_wndclass_scan.py`)、closure 外の WNDPROC を seed に RetDec で lift (boot5) して IR に結合する流れを 1 コマンド化した (`bash tools/m11/m11_wndseed.sh`)。
新規 lift 欠陥は無し (DEFECTS.md 該当なし)。issue 記載の `0x31dd10` は **RVA**で、VA は `0x71dd10` (m11 の LVA は RVA 座標)。

| 項目 | 実測 | 定義 / 分母 |
|---|---|---|
| WNDCLASS 静的実体 | **11 件** (全て `.data`) | `.reloc` DIR64 の +8 が `.pdata` 関数先頭/import thunk、+64 が識別子風文字列、+16/+20/+24..+56 が妥当な全条件 AND。棄却 = 関数でない 132,128 / フィールド不整合 120,306 / 名前不正 41 (`results/wndclass_scan.json`) |
| WNDPROC の内訳 | 関数 **8** 本 (全て distinct) + `DefWindowProcW` import thunk (`0x424920`) **3** 件 (TPUtilWindow / TApplication / VTPanningWindow) | thunk は closure 外だが `gen_thunks.py` が shim へ解決済み (§2-1 #5) |
| closure 内 / 外 (seed 導入前 = boot0..4, 7,421 関数) | **内 0 / 外 8** | 0x6d8330 TTimerWindow, 0x71dd10 TLightweightLayeredControl, 0xc3e940 flpianoroll.Marker, 0xc3f060 flpianoroll.Pattern, 0xd2e620 flcpt.ChordAlternative, 0xd339b0 flrack.Channels, 0xd70600 TILRemoteWindow, 0xd82150 flmidimsg |
| seed の閉包 | 8 WNDPROC → call/jmp 即値を辿り **1,212 関数 / 398,396 B** を追加 (うち import thunk 6B 関数を含む) | 既存 lift 済みに当たったら止める。境界は `.pdata` + import thunk |
| lift / IR | RetDec boot5 **2 分 0.5 秒** (1,212 range)。`m11_gen_ir2.sh` 30.0 秒。IR 定義関数 **7,421 → 8,647** (+1,226 = 閉包 1,212 + RetDec の内部入口別関数化 14)。未定義 `function_*` は **8 → 8 (同一集合)** | 初回 (thunk 抜き 1,179 range) は未定義が 33 に増えたため、import thunk と遅延 import スロットの 6B 関数を閉包に含めた (2 回目 1,210 → 3 回目 1,212 で収束) |
| wasm | 6,021,637 → **6,905,826 B**、`wasm-ld` signature mismatch 0 / undefined 0 / duplicate 0 (m11 と GUI 結合の ff・soft) | `disp_entries` 7,399 → 8,621 |
| 起動・survey の回帰 | units_run **22** / init_count **23** / dllmain_done true / GetMem 33 / FreeMem 20 / icall_miss 0 は不変。survey の値は §6c (HEAD `19ebb43`: 864/1/46/31) | baseline (m11 単体) と GUI 結合の双方を新 IR で再測 |
| 指向 probe | `TLightweightLayeredControl` の `CreateWindowExW` が **NULL → hwnd 0x110000e** (WNDPROC `0x31dd10` = closure 内の `function_71dd10` へ `m11_icall` ok)。`RegisterClassW` ×2 / `TApplication` hwnd 0x110000f も維持 | gate **P5** (旧 REPORT §4 の OPEN の解消)。hwnd 値は GUI 関数が増えて採番が変わった (旧 0x210000e) |

残る観測: probe の `m11_icall` miss は 3 件 (target `0x6c6f` 1 種)。`function_71dd10` が WM_NCCREATE で `[lpCreateParams+0x78]` を `SetWindowLongPtrW(GWL_WNDPROC)` に渡す経路で、probe の `lpParam=NULL` だと低位メモリの値が WNDPROC になるためと**推定** (偽オブジェクトに `0x24920` を置いた追試でも 0x6c6f のままだったため、この仮説は**未確認**。再現・原因は未調査)。窓生成自体は成功する。
`function_52a7f0` (AllocateHWnd) の `RegisterClassW` 脱落 (§5-2) は本 issue の範囲外で未解決のまま (judge の OPEN 行)。

### 6b-1. 検証 (W1 / P5 / ネガコン N6〜N9。実測値は §6b-2)

- **W1** (走査 gate): 検出 WNDCLASS ≥ 11 かつ fn WNDPROC ≥ 8 かつ最終 IR に未定義の WNDPROC = 0。**P5**: `TLightweightLayeredControl` の hwnd が 31bit 内かつ `m11_icall` ok > 0。
- ネガコン (期待した FAIL 行まで検査): **N6** seed 導入前 IR (boot0 のみ) で `--check` → `WNDCLASS-CHECK FAIL` / **N7** その走査 JSON を judge → W1 FAIL / **N8** 検出 floor を実測+1 → floor FAIL (空振り PASS 防止) / **N9** hwnd=NULL の probe → P5 FAIL。
- `m11_wndclass_scan.py --check` は 走査 0 件・未定義 WNDPROC のどちらでも exit 1 (終了コードをそのまま gate に使う)。

### 6b-2. 実測 (コード commit `b867b94` の HEAD、`git status --porcelain -- tools` 空で実行)

- `bash tools/gui/flengine/e2e.sh`: **rc 0 / 160 秒** (load average 開始 0.35 → 終了 1.04)。judge **14/14 PASS** (W1 / P5 追加)、native selftest 324 passed / 0 failed、ネガコン **9/9** が期待した FAIL 行つきで FAIL (N1〜N5 既存、N6〜N9 追加)。実行前の同内容 (未 commit) の 1 回目も rc 0 / 163 秒・同一結果。
- `bash tools/gui/e2e.sh` (受入条件 3): 1 回目 **rc 1** — step 1 の native selftest (ASan) が `heap-use-after-free` (`gui_headless.c:33 blit_surf` を render スレッドが読み、`gui_core.c:174 surf_free` を main スレッドが先に解放)。同じ HEAD で再実行した 2 回目は **rc 0 / 61 秒** (selftest 324 passed、native lift・Chrome とも golden EXACT MATCH 0/64000 px、reach_test 11 / adapt_test 28 passed)。
  この PR は `tools/gui/src`・`test`・`include` を **変更していない** (`git diff a38ba81 HEAD` が空)。selftest 単体を 3 連続実行した結果は 3 回とも 324 passed / 0 failed。1/6 回の失敗の原因 (render スレッドと surface 解放の競合と推定、**未確認**) は未調査 → §7。
  なお最初の rc 1 の前に、新規 worktree に `node_modules` が無く step 5 (tsc) で rc 1 になる環境起因の失敗が 1 回あった (本 PR と無関係。symlink で解消)。
- 環境: runner 4 vCPU、素材 work-m11 + fl-win64 (PE は `FL_WIN64_DIR` 参照。§6c の再測は symlink 無しで実行)。`m11_wndseed.sh` の lift 実測: RetDec 1,212 range が 2 分 0.5 秒 (3 回目) / gen_ir2 30.0 秒。

## 6c. HEAD 再測 (review #576 指摘 1・4 への対応。修正 HEAD `19ebb43`)

main 取込後の木 (`c37522c`) で S1 が FAIL (828/67 vs 864/31) したため切り分けし、`run.mjs --survey` の隔離手順の差を修正した (commit `19ebb43`)。順序は `m11_wndseed.sh` → `flengine/e2e.sh` → `gui/e2e.sh`。素材は work-m11 / fl-win64 (`FL_WIN64_DIR`)、`toolchain-retdec` / `toolchain-emsdk` ([RETDEC] / [EMSDK] の展開先)、`apt: gcc-mingw-w64-x86-64`、capstone / pefile、`pnpm install --frozen-lockfile`。

| 実行 | 結果 | 所要 (実測) |
|---|---|---|
| `bash tools/m11/m11_wndseed.sh` (HEAD `c37522c`) | rc 0。WNDCLASS 11 件 / fn WNDPROC 8 / 最終 IR で未定義 0 (`WNDCLASS-CHECK PASS`) | 2 分 44 秒 |
| `bash tools/gui/flengine/e2e.sh` (修正前 `c37522c`) | rc 1。judge **13/14** (S1 のみ FAIL: 828/1/46/67) | 3 分 13 秒 |
| `bash tools/gui/flengine/e2e.sh` (**HEAD `19ebb43`**) | rc 0。**JUDGE PASS 14/14**。S1 = 864/1/46/31 (base 一致)。ネガコン N1〜N9 は 9/9 が期待どおり FAIL。selftest 0 failed | 2 分 36 秒 (load 0.45 → 0.97) |
| `bash tools/gui/e2e.sh` (**HEAD `19ebb43`**) | rc 0。ALL PASS (bpp / text / simd / present / Chrome E2E / fail-fast / reach-log / sigprobe)。ASan UAF は本回に出ず | 1 分 33 秒 |

### 6c-4. 現 HEAD `c4e3c064` の再測 (main `97f28539` を merge commit `986d8a67` で取込済み。`/opt` 絶対パスを REPORT から除去)

素材: `fl-win64` → `$RUNNER_TEMP/fl-win64`、`work-m11` → `tools/m11/work/`、`toolchain-retdec` / `toolchain-emsdk` を [RETDEC] / [EMSDK] として使用 (`PATH` / `EMSDK_ENV`)、capstone 5.0.7 / pefile 2024.8.26、`pnpm install --frozen-lockfile`、`tools/e2e` は `npm install --no-save`。

| 実行 (HEAD `c4e3c064`, 2026-10-13 UTC) | 結果 | 所要 (実測) |
|---|---|---|
| `bash tools/m11/m11_wndseed.sh` | rc 0。`WNDCLASS-CHECK PASS` (WNDCLASS 11 / fn WNDPROC 8 / 最終 IR 未定義 0) | 146 秒 (load 0.53 → 0.95) |
| `bash tools/gui/flengine/e2e.sh` | rc 0。**JUDGE PASS 14/14**。native selftest 500 passed / 0 failed。ネガコン N1〜N9 は 9/9 が期待どおり FAIL | 188 秒 (load 0.80 → 1.11) |
| `bash tools/gui/e2e.sh` | rc 0。**ALL PASS** (`stress` の readback は golden と EXACT MATCH 0 px / 64000) | 132 秒 (load 1.88) |

- judge の各 gate: L1 (ff・soft) PASS / A1 declare=193 = adapter=193 (impl 173 / stub 20) / B1 units_run 52 = base 52 / R1 `LoadStringW` IMPL / R2 reach 32 ≥ floor 19 / **S1 871/1/47/23/0 = base 871/1/47/23/0 PASS** / S2 ff・soft とも STUB `LoadImageW` / P1〜P5 PASS (P5 hwnd `0x110000e`) / W1 PASS (外 0)。
- 本 run は 1 回の実測。繰り返しは行っていない。
- 初回失敗はいずれも環境要因で、コードの変更ではない: (a) `EMSDK_ENV` 未指定で `emcc` 不在 (rc 2)、(b) worktree の `node_modules` 不在 (rc 127)、(c) `tools/e2e/node_modules` 不在で agent-browser が ENOENT (rc 2)。(a)〜(c) を入れた後の rc 0 を上表に記録した。
- 直前の `f1e88c82` / `3d433c6f` で出た S1 FAIL (869/1/47/25 vs base 871/1/47/23) は、`c4e3c064` と `e9007ec` の実測では再現しない。**原因は特定していない** (unit 304 / 555 の差は未切り分け)。判定式は緩めていない。

### 6c-3. 旧 HEAD `e9007eca` の再測 (main `1adff847` を merge commit で取込済み。e2e の `m6/ottlib.py` 複製を追加)

素材: `fl-win64` → `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR`)、`work-m11` → `tools/m11/work/`、`toolchain-retdec` → [RETDEC] (`RETDEC`)、`toolchain-emsdk` → [EMSDK] (`EMSDK_ENV`)、`apt-mingw` (`x86_64-w64-mingw32-gcc`)、pefile 2024.8.26 / capstone 5.0.7 (`python3 -m pip install --user`)、`pnpm install --frozen-lockfile` (ルート)、`tools/e2e` は `npm install --no-save` (agent-browser 0.39.0。repo に lockfile が無いため `--no-save` で入れた)。

手順は WORKFLOW どおり `m11_wndseed.sh` (boot6 lift + 最終 IR) → `flengine/e2e.sh` → `gui/e2e.sh`。

| 実行 (HEAD `e9007eca`) | 結果 | 所要 (実測) |
|---|---|---|
| `bash tools/m11/m11_wndseed.sh` | rc 0。`WNDCLASS-CHECK PASS` (WNDCLASS 11 / fn WNDPROC 8 / 最終 IR 未定義 0) | 2 分 13 秒 (user 2 分 13 秒) |
| `bash tools/gui/flengine/e2e.sh` run 1 | rc 0。**judge 14/14 PASS**。selftest 500 passed / 0 failed。ネガコン 9/9 が期待どおり FAIL | 175 秒 (load 0.99 → 0.90) |
| 同 run 2 | rc 0。judge 14/14。S1 871/1/47/23 = base | 176 秒 (load 1.00 → 0.92) |
| 同 run 3 | rc 0。judge 14/14。S1 871/1/47/23 = base | 175 秒 (load 1.01 → 0.95) |
| `bash tools/gui/e2e.sh` | rc 0。**ALL PASS** (simd / text / present / input / stress / Chrome E2E。ネガコン含む。ASan UAF は本回に出ず) | 2 分 1 秒 (121 s。`node_modules` 準備後の 1 回) |

- judge の各 gate (run 1〜3 共通): L1 (ff・soft) PASS / A1 declare=193 = adapter=193 (impl 173 / stub 20) / B1 units_run 52 = base 52 / R1 `LoadStringW` IMPL / R2 reach 32 ≥ floor 19 / S1 871/1/47/23/0 = base / S2 ff・soft とも STUB `LoadImageW` / P1〜P4 PASS / W1 PASS (外 0) / P5 PASS (hwnd 0x110000e)。
- 前段の 13/14 (S1 のみ FAIL: 869/1/47/25) は、取り込み前の main (`fe53ba30`) で出ていた値。main 取込後の `e9007eca` では base と一致し、判定式は一度も緩めていない。差分の詳細 (unit 304 / 555) は取込前の HEAD での調査結果で、現 HEAD では再現しない。
- `gui/e2e.sh` の初回は step 5 (tsc) と step 6 (agent-browser) が worktree に依存が無いため落ちた (rc 1 / rc 2)。環境起因で本 PR の変更とは無関係。依存を入れて rc 0 を得た。
- 素材の注意: `work-m11` の `boot0..4` は素材のまま、`boot6` は `m11_wndseed.sh` で作る必要がある。`m11_gen_ir2.sh` 単独では WNDPROC 8 件が未定義になり W1 FAIL。

### 6c-2. HEAD `b3819e2` の再測 (review #576 指摘 2 への対応・素材 `work-m11` / `toolchain-*` / `apt-mingw` を展開して実行)

素材: `work-m11` → `tools/m11/work/` (1.6 GiB)、`toolchain-retdec` (RetDec v5.0)、`toolchain-emsdk`、`fl-win64`、`apt-mingw` (`x86_64-w64-mingw32-gcc` は runner 既定で存在)、capstone 5.0.7 / pefile 2024.8.26、`pnpm install --frozen-lockfile`。

| 実行 (HEAD `b3819e2`) | 結果 | 所要 (実測) |
|---|---|---|
| `bash tools/m11/m11_wndseed.sh` | **rc 0**。WNDCLASS 11 / fn WNDPROC 8 / 最終 IR 未定義 0 (`WNDCLASS-CHECK PASS`)。boot6 lift 1212 関数 → 8648 defines | 2 分 52 秒 (172 s) |
| `bash tools/gui/flengine/e2e.sh` | **rc 1**。judge **12/14 FAIL**。FAIL は **B1** (`units_run 52 (base 52)` / `dllmain_done False` / `GetMem 560 FreeMem 20` / `icall_miss 5`) と **S2** (ff 側 fail-fast 集合 `LoadImageW`・`SystemParametersInfoW` ⊄ soft STUB `LoadImageW`)。L1・A1・R1・R2・S1 (865/1/47/29)・P1〜P5・W1 は PASS。ネガコン 9 本は FAIL 期待どおり | 3 分 21 秒 (201 s) |
| `bash tools/gui/e2e.sh` | **rc 0**。ALL PASS (text / simd / present / Chrome E2E)。**ASan UAF は本回に出ず** | 1 分 45 秒 (105 s) |

- **B1 の FAIL は GUI shim の回帰ではない**: 同じ IR で GUI shim 無しの `baseline_boot.json` 自体が `units_run 52 / dllmain_done false / boot_threw "memory access out of bounds"` になる。REPORT §6c 冒頭の期待値 (units_run 22 / init 23 / dllmain true) とは別物。素材 `work-m11` は #516 以前の生成で、現 main の手順と一致しない (WORKFLOW §11・#680)。`boot0..4` を現 main の `m11_e2e.sh --full` から再生成していないことが原因と**推定** (未確認)。
- **S2 の FAIL**: `SystemParametersInfoW` が ff survey で fail-fast 到達 (3 unit) だが soft 側は STUB 判定の集合に入らない。§3 の表では `SystemParametersInfoW` は P0 の「実装済み」扱いで、今回の素材 (`work-m11` 由来の IR) では別の経路で fail-fast に落ちている。原因は未調査。
- 結論: **HEAD `b3819e2` の flengine gate は 14/14 にならなかった** (`19ebb43` の 14/14 は素材の IR が違う時点の値で、現素材では再現しない)。PR は「未達」を明記して出す。

### S1 の切り分け (結論: shim の回帰ではなく survey ハーネスの隔離不足)

- unit 単位の結果を取得した。baseline (shim 無し, `m11_survey.mjs` の `M11_SURVEY_UNITS`) と GUI 結合 (soft) を突き合わせると、差は **36 unit の ok→trap** のみで、全て `halt0->longjmp` だった。
- 同じ GUI 結合 wasm を **`m11_survey.mjs` の手順で**回すと `864/1/46/31` になり、942 unit の結果が baseline と **1 件も違わない** (`GUI 結合 wasm × m11_survey.mjs` = baseline)。
- 差は `run.mjs --survey` だけにあった。`m11_survey.mjs` は unit ごとに `_m11_va_unit_begin()` で VA 上限を張り直し、unit が書いた image を実行前へ戻すが (clobber 対策)、`run.mjs` はこれを省いていたため、前 unit の状態を引きずって 36 unit が Halt0 で落ちていた。
- 修正: `run.mjs --survey` に `_m11_set_va_unit_budget` / `_m11_va_unit_begin` / unit 単位の image 復元を入れ、`m11_survey.mjs` と同じ手順にそろえた。shim 本体は変更していない。

(`19ebb43` 時点の値。HEAD `b3819e2` 以降の judge は上表のとおり 12/14 で、本段落は現 HEAD の結果ではない) judge の 14 gate は当時全て PASS: L1 (ff・soft) / A1 / B1 (units_run 22・init 23) / R1 (`LoadStringW` IMPL ×4) / R2 (到達 23 ≥ floor 19) / S1 (864/31) / S2 / P1〜P4 / P5 (`TLightweightLayeredControl` hwnd `0x110000e`) / W1 (WNDCLASS 11・fn WNDPROC 8・外 0)。
- R2 の到達は 23 (floor 19)。`run.mjs` の survey は unit 隔離の修正で到達集合が増えた (floor は未更新。下限として有効)。

### 発見 (本 PR 外)

- `tools/gui/flengine/e2e.sh` の前提: `x86_64-w64-mingw32-gcc` は runner 既定に無く `apt-get install gcc-mingw-w64-x86-64` が要る (`oc_artifacts` の `apt-mingw` で入る)。
- `tools/m11/m11_survey.mjs` 単体の `M11_SURVEY_UNITS` 出力は、`run.mjs` と同じ `[i, label]` 形式ではなく `label` の配列 (`perUnit` は文字列配列)。比較時は index で突き合わせる。

## 6d. 現 HEAD 節 (review #577 対応。HEAD `bf9cf547`)

review `b9f0b32b` の指摘 1 (S1) と 2 (run.mjs のコメント) への対応。

- **S1 の切り分け (実測)**: baseline と soft は **同じ `run.mjs --survey` 経路・同じ VA 予算 256 MiB** で取っており、予算の差ではない (前回の「baseline は m11_survey.mjs 既定 256 MB」は `e2e.sh` の経路変更で成立しなくなっていた)。`baseline_base_survey.json` と `survey_soft_units.json` を unit 別に突き合わせると、差は **unit 304 と 555 の 2 件のみ** (base `ok` / soft `memory access out of bounds` の trap)。ok/trap 以外の差は無い。shim の有無で build が違うため、この 2 件は shim 組込み後の wasm 側の挙動差 (未特定)。
- 単独 unit の再現 (`m11_base.cjs` / `m11_gui_soft.cjs` を unit 304・555 で単独実行) は、両方とも trap したため切り分けに使えず、原因は未特定。
- **判定**: S1 は FAIL のまま (870/1/47/24/0 vs 872/1/47/22/0)。判定を PASS に動かす変更は入れていない。judge 13/14。
- `run.mjs` 4 行目のコメントを実装 (既定 256 MiB) に合わせた。

本節の実測は **HEAD `125fefd2`** (コード差分なし。`bf9cf547` の測定値を含む) で取り直した値。実行環境: runner 4 vCPU、`apt-mingw` (`x86_64-w64-mingw32-gcc`) を apt 導入、`[EMSDK]` (`EMSDK_ENV` で指定)、`fl-win64` / `work-m11` を展開。

| 実行 (HEAD `125fefd2`・foreground・1 回) | rc | 所要 | 結果 |
|---|---|---|---|
| `EMSDK_ENV=<[EMSDK] の emsdk_env.sh> FL_WIN64_DIR=<[WIN64]> ANALYSIS_DIR=… RETDEC=<[RETDEC] の retdec-decompiler> bash tools/gui/flengine/e2e.sh` | **1** | 466 s (load 0.68→1.09) | judge **13/14**。S1 のみ FAIL: `870/1/47/24/0` vs base `872/1/47/22/0`。他 13 gate PASS (L1×2・A1 declare=193 adapter=193 impl=173 stub=20・B1 units 52・R1 LoadStringW・R2 reach 33≥19・S2・P1〜P5・W1)。ネガコン N1〜N9 期待どおり FAIL。selftest 506 passed / 0 failed |
| `EMSDK_ENV=… FL_WIN64_DIR=… bash tools/m11/ldfix/f4_e2e.sh` | **0** | 385 s (load 1.00) | 6 gate PASS (F1/F2/D1/D2/P1/A1)。ネガコン 4/4 期待行付き FAIL。RegisterClassW 2→2→3。`function_52a7f0` ret pre `0x0` → noand `0x0` → post **`0x110000f`**。survey pre/noand/post = `870/1/47/24`。`ir_sha256.txt` の `after_m11_build` 行は再生成で変化 (下記 §6d-2) |
| `EMSDK_ENV=… FL_WIN64_DIR=… bash tools/gui/e2e.sh` | **0** | 302 s (load 2.28) | ALL PASS (SIMD / present / input / stress (negctl 2/2 exit 1) / pe_image / selftest 506/0) |

**S1 の判定**: 上表のとおり FAIL のまま。判定式は変えていない。unit 304 / 555 の差 (soft 側のみ `memory access out of bounds`) の原因は未特定。同じ unit 304 / 555 の oob を扱う OPEN issue として [M11-N78] #1275 (`ClassCreate ON で unit 304/555 が oob→abort`) があるが、原因が同一かは未確認。起票先は #1275 にコメントで接続する。

### 6d-2. `function_52a7f0` の ret 値の対応 (同一 build 内の不整合ではない)

| 測定元 | IR の作り方 | 窓の採番 (probe) | `function_52a7f0` ret |
|---|---|---|---|
| `f4_e2e.sh` post (`0246df1f`〜`125fefd2`) | `m11_gen_ir2.sh` → `m11_build.sh` | `TLightweightLayeredControl` = `0x0` (未生成)、`TApplication` = `0x210000e` | `0x110000f` |
| `flengine/e2e.sh` probe (`125fefd2`) | 上記に加え `m11_wndseed.sh` (boot6 seed。WNDPROC 閉包を追加) | `TLightweightLayeredControl` = `0x110000e`、`TApplication` = `0x110000f` | `0x1100010` |

- 両者とも soft build・同じ `probe.mjs` で取っている。差は IR (`m11_wndseed.sh` の有無) で、`e2e.sh` は step 0 で wndseed を回し、`f4_e2e.sh` は回さない (スクリプトで確認済み)。窓の採番が変わる機構は推定 (未検証)。
- したがって受入条件 3 の値は **「f4 の IR (wndseed 無し) では `0x110000f`、wndseed 込みの最終 IR では `0x1100010`」**。どちらも `0x0` からの修復を示す。一意の値は wndseed 込みの最終 IR (flengine の値) とする。f4 の値は f4 の構成でのみ有効。

### 6d-3. 注記 (run 上の前提)

- `x86_64-w64-mingw32-gcc` は runner に無かったため `apt-get install gcc-mingw-w64-x86-64` で導入 (`apt-mingw` 素材の代替)。初回の flengine e2e は前提欠如 (rc 2) で止まり、導入後に再実行。
- `tools/m11/work` は `work-m11` の展開先 (gitignore。commit しない)。


注記: `tools/gui/e2e.sh` の初回は `node_modules` 不在で step 5 (tsc) が rc 127 だった (`pnpm install` で解消。環境要件)。

## 6i. S1 (soft) の unit 304/555 調査 (#1442 / GUI-21)

結論 (測定 commit `719f1c43`・judge 13/14・S1 `870/1/47/24/0` vs base `867/1/47/27/0`): 304/555 は base・soft 両方で OOB (真因は #1426 で未達)。S1 は FAIL のまま (差は 101/291/296 の 3 unit)。

| 判定 gate (現 HEAD) | 結果 | 備考 |
|---|---|---|
| S1 survey parity (soft) | FAIL `870/1/47/24/0` (base `867/1/47/27/0`) | 判定式は不変。FAIL は未解消 |
| S2 soft adds no fail-fast beyond ff | PASS | 判定式は `8a6dcf4b` (main) 由来。本 PR では不変 |

詳細と実測値は [REPORT_APPENDIX.md](REPORT_APPENDIX.md) §6i (測定 commit `719f1c43`・鮮度の範囲を含む)。

WIN-4 (#2715・部分達成): `CreateFruityInstance` の閉包 (2,071 関数) を boot7 として取り込み、呼出しまで到達した (`EnterCriticalSection` で fail-fast)。測定 commit `5f9d7cbd`・判定と未解決は [REPORT_APPENDIX.md](REPORT_APPENDIX.md) §7 を正とする。

