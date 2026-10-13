# REPORT — KH-7 (#59): Kilohearts UI (Skia CPU ラスタ) の M7 フレーム転送 HUD への接続可否評価

- 評価日: 2026-10-13 / 担当 dir: `tools/targets/kilohearts/ui_eval/` / 親: #15 (PLG-E) / 関連: #10 (GUI-10 HUD)・#248 (KH-10 EditorModel lift)
- 検証起点 commit: `a0b5377` (スクリプト一式。`8cef593` からの変更は run_all.sh の llvm-objdump 解決の追加と ui_present.py のネガコン lambda の整理のみ)。数値は全てこの commit のクリーン worktree (`git worktree add --detach`) での実測。以降の commit は REPORT のみ変更。
- 素材: Kilohearts Offline Installer 132102 → `HeartCore.core_64` (Win64 PE, 76,642,304 B, sha256 `d55ce8b4…8751441e` を `extract_core.sh` が検証)
- 既知類型との関係: `docs/DEFECTS.md` D1a〜D17 **該当なし** (lift 欠陥ではない; main `6f4f3b0` 時点の最後の ID は D17)。ただし M7 GUI shim 側の API 意味論の不一致を 1 件発見 (§2.4、行案は §6 で D18)。

## 0. 結論 (先出し)

**判定: 画面転送の形は M7 HUD に接続可能 (静的解析 + native プローブの範囲。範囲外は §5)。ただし未達 4 件 (G1〜G4) が残り、現時点では「接続準備 NG」(`run_all.sh` は exit 2 = VERDICT: NOT READY)。**

| # | 項目 | 結果 (定義・分母は §2) |
|---|---|---|
| 1 | 画面転送の形 | **GDI のみ**。`SetDIBitsToDevice` の静的 call site は **1 箇所** (`UIWindowWin32` の WndProc `0x18024f500`, 4,635 B)。32bpp・BI_RGB・top-down (biHeight=−H)・`BeginPaint` の rcPaint 1 矩形/回。M7 HUD の SAB フレーム転送と形が合う |
| 2 | GPU 系 API | **0 件** (static import 404 件 / 17 DLL に OpenGL・D3D・DXGI・Vulkan・EGL・D2D・DComp なし。DLL 名/API 名文字列もイメージ全域で 0 件) |
| 3 | shim 被覆 (tools/gui) | gdi32 **9/9 IMPL**、user32 **76/93 IMPL** (未実装 17 = fail-fast stub 9 + 名前自体なし 8) → **G2** |
| 4 | shim の意味論 | **G1: `SetDIBitsToDevice` が HeartCore の呼び方 (top-down + 部分矩形) で誤った行を描く**。プローブ 7 ケース中 **5 ケース不一致** (全面更新と上下対称矩形だけ一致)。bottom-up 対照は 7/7 一致。修正案 (`g1_shim_fix.patch`, 実質 1 式) を当てた作業コピーでは 7/7 一致 |
| 5 | フォント | **G3: Skia が DirectWrite を動的ロード** (`DWriteCreateFactory`)。repo に DirectWrite 代替なし (shim・FreeType 経路とも) |
| 6 | UI 層の規模 | 42 効果の UI 閉包 (直接辺のみ = 下限) **2,405,825 B = .text の 11.69%**、同手法の DSP 閉包の **6.44 倍**。うち Skia 由来 1,420,448 B。効果ごとの固有分は小さい (Gain: 25 関数 / 3,387 B)。重いのは共有 UI+Skia 基盤 (717,474 B) |
| 7 | OS 境界 | UI の OS 依存は **`UIWindowWin32`** (抽象 `UIWindow` の Win32 実装; `UIWindow` vtable 42 slot / `UIWindowWin32` vtable 43 slot・重複を除く 42 関数 15,777 B) に集約。ここを差し替えれば (推定: 呼び出し元が層内かどうかによる) 未実装 17 名のうち 11 名は不要になる (残る 6 名はダイアログ/LoadStringA 等で境界外) |

推奨 (PM 判断が必要): Skia を upstream から wasm 再ビルドして lift 済み Editor に繋ぐ案は**非推奨** (§3)。基準線は **D7 (Fresh Air) の拡張 = DSP のみ lift・UI は HUD 側別実装**。UI 忠実度が必要になった場合のみ、`UIWindow` の 42 slot 契約を逆解析して `UIWindowWin32` を差し替える経路 (§3-B) を検討する。

