# 自動生成: `python3 tools/gui/analysis/gui_imports.py && python3 tools/gui/gen_api.py`

> **人手編集禁止** (生成元を直す)。本ファイルは測定・抽出結果の**単一の正本**。
> **行数目安**: 自動生成ファイルのため行数上限はなし (`docs/DOC_MAP.md` §1)。


# FL (win64 FLEngine_x64.dll) GUI 系 import と shim 優先度
自動生成: `python3 tools/gui/analysis/gui_imports.py && python3 tools/gui/gen_api.py` (入力 `tools/m2/work/block00031_PE.bin` = FLEngine_x64.dll 22,227,016 B)。

使用頻度 = `.text` の静的 xref 推定 (FF15/FF25/mov [rip+IAT] と、IAT へ jmp する thunk への E8/E9 call の件数; Ghidra 非使用の推定値)。

## 1. DLL 別 import 数 (全 795 名 / 33 DLL; うち delay-load 57)

| DLL | import 数 | xref 計 | GUI 系 |
|---|---|---|---|
| kernel32.dll | 194 | 3486 |  |
| user32.dll | 242 | 2482 | ● |
| gdi32.dll | 127 | 1159 | ● |
| ole32.dll | 30 | 292 |  |
| advapi32.dll | 15 | 217 |  |
| winmm.dll | 24 | 140 |  |
| oleaut32.dll | 19 | 110 |  |
| comctl32.dll | 30 | 102 | ● |
| shell32.dll | 25 | 89 |  |
| wininet.dll | 15 | 48 |  |
| msacm32.dll | 14 | 35 |  |
| uxtheme.dll | 5 | 23 | ● |
| crypt32.dll | 7 | 23 |  |
| imm32.dll | 7 | 21 | ● |
| propsys.dll | 5 | 16 |  |
| winspool.drv | 5 | 15 | ● |
| version.dll | 3 | 13 |  |
| imagehlp.dll | 3 | 9 |  |
| mpr.dll | 4 | 9 |  |
| api-ms-win-crt-string-l1-1-0.dll | 1 | 8 |  |
| msimg32.dll | 2 | 8 | ● |
| wintrust.dll | 1 | 5 |  |
| dsound.dll | 2 | 5 |  |
| shfolder.dll | 1 | 4 |  |
| dwmapi.dll | 2 | 4 | ● |
| opengl32.dll | 2 | 4 | ● |
| shcore.dll | 2 | 4 | ● |
| wtsapi32.dll | 2 | 4 | ● |
| oleacc.dll | 1 | 2 | ● |
| rpcrt4.dll | 1 | 2 |  |
| shlwapi.dll | 1 | 2 |  |
| windowscodecs.dll | 1 | 2 |  |
| comdlg32.dll | 2 | 2 | ● |

GUI 系 DLL (user32.dll, gdi32.dll, comctl32.dll, comdlg32.dll, opengl32.dll, uxtheme.dll, imm32.dll, msimg32.dll, dwmapi.dll, winspool.drv, oleacc.dll, wtsapi32.dll, shcore.dll) の import 合計 **429 名**: 実装済み **294** / fail-fast stub **135** / arity 不明で未生成 **0**。

## 2. 優先度定義

- **P0** 起動〜描画ループに必須 (ウィンドウ生成・メッセージポンプ・paint・DC/DIB・BitBlt/StretchDIBits)。未実装なら FL が立ち上がらない。
- **P1** 通常 UI 操作に必要 (入力状態・テキスト・クリップ/リージョン・カーソル・システム値・クリップボード)。fail-fast で段階導入。
- **P2** 周辺 (メニュー・スクロールバー・IME・ImageList・パレット・ベクタ描画・ダイアログ)。
- **P3** 当面スコープ外 (印刷・メタファイル・wgl・タッチ/ジェスチャ・Dwm/WTS)。stub のまま。

## 3.0 P0 (120 名)

