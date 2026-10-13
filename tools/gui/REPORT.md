# REPORT — B: gui-shim (Win32 user32/gdi32 → OffscreenCanvas + SAB + 入力キュー)

## 結論 (先出し)
- **FL(win) の GUI import を全列挙・優先度付け済み** (`IMPORTS.md`)。対象は `FLEngine_x64.dll` (FL64.exe の GUI import は `MessageBoxA` 1 件のみで、これも包含済み)。GUI 系 DLL 13 本で **429 エントリ** (一意名 428: `MessageBoxA` が static+delay-load の 2 エントリ; user32 242 / gdi32 127 / comctl32 30 他)。
  描画は転送系中心 (`BitBlt` 47・`StretchBlt` 14・`CreateDIBSection` 7・`StretchDIBits` 4・`AlphaBlend` 6) でベクタ系は僅少 (`LineTo` 14・`Rectangle` 2・`Ellipse` 2) → 「ほぼ 100% 自前ビットマップ描画」を import 面からも裏付け。
- **shim ABI と SAB プロトコルを設計・文書化** (`PROTOCOL.md`: 共有メモリレイアウト・リング・スレッドモデル・lift ABI・GDI モデル・制限)。
- **最小 PoC を超えて実装**: 312 関数 (lift ABI; うち 42 は FL が import しない A 版・テスト用 kernel32 最小 5 本) = FL の GUI import 429 エントリのうち **270 (63%) をカバー (CAB-159 で +51: 219→270)、P0 は 120/120、P1 は 119/119 (69→119)、P2 22/98、P3 9/92**。残り 159 は mingw ヘッダ由来 arity の fail-fast stub を自動生成。
- **PE→lift 経路の E2E 成功** (対象はテスト用 PE `test/gui_app.c`。FLEngine 本体での描画は未達): mingw-w64 で PE32+ → RetDec → 後処理 → emcc (pthread wasm) → **headless Chrome**、CDP の実マウス/キー入力でシナリオ駆動、
  OffscreenCanvas 読み戻し・画面スクリーンショットとも **golden と 64,000 px 完全一致 (差 0)**。`bash tools/gui/e2e.sh` 1 コマンド (16〜24 s、Chrome 6 連続で安定; クリーン状態からも PASS)。
- **P1 50 名を実装 (CAB-159)**: DrawEdge/DrawFrameControl/DrawFocusRect・クリップボード 7・フック 3・モニタ/DPI 7・キャレット 4・アイコン/カーソル 5・入力 7・util 8・リージョン 3・DC/ブラシ原点/DDB 3 (+P2 から `CreateCaret` を前倒し)。各 API に unit テスト (selftest **83→314 assertion**、`integ/check_p1_tests.py` が 51 名すべての実装+テスト呼出を機械検査)。
- **実 FLEngine 結合の準備 (CAB-156)**: 到達 API ログ・m11 IR との署名突合と wasm32 署名 adapter・icall hook・結合手順書/ABI チェックリスト (`INTEGRATION.md`)。m11 IR の GUI declare **177 名**(実装 132→153 / stub 45→24; 後者は CAB-159 後)を突合し、wasm-ld 署名不一致 **177 → 0**(adapter 無しを陰性対照)。`--wndproc` 手指定を廃止(自動検出)。e2e に 6d(到達ログ)/6e(sigprobe)/2b を追加し ALL PASS 維持。
- 副産物: RetDec の PE lift 欠陥 4 件と ABI 要件 3 件 (GLOBAL_BASE≥64KiB, 31bit ハンドル, WNDPROC 4 引数 + VA→関数 fnmap) を実測で特定 (§4)。FL 本体 lift にそのまま効く。

