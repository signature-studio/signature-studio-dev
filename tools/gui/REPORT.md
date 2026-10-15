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
- **実 FLEngine 結合 (GUI-3 #174)**: m11 closure に本 shim を結線し、自然起動で shim に届く GUI API と未実装 API を実測・集計 (部分達成; `RegisterClass*`/`CreateWindowEx*` の自然到達は未達)。全文は [flengine/REPORT.md](flengine/REPORT.md)。
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
- 解釈: 1080p/60fps の予算 16.7 ms に対し 転送+変換は ~3〜8 ms で、M7 の 30fps 条件は満たせる見込み。変換は CPU ループなので WebGL2 化で更に削減可 (GUI-4: §9 に実装と実測)。
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
- 機能制約: DIB は 1/4/8/24/32bpp 対応 (GUI-5 #181, §10; 16bpp DIB・DIB_PAL_COLORS・圧縮は fail-fast)、GDI テキストは内蔵 8×8 固定幅 (ASCII)、無効領域は単一外接矩形、非クライアント領域なし、`SetCursorPos` は Pointer Lock 未連携、
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
| GUI-5 | CAB-180 / #181 | 部分達成 (§10; FL 非依存部は実装・検証済み、`e2e.sh` ALL PASS と FLEngine 到達 bpp/ROP の確定は未達) | 24/8/4/1bpp DIB・mono DDB 対応 + ROP/StretchBlt/AlphaBlend の SIMD128 化 |
| GUI-9 | CAB-185 | Backlog (blockedBy GUI-3; フォント方針はユーザ判断) | GDI テキストを内蔵 8×8 → FreeType (CAB-18) 実フォント描画 |
| GUI-7 | CAB-182 | Backlog (blockedBy GUI-3) | ポップアップ/メニュー/ツールチップ窓、非クライアント領域、DPI、複数 canvas 重畳 |
| GUI-4 | CAB-179 / #180 | 部分達成 (§9; FL 非依存部は実装・e2e 済み、FL 依存部は GUI-3 待ち) | WebGL2 present・dirty 複数矩形・rAF 同期・seqlock (現行 CPU 経路は 1080p 2.2〜3.8 ms/frame で予算内) |
| GUI-6 | CAB-181 | Backlog (blockedBy GUI-3) | Pointer Lock による SetCursorPos、IME、タッチ、キーボード配列 (実機確認はユーザ依頼の可能性) |
| GUI-8 | CAB-183 | Todo | e2e を agent-browser 載せ替え・数万フレーム耐久/リーク検査・Firefox (CAB-126 依存) |

## 8. 再現
```
bash tools/gui/e2e.sh            # 全層 (17〜24 s): 解析→API 面生成→golden→selftest→native lift→PE lift→emcc→tsc→Chrome E2E ×3
bash tools/gui/test/selftest.sh  # native 単体のみ
bash tools/gui/test/text_golden.sh && bash tools/gui/test/ft_wasm.sh   # GUI-9 FreeType テキスト (前提: tools/shared/oss/freetype/build.sh, test/fetch_fonts.sh)
bash tools/gui/test/text_wasm_e2e.sh   # GUI-13 wasm ビルド + ブラウザ上テキスト描画 (RetDec 不要; 前提は同上 + emsdk + google-chrome + tsc)
python3 tools/gui/analysis/gui_imports.py && python3 tools/gui/gen_api.py   # import 面 / IMPORTS.md 再生成 (入力 tools/m2/work/block00031_PE.bin)
```
前提: x86_64-w64-mingw32-gcc, RetDec (`[RETDEC]`), Emscripten (`[EMSDK]`・同梱 node 24 を PATH に使用), google-chrome, gcc。

## 9. GUI-4 (#180): WebGL2 present / dirty 複数矩形 / rAF 同期 / seqlock
全文は [REPORT_APPENDIX.md](REPORT_APPENDIX.md) に分割移動 (250 行上限; 内容は無変更)。結論: 現行 CPU 経路は 1080p 2.2〜3.8 ms/frame で予算内、WebGL2 present・複数矩形・rAF 同期・seqlock は FL 非依存部を実装・e2e 済み。

- **前面 surface の z 順再描画** (#180 / PR #1022, 検証起点 `b54fb619`): `present()` / `glDrawRects()` で dirty 矩形内の前面 surface を z 昇順に描く。`e2e.sh` ALL PASS (35 件 OK、golden 4 方式 × 46 step × 230,400 px 差 0)。ソート除去の陰性対照は cpu-immediate (差 3,512 px) が 5/5 回 FAIL、gl-direct-immediate・cpu-raf-seqlock (差 2,862 px) が 5 回中 2〜3 回 FAIL、gl-staged-raf-seqlock は 5/5 回 PASS (検出しない)。全文は [REPORT_APPENDIX.md](REPORT_APPENDIX.md) §9b。

## 10. GUI-5 (#181): 24/8/4/1bpp DIB・mono DDB と wasm SIMD128 行カーネル
既知類型との関係: lift 欠陥ではなく shim の意味論 (`docs/DEFECTS.md` D18 として登録)。ただし shim 自身の silent 誤りを 1 件発見 (下記「発見」)。検証起点: 実装 `dd7be3e`、本節の数値は `9cff72c` のクリーン tree での実測 (src/test は最終 HEAD と同一で、以降の commit は REPORT・DOC_MAP のみ; `gui_gdi.c` は `dd7be3e` と同一)。

### 結論
- **機能欠落 (スコープ 1) は FL 非依存の範囲で解消**: `CreateDIBSection` の 1/4/8/24bpp (app から見えるネイティブ形式 `nat` と内部 BGRA shadow を pull/push で同期; 仕様 [PROTOCOL.md §8](PROTOCOL.md))・`CreateBitmap` の mono(1bpp)/24/32bpp・`StretchDIBits`/`SetDIBitsToDevice`/`SetDIBits`/`CreateDIBitmap`/`LoadBitmapW` の 1/4/8/24/32bpp 源・`GetDIBits` の 1/4/8/24/32bpp 出力・`GetDIBColorTable`/`SetDIBColorTable` (IMPORTS: STUB→IMPL, 実装 270→272)・mono↔color 転送の bk/text 色写像・`MERGEPAINT`。未対応は理由付き fail-fast (16bpp DIB / DIB_PAL_COLORS / 圧縮 / `CreateBitmap` 4,8,16bpp の初期 bits)。
- **SIMD 化 (スコープ 2)**: `src/gui_simd.h` の行カーネル (ROP 15 種・AlphaBlend 定数/per-pixel alpha・不透明化コピー・2x 水平拡大) を wasm SIMD128 と scalar 参照で持ち、`BitBlt`/`StretchBlt`/`StretchDIBits`/`AlphaBlend` が使う。拡縮は x 写像を転送ごとに 1 回計算 (画素ごとの 64bit 除算を排除)。`lift/gui_wasm.sh` は既定 `-msimd128` (`GUI_NO_SIMD=1` で scalar)。
- **受入条件は未達 → PR は `Refs #181`**: (a) `bash tools/gui/e2e.sh` の ALL PASS は runner に RetDec (`toolchain-retdec`) が無く PE lift 層 (2/6・3/6・4/6・6/6〜6d) を実行できず**未確認**、(b) issue の保留理由 (FLEngine が実際に要求する bpp/ROP を GUI-3 #174 の到達ログで確定) は未充足、(c) Chrome 上で SIMD 版 wasm 全体 (lift 済みアプリ込み) を走らせていない (SIMD は kernel 単位で node 検証)。

### 検証 (全て `9cff72c` のクリーン tree、runner 4 CPU、`uptime` load 0.5〜1.4)
| 層 | 結果 | 陰性対照 |
|---|---|---|
| native `selftest` (ASan/UBSan) | **378 passed / 0 failed** (319 → 378: +59 assertion)。各 bpp の native↔shadow 往復 (24bpp 行 4B 境界・bottom-up/top-down・8bpp 最近傍/重複色 index 保持/SetDIBColorTable・4bpp nibble・1bpp MSB 先頭)・各 bpp 源の StretchDIBits・GetDIBits/SetDIBits・mono 色写像・fail-fast 5 件 | fail-fast 5 件は `SIGABRT` + API 名/理由の文字列を検査 (出力を EOF まで読む) |
| 行カーネル版 == 画素単位参照 (`gdi_set_ref_blit`) | ROP 15 種 × 幾何 (1:1・2x・任意比・水平/垂直反転) × クリップ (なし/矩形/穴/複数穴) × 同一サーフェス重複: **4,500 ケース (うち同一サーフェス 642) で不一致 0**。各 ROP 300 ケース。同一サーフェスは「転送元を事前コピーした別サーフェスから転送した結果」とも一致 | 別 ROP・別オフセットで実行した結果は参照と不一致 (90 プローブ中 76 で検出) |
| AlphaBlend 独立オラクル (テスト内に直書き `(x+127)/255` 丸め) | 60 ランダムケース (定数 α/per-pixel α・1:1/拡縮・端のはみ出し) で不一致 0。`gs_div255(x)==(x+127)/255` を x∈[0,65025] 全件確認 | sca=101 の結果を sca=100 のオラクルと比較 → 不一致を検出 (+ 同条件 sca=100 は一致の陽性対照) |
| **golden** (`bash tools/gui/test/bpp_golden.sh`): 24/8/4/1bpp StretchDIBits + 24/8bpp DIB section (native 直書き + GDI FillRect/LineTo → BitBlt) + mono + SRCINVERT 2x + AlphaBlend の 160×100 シーンを独立 Python オラクル `golden/gen_golden_bpp.py` (shim と共有するのはパターン式のみ) と比較 | **16,000 px 差 0 (EXACT MATCH)** | 期待値を 1 画素壊す → 不一致で拒否 / shim 側に故意の欠陥 (パレット index 2 の色差し替え) → **40 px 不一致で拒否** (どちらかが通ると script が exit 1) |
| wasm SIMD128 (`bash tools/gui/test/simd_e2e.sh`, emcc 6.0.12 + node v22.23.3) | SIMD == scalar: ROP 15 種 × 長さ 0..70 × アライメント 0..3、α 全 256 値 × 2 方式、不透明化コピー・2x 拡大の端数、1080p 1 行 (1920 px): **15,679 ケース不一致 0**。`gui_gdi.c` を `-msimd128` で wasm 化すると v128 系命令 1,020 / `-DGUI_NO_SIMD` で 0 (SIMD 経路が実際に入る) | SIMD 無効ビルドの simd_test は exit 2 で拒否 (scalar 同士の比較で PASS しない) / 故意の欠陥 4 種 (`-DGS_FAULT=1..4`: div255 丸め・SRCINVERT→OR・shuffle 誤り・OR 落ち) は全て FAIL (不一致 1,632 / 271 / 252 / 268) |
| 既存層 | `reach_test` 11 passed・`adapt_test` 28 passed・改名 selftest 378 passed (`test/reach_test.sh`)、`tsc -p tools/gui/tsconfig.json` rc 0、`sigprobe` signature mismatch=0 (陰性対照 177)、present e2e (`PRESENT_SKIP_BENCH=1`) 7 pass / 0 fail ALL PASS (18.8 s) | — |
| **未実行** | `bash tools/gui/e2e.sh` の PE lift 層 (RetDec 不在)。`e2e.sh` に 1b/6 (bpp golden)・1c/6 (SIMD) を追加済みだが全体の ALL PASS は未確認 | — |
- **origin/main (`d1ff878`; #172 shimx・#118 等) との merge 後 `04dd71e`**: `selftest` 406 passed / 0 failed (3 回連続; main 側の `selftest_fd.inc` +28 を含む)・`bpp_golden` EXACT MATCH 16,000 px・`simd_e2e` ALL PASS・`reach_test` 11/28 passed・改名 selftest 406 passed・`tsc` rc 0 を再確認。
- 再現 1 コマンド: `bash tools/gui/test/selftest.sh` / `bash tools/gui/test/bpp_golden.sh` / `bash tools/gui/test/simd_e2e.sh` (bench は `BENCH=0` で省略。上記 3 本 + reach_test の合計 44.0 s, load 1.05)。
- **既存の不安定 (本変更と無関係)**: native `selftest` は ASan で `gui_headless.c:blit_surf` の heap-use-after-free で 20 回中 4 回 (20%) exit 1 (全て同一スタック; #489 → 本 REPORT §12 で修正)。それ以外の失敗は 0。

### 性能 (1080p, 参考値; 実 FL 負荷・実ブラウザは未測)
native `-O2` gcc 13 (`bash tools/gui/test/bench.sh 5 [旧 tools/gui のパス]`; 前 = `17b7777` の src に同じ bench.c を適用, 後 = 最終; 各 n=5 の min–max ms/frame, load 0.5〜0.6; native は wasm SIMD が使えないため行ループ化・除算排除の効果のみ):
| API | 前 | 後 | min 比 |
|---|---|---|---|
| BitBlt SRCINVERT | 7.17–7.30 | 2.60–2.67 | 2.76x |
| BitBlt SRCPAINT | 7.17–7.30 | 2.63–2.87 | 2.73x |
| StretchBlt 2x nearest | 7.20–7.83 | 1.90–1.97 | 3.79x |
| StretchDIBits 32bpp 1:1 | 7.20–7.63 | 0.70–0.73 | 10.29x |
| AlphaBlend per-pixel α | 18.97–19.13 | 14.73–15.17 | 1.29x |
| AlphaBlend 定数 α | 18.13–18.80 | 15.77–16.07 | 1.15x |
| StretchDIBits 24bpp 1:1 / 8bpp 1:1 | fail-fast | 2.10–2.13 / 1.40–1.43 | — |
| BitBlt SRCCOPY 24bpp DIB section → 32bpp / 逆向き | fail-fast | 1.90–2.20 / 3.57–4.37 | — |

wasm 行カーネル (node, 各 n=5 の min–max ms/frame; scalar = `-msimd128` なしの同一ソース):
| カーネル | scalar | SIMD128 | min 比 |
|---|---|---|---|
| ROP SRCINVERT | 2.122–2.466 | 0.751–0.892 | 2.83x |
| ROP PATPAINT | 2.149–2.193 | 0.772–1.078 | 2.78x |
| AlphaBlend 定数 α | 12.745–12.838 | 2.942–3.309 | 4.33x |
| AlphaBlend per-pixel α | 18.476–18.745 | 4.260–4.321 | 4.34x |
| StretchDIBits 1:1 (不透明化コピー) | 1.550–1.754 | 0.627–0.661 | 2.47x |
| StretchBlt 2x の水平拡大行 | 1.301–1.430 | 0.566–0.583 | 2.30x |
- 数え方: 行カーネルだけの時間 (clip・xmap・pull/push・dirty は含まない; 全 API の wasm 計測は Chrome 上の lift 済みアプリが要るため未実施)。AlphaBlend の native 改善が小さい (1.15〜1.29x) のは native に SIMD 経路が無く整数演算が支配的なため。
- 24bpp 以下の DIB section は GDI 操作ごとに pull/push (矩形限定) が入る分、32bpp より遅い (BitBlt 先が 24bpp で 3.57–4.37 ms)。

### 発見・限界
- **発見 (shim の silent 誤り・本 PR で修正)**: 同一サーフェス BitBlt でクリップが複数矩形のとき、旧実装は先行矩形の書込みを後続矩形が転送元として読む (穴あきクリップで画素が源と異なる; 旧画素単位実装で 642 ケース中 32 件を再現)。本 PR は転送元矩形の事前コピーで修正。`docs/DEFECTS.md` 形式の行案: 症状 = スクロール/コピーで穴の周りの画素が壊れる / 根本原因 = クリップ矩形ごとに全行を処理し先行矩形の結果を源として読む / 検出信号 = 事前コピー転送との画素比較 / 修復 = 源矩形のスナップショット (DEFECTS.md の直接編集は PM 判断)。
- 近似: mono への color 書込み (輝度 ≥128 を白)、`GetDIBits` の ≤8bpp 既定色表 (決定論的な 1bpp 黒白/4bpp VGA16/8bpp 3-3-2; 実 Windows の DDB パレットとは異なる)、≤8bpp への書込みは最近傍 (距離関数は RGB 二乗距離で、実 Windows との照合は未実施)。

### 範囲外・未達
| 未解決 | 影響 | 起票先 |
|---|---|---|
`bash tools/gui/e2e.sh` 全体 ALL PASS → 付録 §16 で実測。現 HEAD `fcd564bc` で ALL PASS (rc=0, 185 s, 1 回。同 HEAD の 1 回目は 6/6 の依存欠落で rc=2)。1/6 の selftest は `e11701db` で 20 回連続 PASS (ASan 0 件)。修正前 src では 7 回中 2 回発火 | 修正後の e2e 全体の PASS は 1 回のみ。受入扱いは PM 判断 | #489 `[GUI-12]` (既存)・PM |
| 実 FLEngine が要求する bpp/ROP の確定 (GUI-3 #174 の到達ログ待ち)・16bpp DIB・DIB_PAL_COLORS・`CreateBitmap` 4/8/16bpp の初期 bits・RLE/JPEG/PNG 圧縮 DIB | 実 FL が要求したら fail-fast で止まる (理由付き) | #174 到達後に #181 へ追記 |
| Chrome 上の lift 済みアプリ込みの API 単位 frame time → 付録 §16 §2 (wasm shim 全体は取得済み。Chrome 上のアプリ込みは未取得、理由は付録 §16 §2) | — | #181 |
| mono / パレットの色写像の実 Windows との照合 (近似) | 色が実機と数階調ずれる可能性 | #181 (実機比較はユーザ依頼候補) |
| native selftest の ASan UAF (20 回中 4 回) | `e2e.sh` 1/6 が約 20% で FAIL | #489 `[GUI-12]` で修正 (本 REPORT §12) |
| `integ/sigprobe.sh` の `unresolved-imports=0` が `wasm-objdump` 不在で空振り (今回も `command not found`) | 未解決 import なし確認が無効 | #180 (既存コメント) |

## 11. GUI-9 (#186): GDI テキストの FreeType 描画 (内蔵 8×8 → FreeType 2.7)
- 結論: GDI テキストは FreeType 2.7 で描画し、独立オラクルと画素差 0・metrics 差 0。`e2e.sh` ALL PASS は af8ba9cc・0cbc5651 で各 1 回のみ (flake 残存)。詳細は [REPORT_APPENDIX_B.md](REPORT_APPENDIX_B.md) §11。

## 12. GUI-12 (#489): headless host の surface 画素 use-after-free (selftest ASan flaky)

既知類型との関係: lift 欠陥ではなく native headless host と shim の free タイミング競合 (`docs/DEFECTS.md` D1a〜D17 に該当なし。`tools/icall/REPORT.md` §4 とも無関係)。実装 commit `6e6c9b7`。検証起点: HEAD `31bcd9a` (main 取り込み後の PR HEAD。コード差分は同一で、以後の commit は docs のみ)。

- **原因**: render thread (`gui_headless.c` `blit_surf`) が `gui_surf_ptr(id)` で画素ポインタ、`S->surf[id].w/h` で寸法を別々に読み、その間に shim 側 `surf_free` / `surf_resize` が旧画素を即 `free()` していた (ASan: `blit_surf:33` read / freed by `surf_free`)。wasm 共有メモリ経路では free 済み領域も有効なので crash しない (stale 読みは別問題・未対応)。
- **修正** (`gui_core.c`): surface ごとに不変 `SurfSnap {px,w,h}` を atomic に公開し host は一組で読む。旧画素と旧 snapshot の free は `retire_locked` で「公開時点の `out_ring.tail` を `out_ring.head` が通過する (= host がその変更レコードを消費し終える)」まで遅延し、`surf_flush` / 次の retire で回収する。host に `gui_lock` を取らせない (out ring 満杯時のデッドロック回避; issue 方針案の前者)。ブラウザ host の挙動・PROTOCOL は不変。
- **再現・検証** `bash tools/gui/test/gui12_race.sh [N=50] [NC_N=30]` (本体 N 回 + ネガコン NC_N 回。いずれか不合格で exit 1):

| 項目 | 実測 (4 vCPU runner, load average は各実行末) |
|---|---|
| 修正前 selftest (`origin/main` 同一コード) 30 回連続 | exit 1 が 2/30 (同一スタック `blit_surf gui_headless.c:33`) |
| 修正後 selftest 60 回連続 (作業ツリー, 1 run あたり約 4 秒) | exit 1 が 0/60 (load 1.78) |
| **`gui12_race.sh 50 30` (`31bcd9a`, クリーン worktree, 所要 251 秒)** | **修正後 exit≠0 が 0/50 (UAF 0)** / ネガコン **30/30 が heap-use-after-free** (load 2.15 / 1.79) → PASS |
| selftest 件数 (`31bcd9a`) | 428 passed, 0 failed (GUI-12 stress 2 件を含む: 150 回の create/MoveWindow×2/destroy 後に保留 free が 0 件に回収) |
| `bpp_golden.sh` / `reach_test.sh` (`31bcd9a`) | ALL PASS / reach 11 + adapt 28 passed (reach_test 内の selftest も 428 passed) |

- **ネガコン**: `-DGUI12_NEGCTL_IMMEDIATE_FREE` (retire を即 free に戻す。`gui12_race.sh` だけが定義) で UAF 30/30。新 stress 節は確率的競合を決定論的に近づけるため、修正前より再現率が高い (修正前 2/30 → ネガコン 30/30)。
- **範囲外**: `native_e2e.sh` / `e2e.sh` 全体は `[RETDEC]` 不在で未実行 (検証 run の素材は `fl-win64` と apt の mingw のみ)。`emcc -c gui_core.c` は `[EMSDK]` 不在で `31bcd9a` では未再実行 (`6e6c9b7` 時点では OK)。Chrome E2E (wasm 経路) も未実行 (本変更は native headless の読み出しと shim 側 free 遅延のみ; wasm でも `SurfSnap` は同じコードが走るため要再確認)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `e2e.sh` 全体 (native_e2e + wasm Chrome) の再実行 | wasm 側で `SurfSnap` / 遅延 free が回帰を起こさないことが未確認 | #489 にコメント (`oc_artifacts: fl-win64 toolchain-emsdk toolchain-retdec` で再実行依頼) |
| wasm 経路で host が free 済み旧画素を stale に読む可能性 | 画面の一瞬のずれ (crash なし) | #489 にコメント (別チケット候補; 本修正で保留 free の仕組みは入ったので、wasm でも旧画素は `head` 通過まで有効と推論 (未実測)) |

## 13. GUI-13 (#615): gui_wasm.sh の wasm ビルドへ gui_ft.c + libfreetype を組込み + ブラウザ上テキスト描画 e2e
既知類型との関係 (DEFECTS.md): 該当なし (lift 欠陥ではなく shim のリンク構成)。検証起点 commit: 4890d60 (HEAD)。c4b293d (e2e.sh の FT 順序修正) の再確認は `REPORT_APPENDIX_B.md` §13 追補。
- **組込み**: `lift/gui_wasm.sh` が既定で `src/gui_ft.c` + `src/gui_ft_wasm.c` + wasm32 `-pthread` libfreetype (`lift/ft_wasm_lib.sh` = `shared/oss/freetype/build.sh` 産の patch 済みツリーを再 make; `ft_wasm.sh` と同方式) をリンク。`GUI_NO_FT=1` で従来ビルド。`gui_ft_add_face` / `gui_ft_add_alias` / `_gui_hostcall_ptr` / `_malloc` / `_free` を export。**host (JS) が `gui_ft_add_face` を呼ぶまで engine は未登録 = 8×8 のまま** (既存 e2e の経路は無変更)。
- **フォントは同梱しない・sha256 検証・遅延取得**: face は `gui_ft_register_lazy` で登録され、最初の `open` で host call `GUI_HC_FETCH_FONT` (=5) を発行 → host (`src/runtime/gui_fonts.ts` `createFontLoader`) が url から取得 → **manifest の sha256 を検証** → wasm heap へ置いて ptr/size を返す。検証失敗・取得失敗は null → shim が LOG に残して 8×8 フォールバック。manifest 台帳は `test/fonts.tsv` (file/url/sha256/face) で、`test/fetch_fonts.sh` (native 用取得) とブラウザ e2e が同じ sha256 を使う。ブラウザ配信は `loadFont` の取得元 (url) を #22 (VFS) の遅延取得に差し替える口 (本 PR では e2e サーバの `/fonts/*` = 未接続, 下記未解決 (1))。
- **ブラウザ e2e** (`bash tools/gui/test/text_wasm_e2e.sh`; RetDec 不要): RetDec lift の代わりに C ゲスト `test/text_wasm_app.c` (GUI-9 と共有の `test/text_scene.inc` のシーンを WM_PAINT で描き BitBlt、metrics 表を LOG へ) を `gui_wasm.sh` で wasm 化 → headless Chrome (CDP, COOP/COEP, SAB) → フォント遅延取得 → OffscreenCanvas 読み戻しと CDP スクリーンショットを独立オラクルと比較 (`e2e/text_e2e.mjs`, `e2e/cdp_lib.mjs`)。
- **実測 (コミット済み HEAD 4890d60 をクリーン worktree へ展開、`build/` 削除から = libfreetype wasm32 `-pthread` 再ビルド込み; 4 vCPU, emcc 6.0.12, Chrome headless; n=3)**: 実時間 13.76–14.53 s (14.53 / 13.76 / 13.78)、開始時 load average (1 分) 1.61 / 2.08 / 2.28、3/3 rc=0。
  - 本番: 読み戻し vs オラクル **差 0 px**、スクリーンショット vs オラクル **差 0 px** (320×120 = 38400 px 中、オラクル前景 3826 px)、metrics 30 行・差 0。フォント 2 本 (Open Sans 147528 B / Barlow 104068 B) が sha256 ok で遅延取得されたことを host event で確認。wasm サイズ 624736 B (`GUI_NO_FT=1`: 109105 B)。
  - ネガコン (全て不一致で拒否): N1 face 未登録 (8×8) 4558 px + metrics 30 行差 / N2 manifest の sha256 不正 → `sha256 mismatch` + shim の 8×8 フォールバック LOG、2409 px 差 / N3 別フォントを sha256 整合のまま配信 1944 px 差 / N4 オラクル 1 画素 + 1 metrics セル破壊 → 1 px・1 行差。さらにオラクルを別フォントで作り直すと `text_e2e.mjs` は rc=1、wasm ディレクトリ不在は rc=2 (どちらも exit 0 にならない)。
  - 8×8 回帰: face 未登録の FT 組込みビルドと `GUI_NO_FT=1` の従来ビルドの出力が読み戻し 0 px・スクリーンショット 0 px・metrics 行一致 (前景 2179 px の非自明シーン)。対照 N5: FreeType 出力と 8×8 基準は 4558 px 差 (区別できる)。 併せて: `text_golden.sh` (シーンを `text_scene.inc` へ共通化後) ALL PASS (前景 3826 px・差 0、ネガコン 4/4)、`ft_wasm.sh` PASS (TOTAL edd537e3b390f846)、`grow` / `reach` 各 variant も `gui_wasm.sh` でビルド成功、`hostcall_help.test.mjs` 3/3 pass、`tsc --noEmit` エラー 0。 **範囲外**: lift 済み PE (`gui_app.c` 経由の既存 `e2e.sh` 全体) の再実行は本 run に RetDec が無く未実施 (`e2e.sh` に 4b として本 e2e を追加済み)。実 FL の face/サイズ (#174)・実 Windows フォントとの一致は主張しない。
- **未解決** (起票先付き):
  | 未解決 | 影響 | 起票先 |
  |---|---|---|
  | (1) `loadFont` の取得元を #22 (VFS) の遅延取得 (Range/OPFS/R2) へ結線 | 本番ブラウザへの配信は未接続 (e2e は同一オリジン `/fonts/*`) | #660 (GUI-14) |
  | (2) `bash tools/gui/e2e.sh` 全体 (PE lift 層込み) の安定した ALL PASS 確認 | af8ba9cc / 0cbc5651 で 1 回 PASS を確認、flake 残存 (`selftest_wrapped` は単独 30 回で 9/30 失敗・7ead604 実測、付録 §13 追補)。1 回 PASS は flake 解消の根拠にならない | flake の `gui_headless.c` 起票は PM 判断 (未起票) |
  | (3) 実 FL の face/サイズ確定・alias 実値 | alias は e2e 用 (Segoe UI/Tahoma → Open Sans) のみ | #174 (GUI-3)・付録 B §11 の未解決 (2) |

## 14. GUI-7 (#183): popup/tooltip・非クライアント領域・無効領域複数矩形・DPI (FL 非依存部)
既知類型との関係 (DEFECTS.md): 該当なし (shim の意味論)。ただし lift 済み WndProc の `WM_NCCALCSIZE` の `NCCALCSIZE_PARAMS*` lParam が int32 切り詰めで取りこぼされ native で SEGV (§4-6 の既知要件の再発)。修正は shim 側で送信中ポインタを保持。
- FL 非依存部は実装・検証済み (golden 28,000 px 差 0、nc_golden asserts 26/0、ネガコン 3 本拒否)。FL の窓種別に基づく部分は未達 → PR は `Refs #183`。
- 全文・実測 (HEAD `63cfe0f` の e2e ALL PASS 191 s、`67d5cb7` / `87c20fc` の記録を含む) は `REPORT_APPENDIX_C.md` §14。
- 未解決 (起票先): FL 実窓種別の確定 (#174 / #564 / #565 後に #183 へ追記)・Chrome 上の NC/popup 描画 (#183)・メニュー (#175)。
## 15. GUI-8 (#184): e2e の agent-browser 載せ替え・長時間ストレス・Firefox 取込み
全文と実測 (検証起点 コード HEAD `3bd220d3`): `REPORT_GUI8.md`。結論: e2e は `tools/e2e` ドライバ (agent-browser / puppeteer-core) 経由で `bash tools/gui/e2e.sh` ALL PASS (golden 差 0、203 s)、50,000 フレームのストレスで drop 0・メモリ増加なし・surface gen 不変、ネガコン 3 本は不合格を検出。Firefox は #127 の結果を `PROTOCOL.md §13` に取込み (Safari・Firefox 実描画は未測定)。

## 16. GUI-5 (#181) 続き: e2e.sh 全体 ALL PASS と wasm shim 全体の SIMD/scalar 比較

本文は `REPORT_APPENDIX.md` §16 (250 行上限による分割)。検証起点 HEAD `fcd564bc` (`tools/gui/src`・`include` は `e11701db` と同一)。結論: RetDec 付き `bash tools/gui/e2e.sh` は ALL PASS (rc=0, 185 s, 1 回。同 HEAD の 1 回目は 6/6 の依存欠落で rc=2)。1/6 selftest は `e11701db` で 20 回連続 PASS (ASan 0 件)。修正前 src の有効 7 回中 2 回の UAF (#489) は、修正後の連続試行で発火していない。wbench (`bash tools/gui/test/wbench.sh 5`): rc=0, 19 s, v128 simd=831 / scalar=0 (測定値は付録 §16 §2)。

## 17. GUI-6 (#182): 入力品質 (キー配列 / IME / タッチ・ジェスチャ / Pointer Lock・ClipCursor)
既知類型との関係: 該当なし (lift 欠陥ではなく shim/host の意味論; `docs/DEFECTS.md` D1a〜D18 に該当なし)。
- **結論**: 仕様・検証表・ネガコン実測・範囲外と起票先の詳細は付録 [REPORT_APPENDIX.md §14](REPORT_APPENDIX.md)。FL 非依存で CDP 再現できる範囲 (US/DE/FR 配列・IME・タッチ/ZOOM・Pointer Lock/ClipCursor) を実装し、`tools/gui/input/e2e.sh` と selftest・ネガコンで検証。WM_POINTER*・実機確認は未実施のため PR は `Refs #182`。

## 18. GUI-15 (#740): e2e.sh の ASan heap-use-after-free (blit_surf / surf_free race) の再検証
既知類型との関係 (DEFECTS.md): 該当なし (native headless host と shim の free タイミング競合)。原因と修正は §12 (GUI-12 / #489, 実装 `6e6c9b7`, closed) が正本。本節は修正が HEAD に入った後の再現試行の記録。検証 HEAD `f0d65f32` (`6e6c9b7` を含む)。
- **selftest 単体** (`bash tools/gui/test/selftest.sh`, ASan): 1 回目 rc 0 / 504 passed / 14.97 s。直列 30 回 rc 0 (UAF 0/30, 開始 load 2.02)。
- **負荷下** (8 並列 × 8 回 = 64 回, 終了時 load 13.59): rc 0 の失敗 0/64、UAF 0/64。
- **ネガコン** `bash tools/gui/test/gui12_race.sh 50 30` (所要 4m36s, load 1.76/2.19): 修正版 exit≠0 0/50 (UAF 0) / `-DGUI12_NEGCTL_IMMEDIATE_FREE` 30/30 が UAF → PASS。
- **未達 (#740 受入条件)**: (1) 修正前の ASan ログを用いた再現は本 run で得られず (修正後 94 回で発火せず)。(2) `e2e.sh` の n≥10 連続 rc 0 は未実施 (RetDec・emsdk を含む全体実行で 1 回約 3 分のため本 run の 60 分内に 10 回は収まらない)。(3) ネガコンは `gui12_race.sh` の 30/30 で代替確認済み。
- **未解決 (起票先)**: #740 のまま、`e2e.sh` 全体の n≥10 連続 PASS と、修正前 ASan ログの再取得。PM 判断で #740 を #489 の重複として閉じるか決める。

## 19. GUI-15 (#740) 続き: e2e.sh 連続実行 (HEAD 29f63707)
- 連続 8 回 (run1〜8): rc 0 が 7 回、rc 1 が 1 回 (run8) → **連続 8 回中 7 回 PASS**。単発 1 回 (rc 0) を加えた 9 回では **9 回中 8 回 PASS**。
- run8 の失敗: step 6h の CDP timeout (`Runtime.evaluate`)、ASan の UAF 0 件。別経路と推定 (未検証)。
- 所要・load の run ごとの値は未記録 (生ログ未保存)。min–max は未確定。
- 残件 (n≥10 連続 rc 0・6h 原因・修正前 ASan ログ) は #1217 (GUI-20) へ移管。
- 再現: `bash tools/gui/e2e.sh` (連続は for ループ)。

## 21. WIN-23 (#3460): FL 非依存の W 版 Win32 テストゲストと headless surface 統計
既知類型との関係: `docs/DEFECTS.md` D11 (PE VA リテラルの切り捨て) と同族 (絶対 VA の即値が幅を失う)。機構は別で、D11 は wasm32 のポインタ幅、本件は RetDec 出力の関数 VA 即値 `0x400011f8` (正しくは `0x1400011f8`) が native x86_64 で SEGV する。D11 の変種として扱うか新規類型にするかは子 #3508 で判断 (測定は付録 W)。
- 結論: headless surface 統計 (`gui_hl_stats`: w×h・非背景・厳密な色数・sha256 (RGB 3 バイト列)) と単体テスト 21/21 PASS を実測。W 版ゲスト `gui_app_w.c` は lift まで通るが、lift 後の関数 VA の 32 bit 切り詰めで native が SEGV し、オラクル比較・wasm 比較は未達 (子 issue)。全文は [REPORT_APPENDIX_W.md](REPORT_APPENDIX_W.md)。
