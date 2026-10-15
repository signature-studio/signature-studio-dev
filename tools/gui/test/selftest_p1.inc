/* selftest_p1.inc — CAB-159: P1 未実装 50 名 (+前倒しの CreateCaret) の unit テスト。selftest.c から #include (CHK/desk/flush_wait 等を共有)。
 * 各 API は `NAME(` の形で最低 1 回登場すること (integ/check_p1_tests.py が p1_batch.txt と突合して機械検査)。 */
extern int64_t GetLastError_gui(void);
extern int gui_beep_count(void);
extern int gui_caret_state(int *x, int *y, int *hide, int *drawn);
#define PTR(x) ((int64_t)(uintptr_t)(x))
static uint32_t cr2px(uint32_t c) { return ((c & 0xFF) << 16) | (c & 0xFF00) | ((c >> 16) & 0xFF); }   /* COLORREF -> 0xRRGGBB */
static uint32_t SC(int idx) { return cr2px((uint32_t)GetSysColor(idx)); }
static void u16s(uint16_t *d, const char *s) { while ((*d++ = (uint8_t)*s++)) {} }
static int u16eq(const uint16_t *a, const char *s) { while (*a && *s) { if (*a++ != (uint8_t)*s++) return 0; } return *a == 0 && *s == 0; }

/* ---- p1 用ウィンドウプロシージャ ---- */
static int g_destroyclip, g_renderfmt;
static int64_t p1proc(int64_t h, int64_t m, int64_t w, int64_t l) {
  if (m == 0x305) { g_renderfmt++; SetClipboardData(w, 0x777); return 0; }   /* WM_RENDERFORMAT */
  if (m == 0x307) { g_destroyclip++; return 0; }                              /* WM_DESTROYCLIPBOARD */
  if (m == WM_USER + 9) return 4242;
  if (m == WM_PAINT) { WPAINTSTRUCT ps; BeginPaint(h, PTR(&ps)); EndPaint(h, PTR(&ps)); return 0; }   /* 背景消去 (WM_ERASEBKGND) は BeginPaint で走る */
  return DefWindowProcA(h, m, w, l);
}
static void *clip_thread(void *a) { (void)a; int64_t r = OpenClipboard(0); int64_t e = GetLastError_gui(); if (r) CloseClipboard(); return (void *)(intptr_t)(r ? 100 : (int)e); }

/* ---- フック proc (lift ABI: code, wParam, lParam) ---- */
static int g_hk_a, g_hk_b, g_hk_gm_msg, g_hk_cwp_msg, g_hk_cwp_wp, g_hk_ret_res, g_hk_kb, g_hk_mouse, g_hk_kb_vk, g_hk_mouse_x, g_hk_kb_block, g_hk_mouse_block;
static int64_t hk_a(int64_t code, int64_t wp, int64_t lp) { g_hk_a++; return CallNextHookEx(0, code, wp, lp); }
static int64_t hk_b(int64_t code, int64_t wp, int64_t lp) { g_hk_b++; return CallNextHookEx(0, code, wp, lp); }
static int64_t hk_gm(int64_t code, int64_t wp, int64_t lp) { g_hk_gm_msg = (int)((WMSG *)(uintptr_t)lp)->message; g_hk_cwp_wp = (int)wp; (void)code; return 0; }
static int64_t hk_cwp(int64_t code, int64_t wp, int64_t lp) { const struct { int64_t lParam; uint64_t wParam; uint32_t message, pad; uint64_t hwnd; } *c = (const void *)(uintptr_t)lp; (void)code; g_hk_cwp_msg = (int)c->message; g_hk_cwp_wp = (int)wp; return 0; }
static int64_t hk_ret(int64_t code, int64_t wp, int64_t lp) { const struct { int64_t lResult, lParam; uint64_t wParam; uint32_t message, pad; uint64_t hwnd; } *c = (const void *)(uintptr_t)lp; (void)code; (void)wp; g_hk_ret_res = (int)c->lResult; return 0; }
static int64_t hk_kb(int64_t code, int64_t wp, int64_t lp) { (void)code; (void)lp; g_hk_kb++; g_hk_kb_vk = (int)wp; return g_hk_kb_block && wp == 'Q'; }
static int64_t hk_mouse(int64_t code, int64_t wp, int64_t lp) { const int32_t *pt = (const int32_t *)(uintptr_t)lp; (void)code; (void)wp; g_hk_mouse++; g_hk_mouse_x = pt[0]; return g_hk_mouse_block; }

/* ---- リソース供給 (LoadStringW/LoadBitmapW) ---- */
static uint16_t g_strblock[64]; static uint32_t g_dib[16]; static int g_res_calls;
static int res_prov(uint64_t hi, uint32_t type, uint32_t id, const void **data, uint32_t *size) {
  g_res_calls++;
  if (hi != 0x400000) return 0;
  if (type == 6 && id == 3) { *data = g_strblock; *size = sizeof g_strblock; return 1; }       /* RT_STRING ブロック 3 = ID 32..47 */
  if (type == 2 && id == 101) { *data = g_dib; *size = sizeof g_dib; return 1; }               /* RT_BITMAP 101 */
  return 0;
}
static int g_mon_calls; static int64_t g_mon_h, g_mon_dc, g_mon_data; static WRECT g_mon_rc; static int g_mon_ret = 1;
static int64_t mon_cb(int64_t hm, int64_t dc, int64_t prc, int64_t data) { g_mon_calls++; g_mon_h = hm; g_mon_dc = dc; g_mon_data = data; g_mon_rc = *(WRECT *)(uintptr_t)prc; return g_mon_ret; }

static void p1_drain(void) { WMSG m; while (PeekMessageA(PTR(&m), 0, 0, 0, PM_REMOVE)) { DispatchMessageA(PTR(&m)); } }
static int64_t new_dib(int w, int hgt, uint32_t **bits, int64_t *mdc, uint32_t fill) {
  WBMIH bi; memset(&bi, 0, sizeof bi); bi.biSize = 40; bi.biWidth = w; bi.biHeight = -hgt; bi.biPlanes = 1; bi.biBitCount = 32;
  uint64_t bp = 0; int64_t dib = CreateDIBSection(0, PTR(&bi), 0, PTR(&bp), 0, 0);
  *bits = (uint32_t *)(uintptr_t)bp; *mdc = CreateCompatibleDC(0); SelectObject(*mdc, dib);
  for (int i = 0; i < w * hgt; i++) (*bits)[i] = 0xFF000000u | fill;
  return dib;
}
#define PX(bits, w, x, y) (((bits)[(y) * (w) + (x)]) & 0xFFFFFF)