## 1. 成果物
| パス | 内容 |
|---|---|
| `tools/gui/PROTOCOL.md` | 設計仕様 (ABI/共有メモリ/リング/スレッド/座標/GDI/制限/lift 知見) |
| `tools/gui/IMPORTS.md` | FL 全 import 面 + GUI 429 名の優先度 P0〜P3・xref・実装状態 (`tools/gui/analysis/gui_imports.py` + `gen_api.py` 自動生成) |
| `tools/gui/include/` | `gui_proto.h` 共有領域の正本 (offset は `_Static_assert` 固定) / `gui_win32.h` (Win64 構造体・定数) |
| `tools/gui/src/` | shim 本体 C: `gui_core.c` (user32 1,583 行) + `gui_core_ext.inc` (P1 拡張 356 行)・`gui_gdi.c` (gdi32/msimg32 1,095 行)・`gui_platform.c` (futex/ring/handle/region)・`gui_headless.c` (native host 代替) |
| `src/runtime/gui.ts` `gui_worker.ts` `gui_proto.ts` | ブラウザ host (入力リング生産者・OffscreenCanvas 描画ワーカ・プロトコルミラー) ※`tsc --noEmit` OK |
| `tools/gui/lift/` | `gui_lift.sh` (mingw→RetDec→後処理), `gui_lift_post.py`, `gui_wasm.sh` (emcc), `gui_lift_main.c` |
| `tools/gui/test/` | `gui_app.c` (テスト PE), `selftest.c` (83 assertion、+P1 `selftest_p1.inc` 231 = 314), `native_run.c`, `bench.c`, `gui_app_ff.c` (fail-fast PE) |
| `tools/gui/INTEGRATION.md` + `integ/` | 結合手順書 (リンク/ABI チェックリスト/ハンドル 31bit/ハーネス拡張方針)・`gen_adapt.py` (突合表 `INTEGRATION_XCHECK.md` + wasm32 adapter)・`sigprobe.sh`・`build_objs.sh`・`lift_fnmap.py`・`reach_report.py`・fixture |
| `src/gui_reach.c` ほか | 到達 API ログ (`GUI-REACH` 行 / `gui_reach_json`)、`gui_set_icall_hook`、`-DGUI_NO_K32` |
| `tools/gui/e2e/` + `e2e.sh` | CDP ドライバ `e2e.mjs`、ページ、1 コマンド E2E |
| `tools/gui/golden/` | `gen_golden.py` (独立オラクル) と `final.png` |
| `tools/gui/shimx_coexist/` + `include/gui_hostcall.h` + `src/runtime/gui_hostcall.ts` | shimx との weak/強定義の境界確定と共存リンク検査・host 呼出路 (ShellExecute/ファイルダイアログ/D&D)。#172。結果は `shimx_coexist/REPORT.md` |

## 2. 検証結果 (全て実測; `bash tools/gui/e2e.sh`)
| 層 | 結果 |
|---|---|
| native 単体 `test/selftest.sh` (gcc -fsanitize=address,undefined, headless host) | **314/314 PASS** (78 + icall hook 5 + P1 231): 作成メッセージ順・投函 FIFO・WM_PAINT・タイマ・ヒットテスト/子窓/キャプチャ/GetCursorPos・キー順・DIB/Rect/Line/BitBlt/StretchBlt(2x・反転)/StretchDIBits(bottom-up)/AlphaBlend/クリップ・region・SaveDC・WindowOrg・z-order 合成・props/Enum/Scroll/SetParent・他スレッド Post/Send・WM_QUIT・fail-fast(SIGABRT+API 名) |
| native lift `test/native_e2e.sh` (PE→RetDec→gcc→shim) | golden **完全一致 (0/64000 px)**、ExitProcess 経由で正常終了 |
| Chrome E2E (固定 128 MiB メモリ) | **OffscreenCanvas 読み戻し 差 0 / 画面スクリーンショット 差 0**、入力リング drop 0、`present_done_seq==present_seq`、タイマ fire 3 |
| Chrome E2E (`ALLOW_MEMORY_GROWTH`, 初期 3 MiB→3.8 MiB に成長) | 同上すべて一致 (worker の `memory.buffer` 再取得を検証) |
| Chrome fail-fast E2E (未実装 `Ellipse` に到達する PE) | host が `EXIT 0xFA11` を受信、console に `FAIL-FAST: unimplemented Win32 API: Ellipse` |
| 結合準備 (CAB-156) | `test/reach_test.sh`: 到達ログ 11 + wasm32 adapter wiring/ハンドル 31bit 28 + 改名ビルドで selftest 83/83。`integ/sigprobe.sh`: 177 declare で署名不一致 0 / 未解決 import 0 (陰性対照 177)。Chrome 6d: host console に `GUI-REACH` 36 API |
| 陰性対照 | golden を 1 bit 改変 → `MISMATCH (1 px)` で exit 1 / ST (非 pthread) ビルドはブロック箇所で fail-fast |
| 安定性 | Chrome E2E 6/6、native lift 5/5 PASS |
- **被覆表** (FL の GUI import 429 エントリ; `IMPORTS.md` 実測。CAB-159 前 → 後):
  | 優先度 | 名数 | 実装 前 → 後 | 未実装 xref 計 (後) |
  |---|---|---|---|
  | P0 | 120 | 120 → 120 | 0 |
  | P1 | 119 | 69 → **119** | 0 |
  | P2 | 98 | 21 → 22 (CreateCaret 前倒し) | 281 |
  | P3 | 92 | 9 → 9 | 190 |
  | 計 | 429 | 219 → **270** (+51) | 471 |
