# m11 IR の GUI declare ↔ shim exports 突合表 (自動生成)

生成: `python3 tools/gui/integ/gen_adapt.py` / 入力 IR: `integ/fixtures/boot_final_gui_declares.ll (m11 boot_final.ll の GUI declare 抜粋)` (10669 B, sha1 03a45205b0)。shim 側は `build/gui_reach_tab.json` (gen_api.py 産; 実装 312 + stub 159)。

## 1. 要約

| 区分 | 件数 | 意味 |
|---|---|---|
| IR が declare する GUI 系 import 名 | 177 | FLEngine の GUI import 428 名のうち m11 IR(boot 到達閉包)に現れるもの |
| (a) 実装済み・adapter 生成可 | 153 | `gui_adapt_w32.c` の wrapper で署名一致 |
| (b) fail-fast stub・adapter 生成可 | 24 | 署名は合うが到達すると `FAIL-FAST: unimplemented Win32 API` で停止 (**実到達 API ログで優先度見直し対象**) |
| (c) 署名不一致 (adapter 不能) | 0 | 下記変換方針で **0 件**であることが完了条件 |
| (d) shim に存在しない | 0 | gen_api.py の arity 表(mingw ヘッダ+手動表)が全 import を網羅しているため 0 の想定 |
| IR 未 declare (まだ lift 閉包に現れない) | 251 | 実結合で lift 範囲が広がると declare される。同じ adapter 生成で追従 |

## 2. 変換方針 (署名不一致 0 の根拠)

shim は全 API を `int64_t NAME(int64_t...)` (lift ABI) で公開、m11 IR は wasm32 型 (`ptr`=i32、WPARAM/LPARAM/LONG_PTR=i32、`i1`/`i16`/`%tagPOINT` 値渡しも出現)。wasm-ld は同名で型が違う関数を結合すると trap thunk を作るため、**shim 本体を `gui_impl_<Name>` へ改名し、IR 署名の adapter が公開名を定義**する (`build/gui_rename.h` を shim TU に `-include`)。

| IR 型 | 引数の int64 化 | 戻り値 |
|---|---|---|
| ptr | zero-extend (shim は 2^31 未満のハンドル/ポインタを発行、< 0x10000 は atom/MAKEINTRESOURCE) | 32bit zero-extend 値を ptr に |
| i32 | sign-extend (`GWL_STYLE=-16` 等が負で来る) | 下位 32bit |
| i16/i8/i1 | zero-extend | 切詰め / `!=0` |
| i64 | そのまま (`POINT` 詰め値など) | そのまま |
| 8 byte 以下 struct 値渡し | wasm 側は要素ごとの scalar 引数 -> adapter が 1 個の int64 に詰める (x64 ABI 相当; `WindowFromPoint`) | - |

コールバック (`WNDPROC`/`TIMERPROC`/`EnumWindowsProc`) の呼出は `gui_set_icall_hook()` で m11 の `m11_icall` (VA -> trampoline, 8×u64 統一署名) に委譲するので、lifted 側 WNDPROC の署名が 4 引数でなくても `call_indirect` 署名不一致は起きない (INTEGRATION.md §3)。

## 3. 到達しうる fail-fast stub (b) — 24 件

| API | xref | IR 署名 | 備考 |
|---|---|---|---|
| DeleteMenu | 11 | `i1(ptr, i32, i32)` |  |
| GetPaletteEntries | 9 | `i32(ptr, i32, i32, ptr)` |  |
| GetSystemPaletteEntries | 6 | `i32(ptr, i32, i32, ptr)` |  |
| DrawMenuBar | 5 | `i1(ptr)` |  |
| CreateHalftonePalette | 4 | `ptr(ptr)` |  |
| GetDIBColorTable | 4 | `i32(ptr, i32, i32, ptr)` |  |
| GetSystemMenu | 4 | `ptr(ptr, i1)` | i1 |
| SetDIBColorTable | 4 | `i32(ptr, i32, i32, ptr)` |  |
| GetBitmapBits | 3 | `i32(ptr, i32, ptr)` |  |
| BufferedPaintInit | 2 | `i32()` |  |
| CharLowerW | 2 | `ptr(ptr)` |  |
| CheckMenuItem | 2 | `i32(ptr, i32, i32)` |  |
| CreateBrushIndirect | 2 | `ptr(ptr)` |  |
| CreateIcon | 2 | `ptr(ptr, i32, i32, i8, i8, ptr, ptr)` |  |
| CreateIconIndirect | 2 | `ptr(ptr)` |  |
| EnumFontFamiliesExW | 2 | `i32(ptr, ptr, ptr, i32, i32)` |  |
| GetDCOrgEx | 2 | `i1(ptr, ptr)` |  |
| GetDpiForMonitor | 2 | `i32(i64, i64, ptr, ptr)` |  |
| GetMenuItemInfoW | 2 | `i1(ptr, i32, i1, ptr)` | i1 |
| GetProcessDpiAwareness | 2 | `i32(ptr, ptr)` |  |
| IsProcessDPIAware | 2 | `i1()` |  |
| LoadImageW | 2 | `ptr(ptr, ptr, i32, i32, i32, i32)` |  |
| SetMenuItemInfoW | 2 | `i1(ptr, i32, i1, ptr)` | i1 |
| WTSRegisterSessionNotification | 2 | `i1(ptr, i32)` |  |

