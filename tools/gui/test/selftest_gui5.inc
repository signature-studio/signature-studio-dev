/* selftest_gui5.inc — GUI-5 (#181): 24/8/4/1bpp DIB・mono DDB・GetDIBits/SetDIBits/StretchDIBits の各 bpp、
 * 行カーネル (SIMD 対応) 版 BitBlt/StretchBlt/AlphaBlend と画素単位の参照実装 (gdi_set_ref_blit) の一致、AlphaBlend の独立オラクル、fail-fast 境界。
 * selftest.c から #include (CHK/PTR/cref/rgb を共有)。 */
#include <errno.h>
extern void gdi_set_ref_blit(int on);
static int rop_needs_src_t(uint32_t rop) { return !(rop == PATCOPY || rop == PATINVERT || rop == DSTINVERT || rop == BLACKNESS || rop == WHITENESS); }

typedef struct { WBMIH h; uint32_t col[256]; } BmiBuf;
static void bmi_init(BmiBuf *b, int w, int h, int bpp, const uint32_t *cols /* 0xRRGGBB */, int ncol) {
  memset(b, 0, sizeof *b); b->h.biSize = 40; b->h.biWidth = w; b->h.biHeight = h; b->h.biPlanes = 1; b->h.biBitCount = (uint16_t)bpp;
  b->h.biClrUsed = (uint32_t)ncol; for (int i = 0; i < ncol; i++) b->col[i] = cols[i];   /* RGBQUAD は B|G<<8|R<<16 = 0xRRGGBB のリトルエンディアン配置 */
}
static uint8_t *mk_dib(int64_t *hbm, int64_t *dc, int w, int h, int bpp, const uint32_t *cols, int ncol) {
  BmiBuf b; bmi_init(&b, w, h, bpp, cols, ncol); uint64_t pv = 0;
  *hbm = CreateDIBSection(0, PTR(&b), 0, PTR(&pv), 0, 0); *dc = CreateCompatibleDC(0); SelectObject(*dc, *hbm);
  return (uint8_t *)(uintptr_t)pv;
}
static void ff_child_ds16(void) { BmiBuf b; bmi_init(&b, 4, 4, 16, 0, 0); uint64_t pv; CreateDIBSection(0, PTR(&b), 0, PTR(&pv), 0, 0); }
static void ff_child_ds_palcolors(void) { uint32_t c[2] = { 0, 0xFFFFFF }; BmiBuf b; bmi_init(&b, 4, 4, 8, c, 2); uint64_t pv; CreateDIBSection(0, PTR(&b), 1 /*DIB_PAL_COLORS*/, PTR(&pv), 0, 0); }
static void ff_child_cb8bits(void) { uint8_t px[8] = {0}; CreateBitmap(4, 2, 1, 8, PTR(px)); }
static void ff_child_sdib16(void) {
  int64_t hb, dc; mk_dib(&hb, &dc, 4, 4, 32, 0, 0); BmiBuf b; bmi_init(&b, 4, 4, 16, 0, 0); uint16_t px[16] = {0};
  StretchDIBits(dc, 0, 0, 4, 4, 0, 0, 4, 4, PTR(px), PTR(&b), 0, SRCCOPY);
}
static void ff_child_getdibits16(void) {
  int64_t hb, dc; mk_dib(&hb, &dc, 4, 4, 32, 0, 0); BmiBuf b; bmi_init(&b, 4, 4, 16, 0, 0); uint16_t px[16];
  GetDIBits(dc, hb, 0, 4, PTR(px), PTR(&b), 0);
}
static void expect_failfast(void (*fn)(void), const char *what, const char *needle) {
  int pfd[2]; if (pipe(pfd)) return;
  pid_t pid = fork();
  if (pid == 0) { dup2(pfd[1], 2); close(pfd[0]); fn(); _exit(0); }
  close(pfd[1]);
  char buf[512] = {0}; size_t got = 0; for (;;) { char junk[256]; int full = got >= sizeof buf - 1; ssize_t nr = read(pfd[0], full ? junk : buf + got, full ? sizeof junk : sizeof buf - 1 - got); if (nr < 0 && errno == EINTR) continue; if (nr <= 0) break; if (!full) got += (size_t)nr; } close(pfd[0]);   /* EOF まで読む (途中で閉じると子が SIGPIPE になる) */
  int st = 0; waitpid(pid, &st, 0);
  CHK(WIFSIGNALED(st) && WTERMSIG(st) == SIGABRT && strstr(buf, needle) != NULL, "%s: fail-fast (%s) wait-status=0x%x got: %.200s", what, needle, st, buf);
}

static uint64_t g_g5rng = 0x243F6A8885A308D3ull;
static uint32_t g5rnd(void) { g_g5rng ^= g_g5rng << 13; g_g5rng ^= g_g5rng >> 7; g_g5rng ^= g_g5rng << 17; return (uint32_t)(g_g5rng >> 11); }

