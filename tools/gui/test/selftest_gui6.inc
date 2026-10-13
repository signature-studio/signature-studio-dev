/* selftest_gui6.inc — GUI-6 (#182): キー配列 (DE/FR) / IME / タッチ・ジェスチャ / Pointer Lock・ClipCursor。selftest.c から #include。 */
/* Win64 レイアウト (mingw-w64 の TOUCHINPUT/GESTUREINFO と _Static_assert で一致確認済み: 48B / 56B)。shim の定義とは独立に再定義 */
typedef struct { int32_t x, y; uint64_t src; uint32_t id, flags, mask, time; uint64_t extra; uint32_t cx, cy; } TouchIn;
typedef struct { uint32_t cbSize, dwFlags, dwID, _p; uint64_t hwnd; int16_t px, py; uint32_t inst, seq; uint64_t args; uint32_t cbExtra, _q; } GestInfo;
_Static_assert(sizeof(TouchIn) == 48 && sizeof(GestInfo) == 56, "win64 layout");
static int g_g6_log[64]; static int64_t g_g6_w[64], g_g6_l[64]; static int g_g6_n;
static uint16_t g_g6_comp[64], g_g6_res[64]; static int g_g6_complen, g_g6_reslen, g_g6_cursor;
static int g_g6_touchn; static uint32_t g_g6_tflags[10], g_g6_tid[10]; static int32_t g_g6_tx[10];
static int g_g6_gid[16], g_g6_gfl[16], g_g6_gn; static uint64_t g_g6_garg[16];
static int64_t g6proc(int64_t h, int64_t m, int64_t w, int64_t l) {
  if (m == 0x10D || m == 0x10E || m == 0x10F || m == 0x240 || m == 0x119 || m == WM_LBUTTONDOWN || m == WM_LBUTTONUP || m == WM_MOUSEMOVE || m == WM_CAPTURECHANGED) {
    if (g_g6_n < 64) { g_g6_log[g_g6_n] = (int)m; g_g6_w[g_g6_n] = w; g_g6_l[g_g6_n] = l; g_g6_n++; }
  }
  if (m == 0x10F) {
    int64_t himc = ImmGetContext(h);
    if (l & 0x8) { g_g6_complen = (int)ImmGetCompositionStringW(himc, 0x8, PTR(g_g6_comp), sizeof g_g6_comp); g_g6_cursor = (int)ImmGetCompositionStringW(himc, 0x80, 0, 0); }
    if (l & 0x800) g_g6_reslen = (int)ImmGetCompositionStringW(himc, 0x800, PTR(g_g6_res), sizeof g_g6_res);
    ImmReleaseContext(h, himc);
    return 0;
  }
  if (m == 0x240) {
    TouchIn ti[10]; memset(ti, 0, sizeof ti);
    g_g6_touchn = (int)w; GetTouchInputInfo(l, w, PTR(ti), sizeof(TouchIn));
    for (int i = 0; i < g_g6_touchn && i < 10; i++) { g_g6_tflags[i] = ti[i].flags; g_g6_tid[i] = ti[i].id; g_g6_tx[i] = ti[i].x; }
    CloseTouchInputHandle(l); return 0;
  }
  if (m == 0x119) {
    GestInfo gi; memset(&gi, 0, sizeof gi); gi.cbSize = sizeof gi;
    if (GetGestureInfo(l, PTR(&gi)) && g_g6_gn < 16) { g_g6_gid[g_g6_gn] = (int)gi.dwID; g_g6_gfl[g_g6_gn] = (int)gi.dwFlags; g_g6_garg[g_g6_gn] = gi.args; g_g6_gn++; }
    CloseGestureInfoHandle(l); return 0;
  }
  if (m == WM_USER + 9) return 4242;
  return DefWindowProcA(h, m, w, l);
}
static void g6_drain(int64_t h) { WMSG m; (void)h; while (PeekMessageA(PTR(&m), 0, 0, 0, PM_REMOVE)) { TranslateMessage(PTR(&m)); DispatchMessageA(PTR(&m)); } }
static void g6_ime(uint32_t phase, const uint16_t *s, int n, int cursor) {   /* host (gui.ts imeRecords) と同じ分割 */
  int off = 0, rec = 0;
  do {
    int k = n - off > 4 ? 4 : n - off; uint32_t u[4] = { 0, 0, 0, 0 }; for (int i = 0; i < k; i++) u[i] = s[off + i];
    int lastrec = off + k >= n;
    gui_hl_input(GUI_IN_IME, 0, (int32_t)(u[0] | (u[1] << 16)), (int32_t)(u[2] | (u[3] << 16)), phase | ((uint32_t)k << 8) | (rec == 0 ? 1u << 12 : 0) | (lastrec ? 1u << 13 : 0), (uint32_t)cursor);
    off += k; rec++;
  } while (off < n);
}
static void run_gui6(void) {
  SECTION("GUI-6: keyboard layouts (US/DE/FR) MapVirtualKey / ToUnicode / GetKeyboardLayout");
  uint8_t st[256]; uint16_t o[8]; memset(st, 0, sizeof st);
  CHK(GetKeyboardLayout(0) == 0x04090409 && MapVirtualKeyW(0x41, 0) == 0x1E && MapVirtualKeyW(0x1E, 1) == 0x41, "US default: VK_A <-> sc 0x1E");
  CHK(MapVirtualKeyW('Z', 0) == 0x2C && MapVirtualKeyW(0x2C, 1) == 'Z', "US: Z at scan 0x2C");
  CHK(MapVirtualKeyW(0xBC, 2) == ',' && MapVirtualKeyW('A', 2) == 'A', "US MAPVK_VK_TO_CHAR (letters upper-case)");
  gui_hl_input(GUI_IN_LAYOUT, 0, 0, 0, 0x0407, 0);   /* DE */
  /* GUI_IN_LAYOUT は入力リング経由: GUI スレッドで消費されるまで pump */
  { WMSG m; for (int i = 0; i < 50 && GetKeyboardLayout(0) != 0x04070407; i++) { PeekMessageA(PTR(&m), 0, 0, 0, PM_REMOVE); gui_futex_wait(&gui_shared_native()->doorbell, gui_shared_native()->doorbell, 5); } }
  CHK(GetKeyboardLayout(0) == 0x04070407, "DE layout applied via input ring");
  CHK(MapVirtualKeyW(0x2C, 1) == 'Y' && MapVirtualKeyW(0x15, 1) == 'Z', "DE: scan 0x2C -> VK_Y, scan 0x15 -> VK_Z (QWERTZ)");
  CHK(MapVirtualKeyW('Z', 0) == 0x15 && MapVirtualKeyW('Y', 0) == 0x2C, "DE: VK_Z -> sc 0x15, VK_Y -> sc 0x2C");
  CHK(MapVirtualKeyW('Q', 2) == 'Q' && MapVirtualKeyW('Z', 2) == 'Z' && MapVirtualKeyW('M', 2) == 'M', "DE MAPVK_VK_TO_CHAR letters upper-case (Q,Z,M)");
  CHK(ToUnicode('Z', 0x15, PTR(st), PTR(o), 4, 0) == 1 && o[0] == 'z', "DE: sc 0x15 -> 'z'");
  st[VK_SHIFT] = 0x80; CHK(ToUnicode('Z', 0x15, PTR(st), PTR(o), 4, 0) == 1 && o[0] == 'Z', "DE: Shift sc 0x15 -> 'Z'");
  CHK(ToUnicode('2', 0x03, PTR(st), PTR(o), 4, 0) == 1 && o[0] == '"', "DE: Shift+2 -> '\"'");
  memset(st, 0, sizeof st);
  CHK(ToUnicode(0xBA, 0x1A, PTR(st), PTR(o), 4, 0) == 1 && o[0] == 0xFC, "DE: sc 0x1A -> u-umlaut");
  st[VK_SHIFT] = 0x80; CHK(ToUnicode(0xBA, 0x1A, PTR(st), PTR(o), 4, 0) == 1 && o[0] == 0xDC, "DE: Shift sc 0x1A -> U-umlaut");
  memset(st, 0, sizeof st); st[VK_CONTROL] = 0x80; st[VK_MENU] = 0x80;
  CHK(ToUnicode('Q', 0x10, PTR(st), PTR(o), 4, 0) == 1 && o[0] == '@', "DE: AltGr+Q -> '@'");
  CHK(ToUnicode('E', 0x12, PTR(st), PTR(o), 4, 0) == 1 && o[0] == 0x20AC, "DE: AltGr+E -> euro");
  CHK(ToUnicode('7', 0x08, PTR(st), PTR(o), 4, 0) == 1 && o[0] == '{', "DE: AltGr+7 -> '{'");
  memset(st, 0, sizeof st); CHK(ToUnicode(0xE2, 0x56, PTR(st), PTR(o), 4, 0) == 1 && o[0] == '<', "DE: ISO key sc 0x56 -> '<'");
  uint16_t nm[16]; GetKeyboardLayoutNameW(PTR(nm)); CHK(u16eq(nm, "00000407"), "DE: GetKeyboardLayoutNameW 00000407");
  gui_hl_input(GUI_IN_LAYOUT, 0, 0, 0, 0x040C, 0);   /* FR */
  { WMSG m; for (int i = 0; i < 50 && GetKeyboardLayout(0) != 0x040C040C; i++) { PeekMessageA(PTR(&m), 0, 0, 0, PM_REMOVE); gui_futex_wait(&gui_shared_native()->doorbell, gui_shared_native()->doorbell, 5); } }
  CHK(GetKeyboardLayout(0) == 0x040C040C, "FR layout applied");
  CHK(MapVirtualKeyW(0x10, 1) == 'A' && MapVirtualKeyW(0x1E, 1) == 'Q' && MapVirtualKeyW(0x2C, 1) == 'W', "FR: AZERTY scan 0x10 -> A, 0x1E -> Q, 0x2C -> W");
  CHK(MapVirtualKeyW('A', 2) == 'A' && MapVirtualKeyW('Q', 2) == 'Q' && MapVirtualKeyW('W', 2) == 'W', "FR MAPVK_VK_TO_CHAR letters upper-case (A,Q,W)");
  CHK(ToUnicode('A', 0x10, PTR(st), PTR(o), 4, 0) == 1 && o[0] == 'a', "FR: sc 0x10 -> 'a'");
  CHK(ToUnicode('1', 0x02, PTR(st), PTR(o), 4, 0) == 1 && o[0] == '&', "FR: unshifted digit row sc 0x02 -> '&'");
  st[VK_SHIFT] = 0x80; CHK(ToUnicode('1', 0x02, PTR(st), PTR(o), 4, 0) == 1 && o[0] == '1', "FR: Shift sc 0x02 -> '1'");
  memset(st, 0, sizeof st); CHK(ToUnicode('0', 0x0B, PTR(st), PTR(o), 4, 0) == 1 && o[0] == 0xE0, "FR: sc 0x0B -> a-grave");
  memset(st, 0, sizeof st); st[0x14] = 1; CHK(ToUnicode('2', 0x03, PTR(st), PTR(o), 4, 0) == 1 && o[0] == 0xE9, "FR: Caps on digit-row e-acute stays e-acute (documented approximation: no shift-lock on digit row)");
  CHK(ToUnicode('A', 0x10, PTR(st), PTR(o), 4, 0) == 1 && o[0] == 'A', "FR: Caps sc 0x10 -> 'A'");
  uint16_t k409[9] = { '0','0','0','0','0','4','0','9',0 }, k411[9] = { '0','0','0','0','0','4','1','1',0 };
  CHK(LoadKeyboardLayoutW(PTR(k409), 0) == 0x04090409, "LoadKeyboardLayoutW(00000409) returns US HKL");
  CHK(LoadKeyboardLayoutW(PTR(k411), 0) == 0, "LoadKeyboardLayoutW(unsupported JP) fails (0), not silently US");
  ActivateKeyboardLayout(0x04090409, 0);
  CHK(GetKeyboardLayout(0) == 0x04090409 && MapVirtualKeyW(0x2C, 1) == 'Z', "ActivateKeyboardLayout(US) restores QWERTY");

  SECTION("GUI-6: scancode -> VK from the input ring uses the layout (KEY_DOWN physical key)");
  { int64_t cls = reg("G6", 0, 6); (void)cls; }
  WWNDCLASS wc; memset(&wc, 0, sizeof wc);
  int64_t h = CreateWindowExA(0, PTR("G6"), PTR("g6"), WS_POPUP | WS_VISIBLE, 0, 0, 200, 150, 0, 0, 0x400000, 0);
  CHK(h != 0, "G6 window");
  { WMSG m; SetWindowLongPtrA(h, GWLP_WNDPROC, (int64_t)(uintptr_t)g6proc); while (PeekMessageA(PTR(&m), 0, 0, 0, PM_REMOVE)) DispatchMessageA(PTR(&m)); }
  /* 注意: reg() は tproc を登録済み; g6proc へ差し替え */
  gui_hl_input(GUI_IN_LAYOUT, 0, 0, 0, 0x0407, 0);
  gui_hl_input(GUI_IN_KEY_DOWN, 0, 0, 0, 'Y' /* host は code=KeyY → VK 'Y' を送る */, (0x15u << 8));   /* 物理 sc 0x15 (US では Y) */
  { WMSG m; int got = 0; for (int i = 0; i < 100 && !got; i++) { if (PeekMessageA(PTR(&m), 0, WM_KEYDOWN, WM_KEYDOWN, PM_REMOVE)) { got = 1; CHK(m.wParam == 'Z', "DE: physical sc 0x15 (host sent VK 'Y') arrives as VK 'Z': got 0x%llx", (unsigned long long)m.wParam); } else gui_futex_wait(&gui_shared_native()->doorbell, gui_shared_native()->doorbell, 5); } CHK(got, "KEYDOWN delivered"); }
  gui_hl_input(GUI_IN_LAYOUT, 0, 0, 0, 0x0409, 0);

  SECTION("GUI-6: IME composition -> WM_IME_STARTCOMPOSITION / COMPOSITION / ENDCOMPOSITION + imm32");
  g_g6_n = 0;
  CHK(ImmGetContext(h) == 0x7D000001 && ImmGetContext(0) == 0, "ImmGetContext: valid window -> HIMC, NULL window -> 0");
  CHK(ImmIsIME(0x04110411) == 1, "ImmIsIME");
  uint16_t ka[3] = { 0x304B, 0x3093, 0x3058 };   /* かんじ */
  g6_ime(1, NULL, 0, 0);
  g6_ime(2, ka, 3, 2);
  uint16_t kj[2] = { 0x6F22, 0x5B57 };              /* 漢字 (確定) */
  g6_ime(3, kj, 2, 0);
  { uint32_t t0 = gui_now_ms(); while (g_g6_n < 4 && gui_now_ms() - t0 < 3000) { g6_drain(h); gui_futex_wait(&gui_shared_native()->doorbell, gui_shared_native()->doorbell, 5); } }
  CHK(g_g6_n == 4 && g_g6_log[0] == 0x10D && g_g6_log[1] == 0x10F && g_g6_log[2] == 0x10F && g_g6_log[3] == 0x10E, "message order START, COMP, COMP(result), END (n=%d: %x %x %x %x)", g_g6_n, g_g6_log[0], g_g6_log[1], g_g6_log[2], g_g6_log[3]);
  CHK(g_g6_l[1] == (0x8 | 0x80) && g_g6_l[2] == 0x800, "lParam GCS_COMPSTR|GCS_CURSORPOS then GCS_RESULTSTR (0x%llx, 0x%llx)", (long long)g_g6_l[1], (long long)g_g6_l[2]);
  CHK(g_g6_complen == 6 && g_g6_comp[0] == 0x304B && g_g6_comp[1] == 0x3093 && g_g6_comp[2] == 0x3058 && g_g6_cursor == 2, "ImmGetCompositionStringW(COMPSTR) = かんじ, 6 bytes, cursor 2 (len %d cur %d)", g_g6_complen, g_g6_cursor);
  CHK(g_g6_reslen == 4 && g_g6_res[0] == 0x6F22 && g_g6_res[1] == 0x5B57, "ImmGetCompositionStringW(RESULTSTR) = 漢字, 4 bytes (len %d)", g_g6_reslen);
  CHK(ImmGetCompositionStringW(0x7D000001, 0x8, 0, 0) == 0, "after commit COMPSTR is empty (size query = 0)");
  /* 6 UTF-16 (2 レコード) の分割/連結 */
  g_g6_n = 0; uint16_t six[6] = { 0x3042, 0x3044, 0x3046, 0x3048, 0x304A, 0x304B };
  g6_ime(2, six, 6, 6);
  { uint32_t t0 = gui_now_ms(); while (g_g6_n < 2 && gui_now_ms() - t0 < 3000) { g6_drain(h); gui_futex_wait(&gui_shared_native()->doorbell, gui_shared_native()->doorbell, 5); } }
  CHK(g_g6_n == 2 && g_g6_log[0] == 0x10D && g_g6_log[1] == 0x10F && g_g6_complen == 12 && g_g6_comp[5] == 0x304B, "composition split over 2 input records is reassembled (6 units, 12 bytes; implicit START when update comes first)");
  g_g6_n = 0; g6_ime(4, NULL, 0, 0);
  { uint32_t t0 = gui_now_ms(); while (g_g6_n < 2 && gui_now_ms() - t0 < 3000) { g6_drain(h); gui_futex_wait(&gui_shared_native()->doorbell, gui_shared_native()->doorbell, 5); } }
  CHK(g_g6_n == 2 && g_g6_log[0] == 0x10F && g_g6_l[0] == 0 && g_g6_log[1] == 0x10E && ImmGetCompositionStringW(0x7D000001, 0x8, 0, 0) == 0, "cancel: COMPOSITION(lParam 0) + END, composition cleared");
  g_g6_n = 0; g6_ime(4, NULL, 0, 0);   /* composition 中でない cancel は何も送らない */
  { uint32_t t0 = gui_now_ms(); while (gui_now_ms() - t0 < 150) { g6_drain(h); gui_futex_wait(&gui_shared_native()->doorbell, gui_shared_native()->doorbell, 5); } }
  CHK(g_g6_n == 0, "cancel while not composing sends no WM_IME_* (n=%d)", g_g6_n);
  { int32_t cf[6] = { 2, 0, 0, 0, 0, 0 }; cf[1] = 10; cf[2] = 20; CHK(ImmSetCompositionWindow(0x7D000001, PTR(cf)) == 1, "ImmSetCompositionWindow"); }
  { int32_t cf[4] = { 0, 0x10, 30, 40 }; CHK(ImmSetCandidateWindow(0x7D000001, PTR(cf)) == 1, "ImmSetCandidateWindow"); }
  CHK(ImmSetOpenStatus(0x7D000001, 0) == 1 && ImmGetOpenStatus(0x7D000001) == 0 && ImmSetOpenStatus(0x7D000001, 1) == 1 && ImmGetOpenStatus(0x7D000001) == 1, "ImmSetOpenStatus round trip");
  { uint32_t cv = 0, sn = 9; CHK(ImmGetConversionStatus(0x7D000001, PTR(&cv), PTR(&sn)) == 1 && cv == 1 && sn == 0, "ImmGetConversionStatus"); }
  CHK(ImmGetCompositionStringW(0xBAD, 0x8, 0, 0) == -1 && ImmSetOpenStatus(0xBAD, 1) == 0, "invalid HIMC rejected (-1 / 0)");

  SECTION("GUI-6: touch -> WM_TOUCH / WM_GESTURE (zoom; GID_PAN は未検証) / mouse promotion");
  g_g6_n = 0;
  /* 未登録窓: primary 接触がマウスへ昇格 */
  gui_hl_input(GUI_IN_TOUCH, 0, 50, 60, 1u | (0u << 8) | (1u << 12), 0);
  gui_hl_input(GUI_IN_TOUCH, 0, 55, 62, 1u | (1u << 8) | (1u << 12), 0);
  gui_hl_input(GUI_IN_TOUCH, 0, 55, 62, 1u | (2u << 8) | (1u << 12), 0);
  { uint32_t t0 = gui_now_ms(); int sawup = 0; while (!sawup && gui_now_ms() - t0 < 3000) { g6_drain(h); for (int i = 0; i < g_g6_n; i++) if (g_g6_log[i] == WM_LBUTTONUP) sawup = 1; if (!sawup) gui_futex_wait(&gui_shared_native()->doorbell, gui_shared_native()->doorbell, 5); } }
  { int d = 0, u = 0, mv = 0; for (int i = 0; i < g_g6_n; i++) { d += g_g6_log[i] == WM_LBUTTONDOWN; u += g_g6_log[i] == WM_LBUTTONUP; mv += g_g6_log[i] == WM_MOUSEMOVE; }
    CHK(d == 1 && u == 1 && mv >= 1, "unregistered window: touch promoted to LBUTTONDOWN/MOUSEMOVE/LBUTTONUP (d=%d mv=%d u=%d)", d, mv, u); }
  CHK(RegisterTouchWindow(h, 0) == 1 && RegisterTouchWindow(0xDEAD, 0) == 0, "RegisterTouchWindow valid / invalid hwnd");
  { uint32_t gc[3] = { 3, 1, 0 }; CHK(SetGestureConfig(h, 0, 1, PTR(gc), 12) == 1 && SetGestureConfig(h, 0, 1, PTR(gc), 8) == 0, "SetGestureConfig (GID_ZOOM=3 GC_ZOOM=1; cbSize 12 ok / 8 rejected)"); }
  { uint32_t ga[3] = { 0, 1, 0 }; CHK(SetGestureConfig(h, 0, 1, PTR(ga), 12) == 1, "SetGestureConfig dwID=0 GC_ALLGESTURES (all gestures enabled)"); }
  g_g6_n = 0; g_g6_gn = 0;
  gui_hl_input(GUI_IN_TOUCH, 0, 70, 80, 7u | (0u << 8) | (1u << 12), 0);
  gui_hl_input(GUI_IN_TOUCH, 0, 120, 80, 8u | (0u << 8), 0);
  { uint32_t t0 = gui_now_ms(); while ((g_g6_n < 3 || g_g6_gn < 1) && gui_now_ms() - t0 < 3000) { g6_drain(h); gui_futex_wait(&gui_shared_native()->doorbell, gui_shared_native()->doorbell, 5); } }
  { int nt = 0, nm = 0; for (int i = 0; i < g_g6_n; i++) { nt += g_g6_log[i] == 0x240; nm += g_g6_log[i] == WM_LBUTTONDOWN || g_g6_log[i] == WM_MOUSEMOVE; }
    CHK(nt == 2 && nm == 0, "registered window gets one WM_TOUCH per touch event and no mouse promotion (WM_TOUCH=%d mouse=%d)", nt, nm); }
  CHK(g_g6_touchn == 2 && g_g6_tid[0] == 7 && g_g6_tid[1] == 8 && g_g6_tx[1] == 12000 && (g_g6_tflags[1] & 0x2) && (g_g6_tflags[0] & 0x10), "GetTouchInputInfo: 2 contacts, ids 7/8, x=120.00 px in 1/100 px, DOWN flag on #2, primary flag on #1 (n=%d x=%d fl0=%x fl1=%x)", g_g6_touchn, g_g6_tx[1], g_g6_tflags[0], g_g6_tflags[1]);
  CHK(g_g6_gn == 1 && g_g6_gid[0] == 3 && (g_g6_gfl[0] & 1) && g_g6_garg[0] == 50, "WM_GESTURE GID_ZOOM GF_BEGIN with distance 50 px (n=%d id=%d fl=%d arg=%llu)", g_g6_gn, g_g6_gid[0], g_g6_gfl[0], (unsigned long long)g_g6_garg[0]);
  gui_hl_input(GUI_IN_TOUCH, 0, 90, 80, 8u | (1u << 8), 0);
  gui_hl_input(GUI_IN_TOUCH, 0, 80, 80, 8u | (1u << 8), 0);
  { uint32_t t0 = gui_now_ms(); while (g_g6_gn < 3 && gui_now_ms() - t0 < 3000) { g6_drain(h); gui_futex_wait(&gui_shared_native()->doorbell, gui_shared_native()->doorbell, 5); } }
  CHK(g_g6_gn == 3 && g_g6_gid[1] == 3 && g_g6_garg[1] == 20 && g_g6_garg[2] == 10 && !(g_g6_gfl[2] & 5), "zoom updates carry distance 20 then 10 px, no BEGIN/END flags (n=%d %llu %llu)", g_g6_gn, (unsigned long long)g_g6_garg[1], (unsigned long long)g_g6_garg[2]);
  gui_hl_input(GUI_IN_TOUCH, 0, 80, 80, 8u | (2u << 8), 0);
  { uint32_t t0 = gui_now_ms(); while (g_g6_gn < 4 && gui_now_ms() - t0 < 3000) { g6_drain(h); gui_futex_wait(&gui_shared_native()->doorbell, gui_shared_native()->doorbell, 5); } }
  CHK(g_g6_gn == 4 && g_g6_gid[3] == 3 && (g_g6_gfl[3] & 4), "GF_END delivered when one of the two contacts lifts (n=%d fl=%d)", g_g6_gn, g_g6_gfl[3]);
  gui_hl_input(GUI_IN_TOUCH, 0, 70, 80, 7u | (2u << 8), 0);
  g6_drain(h);
  GestInfo bad = { sizeof(GestInfo) }; CHK(GetGestureInfo(0x1234, PTR(&bad)) == 0, "GetGestureInfo with a bad handle fails");

  SECTION("GUI-6: Pointer Lock request (ShowCursor(FALSE)+capture) / SetCursorPos / ClipCursor");
  { GuiShared *S = gui_shared_native(); uint32_t before = S->out_pushed;
    WRECT cr = { 10, 10, 110, 90 }; CHK(ClipCursor(PTR(&cr)) == 1, "ClipCursor");
    WRECT got; GetClipCursor(PTR(&got)); CHK(got.left == 10 && got.top == 10 && got.right == 110 && got.bottom == 90, "GetClipCursor returns the clip rect");
    SetCursorPos(500, -5); WPOINT p; GetCursorPos(PTR(&p)); CHK(p.x == 109 && p.y == 10, "SetCursorPos clamps to ClipCursor rect: (%d,%d)", p.x, p.y);
    SetCursorPos(50, 50); GetCursorPos(PTR(&p)); CHK(p.x == 50 && p.y == 50, "SetCursorPos inside rect unchanged");
    CHK(ClipCursor(0) == 1, "ClipCursor(NULL) releases"); GetClipCursor(PTR(&got)); CHK(got.right == 640 && got.bottom == 480, "released -> screen rect");
    SetCursorPos(500, 400); GetCursorPos(PTR(&p)); CHK(p.x == 500 && p.y == 400, "no clip -> unclamped");
    WRECT bad = { 5, 5, 5, 5 }; CHK(ClipCursor(PTR(&bad)) == 0, "empty rect rejected");
    CHK(S->out_pushed > before, "CLIP_RECT commands emitted");
    ShowCursor(0);   /* 非表示 (カウンタ -1) */
    uint32_t p0 = S->out_pushed;
    SetCapture(h);   /* 非表示 + capture → POINTER_LOCK 要求を 1 回 push */
    uint32_t p1 = S->out_pushed;
    gui_hl_input(GUI_IN_POINTER_LOCK, 0, 0, 0, 1, 0);
    { uint32_t t0 = gui_now_ms(); while (gui_now_ms() - t0 < 200) { g6_drain(h); gui_futex_wait(&S->doorbell, S->doorbell, 5); } }
    ReleaseCapture();   /* 解除 → POINTER_LOCK 解除 (w2=0) を 1 回 push */
    uint32_t p2 = S->out_pushed;
    while (ShowCursor(1) < 0) {}   /* 表示に戻す: 既に解除済みなので push なし */
    uint32_t p3 = S->out_pushed;
    CHK(p1 - p0 == 1 && p2 - p1 == 1 && p3 == p2, "Pointer Lock request: SetCapture with hidden cursor pushes one POINTER_LOCK, ReleaseCapture pushes one, ShowCursor(TRUE) none (push %u/%u/%u)", p1 - p0, p2 - p1, p3 - p2);
  }
  DestroyWindow(h);
}