## 1. 再現

```sh
bash tools/targets/kilohearts/ui_eval/run_all.sh     # 素材: oc_artifacts: plugins-kilohearts。KH_CORE=<HeartCore.core_64> 指定で展開を省略
```
終了コード: **0 = 全検査 PASS (接続準備 OK) / 1 = 評価の前提違反・ネガコン失敗・素材なし・検算不能 / 2 = 前提は成立・接続準備に未達 (gap) が残る**。
ステップ: `ui_imports.py` (§2.1〜2.2・2.6) → `ui_present.py` (§2.3) → `ui_closure.py` (§2.5) → `xcheck_xref.py` (別算法) → `shim_probe.sh` (§2.4) → `shim_probe_fixed.sh` (G1 修正案 `g1_shim_fix.patch` の事前検証; 期待 exit 0, 0 以外は評価無効 = exit 1)。
前提: gcc・llvm-objdump・uv (python に pefile/capstone/numpy が無ければ `uv run --with` で自動)。llvm-objdump は PATH に無ければ `/usr/lib/llvm-*/bin` の最新版を使い、どこにも無ければ段階 1 の前に exit 1。**mingw が無い runner でも動く** (shim 本体 4 ファイルを直接ビルドし `gen_api.py` を使わない)。

## 2. 測定結果

### 2.1 import 面と shim 被覆 (`ui_imports.py`)
- HeartCore の import: **404 件 / 17 DLL / delay-load 0** (kernel32 200, user32 93, ws2_32 29, advapi32 16, crypt32 16, ole32 11, gdi32 9, shell32 8, setupapi 7, winmm 4, version 3, comdlg32 2, psapi 2, 他 4)。
- GUI 担当 (user32+gdi32) **102 名** (IAT 経由の静的 xref 234 件)。tools/gui の実装は `src/gui_{core,gdi}.c`・`gui_core_ext.inc` の `^API Name(` 312 名 (gen_api.py と同じ規則)。判定: gdi32 **9/9 IMPL**、user32 **76/93 IMPL**。
- **未実装 17 名** (xref 件数): fail-fast stub のみ 9 = メニュー系 8 [`CreateMenu`1 `CreatePopupMenu`1 `DestroyMenu`2 `GetMenu`1 `GetMenuItemInfoW`1 `InsertMenuItemW`1 `SetMenu`3 `SetMenuItemInfoW`1] + `MonitorFromPoint`1 (FL の import 一覧から生成された stub; 呼ぶと abort) / 名前自体なし 8 [`BringWindowToTop`1 `TrackMouseEvent`1 `UpdateLayeredWindow`1 `DialogBoxIndirectParamW`1 `EndDialog`1 `MapDialogRect`1 `GetDialogBaseUnits`1 `LoadStringA`2]。
  - 分類 (`ui_closure.py`): `UIWindowWin32` 層内 **11 名** (メニュー 7・`BringWindowToTop`・`MonitorFromPoint`・`TrackMouseEvent`・`UpdateLayeredWindow`)、層外 **6 名** (ダイアログ 4・`LoadStringA`・`SetMenuItemInfoW`)。ダイアログ 4 名の呼び元の特定は本評価では未実施 (`ui_closure.py` は層への到達所属を出すが、呼び元の一覧は出さない)。