static void run_p1(int64_t keep_focus) {
  /* ================= util ================= */
  SECTION("P1/util: CharNextW CharUpperW CharUpperBuffW CharLowerBuffW LoadStringW MessageBeep");
  { uint16_t s[8]; u16s(s, "ab");
    CHK(CharNextW(PTR(s)) == PTR(s + 1), "CharNextW advances one unit");
    CHK(CharNextW(PTR(s + 2)) == PTR(s + 2), "CharNextW stays at NUL");
    uint16_t sp[4] = { 0xD83D, 0xDE00, 'x', 0 };
    CHK(CharNextW(PTR(sp)) == PTR(sp + 2), "CharNextW skips surrogate pair");
    CHK(CharUpperW('a') == 'A' && CharUpperW(0xE9) == 0xC9 && CharUpperW(0x3B1) == 0x391 && CharUpperW(0x430) == 0x410 && CharUpperW('Z') == 'Z' && CharUpperW('1') == '1',
        "CharUpperW single-char form (ASCII/Latin-1/Greek/Cyrillic)");
    uint16_t t[8] = { 'a', 'b', 'c', 0xE9, '9', 0 };
    CHK(CharUpperW(PTR(t)) == PTR(t) && t[0] == 'A' && t[1] == 'B' && t[2] == 'C' && t[3] == 0xC9 && t[4] == '9', "CharUpperW string in place returns pointer");
    uint16_t b1[8]; u16s(b1, "hello");
    CHK(CharUpperBuffW(PTR(b1), 5) == 5 && u16eq(b1, "HELLO"), "CharUpperBuffW full");
    u16s(b1, "hello");
    CHK(CharUpperBuffW(PTR(b1), 2) == 2 && u16eq(b1, "HEllo"), "CharUpperBuffW limited to n chars");
    uint16_t b2[8] = { 'A', 0xC9, 0x391, 0x410, 'Z', '5' };
    CHK(CharLowerBuffW(PTR(b2), 6) == 6 && b2[0] == 'a' && b2[1] == 0xE9 && b2[2] == 0x3B1 && b2[3] == 0x430 && b2[4] == 'z' && b2[5] == '5', "CharLowerBuffW"); }
  { /* RT_STRING ブロック: slot0 "abc", slot1 空, slot2 "xy" (ID 32/33/34) */
    memset(g_strblock, 0, sizeof g_strblock); int k = 0;
    g_strblock[k++] = 3; g_strblock[k++] = 'a'; g_strblock[k++] = 'b'; g_strblock[k++] = 'c'; g_strblock[k++] = 0; g_strblock[k++] = 2; g_strblock[k++] = 'x'; g_strblock[k++] = 'y';
    uint16_t buf[8]; memset(buf, 0xAA, sizeof buf);
    CHK(LoadStringW(0x400000, 32, PTR(buf), 8) == 0 && GetLastError_gui() == 1814 && buf[0] == 0, "LoadStringW without provider: 0 + ERROR_RESOURCE_NAME_NOT_FOUND, buf[0]=0");
    gui_set_resource_provider(res_prov);
    CHK(LoadStringW(0x400000, 32, PTR(buf), 8) == 3 && u16eq(buf, "abc"), "LoadStringW slot0");
    CHK(LoadStringW(0x400000, 34, PTR(buf), 8) == 2 && u16eq(buf, "xy"), "LoadStringW slot2 (skips empty slot)");
    CHK(LoadStringW(0x400000, 32, PTR(buf), 3) == 2 && u16eq(buf, "ab"), "LoadStringW truncates to cch-1 and NUL-terminates");
    CHK(LoadStringW(0x400000, 33, PTR(buf), 8) == 0 && GetLastError_gui() == 1814, "LoadStringW empty slot = not found");
    CHK(LoadStringW(0x400000, 40, PTR(buf), 8) == 0 && LoadStringW(0x999, 32, PTR(buf), 8) == 0, "LoadStringW missing id / wrong module");
    uint16_t *rp = NULL;
    CHK(LoadStringW(0x400000, 32, PTR(&rp), 0) == 3 && rp == &g_strblock[1], "LoadStringW cch==0 returns read-only pointer into the resource"); }
  { int c0 = gui_beep_count(); CHK(MessageBeep(0xFFFFFFFF) == 1 && MessageBeep(0x10) == 1 && gui_beep_count() == c0 + 2, "MessageBeep returns TRUE and is counted"); }

  /* ================= touch ================= */
  SECTION("P1/touch: EvaluateProximityToRect PackTouchHitTestingProximityEvaluation");
  { WRECT rc = { 0, 0, 100, 100 };
    int32_t in[12]; memset(in, 0, sizeof in); in[1] = 50; in[2] = 50; in[3] = 40; in[4] = 40; in[5] = 60; in[6] = 60;     /* point(50,50) bbox 20x20 */
    uint8_t ev[12] = { 0 };
    CHK(EvaluateProximityToRect(PTR(&rc), PTR(in), PTR(ev)) == 1 && *(uint16_t *)ev == 65535 && ((int32_t *)ev)[1] == 50 && ((int32_t *)ev)[2] == 50, "inside: score 65535, point unchanged");
    in[1] = 105; in[3] = 95; in[5] = 115;     /* bbox 20 wide -> reach 10; 点は右に 6 px はみ出し (最近傍 x=99) */
    EvaluateProximityToRect(PTR(&rc), PTR(in), PTR(ev));
    CHK(*(uint16_t *)ev == 26214 && ((int32_t *)ev)[1] == 99 && ((int32_t *)ev)[2] == 50, "outside: linear falloff (%u), adjusted to nearest edge (%d,%d)", *(uint16_t *)ev, ((int32_t *)ev)[1], ((int32_t *)ev)[2]);
    in[1] = 130; EvaluateProximityToRect(PTR(&rc), PTR(in), PTR(ev));
    CHK(*(uint16_t *)ev == 0, "far: score 0");
    in[1] = 105; EvaluateProximityToRect(PTR(&rc), PTR(in), PTR(ev));
    int64_t packed = PackTouchHitTestingProximityEvaluation(PTR(in), PTR(ev));
    CHK((packed & 0xFFFF) == 26214 && ((packed >> 16) & 0xFFFF) == (uint32_t)(99 - 95) && ((packed >> 32) & 0xFFFF) == (uint32_t)(50 - 40), "Pack: score | adjusted point relative to bbox origin (0x%llx)", (long long)packed);
    CHK(EvaluateProximityToRect(0, PTR(in), PTR(ev)) == 0 && GetLastError_gui() == 87, "NULL arg -> FALSE/ERROR_INVALID_PARAMETER"); }

  /* ================= GDI: 枠/フレーム/フォーカス ================= */
  SECTION("P1/gdi: DrawEdge DrawFrameControl DrawFocusRect");
  { uint32_t *bits; int64_t mdc; int64_t dib = new_dib(40, 40, &bits, &mdc, 0x123456);
    WRECT r = { 2, 2, 12, 12 };
    CHK(DrawEdge(mdc, PTR(&r), 5 /*EDGE_RAISED*/, 15 /*BF_RECT*/) == 1, "DrawEdge returns TRUE");
    CHK(PX(bits, 40, 2, 5) == SC(22) && PX(bits, 40, 5, 2) == SC(22), "raised outer LT = COLOR_3DLIGHT");
    CHK(PX(bits, 40, 11, 5) == SC(21) && PX(bits, 40, 5, 11) == SC(21), "raised outer RB = COLOR_3DDKSHADOW");
    CHK(PX(bits, 40, 3, 5) == SC(20) && PX(bits, 40, 5, 3) == SC(20), "raised inner LT = COLOR_BTNHIGHLIGHT");
    CHK(PX(bits, 40, 10, 5) == SC(16) && PX(bits, 40, 5, 10) == SC(16), "raised inner RB = COLOR_BTNSHADOW");
    CHK(PX(bits, 40, 11, 2) == SC(21) && PX(bits, 40, 2, 11) == SC(21), "TR and BL corner pixels take the RB colour");
    CHK(PX(bits, 40, 6, 6) == 0x123456, "interior untouched without BF_MIDDLE");
    r = (WRECT){ 14, 2, 24, 12 };
    DrawEdge(mdc, PTR(&r), 10 /*EDGE_SUNKEN*/, 15 | 0x800 /*BF_MIDDLE*/);
    CHK(PX(bits, 40, 14, 5) == SC(16) && PX(bits, 40, 15, 5) == SC(21) && PX(bits, 40, 23, 5) == SC(20) && PX(bits, 40, 22, 5) == SC(22), "sunken: outer LT shadow / inner LT dkshadow / outer RB hilight / inner RB light");
    CHK(PX(bits, 40, 18, 6) == SC(15), "BF_MIDDLE fills with COLOR_BTNFACE");
    r = (WRECT){ 2, 14, 12, 24 };
    DrawEdge(mdc, PTR(&r), 6 /*EDGE_ETCHED*/, 15);
    CHK(PX(bits, 40, 2, 18) == SC(16) && PX(bits, 40, 3, 18) == SC(20) && PX(bits, 40, 11, 18) == SC(20) && PX(bits, 40, 10, 18) == SC(16), "etched = sunken outer + raised inner");
    r = (WRECT){ 14, 14, 24, 24 };
    DrawEdge(mdc, PTR(&r), 5, 15 | 0x4000 /*BF_FLAT*/);
    CHK(PX(bits, 40, 14, 18) == SC(16) && PX(bits, 40, 15, 18) == SC(15), "BF_FLAT: outer BTNSHADOW, inner BTNFACE");
    r = (WRECT){ 26, 2, 36, 12 };
    DrawEdge(mdc, PTR(&r), 5, 2 /*BF_TOP*/);
    CHK(PX(bits, 40, 28, 2) == SC(22) && PX(bits, 40, 28, 3) == SC(20) && PX(bits, 40, 26, 6) == 0x123456 && PX(bits, 40, 28, 11) == 0x123456, "single-side edge draws only that side");
    r = (WRECT){ 26, 14, 36, 24 };
    WRECT before = r;
    DrawEdge(mdc, PTR(&r), 5, 15 | 0x2000 /*BF_ADJUST*/);
    CHK(r.left == before.left + 2 && r.top == before.top + 2 && r.right == before.right - 2 && r.bottom == before.bottom - 2, "BF_ADJUST shrinks the rect by both layers");
    CHK(DrawEdge(0x1234, PTR(&r), 5, 15) == 0, "invalid DC -> FALSE");
    DeleteDC(mdc); DeleteObject(dib); }
  { uint32_t *bits; int64_t mdc; int64_t dib = new_dib(80, 40, &bits, &mdc, 0xFFFFFF);
    WRECT r = { 0, 0, 20, 20 }, ref = { 40, 0, 60, 20 };
    CHK(DrawFrameControl(mdc, PTR(&r), 4 /*DFC_BUTTON*/, 0x10 /*PUSH*/) == 1, "DrawFrameControl DFC_BUTTON push");
    DrawEdge(mdc, PTR(&ref), 5, 15 | 0x800);
    int same = 1; for (int y = 0; y < 20; y++) for (int x = 0; x < 20; x++) if (PX(bits, 80, x, y) != PX(bits, 80, 40 + x, y)) same = 0;
    CHK(same, "push button == EDGE_RAISED|BF_MIDDLE");
    WRECT r2 = { 20, 0, 40, 20 };
    DrawFrameControl(mdc, PTR(&r2), 4, 0x10 | 0x200 /*PUSHED*/);
    CHK(PX(bits, 80, 20, 5) == SC(16) && PX(bits, 80, 39, 5) == SC(20), "pushed button uses the sunken edge");
    WRECT r3 = { 0, 20, 20, 40 };
    DrawFrameControl(mdc, PTR(&r3), 4, 0 /*CHECK*/);
    int dark = 0; for (int y = 20; y < 40; y++) for (int x = 0; x < 20; x++) if (PX(bits, 80, x, y) == SC(18)) dark++;
    CHK(dark == 0, "unchecked checkbox has no check mark");
    DrawFrameControl(mdc, PTR(&r3), 4, 0x400 /*CHECKED*/);
    dark = 0; for (int y = 20; y < 40; y++) for (int x = 0; x < 20; x++) if (PX(bits, 80, x, y) == SC(18)) dark++;
    CHK(dark >= 10, "checked checkbox draws a mark (%d px)", dark);
    WRECT r4 = { 20, 20, 40, 40 };
    DrawFrameControl(mdc, PTR(&r4), 4, 4 /*RADIO*/ | 0x400);
    CHK(PX(bits, 80, 30, 30) == SC(18) && PX(bits, 80, 26, 30) == SC(5), "checked radio: black dot at centre, white disc around");
    WRECT r5 = { 40, 20, 60, 40 };
    DrawFrameControl(mdc, PTR(&r5), 3 /*SCROLL*/, 0 /*UP*/);
    CHK(PX(bits, 80, 50, 28) == SC(18) && PX(bits, 80, 47, 28) != SC(18) && PX(bits, 80, 50, 31) == SC(18), "scroll-up arrow: apex at (50,28), widening below");
    WRECT r6 = { 60, 20, 80, 40 };
    DrawFrameControl(mdc, PTR(&r6), 1 /*CAPTION*/, 0 /*CLOSE*/);
    CHK(PX(bits, 80, 70, 30) == SC(18) && PX(bits, 80, 67, 27) == SC(18) && PX(bits, 80, 73, 27) == SC(18), "caption close glyph X");
    WRECT r7 = { 60, 0, 80, 20 };
    DrawFrameControl(mdc, PTR(&r7), 2 /*MENU*/, 0 /*ARROW*/);
    CHK(PX(bits, 80, 71, 10) == SC(18), "menu arrow glyph");
    CHK(DrawFrameControl(mdc, PTR(&r7), 99, 0) == 0 && GetLastError_gui() == 87, "unknown type -> FALSE/ERROR_INVALID_PARAMETER");
    DeleteDC(mdc); DeleteObject(dib); }
  { uint32_t *bits; int64_t mdc; int64_t dib = new_dib(16, 16, &bits, &mdc, 0xFFFFFF);
    WRECT r = { 2, 2, 10, 10 };
    CHK(DrawFocusRect(mdc, PTR(&r)) == 1, "DrawFocusRect returns TRUE");
    CHK(PX(bits, 16, 2, 2) == 0x000000 && PX(bits, 16, 3, 2) == 0xFFFFFF && PX(bits, 16, 4, 2) == 0x000000, "dotted: (x+y) even pixels inverted on the top edge");
    CHK(PX(bits, 16, 2, 4) == 0x000000 && PX(bits, 16, 9, 9) == 0x000000 && PX(bits, 16, 9, 8) == 0xFFFFFF, "left/bottom/right edges");
    CHK(PX(bits, 16, 5, 5) == 0xFFFFFF && PX(bits, 16, 1, 1) == 0xFFFFFF, "inside and outside untouched");
    DrawFocusRect(mdc, PTR(&r));
    int ok = 1; for (int i = 0; i < 256; i++) if (PX(bits, 16, i % 16, i / 16) != 0xFFFFFF) ok = 0;
    CHK(ok, "second DrawFocusRect restores the pixels (XOR toggle)");
    DeleteDC(mdc); DeleteObject(dib); }

  /* ================= GDI: リージョン / ブラシ原点 / DC / DDB ================= */
  SECTION("P1/gdi: GetClipRgn GetRandomRgn GetRegionData GetBrushOrgEx CreateDCW CreateDIBitmap");
  { uint32_t *bits; int64_t mdc; int64_t dib = new_dib(16, 16, &bits, &mdc, 0);
    int64_t rg = CreateRectRgn(0, 0, 1, 1); WRECT bb;
    CHK(GetClipRgn(mdc, rg) == 0, "GetClipRgn: no app clip -> 0");
    CHK(GetClipRgn(0x1234, rg) == -1 && GetClipRgn(mdc, 0x1234) == -1, "GetClipRgn invalid args -> -1");
    IntersectClipRect(mdc, 2, 3, 10, 12);
    CHK(GetClipRgn(mdc, rg) == 1, "GetClipRgn with clip -> 1");
    GetRgnBox(rg, PTR(&bb)); CHK(bb.left == 2 && bb.top == 3 && bb.right == 10 && bb.bottom == 12, "clip region box (%d,%d,%d,%d)", bb.left, bb.top, bb.right, bb.bottom);
    SetWindowOrgEx(mdc, 1, 1, 0);
    int64_t rg2 = CreateRectRgn(0, 0, 5, 5); SelectClipRgn(mdc, rg2);
    int64_t rg3 = CreateRectRgn(0, 0, 1, 1); GetClipRgn(mdc, rg3);
    CHK(EqualRgn(rg2, rg3), "GetClipRgn returns the region in logical coordinates (round trip with SelectClipRgn under a window origin)");
    SetWindowOrgEx(mdc, 0, 0, 0); SelectClipRgn(mdc, 0);
    int64_t rr = CreateRectRgn(0, 0, 1, 1);
    CHK(GetRandomRgn(mdc, rr, 4) == 1, "GetRandomRgn(SYSRGN) on memory DC");
    GetRgnBox(rr, PTR(&bb)); CHK(bb.left == 0 && bb.top == 0 && bb.right == 16 && bb.bottom == 16, "SYSRGN = bitmap rect");
    CHK(GetRandomRgn(mdc, rr, 1) == 0, "GetRandomRgn(CLIPRGN) without clip -> 0");
    IntersectClipRect(mdc, 4, 4, 8, 8);
    CHK(GetRandomRgn(mdc, rr, 1) == 1, "GetRandomRgn(CLIPRGN) with clip -> 1");
    GetRgnBox(rr, PTR(&bb)); CHK(bb.left == 4 && bb.right == 8, "CLIPRGN box");
    CHK(GetRandomRgn(mdc, rr, 2) == 0 && GetRandomRgn(mdc, rr, 3) == 0 && GetRandomRgn(0x1234, rr, 4) == -1, "METARGN/APIRGN -> 0, invalid DC -> -1");
    /* GetRegionData */
    int64_t ra = CreateRectRgn(20, 2, 30, 12), rb = CreateRectRgn(1, 2, 11, 12), ru = CreateRectRgn(0, 0, 1, 1);
    CombineRgn(ru, ra, rb, RGN_OR);
    CHK(GetRegionData(ru, 0, 0) == 32 + 2 * 16, "GetRegionData(NULL) returns the required size");
    uint32_t buf[32]; memset(buf, 0, sizeof buf);
    CHK(GetRegionData(ru, 10, PTR(buf)) == 0, "buffer too small -> 0");
    CHK(GetRegionData(ru, sizeof buf, PTR(buf)) == (int64_t)sizeof buf, "returns dwCount on success");
    CHK(buf[0] == 32 && buf[1] == 1 && buf[2] == 2 && buf[3] == 32, "RGNDATAHEADER dwSize/iType=RDH_RECTANGLES/nCount/nRgnSize");
    const WRECT *rc = (const WRECT *)(buf + 4); const WRECT *rs = (const WRECT *)(buf + 8);
    CHK(rc->left == 1 && rc->top == 2 && rc->right == 30 && rc->bottom == 12, "rcBound");
    CHK(rs[0].left == 1 && rs[0].right == 11 && rs[1].left == 20 && rs[1].right == 30, "rects sorted top,left");
    int64_t re = CreateRectRgn(0, 0, 0, 0); SetRectRgn(re, 5, 5, 5, 5); CombineRgn(re, re, re, RGN_DIFF);
    CHK(GetRegionData(re, 0, 0) == 32, "empty region: header only");
    CHK(GetRegionData(0x1234, 0, 0) == 0, "invalid region -> 0");
    /* ブラシ原点 */
    WPOINT bo = { 9, 9 };
    CHK(GetBrushOrgEx(mdc, PTR(&bo)) == 1 && bo.x == 0 && bo.y == 0, "GetBrushOrgEx default (0,0)");
    WPOINT old = { 9, 9 };
    CHK(SetBrushOrgEx(mdc, 3, 4, PTR(&old)) == 1 && old.x == 0 && old.y == 0, "SetBrushOrgEx returns the previous origin");
    GetBrushOrgEx(mdc, PTR(&bo)); CHK(bo.x == 3 && bo.y == 4, "GetBrushOrgEx after Set");
    SetBrushOrgEx(mdc, 7, 8, 0); int sv = (int)SaveDC(mdc); SetBrushOrgEx(mdc, 1, 1, 0); RestoreDC(mdc, sv);
    GetBrushOrgEx(mdc, PTR(&bo)); CHK(bo.x == 7 && bo.y == 8, "SaveDC/RestoreDC keeps the brush origin");
    CHK(GetBrushOrgEx(0x1234, PTR(&bo)) == 0, "invalid DC -> FALSE");
    DeleteObject(rg); DeleteObject(rg2); DeleteObject(rg3); DeleteObject(rr); DeleteObject(ra); DeleteObject(rb); DeleteObject(ru); DeleteObject(re);
    DeleteDC(mdc); DeleteObject(dib); }
  { uint16_t disp[8]; u16s(disp, "DISPLAY");
    int64_t dc = CreateDCW(PTR(disp), 0, 0, 0);
    CHK(dc != 0 && GetDeviceCaps(dc, HORZRES) == 640 && GetDeviceCaps(dc, VERTRES) == 480 && GetDeviceCaps(dc, BITSPIXEL) == 32, "CreateDCW(DISPLAY) is a screen-compatible DC (caps %lld x %lld)", (long long)GetDeviceCaps(dc, HORZRES), (long long)GetDeviceCaps(dc, VERTRES));
    int64_t bmp = CreateCompatibleBitmap(dc, 8, 8);
    CHK(bmp != 0 && SelectObject(dc, bmp) != 0, "bitmap can be selected into the screen DC");
    SelectObject(dc, GetStockObject(0)); DeleteObject(bmp);
    CHK(DeleteDC(dc) == 1, "DeleteDC");
    uint16_t lc[8]; u16s(lc, "display");
    int64_t dc2 = CreateDCW(PTR(lc), 0, 0, 0); CHK(dc2 != 0, "case-insensitive driver name"); DeleteDC(dc2);
    uint16_t dev[16]; u16s(dev, "\\\\.\\DISPLAY1");
    int64_t dc3 = CreateDCW(0, PTR(dev), 0, 0); CHK(dc3 != 0, "device name \\\\.\\DISPLAYn with NULL driver"); DeleteDC(dc3);
    int pfd[2]; pipe(pfd); pid_t pid = fork();
    if (pid == 0) { dup2(pfd[1], 2); close(pfd[0]); uint16_t pr[16]; u16s(pr, "WINSPOOL"); CreateDCW(PTR(pr), 0, 0, 0); _exit(0); }
    close(pfd[1]); char eb[512] = { 0 }; ssize_t en = read(pfd[0], eb, sizeof eb - 1); (void)en; int est = 0; waitpid(pid, &est, 0);
    CHK(WIFSIGNALED(est) && strstr(eb, "unimplemented Win32 API: CreateDCW") != NULL, "non-DISPLAY driver fail-fasts naming CreateDCW"); }
  { /* CreateDIBitmap: 4x2 32bpp bottom-up (先頭行 = 下の行) と 3x2 24bpp (行 4B 境界) */
    WBMIH bih; memset(&bih, 0, sizeof bih); bih.biSize = 40; bih.biWidth = 4; bih.biHeight = 2; bih.biPlanes = 1; bih.biBitCount = 32;
    uint32_t px[8] = { 0x00112233, 0x00445566, 0x00778899, 0x00AABBCC, 0x00010203, 0x00040506, 0x00070809, 0x000A0B0C };
    int64_t hb = CreateDIBitmap(0, PTR(&bih), 4 /*CBM_INIT*/, PTR(px), PTR(&bih), 0);
    CHK(hb != 0, "CreateDIBitmap(CBM_INIT 32bpp)");
    WBITMAP bm; GetObjectW(hb, sizeof bm, PTR(&bm)); CHK(bm.bmWidth == 4 && bm.bmHeight == 2, "DDB size 4x2");
    int64_t dc = CreateCompatibleDC(0); SelectObject(dc, hb);
    CHK(GetPixel(dc, 0, 1) == cref(0x11, 0x22, 0x33) && GetPixel(dc, 3, 1) == cref(0xAA, 0xBB, 0xCC) && GetPixel(dc, 0, 0) == cref(0x01, 0x02, 0x03), "bottom-up row order (rows: %06llx %06llx)", (long long)GetPixel(dc, 0, 1), (long long)GetPixel(dc, 0, 0));
    SelectObject(dc, GetStockObject(0)); DeleteDC(dc); DeleteObject(hb);
    int64_t hb0 = CreateDIBitmap(0, PTR(&bih), 0, 0, 0, 0);
    CHK(hb0 != 0, "CreateDIBitmap without CBM_INIT creates an empty bitmap"); DeleteObject(hb0);
    WBMIH b24 = bih; b24.biWidth = 3; b24.biBitCount = 24;
    uint8_t d24[16] = { 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80, 0x90, 0, 0, 0, 0xA1, 0xA2, 0xA3, 0xB1 };   /* row0 = 下: (B,G,R)x3 + pad */
    uint8_t buf24[2 * 12]; memset(buf24, 0, sizeof buf24); memcpy(buf24, d24, 9); memcpy(buf24 + 12, d24 + 12, 3);
    int64_t h24 = CreateDIBitmap(0, PTR(&b24), 4, PTR(buf24), PTR(&b24), 0);
    int64_t dc24 = CreateCompatibleDC(0); SelectObject(dc24, h24);
    CHK(GetPixel(dc24, 0, 1) == cref(0x30, 0x20, 0x10) && GetPixel(dc24, 2, 1) == cref(0x90, 0x80, 0x70) && GetPixel(dc24, 0, 0) == cref(0xA3, 0xA2, 0xA1), "24bpp source converted (BGR order, 4-byte row stride)");
    SelectObject(dc24, GetStockObject(0)); DeleteDC(dc24); DeleteObject(h24);
    CHK(CreateDIBitmap(0, 0, 0, 0, 0, 0) == 0 && GetLastError_gui() == 87, "NULL header -> 0/ERROR_INVALID_PARAMETER"); }

  /* ================= クリップボード ================= */
  SECTION("P1/clipboard: Open Close Empty Set Get Enum GetFormatName");
  { WWNDCLASS wc; memset(&wc, 0, sizeof wc); wc.lpfnWndProc = (uint64_t)(uintptr_t)p1proc; wc.lpszClassName = (uint64_t)(uintptr_t)"P1C"; wc.hbrBackground = 6;
    RegisterClassA(PTR(&wc));
    int64_t cw = CreateWindowExA(0, PTR("P1C"), PTR("clip"), WS_POPUP | WS_VISIBLE, 300, 200, 60, 40, 0, 0, 0x400000, 0);
    p1_drain();
    CHK(CloseClipboard() == 0 && GetLastError_gui() == 1418, "CloseClipboard when closed -> ERROR_CLIPBOARD_NOT_OPEN");
    CHK(EmptyClipboard() == 0 && GetClipboardData(1) == 0 && SetClipboardData(1, 5) == 0 && EnumClipboardFormats(0) == 0 && GetLastError_gui() == 1418, "operations require an open clipboard");
    CHK(OpenClipboard(cw) == 1, "OpenClipboard");
    pthread_t th; void *tr = NULL; pthread_create(&th, NULL, clip_thread, NULL); pthread_join(th, &tr);
    CHK((int)(intptr_t)tr == 5, "another thread cannot open: ERROR_ACCESS_DENIED (%d)", (int)(intptr_t)tr);
    CHK(EmptyClipboard() == 1, "EmptyClipboard");
    uint16_t nm[16]; u16s(nm, "MyFmt");
    int64_t rf = RegisterClipboardFormatW(PTR(nm));
    CHK(rf >= 0xC000, "RegisterClipboardFormatW id >= 0xC000");
    CHK(SetClipboardData(1, 0x1234) == 0x1234 && SetClipboardData(13, 0x5678) == 0x5678 && SetClipboardData(rf, 0x9ABC) == 0x9ABC, "SetClipboardData returns the handle");
    CHK(EnumClipboardFormats(0) == 1 && EnumClipboardFormats(1) == 13 && EnumClipboardFormats(13) == rf && EnumClipboardFormats(rf) == 0, "EnumClipboardFormats walks insertion order and ends with 0");
    CHK(GetClipboardData(13) == 0x5678 && GetClipboardData(rf) == 0x9ABC && GetClipboardData(2) == 0, "GetClipboardData");
    SetClipboardData(13, 0x5679); CHK(GetClipboardData(13) == 0x5679 && EnumClipboardFormats(1) == 13, "re-Set replaces data, keeps position");
    uint16_t out[16];
    CHK(GetClipboardFormatNameW(rf, PTR(out), 16) == 5 && u16eq(out, "MyFmt"), "GetClipboardFormatNameW registered format");
    CHK(GetClipboardFormatNameW(rf, PTR(out), 3) == 2 && u16eq(out, "My"), "GetClipboardFormatNameW truncation");
    CHK(GetClipboardFormatNameW(1, PTR(out), 16) == 0 && GetLastError_gui() == 87, "predefined format has no name -> ERROR_INVALID_PARAMETER");
    CHK(CloseClipboard() == 1, "CloseClipboard");
    CHK(GetClipboardData(13) == 0 && GetLastError_gui() == 1418, "Get after Close fails");
    /* 遅延レンダリング + 所有者通知 */
    OpenClipboard(cw); EmptyClipboard(); CHK(SetClipboardData(1, 0) == 0, "delayed rendering: Set(fmt, NULL)");
    CHK(GetClipboardData(1) == 0x777 && g_renderfmt == 1, "Get triggers WM_RENDERFORMAT in the owner (rendered 0x777)");
    CloseClipboard();
    int64_t cw2 = CreateWindowExA(0, PTR("P1C"), PTR("clip2"), WS_POPUP, 400, 200, 20, 20, 0, 0, 0x400000, 0);
    g_destroyclip = 0; OpenClipboard(cw2); EmptyClipboard();
    CHK(g_destroyclip == 1 && EnumClipboardFormats(0) == 0, "Empty by a new owner sends WM_DESTROYCLIPBOARD to the old owner and drops formats");
    CloseClipboard(); DestroyWindow(cw2); DestroyWindow(cw); }

  /* ================= フック ================= */
  SECTION("P1/hooks: SetWindowsHookExW UnhookWindowsHookEx CallNextHookEx");
  { WWNDCLASS wc; memset(&wc, 0, sizeof wc); wc.lpfnWndProc = (uint64_t)(uintptr_t)p1proc; wc.lpszClassName = (uint64_t)(uintptr_t)"P1H"; wc.hbrBackground = 6;
    RegisterClassA(PTR(&wc));
    int64_t hw = CreateWindowExA(0, PTR("P1H"), PTR("hook"), WS_POPUP | WS_VISIBLE, 300, 200, 120, 90, 0, 0, 0x400000, 0);
    p1_drain();
    CHK(SetWindowsHookExW(99, PTR(hk_a), 0, 0) == 0 && GetLastError_gui() == 1171, "invalid hook id -> ERROR_INVALID_HOOK_FILTER");
    CHK(SetWindowsHookExW(3, 0, 0, 0) == 0 && GetLastError_gui() == 87, "NULL proc -> ERROR_INVALID_PARAMETER");
    CHK(UnhookWindowsHookEx(0x1234) == 0 && GetLastError_gui() == 1404, "unknown hook -> ERROR_INVALID_HOOK_HANDLE");
    /* チェーン: 新しいフックが先 → CallNextHookEx で旧フックへ */
    int64_t ha = SetWindowsHookExW(3, PTR(hk_a), 0, 0), hb = SetWindowsHookExW(3, PTR(hk_b), 0, 0);
    CHK(ha > 0 && hb > 0 && ha != hb && hb < 0x80000000ll, "two WH_GETMESSAGE hooks installed (handles %llx %llx)", (long long)ha, (long long)hb);
    g_hk_a = g_hk_b = 0; PostMessageA(hw, WM_USER + 5, 0, 0); WMSG m;
    CHK(PeekMessageA(PTR(&m), 0, WM_USER + 5, WM_USER + 5, PM_REMOVE) && g_hk_b == 1 && g_hk_a == 1, "newest hook runs first and CallNextHookEx reaches the older one (b=%d a=%d)", g_hk_b, g_hk_a);
    CHK(UnhookWindowsHookEx(hb) == 1, "UnhookWindowsHookEx"); g_hk_a = g_hk_b = 0;
    PostMessageA(hw, WM_USER + 5, 0, 0); PeekMessageA(PTR(&m), 0, WM_USER + 5, WM_USER + 5, PM_REMOVE);
    CHK(g_hk_b == 0 && g_hk_a == 1, "unhooked hook no longer runs");
    CHK(UnhookWindowsHookEx(hb) == 0, "double unhook fails"); UnhookWindowsHookEx(ha);
    /* GETMESSAGE: PM_REMOVE / PM_NOREMOVE と MSG 内容 */
    int64_t hg = SetWindowsHookExW(3, PTR(hk_gm), 0, 0);
    PostMessageA(hw, WM_USER + 6, 0, 0); g_hk_gm_msg = 0;
    PeekMessageA(PTR(&m), 0, WM_USER + 6, WM_USER + 6, PM_NOREMOVE);
    CHK(g_hk_gm_msg == WM_USER + 6 && g_hk_cwp_wp == PM_NOREMOVE, "WH_GETMESSAGE sees the message with PM_NOREMOVE");
    PeekMessageA(PTR(&m), 0, WM_USER + 6, WM_USER + 6, PM_REMOVE);
    CHK(g_hk_cwp_wp == PM_REMOVE, "WH_GETMESSAGE wParam = PM_REMOVE");
    PostMessageA(hw, WM_USER + 7, 0, 0); g_hk_gm_msg = 0; GetMessageA(PTR(&m), 0, WM_USER + 7, WM_USER + 7);
    CHK(g_hk_gm_msg == WM_USER + 7, "WH_GETMESSAGE also runs for GetMessage");
    UnhookWindowsHookEx(hg);
    /* CALLWNDPROC / RET : SendMessage のみ (DispatchMessage には掛からない) */
    int64_t hc = SetWindowsHookExW(4, PTR(hk_cwp), 0, 0), hr = SetWindowsHookExW(12, PTR(hk_ret), 0, 0);
    g_hk_cwp_msg = 0; g_hk_cwp_wp = 0; g_hk_ret_res = 0;
    CHK(SendMessageA(hw, WM_USER + 9, 1, 2) == 4242 && g_hk_cwp_msg == WM_USER + 9 && g_hk_cwp_wp == 1 && g_hk_ret_res == 4242, "CALLWNDPROC(sent-by-this-thread=1) and CALLWNDPROCRET(lResult=4242) around SendMessage");
    g_hk_cwp_msg = 0; PostMessageA(hw, WM_USER + 9, 0, 0); PeekMessageA(PTR(&m), 0, WM_USER + 9, WM_USER + 9, PM_REMOVE); DispatchMessageA(PTR(&m));
    CHK(g_hk_cwp_msg == 0, "posted + dispatched message does not hit WH_CALLWNDPROC");
    UnhookWindowsHookEx(hc); UnhookWindowsHookEx(hr);
    /* KEYBOARD / MOUSE : 入力 → キュー前、非 0 で破棄 */
    SetActiveWindow(hw); SetFocus(hw); p1_drain();
    int64_t hk = SetWindowsHookExW(2, PTR(hk_kb), 0, 0), hm = SetWindowsHookExW(7, PTR(hk_mouse), 0, 0);
    uint8_t in[2 * 40]; memset(in, 0, sizeof in); g_hk_kb = 0; g_hk_kb_block = 1;
    *(uint32_t *)in = 1; *(uint16_t *)(in + 8) = 'Q';
    SendInput(1, PTR(in), 40);
    CHK(g_hk_kb == 1 && g_hk_kb_vk == 'Q' && !PeekMessageA(PTR(&m), 0, WM_KEYDOWN, WM_KEYDOWN, PM_REMOVE), "WH_KEYBOARD returning nonzero discards the key message");
    *(uint16_t *)(in + 8) = 'W'; SendInput(1, PTR(in), 40);
    CHK(g_hk_kb == 2 && PeekMessageA(PTR(&m), 0, WM_KEYDOWN, WM_KEYDOWN, PM_REMOVE) && m.wParam == 'W', "WH_KEYBOARD returning 0 lets the message through");
    memset(in, 0, 40); *(uint16_t *)(in + 8) = 'W'; *(uint32_t *)(in + 12) = 2; *(uint32_t *)in = 1; SendInput(1, PTR(in), 40); p1_drain();
    memset(in, 0, 40); *(uint32_t *)in = 0; *(int32_t *)(in + 8) = 350 * 65536 / 640 + 1; *(int32_t *)(in + 12) = 240 * 65536 / 480 + 1; *(uint32_t *)(in + 20) = 0x8001; /* MOVE|ABSOLUTE */
    g_hk_mouse = 0; g_hk_mouse_block = 1;
    SendInput(1, PTR(in), 40);
    CHK(g_hk_mouse == 1 && g_hk_mouse_x == 350 && !PeekMessageA(PTR(&m), 0, WM_MOUSEMOVE, WM_MOUSEMOVE, PM_REMOVE), "WH_MOUSE gets MOUSEHOOKSTRUCT.pt and can discard (x=%d)", g_hk_mouse_x);
    g_hk_mouse_block = 0; SendInput(1, PTR(in), 40);
    CHK(g_hk_mouse == 2 && PeekMessageA(PTR(&m), 0, WM_MOUSEMOVE, WM_MOUSEMOVE, PM_REMOVE), "WH_MOUSE passing 0 queues WM_MOUSEMOVE");
    UnhookWindowsHookEx(hk); UnhookWindowsHookEx(hm);
    g_hk_kb_block = 0; p1_drain(); DestroyWindow(hw); }

  /* ================= モニタ / DPI ================= */
  SECTION("P1/system: MonitorFromWindow MonitorFromRect GetMonitorInfoW EnumDisplayMonitors EnumDisplaySettingsW GetGuiResources SetThreadDpiHostingBehavior");
  { WWNDCLASS wc; memset(&wc, 0, sizeof wc); wc.lpfnWndProc = (uint64_t)(uintptr_t)p1proc; wc.lpszClassName = (uint64_t)(uintptr_t)"P1M"; RegisterClassA(PTR(&wc));
    int64_t mw = CreateWindowExA(0, PTR("P1M"), PTR("mon"), WS_POPUP | WS_VISIBLE, 300, 200, 50, 50, 0, 0, 0x400000, 0);
    int64_t hm = MonitorFromWindow(mw, 0);
    CHK(hm != 0 && hm < 0x80000000ll, "MonitorFromWindow(on-screen window) -> primary monitor (31-bit handle 0x%llx)", (long long)hm);
    CHK(MonitorFromWindow(0, 0) == 0 && MonitorFromWindow(0, 1) == hm && MonitorFromWindow(0, 2) == hm, "invalid window: NULL / DEFAULTTOPRIMARY / NEAREST");
    int64_t off = CreateWindowExA(0, PTR("P1M"), PTR("off"), WS_POPUP, 2000, 2000, 20, 20, 0, 0, 0x400000, 0);
    CHK(MonitorFromWindow(off, 0) == 0 && MonitorFromWindow(off, 1) == hm, "off-screen window honours the flags");
    WRECT in = { 10, 10, 20, 20 }, outr = { 1000, 1000, 1100, 1100 };
    CHK(MonitorFromRect(PTR(&in), 0) == hm && MonitorFromRect(PTR(&outr), 0) == 0 && MonitorFromRect(PTR(&outr), 1) == hm, "MonitorFromRect");
    uint32_t mi[26]; memset(mi, 0xCC, sizeof mi); mi[0] = 40;
    CHK(GetMonitorInfoW(hm, PTR(mi)) == 1 && mi[1] == 0 && mi[2] == 0 && mi[3] == 640 && mi[4] == 480 && mi[5] == 0 && mi[7] == 640 && mi[9] == 1, "GetMonitorInfoW (MONITORINFO): rcMonitor/rcWork = screen, PRIMARY flag");
    memset(mi, 0, sizeof mi); mi[0] = 104;
    CHK(GetMonitorInfoW(hm, PTR(mi)) == 1 && u16eq((uint16_t *)(mi + 10), "\\\\.\\DISPLAY1"), "GetMonitorInfoW (MONITORINFOEXW): device name");
    mi[0] = 41; CHK(GetMonitorInfoW(hm, PTR(mi)) == 0 && GetLastError_gui() == 87, "bad cbSize -> FALSE");
    mi[0] = 40; CHK(GetMonitorInfoW(0x1234, PTR(mi)) == 0, "bad monitor handle -> FALSE");
    g_mon_calls = 0; g_mon_ret = 1;
    CHK(EnumDisplayMonitors(0, 0, PTR(mon_cb), 77) == 1 && g_mon_calls == 1 && g_mon_h == hm && g_mon_data == 77 && g_mon_rc.right == 640 && g_mon_rc.bottom == 480, "EnumDisplayMonitors calls back once with (hmon, hdc, rect, data)");
    WRECT clip = { 100, 50, 300, 200 };
    EnumDisplayMonitors(0, PTR(&clip), PTR(mon_cb), 78);
    CHK(g_mon_calls == 2 && g_mon_rc.left == 100 && g_mon_rc.top == 50 && g_mon_rc.right == 300 && g_mon_rc.bottom == 200, "clip rectangle intersects the monitor rect");
    WRECT miss = { 1000, 1000, 1100, 1100 }; g_mon_calls = 0;
    CHK(EnumDisplayMonitors(0, PTR(&miss), PTR(mon_cb), 0) == 1 && g_mon_calls == 0, "disjoint clip: no callback");
    g_mon_ret = 0; CHK(EnumDisplayMonitors(0, 0, PTR(mon_cb), 0) == 0, "callback FALSE stops the enumeration and is returned"); g_mon_ret = 1;
    uint8_t dm[220]; memset(dm, 0xEE, sizeof dm); *(uint16_t *)(dm + 68) = 220;
    CHK(EnumDisplaySettingsW(0, 0xFFFFFFFFu, PTR(dm)) == 1, "EnumDisplaySettingsW(ENUM_CURRENT_SETTINGS)");
    CHK(*(uint32_t *)(dm + 172) == 640 && *(uint32_t *)(dm + 176) == 480 && *(uint32_t *)(dm + 168) == 32 && *(uint32_t *)(dm + 184) == 60 && *(uint16_t *)(dm + 68) == 220, "DEVMODEW width/height/bpp/frequency/dmSize");
    CHK((*(uint32_t *)(dm + 72) & (0x80000 | 0x100000 | 0x40000)) == (0x80000 | 0x100000 | 0x40000) && u16eq((uint16_t *)dm, "\\\\.\\DISPLAY1"), "dmFields and device name");
    CHK(EnumDisplaySettingsW(0, 0, PTR(dm)) == 1 && EnumDisplaySettingsW(0, 1, PTR(dm)) == 0, "mode 0 exists, mode 1 does not");
    uint16_t bogus[8]; u16s(bogus, "bogus"); CHK(EnumDisplaySettingsW(PTR(bogus), 0, PTR(dm)) == 0, "unknown device -> FALSE");
    /* GetGuiResources : ウィンドウ/GDI オブジェクトの増減に追従 */
    int64_t u0 = GetGuiResources(0xFFFF, 1), g0 = GetGuiResources(0xFFFF, 0);
    int64_t w2 = CreateWindowExA(0, PTR("P1M"), PTR("cnt"), WS_POPUP, 500, 300, 10, 10, 0, 0, 0x400000, 0);
    int64_t br = CreateSolidBrush(0x112233), rg = CreateRectRgn(0, 0, 4, 4);
    CHK(GetGuiResources(0xFFFF, 1) == u0 + 1 && GetGuiResources(0xFFFF, 0) == g0 + 2, "GR_USEROBJECTS +1 / GR_GDIOBJECTS +2 after creating a window, a brush and a region (%lld/%lld)", (long long)(GetGuiResources(0xFFFF, 1) - u0), (long long)(GetGuiResources(0xFFFF, 0) - g0));
    DeleteObject(br); DeleteObject(rg); DestroyWindow(w2);
    CHK(GetGuiResources(0xFFFF, 1) == u0 && GetGuiResources(0xFFFF, 0) == g0, "counts drop back");
    CHK(GetGuiResources(0xFFFF, 2) >= g0 + 2 && GetGuiResources(0xFFFF, 4) >= u0 + 1, "peak counts are >= the maxima observed");
    CHK(GetGuiResources(0xFFFF, 7) == 0 && GetLastError_gui() == 87, "bad flag -> 0/ERROR_INVALID_PARAMETER");
    CHK(SetThreadDpiHostingBehavior(1) == 0 && SetThreadDpiHostingBehavior(0) == 1 && SetThreadDpiHostingBehavior(5) == -1, "SetThreadDpiHostingBehavior returns the previous value, -1 for invalid");
    DestroyWindow(off); DestroyWindow(mw); }

  /* ================= キャレット ================= */
  SECTION("P1/caret: CreateCaret SetCaretPos ShowCaret HideCaret DestroyCaret");
  { WWNDCLASS wc; memset(&wc, 0, sizeof wc); wc.lpfnWndProc = (uint64_t)(uintptr_t)p1proc; wc.lpszClassName = (uint64_t)(uintptr_t)"P1K"; wc.hbrBackground = 6; RegisterClassA(PTR(&wc));
    int64_t kw = CreateWindowExA(0, PTR("P1K"), PTR("caret"), WS_POPUP | WS_VISIBLE, 300, 300, 60, 60, 0, 0, 0x400000, 0);
    p1_drain(); flush_wait();
    int x, y, hide, drawn;
    CHK(SetCaretPos(1, 1) == 0 && GetLastError_gui() == 5 && ShowCaret(0) == 0 && HideCaret(0) == 0 && DestroyCaret() == 0, "no caret: all four fail (ERROR_ACCESS_DENIED)");
    CHK(CreateCaret(kw, 0, 2, 10) == 1 && gui_caret_state(&x, &y, &hide, &drawn) && hide == 1 && !drawn, "CreateCaret creates a hidden caret");
    CHK(desk(300 + 5, 300 + 5) == 0xFFFFFF, "window background is white");
    CHK(SetCaretPos(5, 5) == 1, "SetCaretPos while hidden is allowed");
    CHK(desk(300 + 5, 300 + 5) == 0xFFFFFF, "...and draws nothing");
    CHK(ShowCaret(0) == 1, "ShowCaret"); flush_wait();
    CHK(desk(300 + 5, 300 + 5) == 0x000000 && desk(300 + 6, 300 + 14) == 0x000000 && desk(300 + 7, 300 + 5) == 0xFFFFFF && desk(300 + 5, 300 + 15) == 0xFFFFFF, "caret rect 2x10 inverted at (5,5)");
    SetCaretPos(20, 8); flush_wait();
    CHK(desk(300 + 5, 300 + 5) == 0xFFFFFF && desk(300 + 20, 300 + 8) == 0x000000, "SetCaretPos moves the visible caret (erases old, draws new)");
    HideCaret(0); flush_wait();
    CHK(desk(300 + 20, 300 + 8) == 0xFFFFFF, "HideCaret erases");
    HideCaret(kw); ShowCaret(kw); flush_wait();
    CHK(desk(300 + 20, 300 + 8) == 0xFFFFFF && gui_caret_state(&x, &y, &hide, &drawn) && hide == 1, "hide count: Hide,Hide,Show leaves it hidden");
    ShowCaret(0); flush_wait();
    CHK(desk(300 + 20, 300 + 8) == 0x000000 && gui_caret_state(&x, &y, &hide, &drawn) && hide == 0 && drawn, "second Show makes it visible");
    CHK(ShowCaret(0x1234) == 0, "wrong window handle rejected");
    CHK(DestroyCaret() == 1, "DestroyCaret"); flush_wait();
    CHK(desk(300 + 20, 300 + 8) == 0xFFFFFF && !gui_caret_state(&x, &y, &hide, &drawn), "caret erased and gone");
    CHK(SetCaretPos(1, 1) == 0, "SetCaretPos after DestroyCaret fails");
    CreateCaret(kw, 0, 0, 0); gui_caret_state(&x, &y, &hide, &drawn);
    CHK(hide == 1, "default-size caret (w/h 0)");
    DestroyWindow(kw);
    CHK(SetCaretPos(1, 1) == 0, "destroying the owner window destroys its caret"); }

  /* ================= 入力 ================= */
  SECTION("P1/input: GetCursorInfo GetKeyNameTextW GetKeyboardLayoutList GetKeyboardLayoutNameW SendInput SetKeyboardState ToUnicode");
  { uint32_t ci[6]; memset(ci, 0, sizeof ci); ci[0] = 24;
    CHK(GetCursorInfo(PTR(ci)) == 1, "GetCursorInfo");
    int64_t c = ShowCursor(0);
    GetCursorInfo(PTR(ci)); CHK(ci[1] == (c >= 0 ? 1u : 0u), "flags follow the ShowCursor counter (cnt=%lld flags=%u)", (long long)c, ci[1]);
    while (ShowCursor(1) < 0) {}
    GetCursorInfo(PTR(ci)); CHK(ci[1] == 1, "CURSOR_SHOWING when the counter is >= 0");
    WPOINT cp; GetCursorPos(PTR(&cp));
    CHK((int32_t)ci[4] == cp.x && (int32_t)ci[5] == cp.y && *(uint64_t *)(ci + 2) == (uint64_t)GetCursor(), "ptScreenPos = GetCursorPos, hCursor = GetCursor");
    ci[0] = 20; CHK(GetCursorInfo(PTR(ci)) == 0 && GetLastError_gui() == 87, "bad cbSize -> FALSE"); }
  { uint16_t nm[32];
    CHK(GetKeyNameTextW(0x01 << 16, PTR(nm), 32) == 3 && u16eq(nm, "Esc"), "Esc");
    CHK(GetKeyNameTextW(0x1D << 16, PTR(nm), 32) == 4 && u16eq(nm, "Ctrl") && GetKeyNameTextW((0x1D << 16) | (1 << 24), PTR(nm), 32) == 10 && u16eq(nm, "Right Ctrl"), "Ctrl / Right Ctrl (extended bit)");
    CHK(GetKeyNameTextW(0x1E << 16, PTR(nm), 32) == 1 && u16eq(nm, "A") && GetKeyNameTextW(0x3B << 16, PTR(nm), 32) == 2 && u16eq(nm, "F1"), "letter and function key");
    CHK(GetKeyNameTextW(0x47 << 16, PTR(nm), 32) == 5 && u16eq(nm, "Num 7") && GetKeyNameTextW((0x47 << 16) | (1 << 24), PTR(nm), 32) == 4 && u16eq(nm, "Home"), "numpad vs navigation key by extended bit");
    CHK(GetKeyNameTextW(0x39 << 16, PTR(nm), 32) == 5 && u16eq(nm, "Space") && GetKeyNameTextW(0x0E << 16, PTR(nm), 32) == 9 && u16eq(nm, "Backspace"), "Space / Backspace");
    CHK(GetKeyNameTextW(0x01 << 16, PTR(nm), 3) == 2 && u16eq(nm, "Es"), "truncation to cch-1");
    CHK(GetKeyNameTextW(0x7F << 16, PTR(nm), 32) == 0 && nm[0] == 0, "unknown scan code -> 0, empty string"); }
  { uint64_t hkl[4] = { 0, 0x55, 0x55, 0x55 };
    CHK(GetKeyboardLayoutList(0, 0) == 1, "GetKeyboardLayoutList(0) returns the count");
    CHK(GetKeyboardLayoutList(4, PTR(hkl)) == 1 && hkl[0] == 0x04090409 && hkl[1] == 0x55, "list holds 1 HKL (US), 8-byte entries");
    CHK(GetKeyboardLayoutList(-1, PTR(hkl)) == 0, "negative count -> 0");
    uint16_t kl[12]; memset(kl, 0xFF, sizeof kl);
    CHK(GetKeyboardLayoutNameW(PTR(kl)) == 1 && u16eq(kl, "00000409") && kl[8] == 0, "GetKeyboardLayoutNameW = 00000409 (NUL-terminated within KL_NAMELENGTH)");
    CHK((int64_t)hkl[0] == GetKeyboardLayout(0), "consistent with GetKeyboardLayout"); }
  { WWNDCLASS wc; memset(&wc, 0, sizeof wc); wc.lpfnWndProc = (uint64_t)(uintptr_t)p1proc; wc.lpszClassName = (uint64_t)(uintptr_t)"P1I"; wc.hbrBackground = 6; RegisterClassA(PTR(&wc));
    int64_t iw = CreateWindowExA(0, PTR("P1I"), PTR("input"), WS_POPUP | WS_VISIBLE, 300, 200, 120, 90, 0, 0, 0x400000, 0);
    SetActiveWindow(iw); SetFocus(iw); p1_drain(); WMSG m; uint8_t in[3 * 40]; memset(in, 0, sizeof in);
    CHK(SendInput(1, PTR(in), 41) == 0 && GetLastError_gui() == 87, "SendInput: bad cbSize -> 0/ERROR_INVALID_PARAMETER");
    /* キー: 'A' down/up */
    *(uint32_t *)in = 1; *(uint16_t *)(in + 8) = 'A'; *(uint32_t *)(in + 40) = 1; *(uint16_t *)(in + 48) = 'A'; *(uint32_t *)(in + 52) = 2;
    CHK(SendInput(2, PTR(in), 40) == 2, "SendInput returns the number of events inserted");
    CHK(PeekMessageA(PTR(&m), 0, WM_KEYDOWN, WM_KEYDOWN, PM_REMOVE) && m.wParam == 'A' && PeekMessageA(PTR(&m), 0, WM_KEYUP, WM_KEYUP, PM_REMOVE) && m.wParam == 'A', "key down/up become WM_KEYDOWN/WM_KEYUP for the focus window");
    CHK(GetKeyState(0x41) == 0, "key released again");
    memset(in, 0, sizeof in); *(uint32_t *)in = 1; *(uint16_t *)(in + 8) = VK_SHIFT; SendInput(1, PTR(in), 40);
    CHK(GetKeyState(VK_SHIFT) < 0, "VK_SHIFT down is reflected in GetKeyState");
    *(uint32_t *)(in + 12) = 2; SendInput(1, PTR(in), 40); p1_drain();
    CHK(GetKeyState(VK_SHIFT) == 0, "and released");
    /* KEYEVENTF_UNICODE -> WM_CHAR, SCANCODE */
    memset(in, 0, sizeof in); *(uint32_t *)in = 1; *(uint16_t *)(in + 10) = 'Z'; *(uint32_t *)(in + 12) = 4;
    SendInput(1, PTR(in), 40);
    CHK(PeekMessageA(PTR(&m), 0, WM_CHAR, WM_CHAR, PM_REMOVE) && m.wParam == 'Z', "KEYEVENTF_UNICODE injects WM_CHAR");
    memset(in, 0, sizeof in); *(uint32_t *)in = 1; *(uint16_t *)(in + 10) = 0x1E; *(uint32_t *)(in + 12) = 8; SendInput(1, PTR(in), 40);
    CHK(PeekMessageA(PTR(&m), 0, WM_KEYDOWN, WM_KEYDOWN, PM_REMOVE) && m.wParam == 'A' && ((m.lParam >> 16) & 0xFF) == 0x1E, "KEYEVENTF_SCANCODE maps scan 0x1E to VK 'A'");
    memset(in, 0, sizeof in); *(uint32_t *)in = 1; *(uint16_t *)(in + 10) = 0x1E; *(uint32_t *)(in + 12) = 8 | 2; SendInput(1, PTR(in), 40); p1_drain();
    /* マウス: 絶対移動 + ボタン + ホイール */
    p1_drain();
    memset(in, 0, sizeof in); *(uint32_t *)in = 0; *(int32_t *)(in + 8) = 350 * 65536 / 640 + 1; *(int32_t *)(in + 12) = 240 * 65536 / 480 + 1; *(uint32_t *)(in + 20) = 0x8001;
    SendInput(1, PTR(in), 40); WPOINT cp; GetCursorPos(PTR(&cp));
    CHK(cp.x == 350 && cp.y == 240, "MOUSEEVENTF_ABSOLUTE maps 0..65535 to the screen: (%d,%d)", cp.x, cp.y);
    CHK(PeekMessageA(PTR(&m), 0, WM_MOUSEMOVE, WM_MOUSEMOVE, PM_REMOVE) && (m.lParam & 0xFFFF) == 50 && ((m.lParam >> 16) & 0xFFFF) == 40, "WM_MOUSEMOVE with client coords (50,40)");
    memset(in, 0, sizeof in); *(uint32_t *)in = 0; *(int32_t *)(in + 8) = 10; *(int32_t *)(in + 12) = -5; *(uint32_t *)(in + 20) = 1;
    SendInput(1, PTR(in), 40); GetCursorPos(PTR(&cp)); p1_drain();
    CHK(cp.x == 360 && cp.y == 235, "relative move (+10,-5): (%d,%d)", cp.x, cp.y);
    memset(in, 0, sizeof in); *(uint32_t *)in = 0; *(uint32_t *)(in + 20) = 2 /*LEFTDOWN*/;
    SendInput(1, PTR(in), 40);
    CHK(PeekMessageA(PTR(&m), 0, WM_LBUTTONDOWN, WM_LBUTTONDOWN, PM_REMOVE) && (m.lParam & 0xFFFF) == 60 && GetKeyState(VK_LBUTTON) < 0, "LEFTDOWN -> WM_LBUTTONDOWN and VK_LBUTTON down");
    *(uint32_t *)(in + 20) = 4 /*LEFTUP*/; SendInput(1, PTR(in), 40);
    CHK(PeekMessageA(PTR(&m), 0, WM_LBUTTONUP, WM_LBUTTONUP, PM_REMOVE) && GetKeyState(VK_LBUTTON) == 0, "LEFTUP -> WM_LBUTTONUP");
    *(uint32_t *)(in + 20) = 8; SendInput(1, PTR(in), 40); *(uint32_t *)(in + 20) = 0x10; SendInput(1, PTR(in), 40);
    CHK(PeekMessageA(PTR(&m), 0, WM_RBUTTONDOWN, WM_RBUTTONDOWN, PM_REMOVE) && PeekMessageA(PTR(&m), 0, WM_RBUTTONUP, WM_RBUTTONUP, PM_REMOVE), "RIGHTDOWN/UP");
    *(uint32_t *)(in + 20) = 0x800 /*WHEEL*/; *(int32_t *)(in + 16) = 120; SendInput(1, PTR(in), 40);
    CHK(PeekMessageA(PTR(&m), 0, WM_MOUSEWHEEL, WM_MOUSEWHEEL, PM_REMOVE) && (int16_t)(m.wParam >> 16) == 120, "WHEEL delta 120 in HIWORD(wParam)");
    /* SetKeyboardState / GetKeyboardState */
    uint8_t ks[256], rd[256]; memset(ks, 0, sizeof ks); ks[0x41] = 0x80; ks[0x14] = 1;
    CHK(SetKeyboardState(PTR(ks)) == 1 && GetKeyboardState(PTR(rd)) == 1 && memcmp(ks, rd, 256) == 0, "SetKeyboardState round-trips through GetKeyboardState");
    CHK(GetKeyState(0x41) < 0, "GetKeyState sees the injected state");
    memset(ks, 0, sizeof ks); SetKeyboardState(PTR(ks)); CHK(GetKeyState(0x41) == 0, "cleared");
    DestroyWindow(iw); }
  { uint8_t st[256]; uint16_t o[4]; memset(st, 0, sizeof st);
    memset(o, 0xFF, sizeof o); CHK(ToUnicode('A', 0x1E, PTR(st), PTR(o), 4, 0) == 1 && o[0] == 'a' && o[1] == 0, "ToUnicode 'A' unshifted -> 'a' (NUL-terminated)");
    st[VK_SHIFT] = 0x80; ToUnicode('A', 0, PTR(st), PTR(o), 4, 0); CHK(o[0] == 'A', "Shift -> 'A'");
    st[VK_SHIFT] = 0; st[0x14] = 1; ToUnicode('A', 0, PTR(st), PTR(o), 4, 0); CHK(o[0] == 'A', "Caps Lock -> 'A'");
    st[VK_SHIFT] = 0x80; ToUnicode('A', 0, PTR(st), PTR(o), 4, 0); CHK(o[0] == 'a', "Caps Lock + Shift -> 'a'");
    memset(st, 0, sizeof st); st[VK_CONTROL] = 0x80; ToUnicode('A', 0, PTR(st), PTR(o), 4, 0); CHK(o[0] == 1, "Ctrl+A -> 0x01");
    memset(st, 0, sizeof st); ToUnicode('1', 0, PTR(st), PTR(o), 4, 0); CHK(o[0] == '1', "digit");
    st[VK_SHIFT] = 0x80; ToUnicode('1', 0, PTR(st), PTR(o), 4, 0); CHK(o[0] == '!', "Shift+1 -> '!'");
    ToUnicode(0xBA, 0, PTR(st), PTR(o), 4, 0); CHK(o[0] == ':', "Shift+; -> ':'");
    memset(st, 0, sizeof st); ToUnicode(0xBC, 0, PTR(st), PTR(o), 4, 0); CHK(o[0] == ',', "OEM comma");
    ToUnicode(0x65, 0, PTR(st), PTR(o), 4, 0); CHK(o[0] == '5', "numpad 5");
    ToUnicode(VK_RETURN, 0, PTR(st), PTR(o), 4, 0); CHK(o[0] == '\r', "Enter -> CR");
    CHK(ToUnicode(0x70 /*F1*/, 0, PTR(st), PTR(o), 4, 0) == 0, "function key -> no character");
    o[1] = 0x7777; CHK(ToUnicode('B', 0, PTR(st), PTR(o), 1, 0) == 1 && o[1] == 0x7777, "cch==1: no NUL written");
    CHK(ToUnicode('B', 0, PTR(st), PTR(o), 0, 0) == 0, "cch==0 -> 0");
    int64_t ta = ToAscii('C', 0, PTR(st), PTR(o), 0); CHK(ta == 1 && o[0] == 'c', "ToAscii shares the same translation"); }

  /* ================= カーソル / アイコン / ビットマップ資源 ================= */
  SECTION("P1/icon: GetIconInfo DrawIcon DrawIconEx DestroyCursor LoadBitmapW");
  { int64_t ico = LoadIconW(0, 32512), arrow = LoadCursorW(0, 32512), cross = LoadCursorW(0, 32515);
    uint8_t ii[32]; memset(ii, 0xCC, sizeof ii);
    CHK(GetIconInfo(ico, PTR(ii)) == 1 && *(uint32_t *)ii == 1, "GetIconInfo(icon): fIcon=TRUE");
    int64_t hm = *(int64_t *)(ii + 16), hc = *(int64_t *)(ii + 24);
    WBITMAP bm; CHK(hm && hc && GetObjectW(hc, sizeof bm, PTR(&bm)) && bm.bmWidth == 32 && bm.bmHeight == 32 && h_type((U64)hm) == HT_BMP, "returns two 32x32 bitmaps (mask, colour)");
    int64_t dc = CreateCompatibleDC(0); SelectObject(dc, hc);
    CHK(GetPixel(dc, 0, 0) == cref(0x40, 0x40, 0x40) && GetPixel(dc, 10, 10) == cref(0xC0, 0xC0, 0xC0), "colour bitmap pixels (border / fill)");
    SelectObject(dc, hm); CHK(GetPixel(dc, 10, 10) == 0, "mask bitmap: opaque = black (AND mask 0)");
    SelectObject(dc, GetStockObject(0)); DeleteDC(dc);
    CHK(DeleteObject(hm) && DeleteObject(hc), "caller owns and can delete both bitmaps");
    GetIconInfo(arrow, PTR(ii)); CHK(*(uint32_t *)ii == 0 && *(uint32_t *)(ii + 4) == 0 && *(uint32_t *)(ii + 8) == 0, "arrow cursor: fIcon=FALSE hotspot (0,0)"); DeleteObject(*(int64_t *)(ii + 16)); DeleteObject(*(int64_t *)(ii + 24));
    GetIconInfo(cross, PTR(ii)); CHK(*(uint32_t *)(ii + 4) == 15 && *(uint32_t *)(ii + 8) == 15, "other cursors: centre hotspot"); DeleteObject(*(int64_t *)(ii + 16)); DeleteObject(*(int64_t *)(ii + 24));
    CHK(GetIconInfo(0x1234, PTR(ii)) == 0 && GetLastError_gui() == 1402, "invalid handle -> ERROR_INVALID_CURSOR_HANDLE");
    uint32_t *bits; int64_t mdc; int64_t dib = new_dib(64, 64, &bits, &mdc, 0xFFFFFF);
    CHK(DrawIcon(mdc, 8, 8, ico) == 1, "DrawIcon");
    CHK(PX(bits, 64, 8, 8) == 0x404040 && PX(bits, 64, 8 + 31, 8 + 31) == 0x404040 && PX(bits, 64, 20, 20) == 0xC0C0C0 && PX(bits, 64, 7, 7) == 0xFFFFFF && PX(bits, 64, 8 + 32, 8) == 0xFFFFFF, "32x32 icon at (8,8), nothing outside");
    for (int i = 0; i < 64 * 64; i++) bits[i] = 0xFFFFFFFF;
    CHK(DrawIconEx(mdc, 0, 0, ico, 16, 16, 0, 0, 3) == 1 && PX(bits, 64, 0, 0) == 0x404040 && PX(bits, 64, 8, 8) == 0xC0C0C0 && PX(bits, 64, 16, 16) == 0xFFFFFF, "DrawIconEx scales to 16x16");
    for (int i = 0; i < 64 * 64; i++) bits[i] = 0xFFFFFFFF;
    DrawIconEx(mdc, 0, 0, ico, 0, 0, 0, 0, 1 /*DI_MASK*/); CHK(PX(bits, 64, 10, 10) == 0x000000, "DI_MASK draws the AND mask (black)");
    for (int i = 0; i < 64 * 64; i++) bits[i] = 0xFFFFFFFF;
    DrawIconEx(mdc, 0, 0, ico, 10, 10, 0, 0, 3 | 8 /*DI_DEFAULTSIZE*/); CHK(PX(bits, 64, 31, 31) == 0x404040, "DI_DEFAULTSIZE ignores cx/cy");
    for (int i = 0; i < 64 * 64; i++) bits[i] = 0xFFFFFFFF;
    DrawIcon(mdc, 0, 0, arrow); CHK(PX(bits, 64, 0, 0) == 0x000000 && PX(bits, 64, 2, 8) == 0xFFFFFF && PX(bits, 64, 20, 5) == 0xFFFFFF, "arrow cursor glyph: black outline, white fill, transparent outside");
    CHK(DrawIcon(mdc, 0, 0, 0x1234) == 0 && DrawIconEx(0x1234, 0, 0, ico, 0, 0, 0, 0, 3) == 0, "invalid icon / DC -> FALSE");
    DeleteDC(mdc); DeleteObject(dib);
    CHK(DestroyCursor(arrow) == 1 && DestroyCursor(cross) == 1, "DestroyCursor on shared cursors is TRUE (no-op)");
    CHK(DestroyCursor(0x1234) == 0 && GetLastError_gui() == 1402, "DestroyCursor on a bad handle -> ERROR_INVALID_CURSOR_HANDLE"); }
  { int64_t b = LoadBitmapW(0, 32760); WBITMAP bm;
    CHK(b != 0 && GetObjectW(b, sizeof bm, PTR(&bm)) && bm.bmWidth == 13 && bm.bmHeight == 13, "LoadBitmapW(NULL, OBM_*) placeholder 13x13"); DeleteObject(b);
    /* RT_BITMAP: 2x2 32bpp bottom-up */
    memset(g_dib, 0, sizeof g_dib); WBMIH *bi = (WBMIH *)g_dib; bi->biSize = 40; bi->biWidth = 2; bi->biHeight = 2; bi->biPlanes = 1; bi->biBitCount = 32;
    uint32_t *pix = g_dib + 10; pix[0] = 0x00102030; pix[1] = 0x00405060; pix[2] = 0x00708090; pix[3] = 0x00A0B0C0;
    gui_set_resource_provider(res_prov); g_res_calls = 0;
    int64_t rb = LoadBitmapW(0x400000, 101);
    CHK(rb != 0 && g_res_calls == 1, "LoadBitmapW from the resource provider");
    int64_t dc = CreateCompatibleDC(0); SelectObject(dc, rb);
    CHK(GetPixel(dc, 0, 1) == cref(0x10, 0x20, 0x30) && GetPixel(dc, 1, 0) == cref(0xA0, 0xB0, 0xC0), "DIB resource rows are bottom-up");
    SelectObject(dc, GetStockObject(0)); DeleteDC(dc); DeleteObject(rb);
    CHK(LoadBitmapW(0x400000, 999) == 0 && GetLastError_gui() == 1813 && LoadBitmapW(0x123, 101) == 0, "missing resource -> 0/ERROR_RESOURCE_TYPE_NOT_FOUND");
    g_res_calls = 0; int64_t li = LoadImageW(0x400000, 101, 0 /* IMAGE_BITMAP */, 2, 2, 0);
    CHK(li != 0 && g_res_calls == 1, "LoadImageW(IMAGE_BITMAP) from the resource provider (natural size)"); DeleteObject(li);
    gui_set_resource_provider(NULL); }
  SECTION("P1/LoadImageW: IMAGE_ICON / IMAGE_CURSOR / IMAGE_BITMAP");
  { int64_t ico = LoadIconW(0, 32512), arrow = LoadCursorW(0, 32512), cross = LoadCursorW(0, 32515);
    CHK(LoadImageW(0, 32512, 1 /* IMAGE_ICON */, 0, 0, 0x8000 /* LR_SHARED */) == ico, "LoadImageW(IMAGE_ICON, OIC_*) = LoadIconW");
    CHK(LoadImageW(0, 32515, 2 /* IMAGE_CURSOR */, 32, 32, 0x8000) == cross, "LoadImageW(IMAGE_CURSOR, IDC_*, 32x32) = LoadCursorW");
    CHK(LoadImageW(0, 32512, 2, 0, 0, 0x40 /* LR_DEFAULTSIZE */) == arrow, "LoadImageW(IMAGE_CURSOR, default size) = LoadCursorW");
    CHK(LoadImageW(0, 0x7F86, 2, 32, 32, 0x8000) == LoadCursorW(0, 0x7F86), "LoadImageW(IMAGE_CURSOR, IDC_SIZEALL) = LoadCursorW");
    WBITMAP bm; int64_t lb = LoadImageW(0, 32760, 0, 13, 13, 0);
    CHK(lb != 0 && GetObjectW(lb, sizeof bm, PTR(&bm)) && bm.bmWidth == 13 && bm.bmHeight == 13, "LoadImageW(IMAGE_BITMAP, OBM_*, 13x13) placeholder");
    DeleteObject(lb); }

  gui_set_resource_provider(NULL);
  SetActiveWindow(keep_focus); SetFocus(keep_focus); p1_drain();
}
