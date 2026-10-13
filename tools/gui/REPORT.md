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
| GUI-4 | CAB-179 / #180 | 部分達成 (§9; FL 非依存部は実装・e2e 済み、FL 依存部は GUI-3 待ち) | WebGL2 present・dirty 複数矩形・rAF 同期・seqlock (現行 CPU 経路は 1080p 2.2〜3.8 ms/frame で予算内) |
| GUI-6 | CAB-181 | Backlog (blockedBy GUI-3) | Pointer Lock による SetCursorPos、IME、タッチ、キーボード配列 (実機確認はユーザ依頼の可能性) |
| GUI-8 | CAB-183 | Todo | e2e を agent-browser 載せ替え・数万フレーム耐久/リーク検査・Firefox (CAB-126 依存) |

## 8. 再現
```
bash tools/gui/e2e.sh            # 全層 (17〜24 s): 解析→API 面生成→golden→selftest→native lift→PE lift→emcc→tsc→Chrome E2E ×3
bash tools/gui/test/selftest.sh  # native 単体のみ
python3 tools/gui/analysis/gui_imports.py && python3 tools/gui/gen_api.py   # import 面 / IMPORTS.md 再生成 (入力 tools/m2/work/block00031_PE.bin)
```
前提: x86_64-w64-mingw32-gcc, RetDec (`[RETDEC]`), Emscripten (`[EMSDK]`・同梱 node 24 を PATH に使用), google-chrome, gcc。

## 9. GUI-4 (#180): WebGL2 present / dirty 複数矩形 / rAF 同期 / seqlock
既知類型との関係: 該当なし (lift 欠陥ではなく present 経路の設計。`docs/DEFECTS.md` への追加類型なし)。検証起点 commit: コードは `88efd49` (レビュー指摘 A・B・軽微 2 の修正後; present e2e 30 run・seqlock・tearing・golden・auto 降格の数値は全てこの HEAD・クリーン tree での実測)。frame time 表だけは修正前の `09e3db9` での実測 (bench は再測定していない; `88efd49` は seqlock 経路・staged 転送の関数分割 `stage()`/`uploadStaged()`・auto 判定のみを変え、seqlock off の GL 経路の処理は同一)。