- **別算法検算 (X1)**: 単語境界でソース全文を検索 → 未実装判定 17 名は 0 件ヒット、IMPL 判定 85 名は全て ≥1 件ヒット (食い違い 0)。
- 非 GUI 302 件 (shimx `exports.txt` + `inventory.csv` で判定): F 128 / S(stub) 22 / exports にあるが inventory 未分類 81 / **shimx に無い 71**。UI 周辺 DLL (shell32/ole32/comdlg32/winmm) の不足は **2 件** (`SHBrowseForFolderW`・shell32 序数 74)。残り 69 件は ws2_32 23・kernel32 17・crypt32 11・advapi32 8・setupapi 7・psapi 2・bcrypt 1 で、通信/認証/ライセンス層 (D2・D3 の対象領域; 別チケット KH-8/9/11 の領域) のため UI 評価の対象外。
- 入力・モデルに効く API の xref: `SetCursorPos` 1・`ShowCursor` 2・`GetCursorPos` 2・`SetCapture` 2・`ToUnicode` 1・`SetClipboardData` 1・`RegisterDragDrop` 2・`DoDragDrop` 3・`SetTimer` 3 (いずれも IMPL。ただし `SetCursorPos` は Pointer Lock 未連携 = GUI-6 #182 の領域)。

### 2.2 GPU 不在 (E1/E2) と DirectWrite (E4)
- E1: static+delay import に `opengl32 glu32 d3d9/10/11/12 dxgi libEGL libGLESv2 vulkan-1 d2d1 dcomp d3dcompiler_43/47 gdiplus` と `wglCreateContext` 等の API 名が **0 件**。E2: イメージ全域 (76,642,304 B) に上記 DLL 名 (ASCII/UTF-16LE) と GPU API 名の文字列が **0 件**。SkSL の backend 名 (`vulkan\0metal\0webgpu\0direct3d`) は DLL 名ではなく、検出器が誤検出しないことを確認 (偽陽性 0)。
- E4: `DWriteCreateFactory`/`DWriteCoreCreateFactory` 文字列 **2**、`dwrite.dll`/`dwritecore.dll` 名 **2**、RTTI `SkFontMgr_DirectWrite`・`SkFontStyleSet_DirectWrite`・`DWriteFontTypeface` **3**。FreeType 文字列は 0 件 (HeartCore の Skia は Windows で DirectWrite をグリフ供給に使う構成)。**動的ロードのため import 表には現れない**。
- 動的ロード DLL 名 (文字列走査; 実際に呼ばれるかは未検証): `dwmapi.dll`・`dwrite.dll`・`dwritecore.dll`・`libpaceedenexperience.dll` ほか。

### 2.3 画面転送呼び出しの復元 (`ui_present.py`, 逆アセンブル)
- `SetDIBitsToDevice` call site `0x18024fce7` ⊂ WndProc `0x18024f500` (.pdata 範囲 4,635 B, IAT 呼び出し **30 種**: BeginPaint/EndPaint/GetUpdateRect/InvalidateRect/SetCapture/GetMenu/TrackMouseEvent/UpdateLayeredWindow/SetDIBits/CreateCompatibleBitmap 他)。WndProc は `UIWindowWin32` の slot `0x180253500` (`RegisterClassW` を呼ぶ create) が `lea` で 1 箇所だけ参照 (C5)。
- 復元した引数 (11 パターンを命令列で検査, 全 PASS):
  `ps=BeginPaint(hwnd,&ps)`; `SetDIBitsToDevice(ps.hdc, L, T, R−L, B−T, xSrc=L, ySrc=H−B, StartScan=0, cLines=H, bits=obj+0x58, &{biSize=40, W=obj+0x78, −H=−obj+0x7c, planes=1, bpp=32, BI_RGB, 0}, DIB_RGB_COLORS)` (L/T/R/B = rcPaint)。
  → 毎回 **1 矩形** の部分更新。ySrc は下原点 (`H−bottom`)。
- ネガコン (実バイトを書換え→再逆アセンブル): biBitCount 32→24 / ySrc の `sub`→`add` / StartScan 0→1 / biSize 40→56 の **4 件とも、対応する 1 検査だけが FAIL** (他 10 検査は PASS のまま)。

### 2.4 M7 GUI shim への投入 (`shim_probe.sh`) — **G1 を発見**
HeartCore の呼び方を tools/gui の native headless host (gcc + ASan/UBSan) に投入し、窓 100×80 の全画素を独立オラクルと比較 (期待画素 = バックバッファ[y][x]; 画素は (x,y) ごとに一意の値)。

| 呼び方 | 全面 (0,0,100,80) | 上寄せ (20,0,60,30) | 非対称 (20,10,60,30) | 下寄せ (30,50,70,80) | 上下対称 top+bottom=H (10,30,50,50) | 1 行 (0,5,100,6) | 1 画素 |
|---|---|---|---|---|---|---|---|
| **HeartCore 形** (top-down, ySrc=H−B) | PASS | **FAIL 1200/1200 px** | **FAIL 800/800** | **FAIL 1200/1200** | PASS | **FAIL 100/100** | **FAIL 1/1** |
| 対照: 同じ引数 + bottom-up DIB (biHeight=+H) | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 対照: top-down で ySrc=top (shim の解釈に合わせた呼び方) | PASS | PASS | PASS | PASS | PASS | PASS | PASS |

- 矩形外の破壊は全ケース 0 px。**不一致は「矩形内の全画素が別の行の内容」**。全面更新と `top+bottom=H` の対称矩形では ySrc=top と偶然一致するため、**全面描画だけの試験では顕在化しない**。
- 仕様の根拠: MS Learn は `ySrc` を「image の **lower-left corner** の y」と定義 (https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-setdibitstodevice, 2026-10-13 取得; top-down DIB での扱いは Remarks が曖昧)。HeartCore (実 Windows で動く製品) が `ySrc=H−bottom` を渡す事実と、Wine の式 (下記) が同じ解釈を与える。
- 原因: `SetDIBitsToDevice` (`gui_gdi.c`) が `StretchDIBits` と同じ `dib_to_dc` を共有し、**top-down DIB の ySrc を上原点とみなす** (`sy_top = ys`) うえ、`StartScan`/`cLines` を無視する。Wine の `nulldrv_SetDIBitsToDevice` (https://github.com/wine-mirror/wine/blob/master/dlls/win32u/dib.c, 2026-10-13 取得) は `src.y = startscan + lines − (ySrc + cy)` (下原点)。HeartCore の引数では全ケースで `= top` になる (プローブが各ケースで確認: 7/7 一致)。**オラクルは Wine ソースと HeartCore の意図であり、実 Windows での実行確認ではない** (§5)。
- **修正案の事前検証** (`shim_probe_fixed.sh`; tools/gui 本体は無変更): `g1_shim_fix.patch` を作業コピーに当てると HeartCore 形 **0/7 不一致 (exit 0)**、bottom-up 対照 0/7、`ySrc=top` の呼び方は逆に **5/7 不一致** (プローブが両方向で判別できる)。修正は `ys_eff = start + lines − (ys + h)` (top-down のみ) の 1 式。`StartScan`/`cLines` を使うバンド転送 (`lines<高さ`) と bottom-up の一般化は未検証。
- オラクル感度 (ネガコン): 期待値を 1 画素だけ壊す → 不一致 **1 件**を検出 (期待 1)。ハーネス異常 0。
- `StretchDIBits` も同じ `dib_to_dc` を使う。Wine は top-down SRCCOPY で非原点/拡縮なら下原点に変換するため、同型の不一致の疑いがある (**未検証**; FL の `StretchDIBits` は 4 call site)。

### 2.7 DirectWrite の呼び出し経路と方針 (KH-20 / #838)
- 呼び出し元: ローダ関数 RVA `0x9382f0` (VA `0x1809382f0`) のみが `DWriteCreateFactory` / `DWriteCoreCreateFactory` の文字列を参照する (LEA 2 件)。ローダの呼び出し元は 2 件 (`0x8b6f7b` / `0x9371c1`)。文字列走査の結果と一致。
- ローダの動作 (逆アセンブル): `LoadLibraryExW` で `DWriteCore.dll` を試し、失敗すると `dwrite.dll` を試す。`GetProcAddress` で `DWriteCoreCreateFactory` → 失敗時 `DWriteCreateFactory` を取得。両方失敗すると NULL を返し、呼び出し元は結果 0 を格納する (`movq $0,(%rsi)`)。取得した工場は静的キャッシュ `0x184168338` に保持する。
- 使用インタフェース: 工場の vtable 経由 (`callq *0x68/0x28/0x20/0x18(%rax)` 等)。COM の `IDWriteFactory` で、フォント列挙・テキストレイアウトを含むため、最小の代替は大きい。
- 方針: FreeType 経由では受けない (COM の DWrite 面全体を置き換える必要があり、文字の描画は `ui_eval` の範囲外)。shimx は未対応 API を `shim_unimplemented` で名前を出して abort する方針 (`shimx.h` §先頭) に合わせ、`GetProcAddress` の段で `DWriteCreateFactory` / `DWriteCoreCreateFactory` を fail-fast させる (`tools/shimx/src/module.c`)。
- 検証 (実測, 検証 HEAD `5b5fb9ee`。以後の commit は本節の文言のみで、`tools/shimx/test.sh` の入力 `src`・`test` に変更なし): `bash tools/shimx/test.sh` = exit 0。開始 epoch `1791909256` → 終了 `1791909303` (所要 47 秒)。load (終了時 uptime) 0.66。(前回実測 `37f640ad`: 開始 `1791908810` → 終了 `1791908855`、45 秒、load 0.72。同コードの初回実測 `c80a1951`: 開始 `1791908643` → 終了 `1791908691`、48 秒、load 0.61。)MT PASS (7 グループ)・ST PASS・M4 互換 PASS・カバレッジ 687 公開関数 PASS。`dwrite` ケースは `exit=1`、stderr 行 `[shim] FAIL-FAST: unimplemented Win32 API: DWriteCreateFactory (DirectWrite 未対応: Kilohearts Skia の動的ロード。KH-20 方針 = 明示 fail-fast)` を確認 (`expect_fail dwrite` ✓)。前提: `test_main.c` の `dwrite` モードは `GetModuleHandleW(L"dwrite.dll")` が非 NULL を返すことを前提にする (実機での確認は未実施)。
- 検証 HEAD の系譜: `c80a1951` (初回実測) → `37f640ad` (実測を本節に記録) → `c8e104f8` (文言整理のみ) → `5b5fb9ee` (dwrite 前提の追記・現行の検証 HEAD) → `065eba1b` (実測値の正本を更新、コード変更なし)。`tools/shimx` は `c80a1951` 以降変更なし。
- 環境: emcc 6.0.12 は [EMSDK] を runner 上に新規展開して使用 (run 環境のみ。`emsdk install 6.0.12` 後、[EMSDK] の配置先へ symlink し、`llvm-nm` を PATH に通した)。test.sh の生成物 (`BACKLOG.md`・`inventory.*`・`exports.txt`・`coverage.json`) は素材不足 (plugins 未展開) で劣化して再生成されるため、コミットしない。
- **未検証**: 実 Windows での DWrite の実呼び出し (動的ロードが実際に走るか・どの DLL が見つかるか)。静的解析の結論であり、実行確認は範囲外 (§5)。ローダの呼び出し元 2 件の役割 (テキスト描画か) は未確認。旧挙動 (NULL → 結果 0 格納 → 呼び出し元続行) からの変化により、**abort が A/B の通常起動で発火し得るか**も未確認 (ローダ呼び出し元 2 件の到達条件を実機で確認するまで、決定の影響範囲は不明)。

### 2.5 UI 層の規模と OS 境界 (`ui_closure.py`, rtti_walk+callgraph 再利用)
方法: roots = 42 効果の名前空間ごとに「Dsp/MasterDsp/DspModel **以外**」クラス (Editor/EditorModel/Controller/UI*/Field) の vtable slot。**直接 call/jmp 辺のみ追跡 = 下限** (間接 call は辿らない)。

| 量 | 値 (関数数 / B) |
|---|---|
| RTTI vtable クラス (分類) | 6,307 (boost 3,622・other 1,688・pace 527・std 259・**Sk*/Gr* 211**) |
| Sk*/Gr* クラス vtable slot の関数 | 1,254 関数 / 276,618 B (直接) → 閉包 6,264 関数 / **2,397,080 B** (.text 20,576,428 B の 11.65%) |
| 42 効果 UI 閉包の和集合 | **5,612 関数 / 2,405,825 B (11.69%)**。うち Skia 閉包と重なる 1,420,448 B・重ならない 985,377 B |
| 同手法・同 42 効果の DSP 閉包の和集合 | 373,728 B → **UI/DSP = 6.44 倍** |
| 共有基盤 (≥8 効果の UI から到達) | 1,959 関数 / 717,474 B (うち Skia 非該当 48,604 B) |
| 効果 1 本の UI 閉包 | 699,012〜1,266,485 B (42 本, 中央値 706,904 B)。Gain 705,745 B で、固有 (Skia 外・共有基盤外) は **25 関数 / 3,387 B** |
| Skia 閉包の命令 | 間接 call サイト **8,131** (下限の弱さを示す)・AVX-128 697・AVX-256 112・FMA 132・AVX-512 0・cpuid 関数 4 |
| UI 閉包和集合の間接 call サイト | 12,192 |

- **OS 境界**: 抽象 `UIWindow` (vtable 42 slot) の Win32 実装 `UIWindowWin32` (vtable 43 slot・重複を除く 42 関数 / 15,777 B) + WndProc (4,635 B) + 登録関数 = 「ウィンドウ層」(`UIWindowWin32` slot・WndProc・`RegisterClassW` 呼び出し関数からの到達) は **919 関数 / 264,649 B**、user32/gdi32 の 102 名中 **77 名**がここに集中 (層外 24 名はクリップボード・IME 周辺・キー変換など別クラス)。mac 版は別実装 (`Metal.framework`; 本評価の範囲外)。
- **Editor↔Skia 結合の兆候**: 非 Skia の vtable クラス 6,096 のうち、RTTI 名に `Sk*` 型を含むのは **48** (`ui_closure.py` の分類で `other` は 0 件。残りは boost/std/pace 分類だが内訳は未集計。RTTI 名に現れる例: `EventSlot<const SkSize&>`・`EventSlot<const SkRegion&>`・`PopupHost` の `SkPoint` 引数)。UI の変更通知が Skia 値型を直接受け渡す = lift 済み Editor と別ビルドの Skia を混在させる際は型レイアウト一致が前提 (**推定**; レイアウト依存の実証は未実施)。
- 検査: C1 (UI 和集合 > DSP 和集合: 2,405,825 > 373,728), C2 (`res.size` と `.pdata` サイズが pdata 内関数で一致), C3 ネガコン (Gain の roots を半分にすると閉包 705,745 → 550,551 B), C4 (DSP 固有関数 506 個は UI 和集合に含まれない), C5 (§2.3)。全 PASS。

### 2.6 別算法による検算
- `xcheck_xref.py`: IAT 経由の call/jmp 件数を **llvm-objdump の線形逆アセンブル** (`--section=.text` の出力 5,604,538 行) と全 404 import で突合 → byte-scan **1,863** = objdump **1,863**、不一致 import **0** (`SetDIBitsToDevice`=1・`UpdateLayeredWindow`=1・`RegisterClassW`=1)。ネガコン: byte-scan 側の件数を 1 減らす → 不一致 import 1 件を検出 (期待 1)。
- §2.1 の X1 (ソース検索)、§2.4 の Wine 式、§2.3 の命令列検査は、それぞれ ui_imports/shim/復元と独立の算法。

## 3. 接続方式の評価

| 方式 | 内容 | 必要条件 (本評価の実測に基づく) | 評価 |
|---|---|---|---|
| **A** 全 lift + Win32 shim | UI+Skia+`UIWindowWin32` を HeartCore ごと lift し、user32/gdi32 は tools/gui へ | G1 修正・未実装 17 名 (うちメニュー 8・layered 窓)・DirectWrite 代替 (G3)・UI 閉包 ≥2.4 MB の lift・Skia の AVX 系 (AVX-128 697・AVX-256 112・FMA 132 命令) | 接続形は最短 (WndProc 1 本) だが規模・依存が最大 |
| **B** `UIWindow` 差し替え | UI+Skia は lift、`UIWindowWin32` を HUD 向け実装に置換 (42 slot の契約を逆解析) | `UIWindow` 契約の逆解析 (未着手)。Win32 の未実装 17 名のうち 11 名・メニュー/layered/DPI 周りが不要になる。Skia lift・DirectWrite 代替 (G3) は A と同じ | 境界は明瞭 (42 slot)。契約が不明な点がリスク |
| **C** DSP のみ lift・UI は別実装 (**D7 の拡張**) | Kilohearts UI は lift せず、HUD 側 (Canvas/WebGL) で別実装。素材は非同梱 | UI 仕様の再実装 (規模は効果ごとに別)。`docs/DECISIONS.md` D7 は Fresh Air (同じ HeartCore 系) のみ決定 | 最小リスク。見た目の再現度は低い |
| ~~D~~ Skia を upstream から wasm 再ビルドし lift 済み Editor に接続 | issue 本文の想定 | Editor 層が Skia 値型を直接やり取りする兆候 (§2.5, 48 クラス)。wasm32 の型レイアウト・Skia リビジョン不一致 | **非推奨** (推定。実証していない) |

HUD 側の転送コスト・present 方式は `tools/gui/REPORT.md` §9 が正本 (CPU putImageData / WebGL2 の frame time 表)。HeartCore の窓サイズ・実フレームレートは**未計測**。

## 4. 検証 (コミット済み `a0b5377` のクリーン worktree・PATH 無加工)
- 素のコマンド `bash tools/targets/kilohearts/ui_eval/run_all.sh` を同一 worktree で **3 回**。1 回目は cold (`work/` 無し: `plugins-kilohearts.tar.zst` からの展開 + sha256 検証 + uv 依存導入 + rtti_walk/callgraph を含む) で **81 s**、2・3 回目は warm (展開・rtti/callgraph を再利用) で **43 s / 44 s**。nproc=4、load average(1 分) 開始→終了 = 0.15→0.89 (cold) / 0.82→1.02 / 1.02→1.09。3 回とも exit 2 (VERDICT: NOT READY)。判定行 (PASS/FAIL・exit 行) は 3 回で一致 (ハッシュ一致)。warm 2 回の出力は所要秒・load の行を除き同一 (`diff` 差分 0)。cold は uv の導入行と rtti/callgraph の進捗行が追加されるのみ。
- llvm-objdump は PATH に無い状態 (`command -v` 不在) で `/usr/lib/llvm-18/bin` (16/17/18 のうち最新) に解決され、ステップ 4 (xcheck_xref) まで通過。`8cef593` の同じ素のコマンドはステップ 3 の後で「llvm-objdump が無い」により exit 1 になっていた (レビュー 5501841861 の再現結果。`a0b5377` で修正)。
- 判定が不合格のとき exit 0 にならないこと: G1〜G4 が残る間は exit 2。ネガコン失敗・前提違反・素材なし・llvm-objdump なしは exit 1。`a0b5377` での実測: llvm-objdump の探索 glob を外した一時コピー → **exit 1** (ステップ 1 の前で停止、「llvm-objdump が無い」); 素材なし (`KH_UI_WORK` を空ディレクトリ、`ARTIFACTS_DIR` を不在パス) → **exit 1** (「素材なし/検証失敗」); 1 byte 改変した core (`KH_CORE`、sha256 不一致) → **exit 1**。exit 0 に到達できること = §2.4 の修正案作業コピーで `shim_probe` が exit 0 (3 回とも。対照の判定が逆転して双方向に判別)。
- ネガコン一覧 (全て期待どおり): ui_imports 9 (GPU import 注入 → 2 件検出 / ASCII・UTF-16 の DLL 名注入 → 各 1 件 / SkSL backend 名で偽陽性 0 / DirectWrite 文字列なし → 0 / IMPL から `SetDIBitsToDevice` 除外 → gap 1 / IMPL 空 → gap 102 = import 数 / shimx exports 空 → MISSING 302 = import 数 / `DWriteCreateFactory` を含む模擬 repo → 検出), ui_present 4 (ySrc 改変の lambda を 1 式に整理した後も 4/4 ok), ui_closure 2 (C3・C5n), xcheck_xref 1, shim_probe 1 (+対照 2 系統。修正案の作業コピーでは対照の判定が逆転 = 双方向の判別を確認)。
- 範囲確認 (`a0b5377`): `git status --porcelain=v1 -- tools/targets/kilohearts/ui_eval` で取りこぼし 0、tracked の `find … -size +20M` 0 件。PR の差分 (`git diff 17b7777 HEAD --stat`) は `ui_eval/`・`tools/targets/kilohearts/REPORT.md`・`docs/DOC_MAP.md` のみ (`tools/gui`・`STATUS.md`・`DEFECTS.md` は未変更)。

## 5. 範囲 / 範囲外
- 範囲: Win64 `HeartCore.core_64` の静的解析 (import・xref・RTTI・直接辺の閉包・逆アセンブル)、tools/gui の native headless ビルドへの投入。
- **範囲外 (主張を弱める)**: 実 Windows での実行 (オラクルは Wine ソース式 + HeartCore の意図)、HeartCore を実際に lift/起動した UI 表示、mac 版 (Metal)、Skia の wasm 再ビルド実験、窓サイズ・実フレームレート・入力レイテンシ、動的ロード DLL が実際に呼ばれるか、間接 call を辿った閉包 (§2.5 の規模は下限)、PACE/ライセンス層の UI (起動時ダイアログ等)。
- 直接辺のみの閉包は間接 call (Skia 閉包で 8,131 サイト) を辿らないため**過小**。「2.4 MB」は上限ではない。

## 6. 未解決 (起票依頼)

| # | 未解決 | 影響 | 起票先 |
|---|---|---|---|
| G1 | shim `SetDIBitsToDevice` (+疑い `StretchDIBits`) が top-down DIB の ySrc を上原点扱い・`StartScan`/`cLines` 無視 | HeartCore の部分更新で別の行が表示される。FL の `SetDIBitsToDevice` 2 call site も同じ関数を通る | **新規** `[GUI-13]` (親 #10): `ui_eval/g1_shim_fix.patch` を起点に shim 修正 + `selftest` に top-down 部分矩形ケース追加 (+`StretchDIBits` の確認)。受入 = `shim_probe.sh` 7/7 PASS (exit 0) |
| G2 | user32 未実装 17 名 | A 方式でウィンドウ生成・メニュー・layered 窓・モーダルダイアログが fail-fast | メニュー 8 → #176 (GUI-2) にコメント、`UpdateLayeredWindow`・`MonitorFromPoint`・`BringWindowToTop`・ダイアログ 4 → #183 (GUI-7) にコメント、`TrackMouseEvent` → #182 (GUI-6)、`LoadStringA` → #174 (GUI-3) |
| G3 | Skia の DirectWrite 経路 (動的ロード) の代替なし | A・B 方式でテキストが描けない/起動時に失敗し得る | **方針決定 (KH-20 / #838)**: 呼び出し元を特定 (§2.7)。代替は作らず **shimx で未対応名を明示 fail-fast** (`DWriteCreateFactory` の GetProcAddress で abort)。FreeType 経由は不採用 (理由 §2.7)。関連 #186 (GUI-9) にコメント |
| G4 | shimx に `SHBrowseForFolderW`・shell32 序数 74 なし | フォルダ選択ダイアログのみ | #172 (SHX-T5) にコメント |
| M1 | 接続方式 (§3 A/B/C) の決定 | 以降の KH-UI 作業の有無が変わる | 親 #15 へ提案: `docs/DECISIONS.md` に D7 の Kilohearts 拡張 ADR を PM が起案 |
| M2 | `UIWindow` 抽象 42 slot の契約が未解析、閉包の間接 call 未追跡 | B 方式の工数が見積れない | **新規** `[KH-14]` (B 方式を採る場合のみ) |
| M3 | 実 Windows でのオラクル確認なし | G1 の根拠が Wine ソース + HeartCore の意図のみ | ユーザ依頼 (任意): 実 Windows で同形の 7 ケースを実行する小プログラム (`shim_probe.c` の呼び出し部) |

DEFECTS.md 行案 (shim 側, 層 `ours`; ID は main `6f4f3b0` の最後の D17 の次の **D18**。起票時に最新 main で再確認):

| ID | 層 | 新旧 | 症状 (silent) | 根本原因 | 観測 (証拠) | 検出信号 (機械的) | 修復 |
|---|---|---|---|---|---|---|---|
| D18 | ours (shim) | 新規 | `SetDIBitsToDevice` (top-down DIB, 部分矩形) で別の行が描かれる。全面更新では顕在化しない | `StretchDIBits` と `dib_to_dc` を共有し top-down の ySrc を上原点とみなす・`StartScan`/`cLines` 無視 (Windows/Wine は下原点: `src_top = startscan + lines − (ySrc + cy)`) | `shim_probe.sh`: 5/7 ケース、矩形内 100% の画素が別行 | biHeight<0 かつ ySrc≠0 または cLines≠cy の転送を、独立オラクルで部分矩形ごとに比較 | `dib_to_dc` の呼び出し前に Wine 式で src 行へ変換 (`g1_shim_fix.patch`; 作業コピーで 0/7) |

## 7. 次タスク提案
1. `[GUI-13]` G1 修正 (小): `g1_shim_fix.patch` を `gui_gdi.c` に適用 + selftest 追加 → `shim_probe.sh` が exit 0 になる。
2. ~~`[KH-13]` DirectWrite 代替方針~~ → #838 (KH-20) で対応済み (§2.7: 静的解析で経路を特定し fail-fast 方針)。残る実機確認 (動的トレース) は M3 と同様に起票依頼。
3. M1 の決定後に、C 方式なら Kilohearts UI の HUD 実装チケット (効果ごとの UI 仕様は共有基盤 + 効果固有 25〜38 関数程度と小さい: Gain 25・Delay 38・Reverb 17・Compressor 32 関数, §2.5)、B 方式なら `[KH-14]`。
4. `tools/gui` の `e2e.sh`/`selftest.sh` は mingw 必須 (`gen_api.py`) で mingw の無い runner では走らない。CI で回すなら mingw 追加が必要 → #184 (GUI-8) にコメント。