| API | DLL | カテゴリ | xref | 状態 | 実到達 (GUI-3 #174) |
|---|---|---|---|---|---|
| SendMessageW | user32 | message | 219 | IMPL |  |
| PostMessageW | user32 | message | 140 | IMPL |  |
| DeleteObject | gdi32 | bitmap/blit | 136 | IMPL | ●起動/survey/probe |
| SelectObject | gdi32 | bitmap/blit | 97 | IMPL |  |
| ReleaseDC | user32 | paint | 84 | IMPL | ●起動/survey/probe |
| GetCursorPos | user32 | input | 83 | IMPL |  |
| GetWindowLongPtrW | user32 | window | 67 | IMPL |  |
| GetCapture | user32 | input | 58 | IMPL |  |
| GetSystemMetrics | user32 | system | 55 | IMPL | ●起動/survey/probe |
| DeleteDC | gdi32 | bitmap/blit | 52 | IMPL |  |
| SetWindowPos | user32 | window | 52 | IMPL |  |
| BitBlt | gdi32 | bitmap/blit | 47 | IMPL |  |
| SetWindowLongPtrW | user32 | window | 44 | IMPL | ●起動/survey/probe |
| SetBkColor | gdi32 | dc-state | 43 | IMPL |  |
| SetCursor | user32 | cursor/icon | 40 | IMPL |  |
| GetDC | user32 | paint | 37 | IMPL | ●起動/survey/probe |
| IntersectRect | user32 | util | 36 | IMPL |  |
| IsWindowVisible | user32 | window | 34 | IMPL |  |
| GetDeviceCaps | gdi32 | dc-state | 32 | IMPL | ●起動/survey/probe |
| SetFocus | user32 | input | 32 | IMPL |  |
| CreateCompatibleDC | gdi32 | bitmap/blit | 30 | IMPL |  |
| GetWindowRect | user32 | window | 30 | IMPL |  |
| ReleaseCapture | user32 | input | 30 | IMPL |  |
| OffsetRect | user32 | util | 29 | IMPL |  |
| ShowWindow | user32 | window | 29 | IMPL |  |
| RegisterClipboardFormatW | user32 | clipboard | 28 | IMPL | ●survey |
| GetObjectW | gdi32 | bitmap/blit | 27 | IMPL | ●起動/survey/probe |
| SetTextColor | gdi32 | dc-state | 27 | IMPL |  |
| DrawTextW | user32 | user-draw | 25 | IMPL |  |
| MapWindowPoints | user32 | window | 25 | IMPL |  |
| SystemParametersInfoW | user32 | system | 25 | IMPL | ●起動/survey/probe |
| DefWindowProcW | user32 | window | 23 | IMPL |  |
| SetWindowOrgEx | gdi32 | dc-state | 22 | IMPL |  |
| GetKeyState | user32 | input | 22 | IMPL |  |
| PeekMessageW | user32 | message | 22 | IMPL |  |
| CombineRgn | gdi32 | clip/region | 21 | IMPL |  |
| RestoreDC | gdi32 | dc-state | 21 | IMPL |  |
| FillRect | user32 | user-draw | 21 | IMPL |  |
| GetParent | user32 | window | 20 | IMPL |  |
| InvalidateRect | user32 | paint | 20 | IMPL |  |
| RedrawWindow | user32 | paint | 19 | IMPL |  |
| SetActiveWindow | user32 | input | 19 | IMPL |  |
| EndPaint | user32 | paint | 17 | IMPL |  |
| DispatchMessageW | user32 | message | 16 | IMPL |  |
| StretchBlt | gdi32 | bitmap/blit | 14 | IMPL |  |
| GetFocus | user32 | input | 14 | IMPL |  |
| GetWindowThreadProcessId | user32 | window | 14 | IMPL |  |
| SetTimer | user32 | message | 14 | IMPL |  |
| CallWindowProcW | user32 | window | 13 | IMPL |  |
| GetAsyncKeyState | user32 | input | 13 | IMPL |  |
| GetWindow | user32 | window | 13 | IMPL |  |
| IsWindowEnabled | user32 | window | 13 | IMPL |  |
| RegisterWindowMessageW | user32 | message | 13 | IMPL | ●起動/survey/probe |
| SetStretchBltMode | gdi32 | bitmap/blit | 12 | IMPL |  |
| BeginPaint | user32 | paint | 12 | IMPL |  |
| GetClassInfoW | user32 | window | 12 | IMPL | ●起動/survey/probe |
| SetCursorPos | user32 | input | 12 | IMPL |  |
| SetPhysicalCursorPos | user32 | input | 12 | IMPL |  |
| GetClientRect | user32 | window | 11 | IMPL |  |
| UnregisterClassW | user32 | window | 11 | IMPL | ●probe |
| GetDIBits | gdi32 | bitmap/blit | 10 | IMPL |  |
| CreateWindowExW | user32 | window | 10 | IMPL | ●起動/survey/probe |
| GetActiveWindow | user32 | input | 10 | IMPL |  |
| CreateBitmap | gdi32 | bitmap/blit | 9 | IMPL |  |
| CreateCompatibleBitmap | gdi32 | bitmap/blit | 9 | IMPL |  |
| DestroyWindow | user32 | window | 9 | IMPL |  |
| IsIconic | user32 | window | 9 | IMPL |  |
| LockWindowUpdate | user32 | paint | 9 | IMPL |  |
| RegisterClassW | user32 | window | 9 | IMPL | ●起動/survey/probe |
| SetCapture | user32 | input | 9 | IMPL |  |
| GdiFlush | gdi32 | bitmap/blit | 8 | IMPL |  |
| PatBlt | gdi32 | bitmap/blit | 8 | IMPL |  |
| ClientToScreen | user32 | window | 8 | IMPL |  |
| GetWindowDC | user32 | paint | 8 | IMPL |  |
| IsWindow | user32 | window | 8 | IMPL |  |
| MapVirtualKeyW | user32 | input | 8 | IMPL |  |
| PhysicalToLogicalPoint | user32 | input | 8 | IMPL |  |
| TranslateMessage | user32 | message | 8 | IMPL |  |
| CreateDIBSection | gdi32 | bitmap/blit | 7 | IMPL |  |
| GetDCEx | user32 | paint | 7 | IMPL |  |
| GetDesktopWindow | user32 | window | 7 | IMPL |  |
| GetKeyboardState | user32 | input | 7 | IMPL |  |
| PostQuitMessage | user32 | message | 7 | IMPL |  |
| SetWindowTextW | user32 | window | 7 | IMPL |  |
| AlphaBlend | msimg32 | bitmap/blit | 6 | IMPL |  |
| GetForegroundWindow | user32 | input | 6 | IMPL |  |
| ActivateKeyboardLayout | user32 | input | 5 | IMPL |  |
| GetPhysicalCursorPos | user32 | input | 5 | IMPL |  |
| IsChild | user32 | window | 5 | IMPL |  |
| KillTimer | user32 | message | 5 | IMPL |  |
| SetForegroundWindow | user32 | input | 5 | IMPL |  |
| ValidateRect | user32 | paint | 5 | IMPL |  |
| WindowFromPoint | user32 | input | 5 | IMPL |  |
| StretchDIBits | gdi32 | bitmap/blit | 4 | IMPL |  |
| EnableWindow | user32 | window | 4 | IMPL |  |
| GetAncestor | user32 | window | 4 | IMPL |  |
| GetClipCursor | user32 | input | 4 | IMPL | ●survey |
| GetKeyboardLayout | user32 | input | 4 | IMPL | ●起動/survey/probe |
| LogicalToPhysicalPoint | user32 | input | 4 | IMPL |  |
| ScreenToClient | user32 | window | 4 | IMPL |  |
| SetDIBits | gdi32 | bitmap/blit | 3 | IMPL |  |
| AdjustWindowRectEx | user32 | window | 3 | IMPL |  |
| GetMessagePos | user32 | message | 3 | IMPL |  |
| GetUpdateRect | user32 | paint | 3 | IMPL |  |
| IsZoomed | user32 | window | 3 | IMPL |  |
| LoadKeyboardLayoutW | user32 | input | 3 | IMPL |  |
| SetParent | user32 | window | 3 | IMPL |  |
| ToAscii | user32 | input | 3 | IMPL |  |
| UpdateWindow | user32 | window | 3 | IMPL |  |
| WaitMessage | user32 | message | 3 | IMPL |  |
| GetStretchBltMode | gdi32 | bitmap/blit | 2 | IMPL |  |
| SetDIBitsToDevice | gdi32 | bitmap/blit | 2 | IMPL |  |
| DispatchMessageA | user32 | message | 2 | IMPL |  |
| GetMessageTime | user32 | message | 2 | IMPL |  |
| GetMessageW | user32 | message | 2 | IMPL |  |
| GetWindowTextW | user32 | window | 2 | IMPL |  |
| InvalidateRgn | user32 | paint | 2 | IMPL |  |
| PostThreadMessageW | user32 | message | 2 | IMPL |  |
| SendMessageA | user32 | message | 2 | IMPL |  |
| SetWindowTextA | user32 | window | 2 | IMPL |  |

## 3.1 P1 (119 名)

| API | DLL | カテゴリ | xref | 状態 | 実到達 (GUI-3 #174) |
|---|---|---|---|---|---|
| SelectPalette | gdi32 | palette | 39 | IMPL |  |
| DrawEdge | user32 | user-draw | 18 | IMPL |  |
| GetWindowPlacement | user32 | window-aux | 18 | IMPL |  |
| InflateRect | user32 | util | 18 | IMPL |  |
| CreateRectRgn | gdi32 | clip/region | 16 | IMPL |  |
| CreateRectRgnIndirect | gdi32 | clip/region | 16 | IMPL |  |
| OffsetRgn | gdi32 | clip/region | 16 | IMPL |  |
| PtInRect | user32 | util | 16 | IMPL |  |
| GetTextExtentPoint32W | gdi32 | text/font | 13 | IMPL |  |
| SaveDC | gdi32 | dc-state | 13 | IMPL |  |
| SetRect | user32 | util | 13 | IMPL |  |
| ExcludeClipRect | gdi32 | clip/region | 12 | IMPL |  |
| SelectClipRgn | gdi32 | clip/region | 12 | IMPL |  |
| GetStockObject | gdi32 | dc-state | 11 | IMPL | ●起動/survey/probe |
| GetTextMetricsW | gdi32 | text/font | 11 | IMPL |  |
| CharNextW | user32 | util | 11 | IMPL | ●起動/survey/probe |
| GetClipboardData | user32 | clipboard | 11 | IMPL |  |
| LoadStringW | user32 | util | 11 | IMPL | ●起動/survey/probe |
| NotifyWinEvent | user32 | hook/sync | 11 | IMPL |  |
| IntersectClipRect | gdi32 | clip/region | 10 | IMPL |  |
| UnionRect | user32 | util | 10 | IMPL |  |
| CreatePen | gdi32 | dc-state | 9 | IMPL |  |
| ExtTextOutW | gdi32 | text/font | 9 | IMPL |  |
| GetClipBox | gdi32 | clip/region | 9 | IMPL |  |
| SetBkMode | gdi32 | dc-state | 9 | IMPL |  |
| MessageBoxW | user32 | util | 9 | IMPL | ●survey |
| CreateFontIndirectW | gdi32 | text/font | 8 | IMPL |  |
| CallNextHookEx | user32 | hook/sync | 8 | IMPL |  |
| LoadCursorW | user32 | cursor/icon | 8 | IMPL | ●起動/survey/probe |
| SetClipboardData | user32 | clipboard | 8 | IMPL |  |
| SetWindowPlacement | user32 | window-aux | 8 | IMPL |  |
| SetWindowsHookExW | user32 | hook/sync | 8 | IMPL |  |
| UnhookWindowsHookEx | user32 | hook/sync | 8 | IMPL |  |
| CreateSolidBrush | gdi32 | dc-state | 7 | IMPL |  |
| EvaluateProximityToRect | user32 | util | 7 | IMPL |  |
| FindWindowW | user32 | window-aux | 7 | IMPL | ●起動/survey/probe |
| FrameRect | user32 | user-draw | 7 | IMPL |  |
| GetMonitorInfoW | user32 | system | 7 | IMPL | ●survey |
| LoadIconW | user32 | cursor/icon | 7 | IMPL | ●起動/survey/probe |
| SetPropW | user32 | window-aux | 7 | IMPL |  |
| SetRectRgn | gdi32 | util | 6 | IMPL |  |
| EnumThreadWindows | user32 | window-aux | 6 | IMPL |  |
| GetDlgItem | user32 | window-aux | 6 | IMPL |  |
| GetIconInfo | user32 | cursor/icon | 6 | IMPL | ●起動/survey/probe |
| GetLastActivePopup | user32 | window-aux | 6 | IMPL |  |
| MessageBeep | user32 | util | 6 | IMPL |  |
| MonitorFromWindow | user32 | system | 6 | IMPL |  |
| ScrollDC | user32 | window-aux | 6 | IMPL |  |
| CreateDIBitmap | gdi32 | window-aux | 5 | IMPL |  |
| ExtSelectClipRgn | gdi32 | clip/region | 5 | IMPL |  |
| GetWindowOrgEx | gdi32 | dc-state | 5 | IMPL |  |
| SetMapMode | gdi32 | dc-state | 5 | IMPL |  |
| DestroyCursor | user32 | cursor/icon | 5 | IMPL |  |
| DrawFrameControl | user32 | user-draw | 5 | IMPL |  |
| EnumClipboardFormats | user32 | clipboard | 5 | IMPL |  |
| EnumWindows | user32 | window-aux | 5 | IMPL |  |
| GetPropW | user32 | window-aux | 5 | IMPL |  |
| IsWindowUnicode | user32 | window-aux | 5 | IMPL |  |
| LoadBitmapW | user32 | cursor/icon | 5 | IMPL |  |
| PackTouchHitTestingProximityEvaluation | user32 | util | 5 | IMPL |  |
| RemovePropW | user32 | window-aux | 5 | IMPL |  |
| ScrollWindow | user32 | window-aux | 5 | IMPL |  |
| SetThreadDpiAwarenessContext | user32 | system | 5 | IMPL |  |
| SetWindowRgn | user32 | window-aux | 5 | IMPL |  |
| EqualRgn | gdi32 | clip/region | 4 | IMPL |  |
| GetRandomRgn | gdi32 | clip/region | 4 | IMPL |  |
| GetRgnBox | gdi32 | clip/region | 4 | IMPL |  |
| LPtoDP | gdi32 | dc-state | 4 | IMPL |  |
| SetBrushOrgEx | gdi32 | dc-state | 4 | IMPL |  |
| AttachThreadInput | user32 | hook/sync | 4 | IMPL |  |
| BeginDeferWindowPos | user32 | window-aux | 4 | IMPL |  |
| CharLowerBuffW | user32 | util | 4 | IMPL | ●survey |
| CharUpperBuffW | user32 | util | 4 | IMPL |  |
| CloseClipboard | user32 | clipboard | 4 | IMPL |  |
| DeferWindowPos | user32 | window-aux | 4 | IMPL |  |
| DrawFocusRect | user32 | user-draw | 4 | IMPL |  |
| EndDeferWindowPos | user32 | window-aux | 4 | IMPL |  |
| EnumChildWindows | user32 | window-aux | 4 | IMPL |  |
| EqualRect | user32 | util | 4 | IMPL |  |
| GetClipboardFormatNameW | user32 | clipboard | 4 | IMPL | ●survey |
| GetCursor | user32 | cursor/icon | 4 | IMPL |  |
| GetUpdateRgn | user32 | window-aux | 4 | IMPL |  |
| MsgWaitForMultipleObjects | user32 | hook/sync | 4 | IMPL |  |
| SetCaretPos | user32 | cursor/icon | 4 | IMPL |  |
| SetClassLongPtrW | user32 | window-aux | 4 | IMPL |  |
| ShowCaret | user32 | cursor/icon | 4 | IMPL |  |
| ShowOwnedPopups | user32 | window-aux | 4 | IMPL |  |
| CreateDCW | gdi32 | dc-state | 3 | IMPL |  |
| GetBkColor | gdi32 | dc-state | 3 | IMPL |  |
| GetBrushOrgEx | gdi32 | dc-state | 3 | IMPL |  |
| GetClipRgn | gdi32 | clip/region | 3 | IMPL |  |
| GetRegionData | gdi32 | clip/region | 3 | IMPL |  |
| GetTextColor | gdi32 | dc-state | 3 | IMPL |  |
| GetTextExtentPointW | gdi32 | text/font | 3 | IMPL |  |
| RectInRegion | gdi32 | clip/region | 3 | IMPL |  |
| SetTextAlign | gdi32 | text/font | 3 | IMPL |  |
| CharUpperW | user32 | util | 3 | IMPL |  |
| DestroyCaret | user32 | cursor/icon | 3 | IMPL |  |
| DrawIcon | user32 | cursor/icon | 3 | IMPL |  |
| DrawIconEx | user32 | cursor/icon | 3 | IMPL |  |
| EmptyClipboard | user32 | clipboard | 3 | IMPL |  |
| EnumDisplayMonitors | user32 | system | 3 | IMPL | ●起動/survey/probe |
| EnumDisplaySettingsW | user32 | system | 3 | IMPL | ●survey |
| GetGuiResources | user32 | system | 3 | IMPL |  |
| GetTopWindow | user32 | window-aux | 3 | IMPL |  |
| HideCaret | user32 | cursor/icon | 3 | IMPL |  |
| MessageBoxA | user32 | util | 3 | IMPL | ●survey |
| MonitorFromRect | user32 | system | 3 | IMPL |  |
| OpenClipboard | user32 | clipboard | 3 | IMPL |  |
| ScrollWindowEx | user32 | window-aux | 3 | IMPL |  |
| SetThreadDpiHostingBehavior | user32 | system | 3 | IMPL |  |
| ShowCursor | user32 | cursor/icon | 3 | IMPL |  |
| GetCursorInfo | user32 | input | 2 | IMPL |  |
| GetKeyNameTextW | user32 | input | 2 | IMPL |  |
| GetKeyboardLayoutList | user32 | input | 2 | IMPL |  |
| GetKeyboardLayoutNameW | user32 | input | 2 | IMPL |  |
| SendInput | user32 | input | 2 | IMPL |  |
| SetKeyboardState | user32 | input | 2 | IMPL |  |
| ToUnicode | user32 | input | 2 | IMPL |  |

## 3.2 P2 (98 名)

| API | DLL | カテゴリ | xref | 状態 | 実到達 (GUI-3 #174) |
|---|---|---|---|---|---|
| RealizePalette | gdi32 | palette | 17 | IMPL |  |
| LineTo | gdi32 | gdi-vector | 14 | IMPL |  |
| ImageList_DrawEx | comctl32 | imagelist | 11 | STUB |  |
| DeleteMenu | user32 | menu | 11 | STUB |  |
| CreatePalette | gdi32 | palette | 10 | IMPL | ●起動/survey/probe |
| MoveToEx | gdi32 | gdi-vector | 10 | IMPL |  |
| GetPaletteEntries | gdi32 | palette | 9 | STUB |  |
| SetPixelV | gdi32 | gdi-vector | 9 | IMPL |  |
| EndBufferedPaint | uxtheme | aux | 9 | STUB |  |
| GetScrollInfo | user32 | scrollbar | 7 | STUB |  |
| FlatSB_SetScrollProp | comctl32 | scrollbar | 6 | STUB |  |
| ImageList_DragEnter | comctl32 | imagelist | 6 | STUB |  |
| ImageList_DragShowNolock | comctl32 | imagelist | 6 | STUB |  |
| GetSystemPaletteEntries | gdi32 | palette | 6 | STUB |  |
| GetMenuItemCount | user32 | menu | 6 | STUB |  |
| GetMenuState | user32 | menu | 6 | STUB |  |
| GetSubMenu | user32 | menu | 6 | STUB |  |
| ImageList_DragLeave | comctl32 | imagelist | 5 | STUB |  |
| ImageList_Draw | comctl32 | imagelist | 5 | STUB |  |
| ImageList_SetIconSize | comctl32 | imagelist | 5 | STUB |  |
| DrawMenuBar | user32 | menu | 5 | STUB |  |
| SetMenu | user32 | menu | 5 | STUB |  |
| SetScrollInfo | user32 | scrollbar | 5 | STUB |  |
| BeginBufferedPaint | uxtheme | aux | 5 | STUB |  |
| BufferedPaintSetAlpha | uxtheme | aux | 5 | STUB |  |
| ImageList_Add | comctl32 | imagelist | 4 | STUB |  |
| ImageList_EndDrag | comctl32 | imagelist | 4 | STUB |  |
| ImageList_GetDragImage | comctl32 | imagelist | 4 | STUB |  |
| ImageList_GetImageCount | comctl32 | imagelist | 4 | STUB |  |
| CreateHalftonePalette | gdi32 | palette | 4 | STUB |  |
| GetDIBColorTable | gdi32 | palette | 4 | IMPL |  |
| SetDIBColorTable | gdi32 | palette | 4 | IMPL |  |
| ImmAssociateContextEx | imm32 | IME | 4 | IMPL |  |
| DestroyMenu | user32 | menu | 4 | STUB |  |
| EnableMenuItem | user32 | menu | 4 | STUB |  |
| GetSystemMenu | user32 | menu | 4 | STUB |  |
| ImageList_BeginDrag | comctl32 | imagelist | 3 | STUB |  |
| ImageList_DragMove | comctl32 | imagelist | 3 | STUB |  |
| ImageList_GetBkColor | comctl32 | imagelist | 3 | STUB |  |
| ImageList_Read | comctl32 | imagelist | 3 | STUB |  |
| GetBitmapBits | gdi32 | aux | 3 | STUB |  |
| GetEnhMetaFilePaletteEntries | gdi32 | palette | 3 | STUB |  |
| MaskBlt | gdi32 | aux | 3 | STUB |  |
| ImmGetContext | imm32 | IME | 3 | IMPL |  |
| ImmGetConversionStatus | imm32 | IME | 3 | IMPL |  |
| ImmReleaseContext | imm32 | IME | 3 | IMPL |  |
| ImmSetConversionStatus | imm32 | IME | 3 | IMPL |  |
| ImmSetOpenStatus | imm32 | IME | 3 | IMPL |  |
| CreatePopupMenu | user32 | menu | 3 | STUB |  |
| GetMenu | user32 | menu | 3 | STUB |  |
| GetMenuItemID | user32 | menu | 3 | STUB |  |
| GetScrollPos | user32 | scrollbar | 3 | STUB |  |
| InsertMenuW | user32 | menu | 3 | STUB |  |
| RemoveMenu | user32 | menu | 3 | STUB |  |
| TrackPopupMenu | user32 | menu | 3 | STUB |  |
| _TrackMouseEvent | comctl32 | input | 2 | STUB |  |
| CreateBrushIndirect | gdi32 | dc-state | 2 | STUB |  |
| CreateFontW | gdi32 | text/font | 2 | IMPL |  |
| CreatePatternBrush | gdi32 | dc-state | 2 | STUB |  |
| CreatePenIndirect | gdi32 | dc-state | 2 | STUB |  |
| CreatePolygonRgn | gdi32 | clip/region | 2 | STUB |  |
| EnumFontFamiliesExW | gdi32 | text/font | 2 | IMPL | ●survey |
| EnumFontsW | gdi32 | text/font | 2 | STUB |  |
| FrameRgn | gdi32 | clip/region | 2 | STUB |  |
| GetCurrentObject | gdi32 | dc-state | 2 | IMPL |  |
| GetTextAlign | gdi32 | text/font | 2 | IMPL |  |
| RectVisible | gdi32 | clip/region | 2 | STUB |  |
| SetROP2 | gdi32 | dc-state | 2 | IMPL |  |
| SetViewportOrgEx | gdi32 | dc-state | 2 | IMPL |  |
| TextOutW | gdi32 | text/font | 2 | IMPL |  |
| GetDpiForMonitor | shcore | system | 2 | STUB |  |
| GetProcessDpiAwareness | shcore | system | 2 | STUB |  |
| CharLowerW | user32 | util | 2 | IMPL | ●起動/survey/probe |
| CharNextExA | user32 | util | 2 | IMPL |  |
| CharToOemBuffW | user32 | util | 2 | IMPL |  |
| CopyImage | user32 | cursor/icon | 2 | STUB |  |
| CountClipboardFormats | user32 | clipboard | 2 | STUB |  |
| CreateCaret | user32 | cursor/icon | 2 | IMPL |  |
| CreateIcon | user32 | cursor/icon | 2 | STUB |  |
| CreateIconFromResource | user32 | cursor/icon | 2 | STUB |  |
| CreateIconIndirect | user32 | cursor/icon | 2 | STUB |  |
| DestroyIcon | user32 | cursor/icon | 2 | STUB |  |
| DrawTextExW | user32 | user-draw | 2 | STUB |  |
| FindWindowExW | user32 | window-aux | 2 | IMPL |  |
| GetClassLongPtrW | user32 | window-aux | 2 | IMPL |  |
| GetClassNameW | user32 | window-aux | 2 | IMPL |  |
| GetDoubleClickTime | user32 | system | 2 | IMPL |  |
| GetMessageExtraInfo | user32 | hook/sync | 2 | IMPL |  |
| GetSysColor | user32 | system | 2 | IMPL |  |
| IsClipboardFormatAvailable | user32 | clipboard | 2 | STUB |  |
| IsProcessDPIAware | user32 | system | 2 | IMPL |  |
| LoadImageW | user32 | cursor/icon | 2 | IMPL | ●起動/survey/probe |
| MessageBoxA | user32 | util | 2 | IMPL | ●survey |
| MonitorFromPoint | user32 | system | 2 | STUB |  |
| MsgWaitForMultipleObjectsEx | user32 | hook/sync | 2 | IMPL |  |
| SubtractRect | user32 | util | 2 | IMPL |  |
| ValidateRgn | user32 | window-aux | 2 | IMPL |  |
| CreateICW | gdi32 | dc-state | 1 | STUB |  |

## 3.3 P3 (92 名)

| API | DLL | カテゴリ | xref | 状態 | 実到達 (GUI-3 #174) |
|---|---|---|---|---|---|
| GetEnhMetaFileHeader | gdi32 | metafile | 9 | STUB |  |
| GetEnhMetaFileDescriptionW | gdi32 | metafile | 5 | STUB |  |
| SetGestureConfig | user32 | touch/gesture | 5 | IMPL |  |
| EnumPrintersW | winspool.drv | printing | 5 | STUB |  |
| CopyEnhMetaFileW | gdi32 | metafile | 4 | STUB |  |
| DeleteEnhMetaFile | gdi32 | metafile | 4 | STUB |  |
| EndPage | gdi32 | printing | 3 | STUB |  |
| GetEnhMetaFileBits | gdi32 | metafile | 3 | STUB |  |
| GetWinMetaFileBits | gdi32 | metafile | 3 | STUB |  |
| PlayEnhMetaFile | gdi32 | metafile | 3 | STUB |  |
| SetWinMetaFileBits | gdi32 | metafile | 3 | STUB |  |
| StartPage | gdi32 | printing | 3 | STUB |  |
| CloseGestureInfoHandle | user32 | touch/gesture | 3 | IMPL |  |
| RegisterTouchHitTestingWindow | user32 | touch/gesture | 3 | IMPL |  |
| ClosePrinter | winspool.drv | printing | 3 | STUB |  |
| DocumentPropertiesW | winspool.drv | printing | 3 | STUB |  |
| FlatSB_GetScrollInfo | comctl32 | scrollbar | 2 | STUB |  |
| FlatSB_GetScrollPos | comctl32 | scrollbar | 2 | STUB |  |
| FlatSB_SetScrollInfo | comctl32 | scrollbar | 2 | STUB |  |
| FlatSB_SetScrollPos | comctl32 | scrollbar | 2 | STUB |  |
| ImageList_Create | comctl32 | imagelist | 2 | STUB |  |
| ImageList_Destroy | comctl32 | imagelist | 2 | STUB |  |
| ImageList_GetIcon | comctl32 | imagelist | 2 | STUB |  |
| ImageList_GetIconSize | comctl32 | imagelist | 2 | STUB |  |
| ImageList_Remove | comctl32 | imagelist | 2 | STUB |  |
| ImageList_Replace | comctl32 | imagelist | 2 | STUB |  |
| ImageList_SetBkColor | comctl32 | imagelist | 2 | STUB |  |
| ImageList_SetImageCount | comctl32 | imagelist | 2 | STUB |  |
| ImageList_Write | comctl32 | imagelist | 2 | STUB |  |
| InitializeFlatSB | comctl32 | scrollbar | 2 | STUB |  |
| DwmExtendFrameIntoClientArea | dwmapi | shell-integration | 2 | STUB |  |
| DwmIsCompositionEnabled | dwmapi | shell-integration | 2 | STUB |  |
| AngleArc | gdi32 | gdi-vector | 2 | STUB |  |
| Arc | gdi32 | gdi-vector | 2 | STUB |  |
| ArcTo | gdi32 | gdi-vector | 2 | STUB |  |
| BeginPath | gdi32 | gdi-vector | 2 | STUB |  |
| Chord | gdi32 | gdi-vector | 2 | STUB |  |
| CloseEnhMetaFile | gdi32 | metafile | 2 | STUB |  |
| CreateEnhMetaFileW | gdi32 | metafile | 2 | STUB |  |
| Ellipse | gdi32 | gdi-vector | 2 | STUB |  |
| EndDoc | gdi32 | printing | 2 | STUB |  |
| EndPath | gdi32 | gdi-vector | 2 | STUB |  |
| ExtFloodFill | gdi32 | gdi-vector | 2 | STUB |  |
| GetCurrentPositionEx | gdi32 | gdi-vector | 2 | IMPL |  |
| GetDCOrgEx | gdi32 | aux | 2 | STUB |  |
| GetNearestPaletteIndex | gdi32 | palette | 2 | STUB |  |
| GetPixel | gdi32 | gdi-vector | 2 | IMPL |  |
| Pie | gdi32 | gdi-vector | 2 | STUB |  |
| PolyBezier | gdi32 | gdi-vector | 2 | STUB |  |
| PolyBezierTo | gdi32 | gdi-vector | 2 | STUB |  |
| Polygon | gdi32 | gdi-vector | 2 | STUB |  |
| Polyline | gdi32 | gdi-vector | 2 | STUB |  |
| Rectangle | gdi32 | gdi-vector | 2 | IMPL |  |
| ResizePalette | gdi32 | palette | 2 | STUB |  |
| RoundRect | gdi32 | gdi-vector | 2 | STUB |  |
| SelectClipPath | gdi32 | gdi-vector | 2 | STUB |  |
| SetAbortProc | gdi32 | printing | 2 | STUB |  |
| SetEnhMetaFileBits | gdi32 | metafile | 2 | STUB |  |
| SetPixel | gdi32 | gdi-vector | 2 | IMPL |  |
| StartDocW | gdi32 | printing | 2 | STUB |  |
| UnrealizeObject | gdi32 | palette | 2 | STUB |  |
| ImmIsIME | imm32 | IME | 2 | IMPL |  |
| GradientFill | msimg32 | aux | 2 | STUB |  |
| LresultFromObject | oleacc | shell-integration | 2 | STUB |  |
| wglGetProcAddress | opengl32 | opengl | 2 | STUB |  |
| wglUseFontBitmapsW | opengl32 | opengl | 2 | STUB |  |
| CheckMenuItem | user32 | menu | 2 | STUB |  |
| CreateMenu | user32 | menu | 2 | STUB |  |
| DefFrameProcW | user32 | aux | 2 | IMPL |  |
| GetGestureInfo | user32 | touch/gesture | 2 | IMPL |  |
| GetMenuItemInfoW | user32 | menu | 2 | STUB |  |
| GetMenuStringW | user32 | menu | 2 | STUB |  |
| InsertMenuItemW | user32 | menu | 2 | STUB |  |
| IsDialogMessageA | user32 | aux | 2 | IMPL |  |
| IsDialogMessageW | user32 | aux | 2 | IMPL |  |
| RegisterTouchWindow | user32 | touch/gesture | 2 | IMPL |  |
| SetMenuItemInfoW | user32 | menu | 2 | STUB |  |
| ShowScrollBar | user32 | scrollbar | 2 | STUB |  |
| TranslateMDISysAccel | user32 | aux | 2 | IMPL |  |
| BufferedPaintInit | uxtheme | aux | 2 | STUB |  |
| BufferedPaintUnInit | uxtheme | aux | 2 | STUB |  |
| GetDefaultPrinterW | winspool.drv | printing | 2 | STUB |  |
| OpenPrinterW | winspool.drv | printing | 2 | STUB |  |
| WTSRegisterSessionNotification | wtsapi32 | shell-integration | 2 | IMPL |  |
| WTSUnRegisterSessionNotification | wtsapi32 | shell-integration | 2 | IMPL |  |
| GetOpenFileNameW | comdlg32 | dialog | 1 | IMPL |  |
| GetSaveFileNameW | comdlg32 | dialog | 1 | IMPL |  |
| DefMDIChildProcW | user32 | aux | 1 | IMPL |  |
| EnableScrollBar | user32 | scrollbar | 1 | STUB |  |
| GetScrollRange | user32 | scrollbar | 1 | STUB |  |
| SetScrollPos | user32 | scrollbar | 1 | STUB |  |
| SetScrollRange | user32 | scrollbar | 1 | STUB |  |

## 4. 実到達ベースの優先順位入力 (GUI-3 #174)

実 FLEngine の lift (m11 closure) に本 shim を結合して実行し、shim に到達した API (表の「実到達」列: 起動 = DllMain attach / survey = 942 unit 隔離 / probe = 指向呼出)。回数・分母・手順は `tools/gui/flengine/REPORT.md`、機械可読は `tools/gui/flengine/results/*.json`。

| 区分 | API (P 分類) |
|---|---|
| 到達 & 実装済み (実行時 kind = IMPL のみ) | CharLowerBuffW (P1), CharLowerW (P2), CharNextW (P1), CreatePalette (P2), CreateWindowExW (P0), DeleteObject (P0), EnumDisplayMonitors (P1), EnumDisplaySettingsW (P1), EnumFontFamiliesExW (P2), FindWindowW (P1), GetClassInfoW (P0), GetClipCursor (P0), GetClipboardFormatNameW (P1), GetDC (P0), GetDeviceCaps (P0), GetIconInfo (P1), GetKeyboardLayout (P0), GetMonitorInfoW (P1), GetObjectW (P0), GetStockObject (P1), GetSystemMetrics (P0), LoadCursorW (P1), LoadIconW (P1), LoadImageW (P2), LoadStringW (P1), MessageBoxA (P2), MessageBoxW (P1), RegisterClassW (P0), RegisterClipboardFormatW (P0), RegisterWindowMessageW (P0), ReleaseDC (P0), SetWindowLongPtrW (P0), SystemParametersInfoW (P0), UnregisterClassW (P0) |
| 到達 & STUB 経路を通った (**実装必須へ昇格**) | なし |
| 到達 & P2/P3 (**P1 以上へ昇格候補**) | CharLowerW (P2), CreatePalette (P2), EnumFontFamiliesExW (P2), LoadImageW (P2), MessageBoxA (P2) |
| 未到達の P0 (現 m11 到達段では未実行) | SendMessageW, PostMessageW, SelectObject, GetCursorPos, GetWindowLongPtrW, GetCapture, DeleteDC, SetWindowPos, BitBlt, SetBkColor, SetCursor, IntersectRect, IsWindowVisible, SetFocus, CreateCompatibleDC, GetWindowRect, ReleaseCapture, OffsetRect, ShowWindow, SetTextColor, DrawTextW, MapWindowPoints, DefWindowProcW, SetWindowOrgEx, GetKeyState, PeekMessageW, CombineRgn, RestoreDC, FillRect, GetParent, InvalidateRect, RedrawWindow, SetActiveWindow, EndPaint, DispatchMessageW, StretchBlt, GetFocus, GetWindowThreadProcessId, SetTimer, CallWindowProcW, GetAsyncKeyState, GetWindow, IsWindowEnabled, SetStretchBltMode, BeginPaint, SetCursorPos, SetPhysicalCursorPos, GetClientRect, GetDIBits, GetActiveWindow, CreateBitmap, CreateCompatibleBitmap, DestroyWindow, IsIconic, LockWindowUpdate, SetCapture, GdiFlush, PatBlt, ClientToScreen, GetWindowDC, IsWindow, MapVirtualKeyW, PhysicalToLogicalPoint, TranslateMessage, CreateDIBSection, GetDCEx, GetDesktopWindow, GetKeyboardState, PostQuitMessage, SetWindowTextW, AlphaBlend, GetForegroundWindow, ActivateKeyboardLayout, GetPhysicalCursorPos, IsChild, KillTimer, SetForegroundWindow, ValidateRect, WindowFromPoint, StretchDIBits, EnableWindow, GetAncestor, LogicalToPhysicalPoint, ScreenToClient, SetDIBits, AdjustWindowRectEx, GetMessagePos, GetUpdateRect, IsZoomed, LoadKeyboardLayoutW, SetParent, ToAscii, UpdateWindow, WaitMessage, GetStretchBltMode, SetDIBitsToDevice, DispatchMessageA, GetMessageTime, GetMessageW, GetWindowTextW, InvalidateRgn, PostThreadMessageW, SendMessageA, SetWindowTextA |

## 5. arity 不明 (mingw ヘッダ未収録) で stub 未生成

なし