## 4. 全突合表 (xref 降順; stub を先頭)

| API | 区分 | shim | P | IR 署名 | 備考 |
|---|---|---|---|---|---|
| DeleteMenu | b | stub | P2 | `i1(ptr, i32, i32)` |  |
| GetPaletteEntries | b | stub | P2 | `i32(ptr, i32, i32, ptr)` |  |
| GetSystemPaletteEntries | b | stub | P2 | `i32(ptr, i32, i32, ptr)` |  |
| DrawMenuBar | b | stub | P2 | `i1(ptr)` |  |
| CreateHalftonePalette | b | stub | P2 | `ptr(ptr)` |  |
| GetDIBColorTable | b | stub | P2 | `i32(ptr, i32, i32, ptr)` |  |
| GetSystemMenu | b | stub | P2 | `ptr(ptr, i1)` | i1 |
| SetDIBColorTable | b | stub | P2 | `i32(ptr, i32, i32, ptr)` |  |
| GetBitmapBits | b | stub | P2 | `i32(ptr, i32, ptr)` |  |
| BufferedPaintInit | b | stub | P3 | `i32()` |  |
| CharLowerW | b | stub | P2 | `ptr(ptr)` |  |
| CheckMenuItem | b | stub | P3 | `i32(ptr, i32, i32)` |  |
| CreateBrushIndirect | b | stub | P2 | `ptr(ptr)` |  |
| CreateIcon | b | stub | P2 | `ptr(ptr, i32, i32, i8, i8, ptr, ptr)` |  |
| CreateIconIndirect | b | stub | P2 | `ptr(ptr)` |  |
| EnumFontFamiliesExW | b | stub | P2 | `i32(ptr, ptr, ptr, i32, i32)` |  |
| GetDCOrgEx | b | stub | P3 | `i1(ptr, ptr)` |  |
| GetDpiForMonitor | b | stub | P2 | `i32(i64, i64, ptr, ptr)` |  |
| GetMenuItemInfoW | b | stub | P3 | `i1(ptr, i32, i1, ptr)` | i1 |
| GetProcessDpiAwareness | b | stub | P2 | `i32(ptr, ptr)` |  |
| IsProcessDPIAware | b | stub | P2 | `i1()` |  |
| LoadImageW | b | stub | P2 | `ptr(ptr, ptr, i32, i32, i32, i32)` |  |
| SetMenuItemInfoW | b | stub | P3 | `i1(ptr, i32, i1, ptr)` | i1 |
| WTSRegisterSessionNotification | b | stub | P3 | `i1(ptr, i32)` |  |
| SendMessageW | a | impl | P0 | `i32(ptr, i32, i32, i32)` |  |
| PostMessageW | a | impl | P0 | `i1(ptr, i32, i32, i32)` |  |
| DeleteObject | a | impl | P0 | `i1(ptr)` |  |
| SelectObject | a | impl | P0 | `ptr(ptr, ptr)` |  |
| ReleaseDC | a | impl | P0 | `i32(ptr, ptr)` |  |
| GetCursorPos | a | impl | P0 | `i1(ptr)` |  |
| GetWindowLongPtrW | a | impl | P0 | `i32(ptr, i32)` |  |
| GetCapture | a | impl | P0 | `ptr()` |  |
| GetSystemMetrics | a | impl | P0 | `i32(i32)` |  |
| DeleteDC | a | impl | P0 | `i1(ptr)` |  |
| SetWindowPos | a | impl | P0 | `i1(ptr, ptr, i32, i32, i32, i32, i32)` |  |
| BitBlt | a | impl | P0 | `i1(ptr, i32, i32, i32, i32, ptr, i32, i32, i32)` |  |
| SetWindowLongPtrW | a | impl | P0 | `i32(ptr, i32, i32)` |  |
| SetBkColor | a | impl | P0 | `i32(ptr, i32)` |  |
| SetCursor | a | impl | P0 | `ptr(ptr)` |  |
| SelectPalette | a | impl | P1 | `ptr(ptr, ptr, i1)` | i1 |
| GetDC | a | impl | P0 | `ptr(ptr)` |  |
| IntersectRect | a | impl | P0 | `i1(ptr, ptr, ptr)` |  |
| IsWindowVisible | a | impl | P0 | `i1(ptr)` |  |
| GetDeviceCaps | a | impl | P0 | `i32(ptr, i32)` |  |
| SetFocus | a | impl | P0 | `ptr(ptr)` |  |
| CreateCompatibleDC | a | impl | P0 | `ptr(ptr)` |  |
| GetWindowRect | a | impl | P0 | `i1(ptr, ptr)` |  |
| ReleaseCapture | a | impl | P0 | `i1()` |  |
| OffsetRect | a | impl | P0 | `i1(ptr, i32, i32)` |  |
| ShowWindow | a | impl | P0 | `i1(ptr, i32)` |  |
| RegisterClipboardFormatW | a | impl | P0 | `i32(ptr)` |  |
| GetObjectW | a | impl | P0 | `i32(ptr, i32, ptr)` |  |
| SetTextColor | a | impl | P0 | `i32(ptr, i32)` |  |
| MapWindowPoints | a | impl | P0 | `i32(ptr, ptr, ptr, i32)` |  |
| SystemParametersInfoW | a | impl | P0 | `i1(i32, i32, ptr, i32)` |  |
| GetKeyState | a | impl | P0 | `i16(i32)` |  |
| PeekMessageW | a | impl | P0 | `i1(ptr, ptr, i32, i32, i32)` |  |
| SetWindowOrgEx | a | impl | P0 | `i1(ptr, i32, i32, ptr)` |  |
| CombineRgn | a | impl | P0 | `i32(ptr, ptr, ptr, i32)` |  |
| FillRect | a | impl | P0 | `i32(ptr, ptr, ptr)` |  |
| GetParent | a | impl | P0 | `ptr(ptr)` |  |
| InvalidateRect | a | impl | P0 | `i1(ptr, ptr, i1)` | i1 |
| RedrawWindow | a | impl | P0 | `i1(ptr, ptr, ptr, i32)` |  |
| SetActiveWindow | a | impl | P0 | `ptr(ptr)` |  |
| GetWindowPlacement | a | impl | P1 | `i1(ptr, ptr)` |  |
| EndPaint | a | impl | P0 | `i1(ptr, ptr)` |  |
| RealizePalette | a | impl | P2 | `i32(ptr)` |  |
| CreateRectRgn | a | impl | P1 | `ptr(i32, i32, i32, i32)` |  |
| CreateRectRgnIndirect | a | impl | P1 | `ptr(ptr)` |  |
| DispatchMessageW | a | impl | P0 | `i32(ptr)` |  |
| OffsetRgn | a | impl | P1 | `i32(ptr, i32, i32)` |  |
| GetFocus | a | impl | P0 | `ptr()` |  |
| GetWindowThreadProcessId | a | impl | P0 | `i32(ptr, ptr)` |  |
| SetTimer | a | impl | P0 | `i32(ptr, i32, i32, ptr)` |  |
| StretchBlt | a | impl | P0 | `i1(ptr, i32, i32, i32, i32, ptr, i32, i32, i32, i32, i32)` |  |
| IsWindowEnabled | a | impl | P0 | `i1(ptr)` |  |
| RegisterWindowMessageW | a | impl | P0 | `i32(ptr)` |  |
| BeginPaint | a | impl | P0 | `ptr(ptr, ptr)` |  |
| ExcludeClipRect | a | impl | P1 | `i32(ptr, i32, i32, i32, i32)` |  |
| GetClassInfoW | a | impl | P0 | `i1(ptr, ptr, ptr)` |  |
| SelectClipRgn | a | impl | P1 | `i32(ptr, ptr)` |  |
| SetPhysicalCursorPos | a | impl | P0 | `i1(i32, i32)` |  |
| CharNextW | a | impl | P1 | `ptr(ptr)` |  |
| GetClientRect | a | impl | P0 | `i1(ptr, ptr)` |  |
| GetStockObject | a | impl | P1 | `ptr(i32)` |  |
| GetTextMetricsW | a | impl | P1 | `i1(ptr, ptr)` |  |
| LoadStringW | a | impl | P1 | `i32(ptr, i32, ptr, i32)` |  |
| UnregisterClassW | a | impl | P0 | `i1(ptr, ptr)` |  |
| CreatePalette | a | impl | P2 | `ptr(ptr)` |  |
| CreateWindowExW | a | impl | P0 | `ptr(i32, ptr, ptr, i32, i32, i32, i32, i32, ptr, ptr, ptr, ptr)` |  |
| GetActiveWindow | a | impl | P0 | `ptr()` |  |
| GetDIBits | a | impl | P0 | `i32(ptr, ptr, i32, i32, ptr, ptr, i32)` |  |
| IntersectClipRect | a | impl | P1 | `i32(ptr, i32, i32, i32, i32)` |  |
| UnionRect | a | impl | P1 | `i1(ptr, ptr, ptr)` |  |
| CreateBitmap | a | impl | P0 | `ptr(i32, i32, i32, i32, ptr)` |  |
| CreateCompatibleBitmap | a | impl | P0 | `ptr(ptr, i32, i32)` |  |
| DestroyWindow | a | impl | P0 | `i1(ptr)` |  |
| GetClipBox | a | impl | P1 | `i32(ptr, ptr)` |  |
| IsIconic | a | impl | P0 | `i1(ptr)` |  |
| MessageBoxW | a | impl | P1 | `i32(ptr, ptr, ptr, i32)` |  |
| RegisterClassW | a | impl | P0 | `i16(ptr)` |  |
| CreateFontIndirectW | a | impl | P1 | `ptr(ptr)` |  |
| GdiFlush | a | impl | P0 | `i1()` |  |
| IsWindow | a | impl | P0 | `i1(ptr)` |  |
| LoadCursorW | a | impl | P1 | `ptr(ptr, ptr)` |  |
| MapVirtualKeyW | a | impl | P0 | `i32(i32, i32)` |  |
| PatBlt | a | impl | P0 | `i1(ptr, i32, i32, i32, i32, i32)` |  |
| SetClipboardData | a | impl | P1 | `ptr(i32, ptr)` |  |
| SetWindowPlacement | a | impl | P1 | `i1(ptr, ptr)` |  |
| SetWindowsHookExW | a | impl | P1 | `ptr(i32, ptr, ptr, i32)` |  |
| TranslateMessage | a | impl | P0 | `i1(ptr)` |  |
| UnhookWindowsHookEx | a | impl | P1 | `i1(ptr)` |  |
| CreateDIBSection | a | impl | P0 | `ptr(ptr, ptr, i32, ptr, ptr, i32)` |  |
| CreateSolidBrush | a | impl | P1 | `ptr(i32)` |  |
| FindWindowW | a | impl | P1 | `ptr(ptr, ptr)` |  |
| GetMonitorInfoW | a | impl | P1 | `i1(i64, ptr)` |  |
| LoadIconW | a | impl | P1 | `ptr(ptr, ptr)` |  |
| PostQuitMessage | a | impl | P0 | `void(i32)` |  |
| SetPropW | a | impl | P1 | `i1(ptr, ptr, ptr)` |  |
| EnumThreadWindows | a | impl | P1 | `i1(i32, ptr, i32)` |  |
| GetIconInfo | a | impl | P1 | `i1(ptr, ptr)` |  |
| GetLastActivePopup | a | impl | P1 | `ptr(ptr)` |  |
| MonitorFromWindow | a | impl | P1 | `i64(ptr, i32)` |  |
| SetRectRgn | a | impl | P1 | `i1(ptr, i32, i32, i32, i32)` |  |
| CreateDIBitmap | a | impl | P1 | `ptr(ptr, ptr, i32, ptr, ptr, i32)` |  |
| DestroyCursor | a | impl | P1 | `i1(ptr)` |  |
| EnumWindows | a | impl | P1 | `i1(ptr, i32)` |  |
| ExtSelectClipRgn | a | impl | P1 | `i32(ptr, ptr, i32)` |  |
| GetPhysicalCursorPos | a | impl | P0 | `i1(ptr)` |  |
| GetPropW | a | impl | P1 | `ptr(ptr, ptr)` |  |
| GetWindowOrgEx | a | impl | P1 | `i1(ptr, ptr)` |  |
| IsWindowUnicode | a | impl | P1 | `i1(ptr)` |  |
| KillTimer | a | impl | P0 | `i1(ptr, i32)` |  |
| RemovePropW | a | impl | P1 | `ptr(ptr, ptr)` |  |
| ValidateRect | a | impl | P0 | `i1(ptr, ptr)` |  |
| WindowFromPoint | a | impl | P0 | `ptr(%tagPOINT)` | struct 値渡し -> int64 詰め |
| BeginDeferWindowPos | a | impl | P1 | `ptr(i32)` |  |
| CharLowerBuffW | a | impl | P1 | `i32(ptr, i32)` |  |
| CharUpperBuffW | a | impl | P1 | `i32(ptr, i32)` |  |
| DeferWindowPos | a | impl | P1 | `ptr(ptr, ptr, ptr, i32, i32, i32, i32, i32)` |  |
| EnableWindow | a | impl | P0 | `i1(ptr, i1)` | i1 |
| EndDeferWindowPos | a | impl | P1 | `i1(ptr)` |  |
| EnumChildWindows | a | impl | P1 | `i1(ptr, ptr, i32)` |  |
| EqualRgn | a | impl | P1 | `i1(ptr, ptr)` |  |
| GetClipCursor | a | impl | P0 | `i1(ptr)` |  |
| GetClipboardFormatNameW | a | impl | P1 | `i32(i32, ptr, i32)` |  |
| GetCursor | a | impl | P1 | `ptr()` |  |
| GetKeyboardLayout | a | impl | P0 | `ptr(i32)` |  |
| GetRandomRgn | a | impl | P1 | `i32(ptr, ptr, i32)` |  |
| GetRgnBox | a | impl | P1 | `i32(ptr, ptr)` |  |
| GetUpdateRgn | a | impl | P1 | `i32(ptr, ptr, i1)` | i1 |
| LPtoDP | a | impl | P1 | `i1(ptr, ptr, i32)` |  |
| MsgWaitForMultipleObjects | a | impl | P1 | `i32(i32, ptr, i1, i32, i32)` | i1 |
| SetClassLongPtrW | a | impl | P1 | `i32(ptr, i32, i32)` |  |
| ShowOwnedPopups | a | impl | P1 | `i1(ptr, i1)` | i1 |
| CharUpperW | a | impl | P1 | `ptr(ptr)` |  |
| EnumDisplayMonitors | a | impl | P1 | `i1(ptr, ptr, ptr, i32)` |  |
| EnumDisplaySettingsW | a | impl | P1 | `i1(ptr, i32, ptr)` |  |
| GetClipRgn | a | impl | P1 | `i32(ptr, ptr)` |  |
| GetRegionData | a | impl | P1 | `i32(ptr, i32, ptr)` |  |
| RectInRegion | a | impl | P1 | `i1(ptr, ptr)` |  |
| ScrollWindowEx | a | impl | P1 | `i32(ptr, i32, i32, ptr, ptr, ptr, ptr, i32)` |  |
| ShowCursor | a | impl | P1 | `i32(i1)` | i1 |
| WaitMessage | a | impl | P0 | `i1()` |  |
| DispatchMessageA | a | impl | P0 | `i32(ptr)` |  |
| GetCursorInfo | a | impl | P1 | `i1(ptr)` |  |
| GetKeyNameTextW | a | impl | P1 | `i32(i32, ptr, i32)` |  |
| GetSysColor | a | impl | P2 | `i32(i32)` |  |
| GetWindowTextW | a | impl | P0 | `i32(ptr, ptr, i32)` |  |
| InvalidateRgn | a | impl | P0 | `i1(ptr, ptr, i1)` | i1 |
| IsDialogMessageA | a | impl | P3 | `i1(ptr, ptr)` |  |
| IsDialogMessageW | a | impl | P3 | `i1(ptr, ptr)` |  |
| MessageBoxA | a | impl | P2 | `i32(ptr, ptr, ptr, i32)` |  |
| SendMessageA | a | impl | P0 | `i32(ptr, i32, i32, i32)` |  |
| SetDIBitsToDevice | a | impl | P0 | `i32(ptr, i32, i32, i32, i32, i32, i32, i32, i32, ptr, ptr, i32)` |  |
| TranslateMDISysAccel | a | impl | P3 | `i1(ptr, ptr)` |  |
| ValidateRgn | a | impl | P2 | `i1(ptr, ptr)` |  |

## 5. IR 未 declare の GUI import (251 名; 実結合で出現しうる)

実装済み 116 / stub 135。stub の内訳 (P 別): P0=0, P1=0, P2=58, P3=77