static void run_gui5(int64_t hwnd) {
  (void)hwnd;
  SECTION("GUI-5: 24bpp DIB section (native BGR, 4-byte rows, bottom-up / top-down)");
  { int64_t hb, dc; uint8_t *p = mk_dib(&hb, &dc, 5, 3, 24, 0, 0);
    CHK(p != NULL, "24bpp DIB section returns native pointer");
    p[1 * 3 + 0] = 0x11; p[1 * 3 + 1] = 0x22; p[1 * 3 + 2] = 0x33;   /* メモリ行 0 = 下端 (logical y=2), x=1: B=11 G=22 R=33 */
    CHK(GetPixel(dc, 1, 2) == cref(0x33, 0x22, 0x11), "app write to native row 0 (bottom-up) is visible at y=2: %06x", (unsigned)GetPixel(dc, 1, 2));
    CHK(GetPixel(dc, 1, 0) == cref(0, 0, 0), "untouched pixel is black");
    WRECT all = { 0, 0, 5, 3 }; int64_t br = CreateSolidBrush(cref(10, 20, 30)); FillRect(dc, PTR(&all), br);
    CHK(p[0] == 30 && p[1] == 20 && p[2] == 10 && p[12] == 30 && p[16 * 2 + 12] == 30, "FillRect writes BGR into native rows");
    CHK(p[15] == 0 && p[16 + 15] == 0 && p[32 + 15] == 0, "row padding bytes are untouched");
    SetPixelV(dc, 4, 0, cref(1, 2, 3));
    CHK(p[2 * 16 + 12] == 3 && p[2 * 16 + 13] == 2 && p[2 * 16 + 14] == 1, "SetPixelV at top row lands in last memory row");
    DeleteDC(dc); DeleteObject(hb); DeleteObject(br); }
  { int64_t hb, dc; uint8_t *p = mk_dib(&hb, &dc, 5, 3, 24, 0, 0); (void)p; DeleteDC(dc); DeleteObject(hb); }
  { BmiBuf b; bmi_init(&b, 5, -3, 24, 0, 0); uint64_t pv; int64_t hb = CreateDIBSection(0, PTR(&b), 0, PTR(&pv), 0, 0), dc = CreateCompatibleDC(0); SelectObject(dc, hb);
    uint8_t *p = (uint8_t *)(uintptr_t)pv; p[0] = 1; p[1] = 2; p[2] = 3;
    CHK(GetPixel(dc, 0, 0) == cref(3, 2, 1), "top-down 24bpp: native row 0 = logical y=0");
    SetPixelV(dc, 2, 2, cref(9, 8, 7)); CHK(p[2 * 16 + 6] == 7 && p[2 * 16 + 8] == 9, "top-down 24bpp: SetPixelV y=2 -> memory row 2");
    DeleteDC(dc); DeleteObject(hb); }

  SECTION("GUI-5: 8bpp palette DIB (RGBQUAD table, nearest match, SetDIBColorTable, duplicate-index preservation)");
  { uint32_t pal[4] = { 0x000000, 0xFF0000, 0x00FF00, 0x0000FF }; int64_t hb, dc; uint8_t *p = mk_dib(&hb, &dc, 8, 2, 8, pal, 4);
    memset(p, 0, 16); p[0] = 1; p[1] = 2; p[2] = 3; p[3] = 9;   /* index 9 は範囲外 = 黒 */
    CHK(GetPixel(dc, 0, 1) == cref(255, 0, 0) && GetPixel(dc, 1, 1) == cref(0, 255, 0) && GetPixel(dc, 2, 1) == cref(0, 0, 255), "indices map through the colour table");
    CHK(GetPixel(dc, 3, 1) == cref(0, 0, 0), "out-of-table index is black");
    WRECT r = { 4, 0, 6, 1 }; int64_t bg = CreateSolidBrush(cref(0, 255, 0)), bn = CreateSolidBrush(cref(250, 10, 10));
    FillRect(dc, PTR(&r), bg); CHK(p[8 + 4] == 2 && p[8 + 5] == 2, "FillRect exact palette colour -> index 2");
    WRECT r2 = { 6, 0, 7, 1 }; FillRect(dc, PTR(&r2), bn); CHK(p[8 + 6] == 1, "off-palette colour -> nearest index (red = 1): %u", p[8 + 6]);
    CHK(p[0] == 1 && p[1] == 2 && p[2] == 3 && p[3] == 9, "pixels outside the drawn rect keep their native indices (incl. out-of-range 9)");
    uint32_t nc = 0x000080; CHK(SetDIBColorTable(dc, 1, 1, PTR(&nc)) == 1, "SetDIBColorTable returns count");
    CHK(GetPixel(dc, 0, 1) == cref(0, 0, 0x80), "SetDIBColorTable re-colours existing pixels: %06x", (unsigned)GetPixel(dc, 0, 1));
    uint32_t back[2] = { 0, 0 }; CHK(GetDIBColorTable(dc, 1, 2, PTR(back)) == 2 && back[0] == 0x000080 && back[1] == 0x00FF00, "GetDIBColorTable round-trip %06x %06x", back[0], back[1]);
    DeleteDC(dc); DeleteObject(hb); DeleteObject(bg); DeleteObject(bn); }
  { uint32_t pal[3] = { 0x112233, 0xAABBCC, 0x112233 }; int64_t hb, dc; uint8_t *p = mk_dib(&hb, &dc, 4, 1, 8, pal, 3);
    p[0] = 2; p[1] = 1; p[2] = 0; p[3] = 2;
    WRECT r = { 0, 0, 4, 1 }; int64_t b = CreateSolidBrush(cref(0xAA, 0xBB, 0xCC)); IntersectClipRect(dc, 1, 0, 3, 1); FillRect(dc, PTR(&r), b);
    CHK(p[0] == 2 && p[1] == 1 && p[2] == 1 && p[3] == 2, "duplicate palette colours: clipped-out pixels keep index 2 (not renumbered to 0), drawn ones -> 1: %u %u %u %u", p[0], p[1], p[2], p[3]);
    DeleteDC(dc); DeleteObject(hb); DeleteObject(b); }

  SECTION("GUI-5: 4bpp / 1bpp palette DIB");
  { uint32_t pal[16]; for (int i = 0; i < 16; i++) pal[i] = (uint32_t)(i * 0x101010); int64_t hb, dc; uint8_t *p = mk_dib(&hb, &dc, 4, 1, 4, pal, 16);
    p[0] = 0x1F; p[1] = 0xA3;   /* pixels: 1, F, A, 3 */
    CHK(GetPixel(dc, 0, 0) == cref(0x10, 0x10, 0x10) && GetPixel(dc, 1, 0) == cref(0xF0, 0xF0, 0xF0) && GetPixel(dc, 2, 0) == cref(0xA0, 0xA0, 0xA0) && GetPixel(dc, 3, 0) == cref(0x30, 0x30, 0x30), "4bpp nibble order (high nibble = left pixel)");
    SetPixelV(dc, 2, 0, cref(0x50, 0x50, 0x50)); CHK(p[1] == 0x53, "4bpp SetPixelV updates only its nibble: %02x", p[1]);
    DeleteDC(dc); DeleteObject(hb); }
  { uint32_t pal[2] = { 0x102030, 0xA0B0C0 }; int64_t hb, dc; uint8_t *p = mk_dib(&hb, &dc, 16, 2, 1, pal, 2);
    p[0] = 0xA5; p[1] = 0x01; p[4] = 0xFF;   /* 下行(メモリ行 0): 1010 0101 0000 0001 ; 上行 = 全 1 */
    CHK(GetPixel(dc, 0, 1) == cref(0xA0, 0xB0, 0xC0) && GetPixel(dc, 1, 1) == cref(0x10, 0x20, 0x30) && GetPixel(dc, 7, 1) == cref(0xA0, 0xB0, 0xC0) && GetPixel(dc, 15, 1) == cref(0xA0, 0xB0, 0xC0) && GetPixel(dc, 14, 1) == cref(0x10, 0x20, 0x30), "1bpp MSB-first");
    CHK(GetPixel(dc, 3, 0) == cref(0xA0, 0xB0, 0xC0), "1bpp top row (memory row 1)");
    WRECT r = { 0, 1, 4, 2 }; int64_t b = CreateSolidBrush(cref(0xA0, 0xB0, 0xC0)); FillRect(dc, PTR(&r), b);
    CHK(p[0] == 0xF5, "1bpp FillRect sets bits 7..4 -> 0xF5: %02x", p[0]);
    WRECT r2 = { 0, 1, 8, 2 }; int64_t b2 = CreateSolidBrush(cref(0x10, 0x20, 0x30)); FillRect(dc, PTR(&r2), b2);
    CHK(p[0] == 0x00 && p[1] == 0x01, "1bpp FillRect clears bits 7..0 without touching the next byte: %02x %02x", p[0], p[1]);
    DeleteDC(dc); DeleteObject(hb); DeleteObject(b); DeleteObject(b2); }

  SECTION("GUI-5: StretchDIBits sources 24/8/4/1bpp (bottom-up, 2x, row padding)");
  { int64_t hd, dd; uint32_t *dp = (uint32_t *)(uintptr_t)mk_dib(&hd, &dd, 8, -4, 32, 0, 0);
    uint8_t s24[16 * 2]; memset(s24, 0, sizeof s24);   /* 3x2, stride 12; bottom-up: 先頭行 = 下 */
    uint8_t px24[6][3] = { {1, 2, 3}, {4, 5, 6}, {7, 8, 9}, {10, 11, 12}, {13, 14, 15}, {16, 17, 18} };   /* B,G,R */
    for (int i = 0; i < 6; i++) memcpy(s24 + (i / 3) * 12 + (i % 3) * 3, px24[i], 3);
    BmiBuf b; bmi_init(&b, 3, 2, 24, 0, 0);
    StretchDIBits(dd, 0, 0, 6, 4, 0, 0, 3, 2, PTR(s24), PTR(&b), 0, SRCCOPY);
    CHK((dp[0] & 0xFFFFFF) == rgb(12, 11, 10) && (dp[1] & 0xFFFFFF) == rgb(12, 11, 10) && (dp[2] & 0xFFFFFF) == rgb(15, 14, 13) && (dp[5] & 0xFFFFFF) == rgb(18, 17, 16), "24bpp bottom-up 2x: top row = last data row (%06x %06x)", dp[0] & 0xFFFFFF, dp[5] & 0xFFFFFF);
    CHK((dp[3 * 8 + 0] & 0xFFFFFF) == rgb(3, 2, 1) && (dp[3 * 8 + 5] & 0xFFFFFF) == rgb(9, 8, 7), "24bpp bottom-up 2x: bottom row = first data row");
    CHK((dp[0] >> 24) == 0xFF, "alpha forced opaque");
    uint32_t pal[3] = { 0x000000, 0xFF8000, 0x0080FF }; uint8_t s8[8] = { 1, 2, 0, 0, 2, 1, 0, 0 };   /* 2x2, stride 4 */
    bmi_init(&b, 2, 2, 8, pal, 3); b.h.biHeight = -2;
    StretchDIBits(dd, 0, 0, 2, 2, 0, 0, 2, 2, PTR(s8), PTR(&b), 0, SRCCOPY);
    CHK((dp[0] & 0xFFFFFF) == 0xFF8000 && (dp[1] & 0xFFFFFF) == 0x0080FF && (dp[8] & 0xFFFFFF) == 0x0080FF && (dp[9] & 0xFFFFFF) == 0xFF8000, "8bpp top-down + colour table");
    uint32_t pal4[16]; for (int i = 0; i < 16; i++) pal4[i] = (uint32_t)i * 0x080808; uint8_t s4[4] = { 0x12, 0x30, 0, 0 };   /* 3x1 */
    bmi_init(&b, 3, -1, 4, pal4, 16);
    StretchDIBits(dd, 0, 0, 3, 1, 0, 0, 3, 1, PTR(s4), PTR(&b), 0, SRCCOPY);
    CHK((dp[0] & 0xFFFFFF) == 0x080808 && (dp[1] & 0xFFFFFF) == 0x101010 && (dp[2] & 0xFFFFFF) == 0x181818, "4bpp nibbles");
    uint32_t pal1[2] = { 0x202020, 0xE0E0E0 }; uint8_t s1[4] = { 0xA0, 0, 0, 0 };   /* 4x1: 1010 */
    bmi_init(&b, 4, -1, 1, pal1, 2);
    StretchDIBits(dd, 0, 0, 8, 1, 0, 0, 4, 1, PTR(s1), PTR(&b), 0, SRCCOPY);
    CHK((dp[0] & 0xFFFFFF) == 0xE0E0E0 && (dp[1] & 0xFFFFFF) == 0xE0E0E0 && (dp[2] & 0xFFFFFF) == 0x202020 && (dp[4] & 0xFFFFFF) == 0xE0E0E0 && (dp[7] & 0xFFFFFF) == 0x202020, "1bpp 2x horizontal");
    DeleteDC(dd); DeleteObject(hd); }

  SECTION("GUI-5: GetDIBits / SetDIBits other bit depths");
  { int64_t hb, dc; uint32_t *p = (uint32_t *)(uintptr_t)mk_dib(&hb, &dc, 3, 2, 32, 0, 0);   /* bottom-up 32bpp section; logical top row: y=0 */
    p[0 * 3 + 0] = 0xFF0000FF; p[0 * 3 + 1] = 0xFF00FF00; p[0 * 3 + 2] = 0xFFFF0000;   /* メモリ行 0 = 下 : B, G, R(=0xFF0000 は青成分 FF -> 0xFFFF0000 は R=FF?) */
    p[1 * 3 + 0] = 0xFFFFFFFF; p[1 * 3 + 1] = 0xFF000000; p[1 * 3 + 2] = 0xFF808080;
    BmiBuf b; bmi_init(&b, 3, 2, 24, 0, 0); uint8_t o24[16 * 2]; memset(o24, 0xEE, sizeof o24);
    CHK(GetDIBits(dc, hb, 0, 2, PTR(o24), PTR(&b), 0) == 2, "GetDIBits 24bpp returns lines");
    CHK(o24[0] == 0xFF && o24[1] == 0 && o24[2] == 0 && o24[3] == 0 && o24[4] == 0xFF && o24[5] == 0 && o24[6] == 0 && o24[7] == 0 && o24[8] == 0xFF, "GetDIBits 24bpp BGR bytes, bottom-up (first output row = memory row 0): %02x %02x %02x | %02x %02x %02x", o24[0], o24[1], o24[2], o24[3], o24[4], o24[5]);
    CHK(o24[9] == 0 && o24[10] == 0 && o24[11] == 0 && o24[12] == 0xFF && o24[13] == 0xFF && o24[14] == 0xFF, "GetDIBits 24bpp row padding zeroed, row 1 = white: %02x %02x", o24[9], o24[12]);
    bmi_init(&b, 3, 2, 1, 0, 0); uint8_t o1[8]; memset(o1, 0xEE, sizeof o1);
    CHK(GetDIBits(dc, hb, 0, 2, PTR(o1), PTR(&b), 0) == 2 && b.h.biClrUsed == 2, "GetDIBits 1bpp returns 2 colours");
    CHK(b.col[0] == 0x000000 && b.col[1] == 0xFFFFFF, "1bpp default table black/white");
    CHK(o1[0] == 0x00 && o1[4] == 0xA0, "1bpp rows: row0 = memory row 0 (0000FF/00FF00/FF0000 -> luminance? nearest of black/white) %02x row1=%02x", o1[0], o1[4]);
    bmi_init(&b, 3, 2, 8, 0, 0); uint8_t o8[4 * 2];
    CHK(GetDIBits(dc, hb, 0, 2, PTR(o8), PTR(&b), 0) == 2 && b.h.biClrUsed == 256, "GetDIBits 8bpp returns 256 colours");
    CHK((b.col[o8[0]] & 0xFFFFFF) == 0x0000FF && (b.col[o8[1]] & 0xFFFFFF) == 0x00FF00 && (b.col[o8[2]] & 0xFFFFFF) == 0xFF0000 && (b.col[o8[4]] & 0xFFFFFF) == 0xFFFFFF && (b.col[o8[5]] & 0xFFFFFF) == 0x000000,
        "8bpp default 3-3-2 table: exact colours round-trip through indices (%06x %06x %06x %06x %06x)", b.col[o8[0]] & 0xFFFFFF, b.col[o8[1]] & 0xFFFFFF, b.col[o8[2]] & 0xFFFFFF, b.col[o8[4]] & 0xFFFFFF, b.col[o8[5]] & 0xFFFFFF);
    DeleteDC(dc); DeleteObject(hb); }
  { int64_t hb, dc; uint8_t *p = mk_dib(&hb, &dc, 3, 2, 24, 0, 0);
    uint32_t pal[2] = { 0x112233, 0xAABBCC }; BmiBuf b; bmi_init(&b, 3, 2, 1, pal, 2); uint8_t s1[8] = { 0xA0, 0, 0, 0, 0x40, 0, 0, 0 };   /* bottom-up: 行0 = 下 */
    CHK(SetDIBits(dc, hb, 0, 2, PTR(s1), PTR(&b), 0) == 2, "SetDIBits from 1bpp");
    CHK(GetPixel(dc, 0, 1) == cref(0xAA, 0xBB, 0xCC) && GetPixel(dc, 1, 1) == cref(0x11, 0x22, 0x33) && GetPixel(dc, 1, 0) == cref(0xAA, 0xBB, 0xCC), "SetDIBits 1bpp decoded through its colour table");
    CHK(p[0] == 0xCC && p[1] == 0xBB && p[2] == 0xAA && p[12 + 3] == 0xCC, "SetDIBits into a 24bpp DIB section is pushed to its native memory: %02x %02x %02x", p[0], p[1], p[2]);
    DeleteDC(dc); DeleteObject(hb); }

  SECTION("GUI-5: CreateBitmap (mono DDB / 24bpp / 32bpp) and mono<->colour BitBlt colour mapping");
  { uint8_t mb[4] = { 0xA0, 0x00, 0x40, 0x00 };   /* 10x2 (行 2B 境界): 行0 = 1010000000 , 行1 = 0100000000 */
    int64_t hm = CreateBitmap(10, 2, 1, 1, PTR(mb)); int64_t mdc = CreateCompatibleDC(0); SelectObject(mdc, hm);
    CHK(hm != 0 && GetPixel(mdc, 0, 0) == cref(255, 255, 255) && GetPixel(mdc, 1, 0) == 0 && GetPixel(mdc, 2, 0) == cref(255, 255, 255) && GetPixel(mdc, 1, 1) == cref(255, 255, 255), "CreateBitmap 1bpp: bit 1 = white, WORD-aligned rows");
    uint8_t bmo[32] = {0}; CHK(GetObjectW(hm, 32, PTR(bmo)) == 32 && *(uint16_t *)(bmo + 18) == 1, "GetObject: bmBitsPixel=1");
    int64_t hd, dd; uint32_t *dp = (uint32_t *)(uintptr_t)mk_dib(&hd, &dd, 10, -2, 32, 0, 0);
    SetTextColor(dd, cref(255, 0, 0)); SetBkColor(dd, cref(0, 0, 255));
    BitBlt(dd, 0, 0, 10, 2, mdc, 0, 0, SRCCOPY);
    CHK((dp[0] & 0xFFFFFF) == rgb(0, 0, 255) && (dp[1] & 0xFFFFFF) == rgb(255, 0, 0) && (dp[2] & 0xFFFFFF) == rgb(0, 0, 255), "mono -> colour: 1 = dest bk colour, 0 = dest text colour");
    /* color -> mono: 転送元 DC の bk 色と一致 = 白 */
    SetBkColor(dd, cref(255, 0, 0)); int64_t hm2 = CreateBitmap(10, 2, 1, 1, 0), m2 = CreateCompatibleDC(0); SelectObject(m2, hm2);
    BitBlt(m2, 0, 0, 10, 2, dd, 0, 0, SRCCOPY);
    CHK(GetPixel(m2, 1, 0) == cref(255, 255, 255) && GetPixel(m2, 0, 0) == 0 && GetPixel(m2, 2, 0) == 0, "colour -> mono mask: pixels equal to the source bk colour become white");
    int64_t hcc = CreateCompatibleBitmap(m2, 4, 4); uint8_t bm3[32]; GetObjectW(hcc, 32, PTR(bm3));
    CHK(*(uint16_t *)(bm3 + 18) == 1, "CreateCompatibleBitmap on a mono DC is a mono DDB");
    DeleteDC(m2); DeleteDC(mdc); DeleteDC(dd); DeleteObject(hm); DeleteObject(hm2); DeleteObject(hd); DeleteObject(hcc); }
  { uint8_t b24[20] = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 0, 11, 12, 13, 14, 15, 16, 17, 18, 0, 0 };   /* 3x2 24bpp DDB: 行 10B (WORD 境界), top-down */
    int64_t hb = CreateBitmap(3, 2, 1, 24, PTR(b24)), dc = CreateCompatibleDC(0); SelectObject(dc, hb);
    CHK(GetPixel(dc, 2, 0) == cref(9, 8, 7) && GetPixel(dc, 0, 1) == cref(13, 12, 11), "CreateBitmap 24bpp initial bits (WORD rows, top-down, BGR)");
    uint32_t b32[2] = { 0xFF102030, 0xFF405060 }; int64_t h32 = CreateBitmap(2, 1, 1, 32, PTR(b32)), d32 = CreateCompatibleDC(0); SelectObject(d32, h32);
    CHK(GetPixel(d32, 1, 0) == cref(0x40, 0x50, 0x60), "CreateBitmap 32bpp");
    DeleteDC(dc); DeleteDC(d32); DeleteObject(hb); DeleteObject(h32); }

  SECTION("GUI-5: fail-fast boundaries (explicit, not silent)");
  expect_failfast(ff_child_ds16, "CreateDIBSection 16bpp", "CreateDIBSection");
  expect_failfast(ff_child_ds_palcolors, "CreateDIBSection DIB_PAL_COLORS", "DIB_PAL_COLORS");
  expect_failfast(ff_child_cb8bits, "CreateBitmap 8bpp with bits", "CreateBitmap");
  expect_failfast(ff_child_sdib16, "StretchDIBits 16bpp", "StretchDIBits");
  expect_failfast(ff_child_getdibits16, "GetDIBits 16bpp", "GetDIBits");

  SECTION("GUI-5: div255 identity + AlphaBlend vs independent oracle (const alpha / per-pixel alpha, 1:1 and stretch)");
  { int bad = 0; for (uint32_t x = 0; x <= 255u * 255u; x++) if (gs_div255(x) != (x + 127) / 255) bad++;
    CHK(bad == 0, "gs_div255(x) == (x+127)/255 for all x in [0,65025] (bad=%d)", bad); }
  { enum { W = 37, H = 9 }; int64_t hs, sd, hd, dd; uint32_t *sp = (uint32_t *)(uintptr_t)mk_dib(&hs, &sd, W, -H, 32, 0, 0), *dp = (uint32_t *)(uintptr_t)mk_dib(&hd, &dd, W, -H, 32, 0, 0);
    static uint32_t d0[W * H], exp_[W * H]; int total_bad = 0, cases = 0;
    #define ALPHA_ORACLE(x, y, w, h, sw, sh, sca, afmt) do { memcpy(exp_, d0, sizeof exp_); \
      for (int yy = 0; yy < (h); yy++) for (int xx = 0; xx < (w); xx++) { \
        int dxp = (x) + xx, dyp = (y) + yy; if (dxp >= W || dyp >= H) continue; \
        int sxp = (int)(((int64_t)xx * (sw)) / (w)), syp = (int)(((int64_t)yy * (sh)) / (h)); if (sxp >= W || syp >= H) continue; \
        uint32_t s_ = sp[syp * W + sxp], d_ = d0[dyp * W + dxp], o_ = 0xFF000000u; \
        for (int c = 0; c < 3; c++) { uint32_t sc = (s_ >> (8 * c)) & 255, dcc = (d_ >> (8 * c)) & 255, a = (afmt) ? ((((s_ >> 24) * (sca)) + 127) / 255) : (sca), r = ((sc * (sca) + 127) / 255) + ((dcc * (255 - a) + 127) / 255); o_ |= (r > 255 ? 255 : r) << (8 * c); } \
        exp_[dyp * W + dxp] = o_; } } while (0)
    for (int it = 0; it < 60; it++) {
      for (int i = 0; i < W * H; i++) { sp[i] = g5rnd() | (it % 5 == 0 ? 0xFF000000u : 0); d0[i] = g5rnd(); dp[i] = d0[i]; }
      uint32_t sca = it < 4 ? (it == 0 ? 0 : it == 1 ? 255 : it == 2 ? 128 : 1) : g5rnd() & 255, afmt = it & 1;
      int w = 1 + (int)(g5rnd() % W), h = 1 + (int)(g5rnd() % H), sw = (it % 3 == 0) ? w : 1 + (int)(g5rnd() % W), sh = (it % 3 == 0) ? h : 1 + (int)(g5rnd() % H), x = (int)(g5rnd() % 8), y = (int)(g5rnd() % 4);
      AlphaBlend(dd, x, y, w, h, sd, 0, 0, sw, sh, (afmt << 24) | (sca << 16));
      ALPHA_ORACLE(x, y, w, h, sw, sh, sca, afmt);
      cases++; if (memcmp(exp_, dp, sizeof exp_)) total_bad++;
    }
    CHK(total_bad == 0, "AlphaBlend equals the independent oracle in %d random cases (bad=%d)", cases, total_bad);
    for (int i = 0; i < W * H; i++) { sp[i] = g5rnd(); d0[i] = g5rnd(); dp[i] = d0[i]; }
    AlphaBlend(dd, 0, 0, W, H, sd, 0, 0, W, H, (1u << 24) | (101u << 16)); ALPHA_ORACLE(0, 0, W, H, W, H, 100u, 1u);
    CHK(memcmp(exp_, dp, sizeof exp_) != 0, "negative control: AlphaBlend(sca=101) differs from the oracle(sca=100)");
    for (int i = 0; i < W * H; i++) dp[i] = d0[i];
    AlphaBlend(dd, 0, 0, W, H, sd, 0, 0, W, H, (1u << 24) | (100u << 16)); ALPHA_ORACLE(0, 0, W, H, W, H, 100u, 1u);
    CHK(memcmp(exp_, dp, sizeof exp_) == 0, "positive control: same parameters match the oracle");
    DeleteDC(sd); DeleteDC(dd); DeleteObject(hs); DeleteObject(hd); }

  SECTION("GUI-5: row-kernel BitBlt/StretchBlt == per-pixel reference (15 ROPs x geometry x clip x overlap)");
  { enum { W = 64, H = 48 };
    int64_t hs, sd, hd, dd; uint32_t *sp = (uint32_t *)(uintptr_t)mk_dib(&hs, &sd, W, -H, 32, 0, 0), *dp = (uint32_t *)(uintptr_t)mk_dib(&hd, &dd, W, -H, 32, 0, 0);
    static const uint32_t rops[] = { SRCCOPY, SRCPAINT, SRCAND, SRCINVERT, SRCERASE, NOTSRCCOPY, NOTSRCERASE, MERGECOPY, MERGEPAINT, PATCOPY, PATINVERT, PATPAINT, DSTINVERT, BLACKNESS, WHITENESS };
    static uint32_t d0[W * H], fast[W * H], ref[W * H]; int cases = 0, bad = 0, neg_detected = 0, per_rop[15] = {0}, same_cases = 0, same_bad = 0;
    int64_t hc, cd; uint32_t *cpp = (uint32_t *)(uintptr_t)mk_dib(&hc, &cd, W, -H, 32, 0, 0);
    for (int it = 0; it < 4500; it++) {
      int ri = it % 15; uint32_t rop = rops[ri];
      for (int i = 0; i < W * H; i++) { sp[i] = g5rnd(); d0[i] = g5rnd(); }
      int mode = (int)(g5rnd() % 6), same = (it % 7 == 6);
      int adw = 1 + (int)(g5rnd() % 60), adh = 1 + (int)(g5rnd() % 44);
      int dw = adw, dh = adh, sw = adw, sh = adh;
      if (mode == 1) { adw = 2 + 2 * (int)(g5rnd() % 25); dw = adw; sw = adw / 2; }                 /* 2x 水平 (dup2) */
      if (mode == 2) { sw = 1 + (int)(g5rnd() % 60); sh = 1 + (int)(g5rnd() % 44); }                /* 任意比 */
      if (mode == 3) { dw = -dw; }                                                                  /* 水平反転 */
      if (mode == 4) { dh = -dh; sw = 1 + (int)(g5rnd() % 60); }                                   /* 垂直反転 + 任意幅 */
      if (mode == 5) { dw = -dw; dh = -dh; }
      int dx = (int)(g5rnd() % 50) - 8, dy = (int)(g5rnd() % 40) - 6, sx = (int)(g5rnd() % 50) - 6, sy = (int)(g5rnd() % 40) - 4;
      int64_t src = same ? dd : sd;
      if (same) { sx = dx + (int)(g5rnd() % 7) - 3; sy = dy + (int)(g5rnd() % 5) - 2; if (!rop_needs_src_t(rop)) sx = sy = 0; }
      int64_t br = CreateSolidBrush((uint32_t)(g5rnd() & 0xFFFFFF)); int64_t ob = SelectObject(dd, br);
      int clipmode = (int)(g5rnd() % 4);
      #define SETUP() do { memcpy(dp, d0, sizeof d0); SelectClipRgn(dd, 0); \
        if (clipmode == 1) IntersectClipRect(dd, 5, 4, 50, 40); \
        if (clipmode == 2) { IntersectClipRect(dd, 0, 0, W, H); ExcludeClipRect(dd, 12, 9, 33, 29); } \
        if (clipmode == 3) { IntersectClipRect(dd, 3, 3, 61, 45); ExcludeClipRect(dd, 20, 0, 24, H); ExcludeClipRect(dd, 0, 20, W, 23); } } while (0)
      SETUP(); gdi_set_ref_blit(0); StretchBlt(dd, dx, dy, dw, dh, src, sx, sy, sw, sh, rop); memcpy(fast, dp, sizeof fast);
      SETUP(); gdi_set_ref_blit(1); StretchBlt(dd, dx, dy, dw, dh, src, sx, sy, sw, sh, rop); memcpy(ref, dp, sizeof ref); gdi_set_ref_blit(0);
      cases++; per_rop[ri]++;
      if (same) {   /* 同一サーフェス (重なりあり): 転送元を事前に全面コピーした別サーフェスから転送した結果 (= スナップショット/memmove 同等) と一致すること */
        memcpy(cpp, d0, sizeof d0); SETUP(); StretchBlt(dd, dx, dy, dw, dh, cd, sx, sy, sw, sh, rop); same_cases++;
        if (memcmp(dp, fast, sizeof fast)) { same_bad++; if (same_bad <= 6) printf("  same-mismatch it=%d rop=%08x mode=%d clip=%d d=(%d,%d,%d,%d) s=(%d,%d,%d,%d)\n", it, rop, mode, clipmode, dx, dy, dw, dh, sx, sy, sw, sh); }
      } else if (memcmp(fast, ref, sizeof fast)) { bad++; if (bad <= 5) printf("  mismatch it=%d rop=%08x mode=%d clip=%d d=(%d,%d,%d,%d) s=(%d,%d,%d,%d)\n", it, rop, mode, clipmode, dx, dy, dw, dh, sx, sy, sw, sh); }
      if (it % 50 == 0) {   /* ネガティブコントロール: 別 ROP / 別位置で実行した結果は参照と一致しない (比較器が差を検出できる) */
        SETUP(); gdi_set_ref_blit(0); StretchBlt(dd, dx + 1, dy, dw, dh, src, sx, sy, sw, sh, rop == SRCINVERT ? SRCPAINT : SRCINVERT);
        if (memcmp(dp, ref, sizeof ref)) neg_detected++;
      }
      SelectObject(dd, ob); DeleteObject(br); SelectClipRgn(dd, 0);
    }
    int minrop = 1 << 30; for (int i = 0; i < 15; i++) if (per_rop[i] < minrop) minrop = per_rop[i];
    printf("[selftest] gui5 equivalence: %d cases (%d same-surface), ref mismatches %d, same-surface mismatches %d, negative-control probes detected %d/90\n", cases, same_cases, bad, same_bad, neg_detected);
    CHK(bad == 0, "fast path == reference in %d cases incl. %d same-surface (%d mismatches vs ref; every ROP >= %d cases)", cases, same_cases, bad, minrop);
    CHK(same_cases > 400 && same_bad == 0, "same-surface overlapping blit (1:1 / stretch / flip / multi-rect clip) == blit from a pre-copied surface in %d cases (%d mismatches)", same_cases, same_bad);
    CHK(neg_detected >= 60, "negative control: wrong ROP/offset differs from the reference in %d/90 probes", neg_detected);
    DeleteDC(sd); DeleteDC(dd); DeleteDC(cd); DeleteObject(hs); DeleteObject(hd); DeleteObject(hc); }
}
