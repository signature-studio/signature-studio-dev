; boot_final.ll から GUI import 名の declare と参照 struct 型だけ抜いた再現用 fixture (gen_adapt.py --refresh-fixture)
%tagPOINT = type { i32, i32 }
declare i1 @BitBlt(ptr, i32, i32, i32, i32, ptr, i32, i32, i32) local_unnamed_addr
declare i1 @DeleteDC(ptr) local_unnamed_addr
declare i1 @DeleteMenu(ptr, i32, i32) local_unnamed_addr
declare i1 @DeleteObject(ptr) local_unnamed_addr
declare i1 @DestroyCursor(ptr) local_unnamed_addr
declare i1 @DestroyWindow(ptr) local_unnamed_addr
declare i1 @DrawMenuBar(ptr) local_unnamed_addr
declare i1 @EnableWindow(ptr, i1) local_unnamed_addr
declare i1 @EndDeferWindowPos(ptr) local_unnamed_addr
declare i1 @EndPaint(ptr, ptr) local_unnamed_addr
declare i1 @EnumChildWindows(ptr, ptr, i32) local_unnamed_addr
declare i1 @EnumDisplayMonitors(ptr, ptr, ptr, i32) local_unnamed_addr
declare i1 @EnumDisplaySettingsW(ptr, i32, ptr) local_unnamed_addr
declare i1 @EnumThreadWindows(i32, ptr, i32) local_unnamed_addr
declare i1 @EnumWindows(ptr, i32) local_unnamed_addr
declare i1 @EqualRgn(ptr, ptr) local_unnamed_addr
declare i1 @GdiFlush() local_unnamed_addr
declare i1 @GetClassInfoW(ptr, ptr, ptr) local_unnamed_addr
declare i1 @GetClientRect(ptr, ptr) local_unnamed_addr
declare i1 @GetClipCursor(ptr) local_unnamed_addr
declare i1 @GetCursorInfo(ptr) local_unnamed_addr
declare i1 @GetCursorPos(ptr) local_unnamed_addr
declare i1 @GetDCOrgEx(ptr, ptr) local_unnamed_addr
declare i1 @GetIconInfo(ptr, ptr) local_unnamed_addr
declare i1 @GetMenuItemInfoW(ptr, i32, i1, ptr) local_unnamed_addr
declare i1 @GetMonitorInfoW(i64, ptr) local_unnamed_addr
declare i1 @GetPhysicalCursorPos(ptr) local_unnamed_addr
declare i1 @GetTextMetricsW(ptr, ptr) local_unnamed_addr
declare i1 @GetWindowOrgEx(ptr, ptr) local_unnamed_addr
declare i1 @GetWindowPlacement(ptr, ptr) local_unnamed_addr
declare i1 @GetWindowRect(ptr, ptr) local_unnamed_addr
declare i1 @IntersectRect(ptr, ptr, ptr) local_unnamed_addr
declare i1 @InvalidateRect(ptr, ptr, i1) local_unnamed_addr
declare i1 @InvalidateRgn(ptr, ptr, i1) local_unnamed_addr
declare i1 @IsDialogMessageA(ptr, ptr) local_unnamed_addr
declare i1 @IsDialogMessageW(ptr, ptr) local_unnamed_addr
declare i1 @IsIconic(ptr) local_unnamed_addr
declare i1 @IsProcessDPIAware() local_unnamed_addr
declare i1 @IsWindow(ptr) local_unnamed_addr
declare i1 @IsWindowEnabled(ptr) local_unnamed_addr
declare i1 @IsWindowUnicode(ptr) local_unnamed_addr
declare i1 @IsWindowVisible(ptr) local_unnamed_addr
declare i1 @KillTimer(ptr, i32) local_unnamed_addr
declare i1 @LPtoDP(ptr, ptr, i32) local_unnamed_addr
declare i1 @OffsetRect(ptr, i32, i32) local_unnamed_addr
declare i1 @PatBlt(ptr, i32, i32, i32, i32, i32) local_unnamed_addr
declare i1 @PeekMessageW(ptr, ptr, i32, i32, i32) local_unnamed_addr
declare i1 @PostMessageW(ptr, i32, i32, i32) local_unnamed_addr
declare i1 @RectInRegion(ptr, ptr) local_unnamed_addr
declare i1 @RedrawWindow(ptr, ptr, ptr, i32) local_unnamed_addr
declare i1 @ReleaseCapture() local_unnamed_addr
declare i1 @SetMenuItemInfoW(ptr, i32, i1, ptr) local_unnamed_addr
declare i1 @SetPhysicalCursorPos(i32, i32) local_unnamed_addr
declare i1 @SetPropW(ptr, ptr, ptr) local_unnamed_addr
declare i1 @SetRectRgn(ptr, i32, i32, i32, i32) local_unnamed_addr
declare i1 @SetWindowOrgEx(ptr, i32, i32, ptr) local_unnamed_addr
declare i1 @SetWindowPlacement(ptr, ptr) local_unnamed_addr
declare i1 @SetWindowPos(ptr, ptr, i32, i32, i32, i32, i32) local_unnamed_addr
declare i1 @ShowOwnedPopups(ptr, i1) local_unnamed_addr
declare i1 @ShowWindow(ptr, i32) local_unnamed_addr
declare i1 @StretchBlt(ptr, i32, i32, i32, i32, ptr, i32, i32, i32, i32, i32) local_unnamed_addr
declare i1 @SystemParametersInfoW(i32, i32, ptr, i32) local_unnamed_addr
declare i1 @TranslateMDISysAccel(ptr, ptr) local_unnamed_addr
declare i1 @TranslateMessage(ptr) local_unnamed_addr
declare i1 @UnhookWindowsHookEx(ptr) local_unnamed_addr
declare i1 @UnionRect(ptr, ptr, ptr) local_unnamed_addr
declare i1 @UnregisterClassW(ptr, ptr) local_unnamed_addr
declare i1 @ValidateRect(ptr, ptr) local_unnamed_addr
declare i1 @ValidateRgn(ptr, ptr) local_unnamed_addr
declare i1 @WTSRegisterSessionNotification(ptr, i32) local_unnamed_addr
declare i1 @WaitMessage() local_unnamed_addr
declare i16 @GetKeyState(i32) local_unnamed_addr
declare i16 @RegisterClassW(ptr) local_unnamed_addr
declare i32 @BufferedPaintInit() local_unnamed_addr
declare i32 @CharLowerBuffW(ptr, i32) local_unnamed_addr
declare i32 @CharUpperBuffW(ptr, i32) local_unnamed_addr
declare i32 @CheckMenuItem(ptr, i32, i32) local_unnamed_addr
declare i32 @CombineRgn(ptr, ptr, ptr, i32) local_unnamed_addr
declare i32 @DispatchMessageA(ptr) local_unnamed_addr
declare i32 @DispatchMessageW(ptr) local_unnamed_addr
declare i32 @EnumFontFamiliesExW(ptr, ptr, ptr, i32, i32) local_unnamed_addr
declare i32 @ExcludeClipRect(ptr, i32, i32, i32, i32) local_unnamed_addr
declare i32 @ExtSelectClipRgn(ptr, ptr, i32) local_unnamed_addr
declare i32 @FillRect(ptr, ptr, ptr) local_unnamed_addr
declare i32 @GetBitmapBits(ptr, i32, ptr) local_unnamed_addr
declare i32 @GetClipBox(ptr, ptr) local_unnamed_addr
declare i32 @GetClipRgn(ptr, ptr) local_unnamed_addr
declare i32 @GetClipboardFormatNameW(i32, ptr, i32) local_unnamed_addr
declare i32 @GetDIBColorTable(ptr, i32, i32, ptr) local_unnamed_addr
declare i32 @GetDIBits(ptr, ptr, i32, i32, ptr, ptr, i32) local_unnamed_addr
declare i32 @GetDeviceCaps(ptr, i32) local_unnamed_addr
declare i32 @GetDpiForMonitor(i64, i64, ptr, ptr) local_unnamed_addr
declare i32 @GetKeyNameTextW(i32, ptr, i32) local_unnamed_addr
declare i32 @GetObjectW(ptr, i32, ptr) local_unnamed_addr
declare i32 @GetPaletteEntries(ptr, i32, i32, ptr) local_unnamed_addr
declare i32 @GetProcessDpiAwareness(ptr, ptr) local_unnamed_addr
declare i32 @GetRandomRgn(ptr, ptr, i32) local_unnamed_addr
declare i32 @GetRegionData(ptr, i32, ptr) local_unnamed_addr
declare i32 @GetRgnBox(ptr, ptr) local_unnamed_addr
declare i32 @GetSysColor(i32) local_unnamed_addr
declare i32 @GetSystemMetrics(i32) local_unnamed_addr
declare i32 @GetSystemPaletteEntries(ptr, i32, i32, ptr) local_unnamed_addr
declare i32 @GetUpdateRgn(ptr, ptr, i1) local_unnamed_addr
declare i32 @GetWindowLongPtrW(ptr, i32) local_unnamed_addr
declare i32 @GetWindowTextW(ptr, ptr, i32) local_unnamed_addr
declare i32 @GetWindowThreadProcessId(ptr, ptr) local_unnamed_addr
declare i32 @IntersectClipRect(ptr, i32, i32, i32, i32) local_unnamed_addr
declare i32 @LoadStringW(ptr, i32, ptr, i32) local_unnamed_addr
declare i32 @MapVirtualKeyW(i32, i32) local_unnamed_addr
declare i32 @MapWindowPoints(ptr, ptr, ptr, i32) local_unnamed_addr
declare i32 @MessageBoxA(ptr, ptr, ptr, i32) local_unnamed_addr
declare i32 @MessageBoxW(ptr, ptr, ptr, i32) local_unnamed_addr
declare i32 @MsgWaitForMultipleObjects(i32, ptr, i1, i32, i32) local_unnamed_addr
declare i32 @OffsetRgn(ptr, i32, i32) local_unnamed_addr
declare i32 @RealizePalette(ptr) local_unnamed_addr
declare i32 @RegisterClipboardFormatW(ptr) local_unnamed_addr
declare i32 @RegisterWindowMessageW(ptr) local_unnamed_addr
declare i32 @ReleaseDC(ptr, ptr) local_unnamed_addr
declare i32 @ScrollWindowEx(ptr, i32, i32, ptr, ptr, ptr, ptr, i32) local_unnamed_addr
declare i32 @SelectClipRgn(ptr, ptr) local_unnamed_addr
declare i32 @SendMessageA(ptr, i32, i32, i32) local_unnamed_addr
declare i32 @SendMessageW(ptr, i32, i32, i32) local_unnamed_addr
declare i32 @SetBkColor(ptr, i32) local_unnamed_addr
declare i32 @SetClassLongPtrW(ptr, i32, i32) local_unnamed_addr
declare i32 @SetDIBColorTable(ptr, i32, i32, ptr) local_unnamed_addr
declare i32 @SetDIBitsToDevice(ptr, i32, i32, i32, i32, i32, i32, i32, i32, ptr, ptr, i32) local_unnamed_addr
declare i32 @SetTextColor(ptr, i32) local_unnamed_addr
declare i32 @SetTimer(ptr, i32, i32, ptr) local_unnamed_addr
declare i32 @SetWindowLongPtrW(ptr, i32, i32) local_unnamed_addr
declare i32 @ShowCursor(i1) local_unnamed_addr
declare i64 @MonitorFromWindow(ptr, i32) local_unnamed_addr
declare ptr @BeginDeferWindowPos(i32) local_unnamed_addr
declare ptr @BeginPaint(ptr, ptr) local_unnamed_addr
declare ptr @CharLowerW(ptr) local_unnamed_addr
declare ptr @CharNextW(ptr) local_unnamed_addr
declare ptr @CharUpperW(ptr) local_unnamed_addr
declare ptr @CreateBitmap(i32, i32, i32, i32, ptr) local_unnamed_addr
declare ptr @CreateBrushIndirect(ptr) local_unnamed_addr
declare ptr @CreateCompatibleBitmap(ptr, i32, i32) local_unnamed_addr
declare ptr @CreateCompatibleDC(ptr) local_unnamed_addr
declare ptr @CreateDIBSection(ptr, ptr, i32, ptr, ptr, i32) local_unnamed_addr
declare ptr @CreateDIBitmap(ptr, ptr, i32, ptr, ptr, i32) local_unnamed_addr
declare ptr @CreateFontIndirectW(ptr) local_unnamed_addr
declare ptr @CreateHalftonePalette(ptr) local_unnamed_addr
declare ptr @CreateIcon(ptr, i32, i32, i8, i8, ptr, ptr) local_unnamed_addr
declare ptr @CreateIconIndirect(ptr) local_unnamed_addr
declare ptr @CreatePalette(ptr) local_unnamed_addr
declare ptr @CreateRectRgn(i32, i32, i32, i32) local_unnamed_addr
declare ptr @CreateRectRgnIndirect(ptr) local_unnamed_addr
declare ptr @CreateSolidBrush(i32) local_unnamed_addr
declare ptr @CreateWindowExW(i32, ptr, ptr, i32, i32, i32, i32, i32, ptr, ptr, ptr, ptr) local_unnamed_addr
declare ptr @DeferWindowPos(ptr, ptr, ptr, i32, i32, i32, i32, i32) local_unnamed_addr
declare ptr @FindWindowW(ptr, ptr) local_unnamed_addr
declare ptr @GetActiveWindow() local_unnamed_addr
declare ptr @GetCapture() local_unnamed_addr
declare ptr @GetCursor() local_unnamed_addr
declare ptr @GetDC(ptr) local_unnamed_addr
declare ptr @GetFocus() local_unnamed_addr
declare ptr @GetKeyboardLayout(i32) local_unnamed_addr
declare ptr @GetLastActivePopup(ptr) local_unnamed_addr
declare ptr @GetParent(ptr) local_unnamed_addr
declare ptr @GetPropW(ptr, ptr) local_unnamed_addr
declare ptr @GetStockObject(i32) local_unnamed_addr
declare ptr @GetSystemMenu(ptr, i1) local_unnamed_addr
declare ptr @LoadCursorW(ptr, ptr) local_unnamed_addr
declare ptr @LoadIconW(ptr, ptr) local_unnamed_addr
declare ptr @LoadImageW(ptr, ptr, i32, i32, i32, i32) local_unnamed_addr
declare ptr @RemovePropW(ptr, ptr) local_unnamed_addr
declare ptr @SelectObject(ptr, ptr) local_unnamed_addr
declare ptr @SelectPalette(ptr, ptr, i1) local_unnamed_addr
declare ptr @SetActiveWindow(ptr) local_unnamed_addr
declare ptr @SetClipboardData(i32, ptr) local_unnamed_addr
declare ptr @SetCursor(ptr) local_unnamed_addr
declare ptr @SetFocus(ptr) local_unnamed_addr
declare ptr @SetWindowsHookExW(i32, ptr, ptr, i32) local_unnamed_addr
declare ptr @WindowFromPoint(%tagPOINT) local_unnamed_addr
declare void @PostQuitMessage(i32) local_unnamed_addr
