# PROTOCOL.md — Win32 GUI shim ABI と SAB プロトコル

対象: FL (lift 済み FLEngine) が呼ぶ user32/gdi32 を、ブラウザ (OffscreenCanvas + 共有メモリ + 入力イベントキュー) に載せる shim の仕様。
正本コード: `include/gui_proto.h` (レイアウト), `src/gui_core.c` (user32), `src/gui_gdi.c` (gdi32), `src/runtime/gui*.ts` (host)。
再現: `bash tools/gui/e2e.sh` (REPORT.md 参照)。

## 1. 構成とスレッドモデル

```
 ┌──────────── browser main thread ───────────┐        ┌──────── render worker (module Worker) ────────┐
 │ gui.ts  GuiHost                            │        │ gui_worker.ts                                  │
 │  <canvas> ─transferControlToOffscreen──────┼───────▶│  OffscreenCanvas 2D  (putImageData)           │
 │  DOM pointer/wheel/key/focus ─┐            │        │  out ring 消費 (Atomics.waitAsync, no poll)   │
 │  cursor/title/ack 受信 ◀──────┼─postMessage┼────────│  PRESENT: BGRA→RGBA 変換 → 描画 → ack          │
 └───────────────────────────────┼────────────┘        └───────────────▲───────────────────────────────┘
                     input ring  │ (SPSC: main→wasm)                    │ out ring (MPSC→SPSC: wasm→worker)
 ┌───────────────────────────────▼──────────────────────────────────────┴───────────────────────────────┐
 │ wasm linear memory = SharedArrayBuffer  ── GuiShared (静的 1 領域, 100,672 B, gui_shared_ptr()) ──      │
 │ wasm GUI thread (PROXY_TO_PTHREAD の main pthread): lifted FL UI ─▶ shim(user32/gdi32) ─▶ surface(BGRA)  │
 │ 他 FL スレッド: PostMessage / SendMessage(同期要求) / memory DC 描画可 (内部 spinlock)                    │
 └──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```
- **GUI thread** (= ウィンドウを作ったスレッド) が唯一のメッセージ消費者。`GetMessage` は `doorbell` を futex wait (timeout = 次タイマ期限)。
  ブロック直前に必ず `surf_flush()` で未 present の dirty を吐く。`PeekMessage` は空なら flush して FALSE。描画しっぱなしでも 16ms 毎に自動 flush。
- **main thread** は絶対にブロックしない。入力は `pointer*`/`wheel`/`keydown|keyup` から入力リングへ書き `doorbell` を ++ して `Atomics.notify`。
- **render worker** は出力リングのみ消費。待機は `Atomics.waitAsync(out.tail)`、wasm 側は push のたび `futex_wake(out.tail)`。
- 起動順序: wasm の `main` は `host_ready` が立つまで futex wait (30 秒で fail-fast)。host は screen 寸法を書き worker を起動後に `host_ready=1`+notify。
- 必須環境: crossOriginIsolated (COOP same-origin + COEP require-corp)。非 pthread (ST) ビルドでは `GetMessage` がブロックできないため fail-fast。

## 2. 共有メモリレイアウト (`GuiShared`, byte offset)

| offset | 内容 | 書き手 |
|---|---|---|
| 0x000 | magic `0x31495547`("GUI1"), version=1, total_size, **host_ready**, screen_w, screen_h, dpr_x100, flags, **doorbell**(0x20), exited, exit_code | host/shim |
| 0x040 | cursor_x, cursor_y, buttons(bit0 L,1 R,2 M), mods(1 shift,2 ctrl,4 alt,8 meta), focused, page_visible, **key_down[8]**(0x60, VK ビットマップ) | host (shim は読むだけ) |
| 0x080 | stats: in_pushed, in_dropped, in_consumed, out_pushed, out_full_waits, present_seq, present_done_seq, msgs_dispatched, timer_fires, paints, frames_flushed | 混在 (§7) |
| 0x0C0 | in_ring {head(consumer=shim), tail(producer=host)} | |
| 0x100 | out_ring {head(consumer=worker), tail(producer=shim)} | |
| 0x140 | surface 表 16 × 128 B | shim |
| 0x940 | in_recs[1024][8×u32] (32 KiB) | host |
| 0x8940 | out_recs[2048][8×u32] (64 KiB) | shim |
| 0x18940 | 終端 (= 100,672 B) | |

