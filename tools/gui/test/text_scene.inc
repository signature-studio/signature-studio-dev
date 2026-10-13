/* text_scene.inc — GUI-9 (#186) / GUI-13 (#615): text_golden.c (native) と text_wasm_app.c (wasm; ブラウザ) が共有する GDI テキストのシーン。
 * 期待値は独立オラクル golden/ft_oracle.c (shim 非依存の native FreeType 直叩き) が同一仕様から作る (このファイルは共有しない)。
 * 使う側が先に gui_api.h / gui_internal.h と <stdio.h> <string.h> を include し、PTR / W / H を定義すること。 */
#define CR(r, g, b) ((uint32_t)((r) | (g) << 8 | (b) << 16))
static void w16(uint16_t *d, const char *s) { while ((*d++ = (uint8_t)*s++)); }
static int64_t mkfont(int h, const char *face) { uint16_t n[32] = { 0 }; w16(n, face); return CreateFontW(h, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, PTR(n)); }
static void wstr(uint16_t *d, const char *s) { w16(d, s); }
/* シーン本体: dc (W x H の 32bpp DIB 選択済みメモリ DC) へ描く。fault = シーン 1 のフォント高さを 1 ずらす (ネガティブコントロール) */
static void text_scene_draw(int64_t dc, int fault) {
  WRECT all = { 0, 0, W, H }; FillRect(dc, PTR(&all), CreateSolidBrush(CR(32, 32, 48)));
  uint16_t s[64];
  SetBkMode(dc, 1 /* TRANSPARENT */);
  /* 1 */ SelectObject(dc, mkfont(fault ? -13 : -12, "Open Sans")); SetTextColor(dc, CR(255, 255, 255)); wstr(s, "Hello, World! gjpqy 0123"); TextOutW(dc, 4, 4, PTR(s), 24);
  /* 2 */ SelectObject(dc, mkfont(-14, "Barlow")); SetBkMode(dc, 2 /* OPAQUE */); SetBkColor(dc, CR(200, 40, 40)); SetTextColor(dc, CR(255, 255, 0)); wstr(s, "Barlow OPAQUE"); TextOutW(dc, 4, 24, PTR(s), 13); SetBkMode(dc, 1);
  /* 3 face 名 "Segoe UI" -> alias で Open Sans */
  SelectObject(dc, mkfont(-16, "Segoe UI")); SetTextColor(dc, CR(0, 255, 128)); wstr(s, "Centered"); WRECT r3 = { 170, 4, 310, 44 }; DrawTextW(dc, PTR(s), -1, PTR(&r3), DT_CENTER | DT_VCENTER | DT_SINGLELINE);
  /* 4 */ SelectObject(dc, mkfont(13, "Open Sans")); SetTextColor(dc, CR(255, 160, 0)); wstr(s, "Line one\nsecond line"); WRECT r4 = { 170, 50, 310, 100 }; DrawTextW(dc, PTR(s), -1, PTR(&r4), DT_LEFT);
  /* 5 */ SelectObject(dc, mkfont(-12, "Open Sans")); SetTextColor(dc, CR(255, 255, 255)); SetTextAlign(dc, 24 | 2); wstr(s, "baseline"); TextOutW(dc, 120, 70, PTR(s), 8); SetTextAlign(dc, 0);
  /* 6 TA_CENTER 相当は x 計算をオラクルと揃えるため TA_CENTER で描く */
  SelectObject(dc, mkfont(-20, "Barlow")); SetTextColor(dc, CR(180, 220, 255)); SetTextAlign(dc, 6); wstr(s, "TA_CENTER"); TextOutW(dc, 80, 80, PTR(s), 9); SetTextAlign(dc, 0);
}
/* metrics 表: 2 face x 15 高さ = 30 行 (列 = face height ascent descent height intlead extlead avg max | extent("The quick brown fox"))。1 行ごとに emit */
static void text_scene_metrics(int64_t dc, void (*emit)(void *user, const char *line), void *user) {
  const char *names[2] = { "Open Sans", "Barlow" }; int hs[] = { -8, -9, -10, -11, -12, -13, -14, -16, -18, -20, -24, -32, 12, 16, 20 };
  uint16_t s[64]; wstr(s, "The quick brown fox");
  for (int fi = 0; fi < 2; fi++) for (unsigned hi = 0; hi < sizeof hs / sizeof *hs; hi++) {
    SelectObject(dc, mkfont(hs[hi], names[fi])); uint8_t tm[64]; memset(tm, 0, sizeof tm); GetTextMetricsW(dc, PTR(tm));
    int32_t *m = (int32_t *)tm; WSIZE z; GetTextExtentPoint32W(dc, PTR(s), 19, PTR(&z));
    char line[160]; snprintf(line, sizeof line, "%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d", names[fi], hs[hi], m[1], m[2], m[0], m[3], m[4], m[5], m[6], z.cx);
    emit(user, line);
  }
}