- シナリオ (10 入力): クリック 2 回 + ドラッグ (SetCapture・領域外移動・GetCursorPos/ScreenToClient) + キー `A` `b` + ESC→DestroyWindow→PostQuitMessage→ExitProcess。
  同期は全て LOG/フレーム ack の Promise (固定 sleep なし)。Chrome 側シナリオ所要 約 200 ms (CDP 往復込み)。
- golden は shim と独立の Python オラクル (`golden/gen_golden.py`; 共有はフォントデータのみ) が `test/gui_app.c` の描画仕様から計算。

## 3. 性能 (参考値。実 GPU 合成・実 FL 負荷は未測)
| 項目 | 実測 |
|---|---|
| shim 転送 (native -O2, 1920×1080) | BitBlt SRCCOPY mem→mem 0.37 ms / →window 0.20 ms / FillRect 0.27 ms / StretchBlt 2x 3.8 ms / StretchDIBits 1:1 2.3 ms / ROP(SRCINVERT) 4.9 ms |
| 描画ワーカ (BGRA→RGBA + putImageData, headless Chrome, 合成画像) | 1280×720 **1.0〜1.5 ms/frame**、1920×1080 **2.2〜3.8 ms/frame** (マシン負荷で変動; 最大でも 60fps 予算内) |
| 成果物サイズ | wasm 128 KB (shim + lift 済みアプリ + stub 159 本; CAB-156 の到達ログ export・CAB-159 の 51 API を含む。以前 114 KB / stub 210 本) |
- 解釈: 1080p/60fps の予算 16.7 ms に対し 転送+変換は ~3〜8 ms で、M7 の 30fps 条件は満たせる見込み。変換は CPU ループなので WebGL2 化で更に削減可 (GUI-4)。
  非 SRCCOPY ROP/拡縮は per-pixel のため wasm SIMD 化の余地 (GUI-5)。画面合成コスト・マルチウィンドウは未計測。

## 4. 実測した lifter (RetDec) 欠陥・ABI 要件 (FL 本体 lift へ直結)
1. **stack 上の構造体の 2 番目以降のフィールド store が消える** (`WNDCLASSA`/`RECT`。API 引数に struct 型が付くため)。静的大域に置けば保存される。
2. 大域構造体は **1 フィールド 1 グローバル `gN`** に分割 → `&g1` を構造体として渡せない。後処理で PE イメージ連続領域へ `#define` (FL 本体では M6〜M11 の data 実体化と同種)。
3. **`while (GetMessage(..) > 0)` が壊れる**: BOOL 戻りが `bool` 型付けされ `if (!v1 != v1)` (常に真) になりループ即終了。真偽判定の `while (GetMessage(..))` は正しい (VCL はこちらの形)。
4. `keybuf[n++] = c` が `g38 = &g39` へ誤った定数畳み込み (別書式で回避可)。
5. **WNDPROC の未使用引数が落ちる** → call_indirect 署名不一致 trap の原因。`--wndproc` で 4 引数へ正規化。`lpfnWndProc` は **関数 VA 整数** で保持 → `{VA, fn}` 表 (`gui_register_fnmap`) で解決。
6. `(int32_t)wParam/(int32_t)lParam` に潰される → ハンドルは 31bit 内で発行 (実装済み)。wasm の >2 GiB ポインタを lParam に載せる API は要注意。
7. wasm では `-sGLOBAL_BASE=1048576` 必須 (静的文字列が `<0x10000` だと atom 扱い。RegisterClass が fail-fast して発覚)。

## 5. 未実装・逸脱 (全量は `IMPORTS.md` の STUB 一覧)
- **P1 未実装 0 名** (CAB-159 で全実装。意味論・近似は PROTOCOL.md §11): クリップボードはプロセス内ストア (ブラウザ Clipboard API 橋渡しは設計のみ=ユーザジェスチャ/権限/非同期の制約)、アイコン/カーソルは標準擬似ハンドルのプレースホルダ画像のみ、`LoadStringW`/`LoadBitmapW` はリソース供給 hook (`gui_set_resource_provider`) 待ち、`DrawEdge(BF_DIAGONAL)` は fail-fast、モニタは単一仮想モニタ。
- **P2 未実装 76 名 (xref 計 281; `CreateCaret` は P1 キャレット成立のため前倒し)**: メニュー 15、ImageList_* 14 (DnD ドラッグ画像)、アイコン/カーソル生成 7、パレット参照 6、IME 6、BufferedPaint/MaskBlt 等 5、スクロールバー API 4、`_TrackMouseEvent` ほか。(ImageList_* 全体 23・メニュー全体 21・IME 全体 7・スクロールバー全体 14 は P2+P3 の合算)
- **P3 未実装 83 名 (xref 計 190)**: ベクタ GDI (Ellipse/Polygon/Arc/Bezier/Path) 15・メタファイル 11・印刷 10・FlatSB 10・ImageList 9・メニュー 6・タッチ/ジェスチャ 5・Dwm/WTS/oleacc 5・wgl 2・共通ダイアログ 2 など。
- 機能制約: DIB は 32bpp のみ (1/8/24bpp は fail-fast)、GDI テキストは内蔵 8×8 固定幅 (ASCII)、無効領域は単一外接矩形、非クライアント領域なし、`SetCursorPos` は Pointer Lock 未連携、
  `GetDC(NULL)` (スクリーン DC)・複数モニタ・IME・DPI スケーリング (dpr は header に載るが未適用)・`SetWindowRgn` の形状反映は未対応 (no-op)。