surface エントリ (128 B): `state, visible, x, y, w, h, stride, pixels(wasm addr), z, gen, wseq, _rsv[5], title[64]`。`wseq` は seqlock (§4 の 6)。
`pixels` は **BGRA32 top-down** (Windows DIB と同じ B,G,R,A バイト順)。リサイズ/再確保で `gen++` かつ `SURF_CHANGE`。
JS ミラー: `src/runtime/gui_proto.ts` (`OFF`, `W`, `S`)。C 側 `_Static_assert` で全オフセット固定、wasm と JS の total_size 不一致は worker 起動時に throw。
メモリ成長対策: worker は処理毎に `memory.buffer` を取り直す (`WebAssembly.Memory` を init で受領)。静的領域とリングは成長で動かない。

## 3. リング

全リング共通: レコード 32 B (8×u32)、サイズ 2 の冪、`head`/`tail` は単調増加 u32 (`idx & (N-1)`)、満杯 = `tail-head ≥ N`。
- **in ring** (host→shim, N=1024, SPSC): host は `rec` 書込 → `tail` を seq-cst store → `in_pushed++` → `doorbell++`+notify。満杯時 host は drop し `in_dropped++` (E2E は 0 を要求)。
- **out ring** (shim→worker, N=2048): push は shim 内 spinlock (複数 FL スレッドが LOG/PRESENT を出し得るため MPSC→SPSC)。
  満杯なら `out_full_waits++` して `head` を futex wait (headless 時は drain コールバック同期)。worker は処理後 `head` を store+notify。
- メモリ順序: レコード/ピクセルの plain store → `tail` の seq-cst atomic store (release) / 消費側 atomic load (acquire)。wasm threads の atomic は seq-cst。

### 3.1 入力レコード `w0..w7 = type, surf, x, y, a, b, time_ms, seq`
| type | 値 | a / b |
|---|---|---|
| MOUSE_MOVE 1 | x,y = desktop 座標 (CSS px) | a = buttons |
| MOUSE_DOWN 2 / UP 3 | 同上 | a = DOM button(0 L,1 M,2 R), b = mods |
| WHEEL 4 | | a = delta(i32, 120/notch, 上向き正), b = mods |
| KEY_DOWN 5 / KEY_UP 6 | | a = VK, b = bit0 repeat, bit1 ext, bits8..15 scancode, bits16..19 mods |
| CHAR 7 | | a = UTF-16 code unit |
| FOCUS 8 | | a = 1/0 |
| SCREEN 9 | x=w, y=h | desktop リサイズ |
| CLOSE 10 | w1 = surf | ユーザが閉じた → WM_CLOSE |

host は **レコード書込の前に** 共有 pointer 状態 (cursor/buttons/mods/key_down) を更新する (GetCursorPos/GetAsyncKeyState は即時値、`GetKeyState` はメッセージ処理時点の値)。

### 3.2 出力コマンド `w0 = cmd, w1 = surf, w2..w7`
| cmd | 意味 |
|---|---|
| SURF_CREATE 1 / DESTROY 2 / CHANGE 3 | surface 表変化 → worker は表を再読込し **desktop 全面再合成** (z 昇順) |
| PRESENT 4 | `l,t,r,b` (surface client 座標・半開区間), w6 = frame seq。dirty のみ転送 |
| FRAME_END 5 | w1 = seq。worker は `present_done_seq = seq` を store+notify し main へ `frame` 通知 (E2E の同期点) |
| SET_TITLE 6 / SET_CURSOR 7 | title は surf 表の UTF-8、cursor は IDC_* 数値 → CSS cursor |
| LOG 8 | w1 = len(0..24) \| bit8=行末, w2..w7 = 24 B payload (`OutputDebugString` の運搬路。E2E の同期点) |
| EXIT 9 | w1 = exit code。fail-fast は 0xFA11 |