### 結論
- **FL 非依存の範囲を実装し e2e 済み・FL 依存の範囲は未達** (受入条件は満たしていない → PR は `Refs #180`)。実装: `src/runtime/gui_present_gl.ts` (WebGL2: BGRA を `texSubImage2D` + fragment swizzle)・`gui_dirty.ts` (surface 内複数矩形の併合)・`gui_renderer.ts` (`GuiPresentOptions`: `backend` / `sync` / `seqlock`)・shim の seqlock 書込み側 (`GuiSurface.wseq`, `gui_core.c` / `gui_gdi.c`)。既定は従来経路 (2D + 即時) で挙動不変。仕様は [PROTOCOL.md §4](PROTOCOL.md)。
- **golden 画素一致 (差 0)**: 模擬 guest で GuiShared を駆動 (wasm / lift 不要)。同一の操作列 46 step (生成・z 前面化・表示切替・移動・リサイズ・破棄/再生成・1〜4 個/step の dirty 矩形 (隣接を含む)・alpha 乱数) を 4 方式 (従来 CPU・WebGL2 direct+即時・WebGL2 staged+rAF+seqlock・CPU+rAF+seqlock) へ流し、**毎 step 640×360 px (u32 全件) を独立 oracle** (バイト単位 painter's algorithm) と比較: **4 方式とも 46 step × 230,400 px = 10,598,400 px で差 0**。CDP スクリーンショット (ブラウザ合成後) 4 面 × 230,400 px も差 0。
- **実 GPU の frame time は未測** (CI の headless Chrome は SwiftShader = ソフトウェア GL)。この環境の比較表を下に示すが、**GPU 化の効果の判断材料にはならない** (下記 解釈)。
- **seqlock**: 書込み中 surface は読まず直前の整合フレームを保ち、静止後に再試行して新フレームを出す (決定的テスト: 書込み中 4 方式 + 読出し後・検証前に書込みが始まる経路 4 方式)。WebGL2 は staging へ行コピー → `stable()` で検証 → 成功時のみ `texSubImage2D` (検証前にテクスチャへ書かない; seqlock off は従来どおり共有メモリを直接転送)。確率的 tearing 試験 (WebGL2 + rAF, 90 frame, 30 run): off で tear 発生 4〜9 件 / **on で 0 件 (30 run 全て; 強制読出し 0)**。ただし**検出と再試行であり snapshot isolation ではない**。

### 検証 (`bash tools/gui/present/e2e.sh`; `tools/gui/e2e.sh` の 6f/6 にも組込み)
| 検査 | 結果 (`bash tools/gui/present/e2e.sh` bench 省略を 30 run: **30 PASS / 0 FAIL**) | 陰性対照 |
|---|---|---|
| golden 4 方式 × 46 step × 230,400 px | 30 run × 4 方式 = 120 件全て差 0 | present せず 1 px 書換え → 差 **1** px を検出 / fragment swizzle を `.rgb` へ壊す → 差 10,557,172 px (FAIL) |
| スクリーンショット 4 面 | 差 0 | swizzle 破壊で差 229,492 px (FAIL) |
| 複数矩形併合 (WebGL2 direct) | 68〜89 PRESENT → 54〜70 矩形 (30 run 全てで矩形数 < PRESENT 数; PRESENT 数は ingest のまとまり方で run ごとに変わる) | `mergeRects` 単体 7 件 (性質テスト: 400 ケースで入力全画素が出力に含まれる = ビットマップ検算) |
| rAF 同期 (staged+raf) | 30 run 全てで rAF 起動 = flush 数 (29 run は 46、1 run は 47 flush)・即時 0・タイマ救済 0。判定は「rAF 起動 ≥ flush − max(1, 10%)・即時 0」 (レビューで旧 `timer === 0` の厳密一致が 19 run 中 1 run `timer=1` で FAIL したため緩和) | 未実施 (許容内のタイマ救済を再現する手段なし。`rafFlushes > 0` と即時 0 の条件は維持) |
| seqlock 決定的 (書込み中) | gl/cpu × 即時/rAF 4 方式 × 30 run: 書込み中は旧フレーム維持 (deferred 1〜5)・静止後 10〜23 ms で新フレーム・forced 0。**検証の前から `wseq` が奇数の経路だけ**を通る | seqlock off は書込み中に新フレームを読む (保護なし; 30 run 全て) |
| seqlock 決定的 (検証中の書込み開始) | 4 方式 × 30 run: surface を読んだ直後・検証の前に guest の書込み開始 (`wseq` 偶→奇) を注入 → 注入 1 回・retries 1・deferred 1〜5・読んだ内容は表示されず旧フレーム維持・静止後 11〜24 ms で新フレーム・forced 0 | 修正前 (`96cf00b` の renderer/GL に同じテストを適用): **gl 即時・gl rAF の 2 方式は新フレームを表示 (= 検証前に `texSubImage2D` していた) で FAIL**、cpu 2 方式は修正前も OK |
| `backend: auto` の降格 | 正常 → webgl2 / シェーダ不可 → 2d へ降格して readback 可 / プローブ後に描画先だけ失敗 → `[gui] 2D fallback unavailable: ...` の明示エラー (30 run 同一) | 修正前: シェーダ不可で `TypeError: Cannot set properties of null (setting 'fillStyle')` |
| tearing 確率的 | 下記 (30 run 全て「on の発生 ≤ forced」成立) | seqlock off (WebGL2) で tear 発生 4〜9 件 (30 run; 全 run で off ≥ 4 > on = 0) |
- **全体 `bash tools/gui/e2e.sh` (`88efd49`, クリーン tree, 4 CPU, RetDec・emsdk・mingw あり): ALL PASS, 55.7 s** (1 run; 6f/6 の present e2e の load は 2.20 → 2.02)。内訳: native `selftest` 319 passed / 0 failed・native lift golden EXACT MATCH・`reach_test` 11 / `adapt_test` 28 passed・wasm の golden EXACT MATCH (固定メモリ・ALLOW_MEMORY_GROWTH)・fail-fast OK・reach log 36 API・sigprobe `signature mismatch=0` (陰性対照 177)・present e2e ALL PASS。他に `tsc --noEmit`・`pnpm build`・`node tools/runtime/gui_e2e.mjs` (ALL OK, 4.2 s) も `88efd49` で確認。
- **tearing 試験の定義**: guest worker が 1280×720 全面を 1 色/フレームで行ごとに描画 (行あたり 8 µs の busy、書込みは busy だけで 5.76 ms/フレーム以上、周期 16 ms、90 frame、seqlock 書込み側プロトコルに従う)。描画器は rAF 同期。毎 flush 後に左端 1 列を読戻し、行ごとに色が混在すれば tear。「発生件数」= 整合→tear への遷移回数。WebGL2: seqlock off 4〜9 件、on 0 件 (30 run; on の `forced` は 30 run 全て 0、`deferred` 19〜34、`seqRetries` 0〜4)。検査は「on の発生件数 ≤ forced」 (強制読出し = 飢餓回避は整合を諦めるので tear を許容する)。CPU は ingest が FRAME_END 直後に完了するため off でも 0 件 (対照にならない; on の deferred は 2〜94)。on の deferred が多いのは検証用の `readPixels` が worker を GPU 同期で止めて読出しが遅れるため (検証ハーネス由来)。
- **修正前の欠陥と経路 (レビュー指摘 A)**: 修正前 (`96cf00b`) の WebGL2 は `stable()` の中で `texSubImage2D` していた。**読み始めた後・検証の前に guest が書込みを始める**と (`seqRetries` に計上) 検証は失敗して矩形を持ち越すが、テクスチャには旧フレームと新フレームの行が混在したまま残り、`ingest()` は転送の成否によらず `drawRects` に入れたので次の rAF commit がその混在テクスチャを描画した (4 ms 後の再試行が先に直せば表に出ない = 確率的)。レビュー実測では on でも forced=0 のまま tear 発生 1 件 (19 run 中 1 run)。修正後は staging へコピー → 検証 → 成功時のみ転送とし、持ち越した矩形は `drawRects` に入れず再試行が成功してから描く (その間は直前の整合フレームが見える)。**「seqlock 決定的 (書込み中)」は検証の前から奇数の経路しか通らない**ので、この経路は「検証中の書込み開始」の決定的テストと確率的 tearing 試験で見る。direct 転送 (共有メモリ view を直接 `texSubImage2D`) の利点は seqlock 有効時のみ失われる (staging へのコピーが 1 回入る)。
- 設計判断: rAF 同期は **ingest (FRAME_END 時点で surface を読む) と commit (rAF で画面反映 + ack) の分離**にした。当初の「FRAME_END を rAF まで遅延して読む」実装は読出しが次フレームの guest 書込みと重なり、CPU 経路 (seqlock off) でも tear 状態の flush が 87 回中 19 回出た。分離後は 86〜87 回中 0 回 (3 run)。

### frame time (headless Chrome 154.0.8037.97, **SwiftShader = 実 GPU ではない**, 4 CPU)
`ms/frame`: flush(submit) = worker 内 CPU 時間 (`GuiRenderer.stats.flushMs / flushes`: 読出し・変換・転送・描画発行); +GPU sync = flush + 1 px `readPixels` による GPU 完了待ち; wall = guest の PRESENT push → ack。各セル = 60 frame × 3 rep × 3 run の **min–max** (n=9)。load average (1 分) は run 開始→終了で 0.68→1.71 / 1.71→2.60 / 2.40→2.63。
| size | dirty | 方式 | flush(submit) | +GPU sync | wall | rect/frame |
|---|---|---|---|---|---|---|
| 1280×720 | 全面 | CPU putImageData | 2.09–2.13 | — | 2.16–2.21 | 1 |
| 1280×720 | 全面 | WebGL2 direct | 0.35–0.58 | 5.67–8.21 | 6.99–9.96 | 1 |
| 1280×720 | 25% | CPU / WebGL2 direct | 0.54–0.56 / 0.07–0.15 | — / 1.74–2.68 | 0.58–0.63 / 1.11–2.54 | 1 |
| 1280×720 | 8 矩形 (128×72) | CPU / WebGL2 direct | 0.19–0.20 / 0.06–0.07 | — / 0.81–1.59 | 0.22–0.27 / 0.11–0.97 | 8 |
| 1920×1080 | 全面 | CPU putImageData | 4.72–4.85 | — | 4.90–5.04 | 1 |
| 1920×1080 | 全面 | WebGL2 direct | 0.75–1.00 | 12.67–13.05 | 17.51–18.25 | 1 |
| 1920×1080 | 全面 | WebGL2 staged | 1.51–1.70 | 13.29–13.52 | 18.16–18.76 | 1 |
| 1920×1080 | 25% | CPU / WebGL2 direct | 1.19–1.35 / 0.29–0.64 | — / 3.70–6.71 | 1.26–1.54 / 0.60–7.68 | 1 |
| 1920×1080 | 64×64 | CPU / WebGL2 direct | 0.01–0.02 / 0.01–0.03 | — / 0.32–0.41 | 0.04–0.06 / 0.05–0.06 | 1 |
| 1920×1080 | 8 矩形 (128×72) | CPU / WebGL2 direct | 0.19–0.20 / 0.04–0.08 | — / 1.37–1.47 | 0.22–0.26 / 0.10–0.17 | 8 |
- 全 24 セル (2 サイズ × 4 dirty × 3 方式: CPU / WebGL2 direct / WebGL2 staged) の完全表は `present_e2e.mjs` の出力 (`bash tools/gui/present/e2e.sh`)。
- **解釈**: GL 経路は worker の CPU 時間 (flush) を CPU 経路の 1/2〜1/6 に減らす (1080p 全面 4.72–4.85→0.75–1.00 ms、1080p 25% 1.19–1.35→0.29–0.64 ms)。一方 SwiftShader では GPU 完了まで 12.7–13.1 ms かかり CPU 経路より遅い (ソフトウェア GL がテクスチャ転送と quad 描画を CPU で行うため)。**実 GPU での完了時間・消費電力・合成コストは未測**で、GUI-4 の「必要性を実測で判断」は実 GPU ブラウザ + 実 FL 負荷が要る。`direct` (共有メモリ view を直接 `texSubImage2D`) は Chrome 154 で許容され、`staged` (行コピー) より全面更新の flush が 0.3〜0.9 ms 小さい。他ブラウザで拒否された場合は `staged` に自動降格 (コード上; 他ブラウザでは未検証)。
- 従来 CPU 経路の数値 (1080p 全面 4.72–4.85 ms) は §3 の旧実測 (2.2〜3.8 ms) と異なる: §3 は別環境・合成画像の変換ループ計測で、本表は `GuiRenderer` の flush を CI runner (4 CPU, load 0.7〜2.6) で測ったもの。両者は直接比較しない。

### 範囲外・未達
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 FLEngine 負荷 (全面再描画 + 多数 BitBlt) での frame time / 入力→表示レイテンシ | #180 完了条件の「実 FLEngine 負荷」「実 GPU の frame time 比較表」が未達 | #180 (Refs のまま open) / GUI-3 (#174) 後 |
| 実 GPU での比較 (SwiftShader のみ) | GL 化の採否判断ができない | #180 に実 GPU ブラウザでの計測を追記 (headed Chrome か実機; ユーザ依頼候補) |
| shim の dirty は surface あたり単一外接矩形のまま (host は複数 PRESENT を併合して扱える) | 離れた小領域が多い描画で転送が増える | #180 (shim 側 `g_dirty` を矩形リスト化; 要 selftest 追加) |
| seqlock は検出と再試行 (back buffer なし) | guest が連続描画だと `staleMs` (100 ms) 後に tear を許容 | #180 (surface の double buffer 化) |
| 入力→表示レイテンシ・rAF 同期の 30fps 目標 (#10) の実 FL 計測 | 同上 | #180 / #10 |
| `tools/gui/e2e.sh` 6e/6 sigprobe の `unresolved-imports=0` は **runner に `wasm-objdump` (wabt) が無く `|| true` で常に 0 になる** (本 run の出力に `wasm-objdump: command not found`)。`signature mismatch=0` と陰性対照 `mismatch=177` は有効 | 「未解決 import なし」の確認が空振り (既存の挙動; 本変更とは無関係) | #180 にコメント (runner image へ wabt を足す、または不在時に fail させる) |
| dirty 内の前面 surface 再描画が surface id 順で z 昇順ではない (`present()` / `glDrawRects()`; レビュー軽微 1) | 前面側が 2 枚以上重なると z の小さい方が上に描かれ得る (golden のシナリオでは顕在化しない; ブラウザ再現は未確認) | #180 にコメント済み (issuecomment-6136756050) |
| `bash tools/gui/e2e.sh` 0/6 の `gen_api.py` が `tools/gui/IMPORTS.md` の先頭の「自動生成・人手編集禁止」ヘッダを落として書き換える (本 run では diff を commit せず元へ戻した) | e2e を回すたびに作業ツリーが dirty になる (既存の挙動) | #180 にコメント (生成元の `gen_api.py` がヘッダを出すようにする) |
| **既存の不安定**: native `selftest` (ASan) が `gui_headless.c:blit_surf` で heap-use-after-free することがある (render thread が `surf_free` 済みの画素を読む)。変更前の `origin/main` で 3/20、本変更後 3/14 回が exit 1 (同一スタック) | `tools/gui/e2e.sh` 1/6 が 15〜21% (3/20・3/14) で FAIL しうる (本変更とは無関係) | **#489 `[GUI-12]`** (headless host の render thread と shim の free の競合; 本 run で起票) |
- 範囲: FL 非依存の模擬 guest・headless Chrome 154 のみ。Firefox / Safari、複数 `canvas`、WebGL コンテキストロスト復帰 (コードあり・未試験) は範囲外。

### 再現
```
bash tools/gui/present/e2e.sh                      # tsc → mergeRects 単体 → golden/screenshot/seqlock/tearing/bench (bench 込み 44.4–44.8 s, 3 run, `09e3db9`; PRESENT_SKIP_BENCH=1 で bench 省略 9.6–11.2 s, 30 run, `88efd49`, load 0.34–3.44)
bash tools/gui/test/selftest.sh                    # native 319 assertion (seqlock wseq の 5 件を追加)
node tools/runtime/gui_e2e.mjs                     # Vite バンドル経由 (本番 worker) で WebGL2+rAF+seqlock の render-selftest を追加
bash tools/gui/e2e.sh                              # 全体 (PE lift を含む); 要 RetDec・emsdk・mingw
```