- 未検証: 実 FLEngine lift との結合 (移植待ち)・長時間ストレス・GPU 合成の実フレームレート・Chrome 以外 (Firefox/Safari)。

## 6. ユーザ依頼事項
現時点で必須の依頼なし (外部素材不要。mingw-w64 / RetDec / emsdk / Chrome は既設を使用)。将来分: ① GUI-9 (CAB-185) GDI フォント同梱方針 (Windows 標準フォントを同梱せず OSS フォントで代替してよいか) の判断、② GUI-6 (CAB-181) / GUI-8 (CAB-183) の IME・タッチ・Firefox 実機確認 (CAB-126 に合流)。

## 7. 下流チケット (Linear 起票済み; 親 CAB-8 / 検収で連番化)
| ID | Linear | 状態 | 内容 |
|---|---|---|---|
| GUI-3a | CAB-156 | In Review | 結合準備 (実 FLEngine 不要): m11 GUI declare ↔ exports 突合表・fnmap/WNDPROC 自動化・到達 API ログ・手順書 (本 REPORT 結論/`INTEGRATION.md`) |
| GUI-1 | CAB-159 | In Review | P1 未実装 50 名 (DrawEdge/Clipboard/フック/モニタ/キャレット/util/入力) → P1 119/119。メニューは GUI-2 へ移動 |
| GUI-3 | CAB-173 | Backlog (blockedBy CAB-5, CAB-156) | FLEngine 結合: `m11_winstubs.c` (`m11_genstubs.py` 生成物) の GUI 部を本 shim に置換、実到達 API ログで P 分類を更新。blocks CAB-31 |
| GUI-2 | CAB-175 | Backlog (blockedBy GUI-3) | ImageList_* 23 + メニュー 21 + IME 7 ほか P2 77 名、OLE DnD ↔ HTML5 DnD |
| GUI-5 | CAB-180 | Backlog (blockedBy GUI-3) | 24/8/1bpp DIB・DDB 対応 (現状 32bpp のみ) + ROP/StretchBlt/AlphaBlend の SIMD128 化 |
| GUI-9 | CAB-185 | Backlog (blockedBy GUI-3; フォント方針はユーザ判断) | GDI テキストを内蔵 8×8 → FreeType (CAB-18) 実フォント描画 |
| GUI-7 | CAB-182 | Backlog (blockedBy GUI-3) | ポップアップ/メニュー/ツールチップ窓、非クライアント領域、DPI、複数 canvas 重畳 |
| GUI-4 | CAB-179 | Backlog (blockedBy GUI-3) | WebGL2 present・dirty 複数矩形・rAF 同期・seqlock (現行 CPU 経路は 1080p 2.2〜3.8 ms/frame で予算内) |
| GUI-6 | CAB-181 | Backlog (blockedBy GUI-3) | Pointer Lock による SetCursorPos、IME、タッチ、キーボード配列 (実機確認はユーザ依頼の可能性) |
| GUI-8 | CAB-183 | Todo | e2e を agent-browser 載せ替え・数万フレーム耐久/リーク検査・Firefox (CAB-126 依存) |

## 8. 再現
```
bash tools/gui/e2e.sh            # 全層 (17〜24 s): 解析→API 面生成→golden→selftest→native lift→PE lift→emcc→tsc→Chrome E2E ×3
bash tools/gui/test/selftest.sh  # native 単体のみ
python3 tools/gui/analysis/gui_imports.py && python3 tools/gui/gen_api.py   # import 面 / IMPORTS.md 再生成 (入力 tools/m2/work/block00031_PE.bin)
```
前提: x86_64-w64-mingw32-gcc, RetDec (`[RETDEC]`), Emscripten (`[EMSDK]`・同梱 node 24 を PATH に使用), google-chrome, gcc。