## 4. Present プロトコル (フレーム)
1. 描画先がウィンドウ DC (surface) のとき、プリミティブごとに `surf_dirty(surf, rect)` が surface 単位の dirty 外接矩形に合流。
2. **flush 契機**: EndPaint / ReleaseDC / GdiFlush / `WM_PAINT` dispatch 後 / `GetMessage` ブロック直前 / PeekMessage 空 / 前回 flush から 16 ms 超 (try_get 入口)。
3. flush は dirty のある surface ごとに `PRESENT`、最後に `FRAME_END(seq)` を 1 個 (`present_seq++`)。
4. worker (`gui_renderer.ts`) の既定は従来経路: PRESENT を受けるたび即描画 (BGRA→RGBA, alpha=255 固定, `putImageData`) し、重なる **より前面の surface** の交差領域を再描画して前後関係を維持。
5. ack: `present_done_seq == present_seq` が「全フレーム描画済み」。
6. **GUI-4 (#180) の present 拡張** (`GuiPresentOptions`; 既定は 4. の従来経路で挙動不変。`GuiHost.attach({present})` / `/?gui=render-selftest&backend=webgl2&sync=raf&seqlock=1` で選択):
   - `backend: "webgl2"`: surface ごとの RGBA8 テクスチャへ dirty 矩形を `texSubImage2D` (共有メモリ view を UNPACK_ROW_LENGTH/SKIP_* 付きで直接。拒否するブラウザは非共有バッファへ行コピーに自動降格)、fragment の swizzle `.bgr` で BGRA→RGB、alpha=1.0。合成は整数 `texelFetch` の quad 描画 (補間なし)。`"auto"` は WebGL2 不可なら 2D。
   - **dirty 複数矩形**: 1 フレーム (PRESENT 群 + FRAME_END) の矩形を surface ごとに `mergeRects` (`gui_dirty.ts`) で併合 (重なり/接触は必ず、離れたものは面積増 ≤ 25% のとき、surface あたり最大 8 個)。shim が PRESENT を複数発行すればそのまま複数矩形で転送される (shim 側の dirty は現状 surface あたり単一外接矩形のまま = 未達)。
   - `sync: "raf"`: **ingest** (FRAME_END 時点で surface 画素を読む = GL はテクスチャ転送) と **commit** (画面反映 + ack) を分離し、commit のみ `requestAnimationFrame` に同期 (複数 FRAME_END は 1 回の commit に集約し最新 seq を ack)。rAF が来ない場合は `rafTimeoutMs` (既定 100 ms) のタイマで commit。
   - **seqlock** (`seqlock: true`): `GuiSurface.wseq` は奇数 = guest が flush 後に画素を書込み中/書込み済み、偶数 = 静止。shim は window surface へ描く直前 (`dc_tgt`) に偶数→奇数、`surf_flush` が PRESENT を push する前に全 live surface を奇数→偶数にする。host は `wseq` を読出しの前後で比較し、奇数または不一致なら読出しを破棄して矩形を持ち越し、4 ms 後に再試行する。`staleMs` (既定 100 ms) を超えて連続で読めない場合のみ強制的に読む (飢餓回避; `stats.seqForced`)。
     **限界**: これは tear の「検出と再試行」で、guest が書込みを止めない限り読めない (back buffer による snapshot isolation ではない)。JS の `Atomics.load` と非 atomic な画素読出しの順序保証はエンジン実装 (SC atomic の full fence) 依存。
- 想定ホットパス: FL の `BitBlt/StretchDIBits(window DC)` → 1 フレーム 1 PRESENT (外接矩形)。

## 5. lift ABI (RetDec 産コード ↔ shim)
- **全 API は `int64_t NAME(int64_t a0, ...)`**。lifter 出力が `int32_t`/ポインタ/`int64_t` を混ぜて呼ぶため、戻り値・引数とも 64bit 整数に統一
  (`build/gui_api.h` を gen_api.py が生成、lifted C は `#include "gui_api.h"`)。`BOOL`/`bool` 戻りは 0/1 (RetDec は BOOL を `bool` と型付け)。
- **ポインタ** は wasm32 では 32bit アドレスを zero-extend した値。**構造体は Win64 レイアウト** (`include/gui_win32.h`: `WWNDCLASS` 72 B, `WMSG` 48 B, `WPAINTSTRUCT` 72 B, BITMAPINFOHEADER 40 B …)。構造体内ポインタ/ハンドルは 8 B。
- **IS_INTRESOURCE**: 文字列/名前引数が `< 0x10000` なら atom/ID。よって wasm は **`-sGLOBAL_BASE=1048576`** 必須 (既定 1024 だと静的文字列 "GuiPoC" が atom 扱いされ RegisterClass が fail-fast した: 実測)。
- **ハンドル** は 31bit 内 (`gen7<<24 | type4<<20 | idx20`)。lifter が `(int32_t)` へ潰す箇所 (実測: `DefWindowProcA(..., (int32_t)wParam, (int32_t)lParam)`) でも壊れない。型/世代違いは NULL 扱い。
- **WNDPROC / TIMERPROC / ENUMPROC** は `int64_t (*)(int64_t,int64_t,int64_t,int64_t)` で `call_indirect`。RetDec は未使用引数を落とすので
  `gui_lift_post.py --wndproc NAME` が 4 引数へ正規化 (署名違いは wasm trap になる)。
- **関数ポインタ値**: lifted コードは `lpfnWndProc` に **関数の VA 整数** (例 `g2 = 0x14000177b`) を格納する。`gui_register_fnmap({VA,fn}[])` に登録した表で解決し、
  表に無く `≥0x10000` ならそのまま関数ポインタ値 (wasm の table index / shim 自身の関数) として扱う。`< 0x10000` は fail-fast。
- **A/W**: 内部は UTF-8。W は UTF-16→UTF-8 変換。`DefWindowProc` は両対応。
- **未実装 API** は `gen_api.py` が mingw-w64 ヘッダ (`-aux-info`) から arity を取り **fail-fast stub** を生成: stderr に `FAIL-FAST: unimplemented Win32 API: <name>`、
  `exit_code=0xFA11`, `exited=2`, `EXIT` コマンドを host に送ってから `abort()`。静かな no-op は意図的に避ける (例外は §9 の benign 一覧)。

## 6. ウィンドウ/座標モデル
- **desktop** = canvas の CSS px 領域 (`screen_w×screen_h`)。**top-level window = 1 surface (BGRA)**。非クライアント領域 (枠/タイトル) は持たない (client == window)。
  子ウィンドウは親 surface 内の矩形で、独自 surface を持たない。`GetDC(child)` は親 surface の部分領域+クリップを返す。
- 可視領域クリップ: 自身の client ∩ 祖先 client。`WS_CLIPSIBLINGS` なら前面兄弟を除外、`WS_CLIPCHILDREN` なら可視子を除外 (Windows 準拠)。
- z-order: 兄弟は連結リスト (末尾が最前面)。top-level は desktop の子で、activate で最前面へ。surface の `z` は host の合成順。
- 入力のヒットテスト: top-level を前面から、子を前面から再帰。mouse capture 中は capture window へ (座標はその client 系)。`WM_SETCURSOR` を同期送出。
- `WM_MOUSEMOVE` は同一 hwnd への連続を合体。`CS_DBLCLKS` なら 500ms/4px で `*DBLCLK` を合成。

## 7. メッセージキュー規則 (GetMessage/PeekMessage)
取り出し順: 他スレッド SendMessage 要求 → 入力リング変換 → 投函キュー (FIFO, 8192) → `WM_QUIT` → `WM_PAINT` (無効領域のある可視窓, 前面から) → `WM_TIMER` (期限最古)。
- `SetTimer`: 最小 10 ms (USER_TIMER_MINIMUM)、期限後に `now+interval` へ再設定。0 hwnd は新 ID を返す。タイマ proc 付きは Dispatch で直接呼ぶ。
- `InvalidateRect` は **単一外接矩形** に合流 (複数矩形 region は未対応)。`BeginPaint` が `WM_ERASEBKGND` を送り、`DefWindowProc` が class brush (COLOR_x+1 / HBRUSH) で塗る。
- `CreateWindowEx`: `WM_NCCREATE`→`WM_CREATE` (CREATESTRUCT を Win64 レイアウトで構築)→(WS_VISIBLE) `WM_SHOWWINDOW`,`WM_SIZE`,`WM_MOVE`,`WM_ACTIVATE`,`WM_SETFOCUS`。
- `DestroyWindow`: `WM_DESTROY` → 子を再帰破棄 → `WM_NCDESTROY`。キャプチャ/フォーカス/タイマ/props を解放。
- 他スレッドからの `SendMessage` は要求キューに積み GUI スレッドの pump 完了を futex 待ち (native selftest で検証)。`PostMessage` は任意スレッドから可。

## 8. GDI モデル (`src/gui_gdi.c`)
- 描画先は常に BGRA32: window DC → top-level surface、memory DC → 選択ビットマップ。`CreateDIBSection` は **32bpp BI_RGB/BITFIELDS のみ** (biHeight<0=top-down / >0=bottom-up を保持。`ppvBits` は wasm 内実アドレス)。
  `CreateCompatibleBitmap`/`CreateBitmap(32bpp)` は top-down。それ以外の bpp/圧縮/file mapping は fail-fast。
- 転送: `BitBlt`/`StretchBlt`/`PatBlt`/`StretchDIBits`/`SetDIBitsToDevice`/`AlphaBlend`/`GetDIBits`/`SetDIBits`。
  ROP: SRCCOPY(等倍は行 memmove・alpha ごと転送), SRCPAINT, SRCAND, SRCINVERT, SRCERASE, NOTSRCCOPY, NOTSRCERASE, MERGECOPY, PATCOPY, PATINVERT, PATPAINT, DSTINVERT, BLACKNESS, WHITENESS。他は fail-fast。
  拡縮は **nearest (`src = floor(i*sw/dw)`)**、dest の負幅/負高は反転、source の負 extent は fail-fast。同一バッファ重複は行/列順を反転して memmove 相当。
  プリミティブ/ROP 経路の alpha は 0xFF 固定 (SRCCOPY のみ alpha 保存)。`AlphaBlend` は 255 除算の丸め付き (premultiplied `AC_SRC_ALPHA` / 定数 alpha)。
- プリミティブ: `FillRect`/`FrameRect`/`Rectangle`/`MoveToEx`+`LineTo` (Bresenham・終点除外・太線は正方スタンプ)/`SetPixel(V)`/`GetPixel`。ペンは SOLID/NULL のみ (他は fail-fast)。ブラシは solid/hollow。
- テキスト: **内蔵 8×8 ビットマップフォント** (font8x8, Public Domain, ASCII のみ。ET/DT/ExtTextOut/DrawText/GetTextExtent/GetTextMetrics は一貫した固定幅 8px)。FL は自前 FreeType 描画が主なので GDI テキストは保険。
- クリップ: `RL` (矩形リスト) 実装の region (`CreateRectRgn/CombineRgn(AND/OR/DIFF/XOR/COPY)/OffsetRgn`)、`SelectClipRgn/ExtSelectClipRgn/IntersectClipRect/ExcludeClipRect/GetClipBox`、`SaveDC/RestoreDC`、`SetWindowOrgEx/SetViewportOrgEx` (MM_TEXT のみ)。
- ROP2: COPYPEN, XORPEN, NOT, BLACK, WHITE, NOP, MASKPEN, MERGEPEN, NOTCOPYPEN。

## 9. 制限・既知の逸脱 (fail-fast ではなく近似で通すもの)
`SetWindowRgn`/`NotifyWinEvent`/`LockWindowUpdate`/`ShowOwnedPopups`/`AttachThreadInput`/`IsDialogMessage`/`SetThreadDpiAwarenessContext` は no-op、`SelectPalette`/`RealizePalette` は常に 32bpp 真色扱い、
`SetCursorPos` は共有 cursor 値のみ更新 (Pointer Lock 連携は未実装)、`GetDeviceCaps(RASTERCAPS)` は RC_PALETTE なし、`MsgWaitForMultipleObjects` は `nCount==0` のみ、`GetDC(NULL)`(スクリーン DC) は fail-fast。
フック (`SetWindowsHookEx` 系) は §11 の範囲で配送 (CAB-159)。ImageList_*/FlatSB_*/uxtheme BufferedPaint/IME/印刷/メタファイル/wgl は stub (IMPORTS.md)。

## 10. FL lift 接続メモ (RetDec 実測知見, PE 実験 3 本から)
1. **stack 上の構造体フィールド store が落ちる** (`WNDCLASSA wc; RECT r` 等。API の struct 引数型が付くと 2 番目以降の stack var が消える)。静的大域に置けば全 store が残る。
2. **大域構造体は 1 フィールド 1 グローバル `gN` に分割される** → `__pe_image` へ `#define gN (*(T*)(__pe_image+off))` で連続化 (`gui_lift_post.py`)。イメージ内ポインタ (.reloc DIR64) は m11_data_gen と同規則の再配置表で起動時に補正 (`lift/pe_image.py`, GUI-12 #566)。
3. **`GetMessage(...)>0` が壊れる**: 戻りが `bool` 型付けされ `if (!v1 != v1)` (常に真) に化ける → メッセージループが即終了。真偽値判定 `while (GetMessage(..))` なら正しく lift される。
4. `keybuf[n++]=c` が `g38 = &g39` (定数畳み込み誤り) に化ける例あり (`n=nkeys; ...; nkeys=n+1` に書き直すと正しい)。
5. WndProc の引数は未使用だと落ちる (`WndProc(a1)` 等) → `--wndproc` で 4 引数正規化。関数ポインタは VA 整数 → fnmap 登録。
6. `(int32_t)lParam` に潰される箇所がある → 64bit 値を lParam で渡す API は 31bit 内ポインタ前提 (wasm の >2GB ヒープは注意)。

## 11. P1 拡張 (CAB-159) の意味論と制約

実装: `src/gui_core_ext.inc` (user32; `gui_core.c` 末尾で #include) と `src/gui_gdi.c` 末尾 (gdi32/user32 描画系)。テスト: `test/selftest_p1.inc` (231 assertion)。

- **クリップボード (7)**: プロセス内ストア。Open 中のみ Empty/Set/Get/Enum 可、他スレッド Open 中は `ERROR_ACCESS_DENIED`、Empty で旧所有者へ `WM_DESTROYCLIPBOARD`、
  `SetClipboardData(fmt, NULL)` は遅延レンダリング (Get 時に所有者へ `WM_RENDERFORMAT`)。データは HGLOBAL 値をそのまま保持し内容は解釈しない (CF_TEXT↔CF_UNICODETEXT の自動合成なし)。
  **ブラウザとの橋渡しは未実装** (host/プロトコル変更が要るため): async Clipboard API (`navigator.clipboard.readText/writeText`) は**ユーザジェスチャ + 権限**が必要で非同期。
  設計案 = ① copy: `CloseClipboard` 時に CF_UNICODETEXT を LOG 系の新 `GUI_CMD_CLIP_SET` で host へ送り host が `writeText` (keydown 等のジェスチャ内で最大 1 回)、
  ② paste: host が `paste` イベントの本文を新 `GUI_IN_CLIP_TEXT` で共有領域へ置き、次の `OpenClipboard` で shim が HGLOBAL 化して Store に積む。同期 API は「直近の paste イベントのスナップショット」を返す形になる (FL が任意タイミングで読む場合は古い可能性)。
- **フック (3)**: 配送は `WH_KEYBOARD`(2)/`WH_MOUSE`(7) (入力→キュー前、戻り≠0 で破棄)・`WH_GETMESSAGE`(3)・`WH_CALLWNDPROC`(4)/`WH_CALLWNDPROCRET`(12) (SendMessage 経路のみ)。
  それ以外の有効 id (-1..14) は登録のみ (呼ばれない)。グローバル/他プロセスのフックは存在しない (`dwThreadId`/`hMod` は無視)。新しいフックほど先、`CallNextHookEx` で次へ。呼出中の解除は遅延回収。
- **モニタ/DPI (7)**: 単一仮想モニタ (HMONITOR=0x7B000001, 矩形 = canvas 寸法)。`EnumDisplaySettingsW` は 1 モード (32bpp/60Hz)。DPI は `SetThreadDpiHostingBehavior` の値保持のみ (描画スケールは GUI-7)。`GetGuiResources` はハンドル表の種別別カウンタ (GDI はストック除く、PEAK は実ピーク)。
- **キャレット (4 + 前倒し `CreateCaret`)**: システムで 1 個。表示 = client DC への `DSTINVERT` (点滅なし)。所有ウィンドウ破棄でキャレット破棄。WM_PAINT で上書きされた場合は次の Show/Hide/移動まで反転状態が不整合になり得る (近似)。
- **入力 (7)**: `SendInput` は host リングを介さず `translate_input` へ直接注入 (キー/Unicode/スキャンコード/マウス相対・絶対 (0..65535→画面)・ボタン・ホイール)。`buttons/mods/cursor` は host 所有の領域を shim も更新し、次の実入力で host 値に上書きされる。`ToUnicode`/`ToAscii` は US 配列 (デッドキー・AltGr なし)。キー名/スキャンコード表は set 1 US。HKL は 1 個 (0x04090409)。
- **リソース**: `LoadStringW` (RT_STRING) / `LoadBitmapW` (RT_BITMAP, 24/32bpp のみ) は `gui_set_resource_provider()` で結合側が供給する (shimx の FindResource/LoadResource 相当を CAB-173 で接続)。未設定/未発見は 0 + `ERROR_RESOURCE_NAME_NOT_FOUND`(1814)/`ERROR_RESOURCE_TYPE_NOT_FOUND`(1813)。
- **GDI**: `DrawEdge` は矩形のみ (`BF_DIAGONAL` は fail-fast; SOFT は近似)。`DrawFrameControl` は形状簡略 (ボタン/チェック/ラジオ/スクロール矢印/キャプション/メニュー記号)。`DrawFocusRect` は (x+y)偶数画素の XOR (2 回で復帰)。
  `CreateDCW("DISPLAY")` は画面寸法を返す互換 DC (描画は破棄; 画面直描きは不可)。`GetClipRgn` は論理座標、`GetRandomRgn` は SYSRGN=画面座標 / CLIPRGN=DC 原点基準。`GetRegionData` は RDH_RECTANGLES を (top,left) 順で返す。
  アイコン/カーソルは標準 (擬似ハンドル) のみ: 32x32 のプレースホルダ画像を生成して `GetIconInfo`/`DrawIcon[Ex]` が使う (実画像資源・`CreateIconIndirect`・`LoadImage` は GUI-2)。
