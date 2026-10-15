/* gui_core_ext.inc — user32 P1 拡張 (CAB-159)。gui_core.c の末尾から #include される (static 関数・状態を共有するため同一 TU)。
 * 範囲: 文字列/ユーティリティ・クリップボード・フック・モニタ/DPI・キャレット・キー名/レイアウト/ToUnicode・タッチ判定。
 * クリップボードはプロセス内ストア (ブラウザ Clipboard API との橋渡しは PROTOCOL.md §11 に設計のみ; host/proto 変更が要るため未実装)。 */

/* ================= 文字列 (UTF-16) ================= */
static uint16_t u16_upper(uint16_t c) {
  if (c < 0x80) return (c >= 'a' && c <= 'z') ? (uint16_t)(c - 32) : c;
  if (c == 0xB5) return 0x39C;
  if (c == 0xFF) return 0x178;
  if (c >= 0xE0 && c <= 0xFE && c != 0xF7) return (uint16_t)(c - 32);
  if (c >= 0x100 && c <= 0x17F) {            /* Latin Extended-A: 偶奇ペア (例外域は除く) */
    if ((c >= 0x139 && c <= 0x148) || (c >= 0x179 && c <= 0x17E)) return (c & 1) ? c : (uint16_t)(c - 1);
    if (c == 0x131) return 'I';
    if (c == 0x138 || c == 0x149 || c == 0x17F) return c;
    return (c & 1) ? (uint16_t)(c - 1) : c;
  }
  if (c >= 0x3B1 && c <= 0x3C9 && c != 0x3C2) return (uint16_t)(c - 32);   /* Greek */
  if (c == 0x3C2) return 0x3A3;
  if (c >= 0x3AC && c <= 0x3CE) { static const uint16_t g[] = { 0x386, 0x388, 0x389, 0x38A, 0, 0x391 }; if (c - 0x3AC < 4) return g[c - 0x3AC]; }
  if (c >= 0x430 && c <= 0x44F) return (uint16_t)(c - 32);                  /* Cyrillic */
  if (c >= 0x450 && c <= 0x45F) return (uint16_t)(c - 80);
  return c;
}
static uint16_t u16_lower(uint16_t c) {
  if (c < 0x80) return (c >= 'A' && c <= 'Z') ? (uint16_t)(c + 32) : c;
  if (c >= 0xC0 && c <= 0xDE && c != 0xD7) return (uint16_t)(c + 32);
  if (c == 0x178) return 0xFF;
  if (c >= 0x100 && c <= 0x17F) {
    if ((c >= 0x139 && c <= 0x148) || (c >= 0x179 && c <= 0x17E)) return (c & 1) ? (uint16_t)(c + 1) : c;
    if (c == 0x130) return 'i';
    if (c == 0x131 || c == 0x138 || c == 0x149 || c == 0x17F) return c;
    return (c & 1) ? c : (uint16_t)(c + 1);
  }
  if (c >= 0x391 && c <= 0x3A9 && c != 0x3A2) return (uint16_t)(c + 32);
  if (c >= 0x410 && c <= 0x42F) return (uint16_t)(c + 32);
  if (c >= 0x400 && c <= 0x40F) return (uint16_t)(c + 80);
  return c;
}
API CharNextW(I64 p) {
  const uint16_t *s = (const uint16_t *)P_(p);
  if (!s || !*s) return p;
  if (s[0] >= 0xD800 && s[0] < 0xDC00 && s[1] >= 0xDC00 && s[1] < 0xE000) return p + 4;
  return p + 2;
}
API CharUpperW(I64 p) {      /* 上位 16bit が 0 なら単一文字 (戻り値も文字)、さもなくば NUL 終端文字列を in-place */
  if ((U64)p < 0x10000) return u16_upper((uint16_t)p);
  for (uint16_t *s = (uint16_t *)P_(p); *s; s++) *s = u16_upper(*s);
  return p;
}
API CharUpperBuffW(I64 p, I64 n) { uint16_t *s = (uint16_t *)P_(p); uint32_t k = (uint32_t)n; if (!s) return 0; for (uint32_t i = 0; i < k; i++) s[i] = u16_upper(s[i]); return k; }
API CharLowerBuffW(I64 p, I64 n) { uint16_t *s = (uint16_t *)P_(p); uint32_t k = (uint32_t)n; if (!s) return 0; for (uint32_t i = 0; i < k; i++) s[i] = u16_lower(s[i]); return k; }
/* wtsapi32: ブラウザにセッション切替通知は無い。shimx の weak 定義 (常に TRUE) と同挙動の強定義 (#172: shimx 側を weak 化して重複を解消) */
API WTSRegisterSessionNotification(I64 h, I64 flags) { (void)h; (void)flags; return 1; }
API WTSUnRegisterSessionNotification(I64 h) { (void)h; return 1; }
/* ---- shimx の user32 weak 9 本の残り (#172): gui 強定義が shimx weak の機能を下回らないよう実装する ---- */
API CharLowerW(I64 p) {      /* CharUpperW の対: 上位 16bit が 0 なら単一文字、さもなくば NUL 終端文字列を in-place */
  if ((U64)p < 0x10000) return u16_lower((uint16_t)p);
  for (uint16_t *s = (uint16_t *)P_(p); *s; s++) *s = u16_lower(*s);
  return p;
}
API CharNextExA(I64 cp, I64 p, I64 flags) { (void)cp; (void)flags; const char *s = (const char *)P_(p); return (s && *s) ? p + 1 : p; }   /* ANSI = 1 byte 単位 (shimx weak と同じ。DBCS は cp932 テーブル (SHX-T8) 側の課題) */
/* OEM 変換は kernel32 (shimx の WideCharToMultiByte(CP_OEMCP)) の表を弱参照で借りる。単体ビルドでは ASCII のみ ('?' 置換) */
extern int WideCharToMultiByte(uint32_t cp, uint32_t flags, const uint16_t *w, int nw, char *out, int nout, const char *def, int *used) __attribute__((weak));
API CharToOemBuffW(I64 src, I64 dst, I64 n) {
  const uint16_t *w = (const uint16_t *)P_(src); char *d = (char *)P_(dst); uint32_t k = (uint32_t)n;
  if (!w || !d) return 0;
  for (uint32_t i = 0; i < k; i++) {
    if (w[i] < 0x80) { d[i] = (char)w[i]; continue; }
    char o = '?';
    if (WideCharToMultiByte) { char b[4] = {0}; int u = 0; if (WideCharToMultiByte(1 /* CP_OEMCP */, 0, &w[i], 1, b, 4, "?", &u) == 1 && !u) o = b[0]; }
    d[i] = o;
  }
  return 1;
}

/* RT_STRING (6): ブロック = (id>>4)+1、16 本の [WORD len][WCHAR*len] */
API LoadStringW(I64 hi, I64 id, I64 buf, I64 cch) {
  uint16_t *b = (uint16_t *)P_(buf); const void *data = NULL; uint32_t sz = 0; uint32_t uid = (uint32_t)id;
  if (g_res_provider && g_res_provider((U64)hi, 6, (uid >> 4) + 1, &data, &sz)) {
    const uint16_t *p = (const uint16_t *)data, *end = p + sz / 2;
    for (uint32_t k = uid & 15; k && p < end; k--) p += 1 + *p;
    if (p < end && *p && p + 1 + *p <= end) {
      uint32_t len = *p++;
      if ((int32_t)cch == 0) { if (buf) *(U64 *)P_(buf) = (U64)(uintptr_t)p; return len; }   /* cchBufferMax==0: 資源内文字列への読取専用ポインタ */
      uint32_t c = len < (uint32_t)cch - 1 ? len : (uint32_t)cch - 1;
      if (b) { memcpy(b, p, c * 2); b[c] = 0; }
      return c;
    }
  }
  gui_set_last_error(1814);   /* ERROR_RESOURCE_NAME_NOT_FOUND */
  if (b && (int32_t)cch > 0) b[0] = 0;
  return 0;
}
static int g_beeps; int gui_beep_count(void) { return g_beeps; }
API MessageBeep(I64 type) { (void)type; g_beeps++; return 1; }   /* 音は audio 担当。headless/host へ出力しない */

/* ================= タッチ当たり判定 (Win8+) =================
 * TOUCH_HIT_TESTING_INPUT (48B): pointerId@0, point@4, boundingBox@12, nonOccludedBoundingBox@28, orientation@44
 * TOUCH_HIT_TESTING_PROXIMITY_EVALUATION (12B): score(u16)@0, adjustedPoint@4
 * score = 点が矩形内なら 65535、外なら接触面 (boundingBox) の大きさに対する距離で線形減衰 (0 = 不一致)。adjustedPoint = 矩形へクランプした点。 */
API EvaluateProximityToRect(I64 prc, I64 pin, I64 pev) {
  const WRECT *r = (const WRECT *)P_(prc); const int32_t *in = (const int32_t *)P_(pin); uint8_t *ev = (uint8_t *)P_(pev);
  if (!r || !in || !ev) { gui_set_last_error(87); return 0; }
  int px = in[1], py = in[2];
  int cx = px < r->left ? r->left : px >= r->right ? r->right - 1 : px, cy = py < r->top ? r->top : py >= r->bottom ? r->bottom - 1 : py;
  int dx = px - cx, dy = py - cy; int64_t d2 = (int64_t)dx * dx + (int64_t)dy * dy, lo = 0, hi = 3037000499ll; while (lo < hi) { int64_t mid = (lo + hi + 1) / 2; if (mid * mid <= d2) lo = mid; else hi = mid - 1; }
  int d = (int)lo;   /* 整数距離 (切捨て) */
  int bw = in[5] - in[3], bh = in[6] - in[4]; int reach = (bw > bh ? bw : bh) / 2; if (reach < 1) reach = 1;
  uint32_t score = d == 0 ? 65535u : d >= reach ? 0u : (uint32_t)(65535 - (int64_t)d * 65535 / reach);
  *(uint16_t *)ev = (uint16_t)score; ev[2] = ev[3] = 0; ((int32_t *)ev)[1] = cx; ((int32_t *)ev)[2] = cy;
  return 1;
}
/* LRESULT の詰め方は非公開 (WM_TOUCHHITTESTING 戻り値): score | 補正点(矩形左上基準 x,y 各 16bit) を詰める最小意味実装 */
API PackTouchHitTestingProximityEvaluation(I64 pin, I64 pev) {
  const int32_t *in = (const int32_t *)P_(pin); const uint8_t *ev = (const uint8_t *)P_(pev); if (!in || !ev) return 0;
  const int32_t *e = (const int32_t *)ev; int ax = e[1] - in[3], ay = e[2] - in[4];
  return (I64)(*(const uint16_t *)ev) | ((I64)(uint16_t)ax << 16) | ((I64)(uint16_t)ay << 32);
}

/* ================= クリップボード (プロセス内ストア) =================
 * Windows 規約: Open 中のみ Empty/Set/Get/Enum 可 (他スレッドが Open 中なら Open 失敗)、Empty が所有者を設定し旧所有者へ WM_DESTROYCLIPBOARD、
 * SetClipboardData(fmt, NULL) は遅延レンダリング (Get 時に所有者へ WM_RENDERFORMAT)。データは HGLOBAL 値をそのまま保持 (内容は解釈しない)。 */
enum { WM_RENDERFORMAT_ = 0x305, WM_DESTROYCLIPBOARD_ = 0x307 };
typedef struct ClipFmt { uint32_t fmt; U64 data; struct ClipFmt *next; } ClipFmt;
static ClipFmt *g_clip; static int g_clip_open; static uint64_t g_clip_open_tid; static U64 g_clip_open_hwnd, g_clip_owner;
API OpenClipboard(I64 hwnd) {
  gui_sh(); uint64_t tid = gui_thread_id();
  if (g_clip_open && g_clip_open_tid != tid) { gui_set_last_error(5); return 0; }   /* ERROR_ACCESS_DENIED */
  g_clip_open = 1; g_clip_open_tid = tid; g_clip_open_hwnd = (U64)hwnd; return 1;
}
API CloseClipboard(void) {
  if (!g_clip_open || g_clip_open_tid != gui_thread_id()) { gui_set_last_error(1418); return 0; }   /* ERROR_CLIPBOARD_NOT_OPEN */
  g_clip_open = 0; return 1;
}
static int clip_is_mine(void) { return g_clip_open && g_clip_open_tid == gui_thread_id(); }
API EmptyClipboard(void) {
  if (!clip_is_mine()) { gui_set_last_error(1418); return 0; }
  U64 old = g_clip_owner;
  while (g_clip) { ClipFmt *n = g_clip->next; free(g_clip); g_clip = n; }
  g_clip_owner = g_clip_open_hwnd;
  if (old && wnd_from_h(old)) send_message(old, WM_DESTROYCLIPBOARD_, 0, 0);
  return 1;
}
API SetClipboardData(I64 fmt, I64 h) {
  if (!clip_is_mine()) { gui_set_last_error(1418); return 0; }
  for (ClipFmt *c = g_clip; c; c = c->next) if (c->fmt == (uint32_t)fmt) { c->data = (U64)h; return h; }
  ClipFmt *n = (ClipFmt *)calloc(1, sizeof *n); n->fmt = (uint32_t)fmt; n->data = (U64)h;
  ClipFmt **pp = &g_clip; while (*pp) pp = &(*pp)->next; *pp = n;
  return h;
}
API GetClipboardData(I64 fmt) {
  if (!clip_is_mine()) { gui_set_last_error(1418); return 0; }
  for (ClipFmt *c = g_clip; c; c = c->next) if (c->fmt == (uint32_t)fmt) {
    if (!c->data && g_clip_owner && wnd_from_h(g_clip_owner)) send_message(g_clip_owner, WM_RENDERFORMAT_, (U64)fmt, 0);   /* 遅延レンダリング */
    return (I64)c->data;
  }
  return 0;
}
API EnumClipboardFormats(I64 fmt) {
  if (!clip_is_mine()) { gui_set_last_error(1418); return 0; }
  gui_set_last_error(0);
  if (!fmt) return g_clip ? g_clip->fmt : 0;
  for (ClipFmt *c = g_clip; c; c = c->next) if (c->fmt == (uint32_t)fmt) return c->next ? c->next->fmt : 0;
  return 0;
}
API GetClipboardFormatNameW(I64 fmt, I64 buf, I64 cch) {
  const char *n = regmsg_name((uint32_t)fmt); uint16_t *b = (uint16_t *)P_(buf);
  if (!n || !b || (int32_t)cch <= 0) { gui_set_last_error(87); return 0; }
  uint16_t tmp[100]; int len = u8_to_u16(n, tmp, 100); if (len > (int32_t)cch - 1) len = (int32_t)cch - 1;
  memcpy(b, tmp, (size_t)len * 2); b[len] = 0; return len;
}

/* ================= フック (プロセス内ディスパッチのみ; グローバル/他プロセスのフックは存在しない) =================
 * 配送する種別: WH_KEYBOARD(2) / WH_MOUSE(7) (入力→キュー前、戻り値≠0 で破棄) / WH_GETMESSAGE(3) / WH_CALLWNDPROC(4) / WH_CALLWNDPROCRET(12)。
 * それ以外 (-1..14 の有効 id) は登録・解除のみ可能で呼ばれない。dwThreadId は無視 (GUI スレッドは 1 本)。新しいフックほど先に呼ばれる。 */
typedef struct Hook { U64 h; int id; U64 proc; int dead; struct Hook *next; } Hook;
static Hook *g_hooks[16]; static int g_hook_depth; static _Thread_local Hook *t_hook_cur;
static Hook *hook_live(Hook *k) { while (k && k->dead) k = k->next; return k; }
static int hook_any(int id) { return id >= -1 && id <= 14 && hook_live(g_hooks[id + 1]) != NULL; }
static I64 hook_invoke(Hook *k, int code, U64 wp, I64 lp) {
  Hook *saved = t_hook_cur; t_hook_cur = k; g_hook_depth++;
  I64 r = gui_call3(k->proc, (I64)code, (I64)wp, lp);
  g_hook_depth--; t_hook_cur = saved;
  if (g_hook_depth == 0)   /* 解除済みノードの遅延回収 */
    for (int i = 0; i < 16; i++) for (Hook **pp = &g_hooks[i]; *pp;) { if ((*pp)->dead) { Hook *d = *pp; *pp = d->next; free(d); } else pp = &(*pp)->next; }
  return r;
}
static I64 hook_run(int id, int code, U64 wp, I64 lp) { Hook *k = hook_live(g_hooks[id + 1]); return k ? hook_invoke(k, code, wp, lp) : 0; }
API SetWindowsHookExW(I64 id, I64 proc, I64 hmod, I64 tid) {
  (void)hmod; (void)tid; gui_sh();
  if (id < -1 || id > 14) { gui_set_last_error(1171); return 0; }   /* ERROR_INVALID_HOOK_FILTER */
  if (!proc) { gui_set_last_error(87); return 0; }
  Hook *k = (Hook *)calloc(1, sizeof *k); k->id = (int)id; k->proc = (U64)proc; k->h = h_alloc(HT_HOOK, k);
  k->next = g_hooks[id + 1]; g_hooks[id + 1] = k; return (I64)k->h;
}
API UnhookWindowsHookEx(I64 hhk) {
  Hook *k = (Hook *)h_get((U64)hhk, HT_HOOK);
  if (!k) { gui_set_last_error(1404); return 0; }   /* ERROR_INVALID_HOOK_HANDLE */
  h_free((U64)hhk); k->dead = 1;
  if (g_hook_depth == 0) for (Hook **pp = &g_hooks[k->id + 1]; *pp; pp = &(*pp)->next) if (*pp == k) { *pp = k->next; free(k); break; }
  return 1;
}
API CallNextHookEx(I64 hhk, I64 code, I64 wp, I64 lp) {
  Hook *k = hhk ? (Hook *)h_get((U64)hhk, HT_HOOK) : NULL; if (!k) k = t_hook_cur;
  if (!k) return 0;
  Hook *n = hook_live(k->next);
  return n ? hook_invoke(n, (int)code, (U64)wp, lp) : 0;
}

/* ================= モニタ / DPI (単一仮想モニタ = デスクトップ全面; DPI 描画スケールは GUI-7) ================= */
#define HMON_PRIMARY 0x7B000001ll
static int mon_rect(WRECT *r) { GuiShared *sh = gui_sh(); r->left = r->top = 0; r->right = (int32_t)sh->screen_w; r->bottom = (int32_t)sh->screen_h; return 1; }
API MonitorFromWindow(I64 hwnd, I64 flags) {
  Wnd *w = wnd_from_h((U64)hwnd);
  if (!w) return flags ? HMON_PRIMARY : 0;
  WRECT m, wr; mon_rect(&m); int sx, sy; to_screen_origin(w, &sx, &sy); wr = (WRECT){ sx, sy, sx + w->w, sy + w->hgt };
  return (!r_empty(r_isect(m, wr)) || flags) ? HMON_PRIMARY : 0;   /* MONITOR_DEFAULTTONULL = 0 */
}
API MonitorFromRect(I64 prc, I64 flags) {
  WRECT m, r = *(const WRECT *)P_(prc); mon_rect(&m);
  return (!r_empty(r_isect(m, r)) || flags) ? HMON_PRIMARY : 0;
}
API GetMonitorInfoW(I64 hmon, I64 pmi) {   /* MONITORINFO (40B) / MONITORINFOEXW (104B): cbSize, rcMonitor, rcWork, dwFlags, [szDevice[32]] */
  uint32_t *u = (uint32_t *)P_(pmi);
  if (hmon != HMON_PRIMARY || !u || (u[0] != 40 && u[0] != 104)) { gui_set_last_error(87); return 0; }
  WRECT m; mon_rect(&m); memcpy(u + 1, &m, 16); memcpy(u + 5, &m, 16); u[9] = 1;   /* MONITORINFOF_PRIMARY */
  if (u[0] == 104) { static const char dev[] = "\\\\.\\DISPLAY1"; uint16_t *d = (uint16_t *)(u + 10); memset(d, 0, 64); for (int i = 0; dev[i]; i++) d[i] = (uint16_t)dev[i]; }
  return 1;
}
API EnumDisplayMonitors(I64 hdc, I64 pclip, I64 proc, I64 data) {
  WRECT m; mon_rect(&m);
  if (pclip) m = r_isect(m, *(const WRECT *)P_(pclip));
  if (r_empty(m)) return 1;
  return gui_call4((U64)proc, HMON_PRIMARY, hdc, H_(&m), data) != 0;   /* MONITORENUMPROC(HMONITOR, HDC, LPRECT, LPARAM) */
}
API EnumDisplaySettingsW(I64 dev, I64 mode, I64 pdm) {   /* DEVMODEW (220B) の表示系フィールド。モード 0 = 現在の 1 モードのみ */
  GuiShared *sh = gui_sh(); uint8_t *d = (uint8_t *)P_(pdm); uint32_t m = (uint32_t)mode;
  if (dev) { const uint16_t *s = (const uint16_t *)P_(dev); static const char n[] = "\\\\.\\DISPLAY1"; for (int i = 0;; i++) { if (s[i] != (uint16_t)n[i]) { gui_set_last_error(87); return 0; } if (!n[i]) break; } }
  if (!d || (m != 0 && m != 0xFFFFFFFFu && m != 0xFFFFFFFEu)) return 0;   /* ENUM_CURRENT_SETTINGS=-1, ENUM_REGISTRY_SETTINGS=-2 */
  memset(d, 0, 220);
  static const char n[] = "\\\\.\\DISPLAY1"; for (int i = 0; n[i]; i++) ((uint16_t *)d)[i] = (uint16_t)n[i];
  *(uint16_t *)(d + 64) = 0x0401; *(uint16_t *)(d + 66) = 0x0401; *(uint16_t *)(d + 68) = 220;
  *(uint32_t *)(d + 72) = 0x20 | 0x40000 | 0x80000 | 0x100000 | 0x200000 | 0x400000;   /* POSITION|BITSPERPEL|PELSWIDTH|PELSHEIGHT|DISPLAYFLAGS|DISPLAYFREQUENCY */
  *(uint32_t *)(d + 168) = 32; *(uint32_t *)(d + 172) = sh->screen_w; *(uint32_t *)(d + 176) = sh->screen_h; *(uint32_t *)(d + 184) = 60;
  return 1;
}
int gdi_object_count(void);   /* gui_gdi.c: ストック除く生存 GDI オブジェクト数 */
int gdi_stock_count(void);
static int user_object_count(void) { return h_count(HT_WND) + h_count(HT_HOOK) + h_count(HT_ICON) + h_count(HT_CURSOR) + h_count(HT_MENU); }
API GetGuiResources(I64 hproc, I64 flags) {   /* GR_GDIOBJECTS=0 / GR_USEROBJECTS=1 / GR_GDIOBJECTS_PEAK=2 / GR_USEROBJECTS_PEAK=4 */
  (void)hproc;
  switch ((int)flags) {
    case 0: return gdi_object_count();
    case 1: return user_object_count();
    case 2: { int p = h_peak(0) - gdi_stock_count(); return p > 0 ? p : 0; }
    case 4: return h_peak(1);
  }
  gui_set_last_error(87); return 0;
}
static int g_dpi_hosting;
API SetThreadDpiHostingBehavior(I64 v) {   /* DPI_HOSTING_BEHAVIOR_DEFAULT=0 / MIXED=1; 戻り値 = 旧値、不正は -1 (INVALID) */
  if (v != 0 && v != 1) { gui_set_last_error(87); return -1; }
  int old = g_dpi_hosting; g_dpi_hosting = (int)v; return old;
}

/* ================= キャレット (1 個/システム; 反転矩形、点滅なし) =================
 * CreateCaret は P2 だが 4 つの P1 API が成立するために前倒し実装。描画は client DC への DSTINVERT で表示/消去をトグル。 */
static struct { U64 hwnd; int w, h, x, y, hide, drawn, exists; } g_caret;
static void caret_xor(void) {
  Wnd *w = wnd_from_h(g_caret.hwnd); if (!w) return;
  extern API PatBlt(I64, I64, I64, I64, I64, I64);
  RL cl = {0}; wnd_clip(w, &cl); U64 dc = gdi_get_dc_for_wnd(w, 0, &cl); rl_free(&cl);
  PatBlt((I64)dc, g_caret.x, g_caret.y, g_caret.w, g_caret.h, DSTINVERT); gdi_release_dc(dc); surf_flush();
}
static int caret_valid(void) {
  if (g_caret.exists && !wnd_from_h(g_caret.hwnd)) memset(&g_caret, 0, sizeof g_caret);   /* 所有ウィンドウ破棄 = キャレット破棄 */
  return g_caret.exists;
}
static void caret_hide_draw(void) { if (g_caret.drawn) { caret_xor(); g_caret.drawn = 0; } }
API CreateCaret(I64 hwnd, I64 hbmp, I64 w, I64 h) {
  (void)hbmp; if (!wnd_from_h((U64)hwnd)) { gui_set_last_error(1400); return 0; }
  if (caret_valid()) caret_hide_draw();
  memset(&g_caret, 0, sizeof g_caret);
  g_caret.exists = 1; g_caret.hwnd = (U64)hwnd; g_caret.w = (int)w > 0 ? (int)w : 1; g_caret.h = (int)h > 0 ? (int)h : 16; g_caret.hide = 1;
  return 1;
}
API SetCaretPos(I64 x, I64 y) {
  if (!caret_valid()) { gui_set_last_error(5); return 0; }
  int was = g_caret.drawn; caret_hide_draw();
  g_caret.x = (int)x; g_caret.y = (int)y;
  if (was) { caret_xor(); g_caret.drawn = 1; }
  return 1;
}
API ShowCaret(I64 hwnd) {
  if (!caret_valid() || (hwnd && (U64)hwnd != g_caret.hwnd)) { gui_set_last_error(5); return 0; }
  if (g_caret.hide > 0 && --g_caret.hide == 0) { caret_xor(); g_caret.drawn = 1; }
  return 1;
}
API HideCaret(I64 hwnd) {
  if (!caret_valid() || (hwnd && (U64)hwnd != g_caret.hwnd)) { gui_set_last_error(5); return 0; }
  caret_hide_draw(); g_caret.hide++; return 1;
}
API DestroyCaret(void) {
  if (!caret_valid()) { gui_set_last_error(5); return 0; }
  caret_hide_draw(); memset(&g_caret, 0, sizeof g_caret); return 1;
}
int gui_caret_state(int *x, int *y, int *hide, int *drawn) { if (!g_caret.exists) return 0; *x = g_caret.x; *y = g_caret.y; *hide = g_caret.hide; *drawn = g_caret.drawn; return 1; }

/* DestroyCursor: LoadCursor の共有 (擬似) ハンドルは no-op で TRUE、HT_CURSOR は解放、他は失敗 */
API DestroyCursor(I64 h) {
  if (h >= 0x7F000000 && h < 0x7F010000) return 1;
  if (h_get((U64)h, HT_CURSOR)) { void *p = h_get((U64)h, HT_CURSOR); h_free((U64)h); free(p); return 1; }
  gui_set_last_error(1402); return 0;   /* ERROR_INVALID_CURSOR_HANDLE */
}

/* ================= キーボード: スキャンコード表 (set 1, US 配列) / キー名 / レイアウト / ToUnicode ================= */
typedef struct { uint8_t sc, ext, vk; const char *name; } ScEnt;
static const ScEnt g_sc[] = {
  { 0x01, 0, 0x1B, "Esc" }, { 0x02, 0, '1', "1" }, { 0x03, 0, '2', "2" }, { 0x04, 0, '3', "3" }, { 0x05, 0, '4', "4" }, { 0x06, 0, '5', "5" },
  { 0x07, 0, '6', "6" }, { 0x08, 0, '7', "7" }, { 0x09, 0, '8', "8" }, { 0x0A, 0, '9', "9" }, { 0x0B, 0, '0', "0" }, { 0x0C, 0, 0xBD, "-" },
  { 0x0D, 0, 0xBB, "=" }, { 0x0E, 0, 0x08, "Backspace" }, { 0x0F, 0, 0x09, "Tab" },
  { 0x10, 0, 'Q', "Q" }, { 0x11, 0, 'W', "W" }, { 0x12, 0, 'E', "E" }, { 0x13, 0, 'R', "R" }, { 0x14, 0, 'T', "T" }, { 0x15, 0, 'Y', "Y" },
  { 0x16, 0, 'U', "U" }, { 0x17, 0, 'I', "I" }, { 0x18, 0, 'O', "O" }, { 0x19, 0, 'P', "P" }, { 0x1A, 0, 0xDB, "[" }, { 0x1B, 0, 0xDD, "]" },
  { 0x1C, 0, 0x0D, "Enter" }, { 0x1D, 0, 0x11, "Ctrl" },
  { 0x1E, 0, 'A', "A" }, { 0x1F, 0, 'S', "S" }, { 0x20, 0, 'D', "D" }, { 0x21, 0, 'F', "F" }, { 0x22, 0, 'G', "G" }, { 0x23, 0, 'H', "H" },
  { 0x24, 0, 'J', "J" }, { 0x25, 0, 'K', "K" }, { 0x26, 0, 'L', "L" }, { 0x27, 0, 0xBA, ";" }, { 0x28, 0, 0xDE, "'" }, { 0x29, 0, 0xC0, "`" },
  { 0x2A, 0, 0x10, "Shift" }, { 0x2B, 0, 0xDC, "\\" },
  { 0x2C, 0, 'Z', "Z" }, { 0x2D, 0, 'X', "X" }, { 0x2E, 0, 'C', "C" }, { 0x2F, 0, 'V', "V" }, { 0x30, 0, 'B', "B" }, { 0x31, 0, 'N', "N" },
  { 0x32, 0, 'M', "M" }, { 0x33, 0, 0xBC, "," }, { 0x34, 0, 0xBE, "." }, { 0x35, 0, 0xBF, "/" }, { 0x36, 0, 0x10, "Right Shift" },
  { 0x37, 0, 0x6A, "Num *" }, { 0x38, 0, 0x12, "Alt" }, { 0x39, 0, 0x20, "Space" }, { 0x3A, 0, 0x14, "Caps Lock" },
  { 0x3B, 0, 0x70, "F1" }, { 0x3C, 0, 0x71, "F2" }, { 0x3D, 0, 0x72, "F3" }, { 0x3E, 0, 0x73, "F4" }, { 0x3F, 0, 0x74, "F5" }, { 0x40, 0, 0x75, "F6" },
  { 0x41, 0, 0x76, "F7" }, { 0x42, 0, 0x77, "F8" }, { 0x43, 0, 0x78, "F9" }, { 0x44, 0, 0x79, "F10" }, { 0x45, 0, 0x13, "Pause" }, { 0x46, 0, 0x91, "Scroll Lock" },
  { 0x47, 0, 0x67, "Num 7" }, { 0x48, 0, 0x68, "Num 8" }, { 0x49, 0, 0x69, "Num 9" }, { 0x4A, 0, 0x6D, "Num -" }, { 0x4B, 0, 0x64, "Num 4" },
  { 0x4C, 0, 0x65, "Num 5" }, { 0x4D, 0, 0x66, "Num 6" }, { 0x4E, 0, 0x6B, "Num +" }, { 0x4F, 0, 0x61, "Num 1" }, { 0x50, 0, 0x62, "Num 2" },
  { 0x51, 0, 0x63, "Num 3" }, { 0x52, 0, 0x60, "Num 0" }, { 0x53, 0, 0x6E, "Num Del" }, { 0x57, 0, 0x7A, "F11" }, { 0x58, 0, 0x7B, "F12" },
  { 0x1C, 1, 0x0D, "Num Enter" }, { 0x1D, 1, 0x11, "Right Ctrl" }, { 0x35, 1, 0x6F, "Num /" }, { 0x37, 1, 0x2C, "Prnt Scrn" }, { 0x38, 1, 0x12, "Right Alt" },
  { 0x45, 1, 0x90, "Num Lock" }, { 0x47, 1, 0x24, "Home" }, { 0x48, 1, 0x26, "Up" }, { 0x49, 1, 0x21, "Page Up" }, { 0x4B, 1, 0x25, "Left" },
  { 0x4D, 1, 0x27, "Right" }, { 0x4F, 1, 0x23, "End" }, { 0x50, 1, 0x28, "Down" }, { 0x51, 1, 0x22, "Page Down" }, { 0x52, 1, 0x2D, "Insert" },
  { 0x53, 1, 0x2E, "Delete" }, { 0x5B, 1, 0x5B, "Left Windows" }, { 0x5C, 1, 0x5C, "Right Windows" }, { 0x5D, 1, 0x5D, "Application" },
};
static const ScEnt *sc_find(uint32_t sc, int ext) { for (size_t i = 0; i < sizeof g_sc / sizeof g_sc[0]; i++) if (g_sc[i].sc == sc && g_sc[i].ext == ext) return &g_sc[i]; return NULL; }
static uint32_t vk_from_scan(uint32_t sc, int ext) { const ScEnt *e = sc_find(sc & 0xFF, ext); return e ? e->vk : 0; }
API GetKeyNameTextW(I64 lparam, I64 buf, I64 cch) {   /* lParam: bit16-23 = scan, bit24 = extended */
  uint16_t *b = (uint16_t *)P_(buf); const ScEnt *e = sc_find(((uint32_t)lparam >> 16) & 0xFF, ((uint32_t)lparam >> 24) & 1);
  if (!b || (int32_t)cch <= 0) return 0;
  if (!e) { b[0] = 0; return 0; }
  int n = 0; for (; e->name[n] && n < (int32_t)cch - 1; n++) b[n] = (uint16_t)(uint8_t)e->name[n];
  b[n] = 0; return n;
}
/* ---- 配列 (GUI-6 #182): US 配列を基準に、DE (0x0407) / FR (0x040C) の差分キーだけを表で持つ。dead key / IME 配列は未対応 (0 = 文字なし)。
 * 表は XKB・KBDGR/KBDFR の公開仕様を元に手作成 (実 Windows との照合は未実施 → REPORT 範囲外)。n/s/g = 無修飾 / Shift / AltGr(Ctrl+Alt) の文字 (0 = なし)。 */
typedef struct { uint8_t sc, vk; uint16_t n, s, g; } LkEnt;
#define LL(sc, vk, c) { sc, vk, (uint16_t)(c), (uint16_t)((c) - 32), 0 }   /* 英小文字 (Shift = 大文字) */
static const LkEnt k_de[] = {
  { 0x02, '1', '1', '!', 0 }, { 0x03, '2', '2', '"', 0xB2 }, { 0x04, '3', '3', 0xA7, 0xB3 }, { 0x05, '4', '4', '$', 0 }, { 0x06, '5', '5', '%', 0 },
  { 0x07, '6', '6', '&', 0 }, { 0x08, '7', '7', '/', '{' }, { 0x09, '8', '8', '(', '[' }, { 0x0A, '9', '9', ')', ']' }, { 0x0B, '0', '0', '=', '}' },
  { 0x0C, 0xDB, 0xDF, '?', '\\' }, { 0x0D, 0xDD, 0xB4, '`', 0 },
  { 0x10, 'Q', 'q', 'Q', '@' }, { 0x12, 'E', 'e', 'E', 0x20AC }, LL(0x15, 'Z', 'z'), { 0x1A, 0xBA, 0xFC, 0xDC, 0 }, { 0x1B, 0xBB, '+', '*', '~' },
  { 0x27, 0xC0, 0xF6, 0xD6, 0 }, { 0x28, 0xDE, 0xE4, 0xC4, 0 }, { 0x29, 0xDC, '^', 0xB0, 0 }, { 0x2B, 0xBF, '#', '\'', 0 },
  LL(0x2C, 'Y', 'y'), { 0x32, 'M', 'm', 'M', 0xB5 }, { 0x33, 0xBC, ',', ';', 0 }, { 0x34, 0xBE, '.', ':', 0 }, { 0x35, 0xBD, '-', '_', 0 },
  { 0x56, 0xE2, '<', '>', '|' },
};
static const LkEnt k_fr[] = {
  { 0x02, '1', '&', '1', 0 }, { 0x03, '2', 0xE9, '2', '~' }, { 0x04, '3', '"', '3', '#' }, { 0x05, '4', '\'', '4', '{' }, { 0x06, '5', '(', '5', '[' },
  { 0x07, '6', '-', '6', '|' }, { 0x08, '7', 0xE8, '7', '`' }, { 0x09, '8', '_', '8', '\\' }, { 0x0A, '9', 0xE7, '9', '^' }, { 0x0B, '0', 0xE0, '0', '@' },
  { 0x0C, 0xDB, ')', 0xB0, ']' }, { 0x0D, 0xBB, '=', '+', '}' },
  LL(0x10, 'A', 'a'), LL(0x11, 'Z', 'z'), { 0x1A, 0xDD, 0, 0, 0 }, { 0x1B, 0xBA, '$', 0xA3, 0xA4 },
  LL(0x1E, 'Q', 'q'), { 0x27, 'M', 'm', 'M', 0 }, { 0x28, 0xC0, 0xF9, '%', 0 }, { 0x29, 0xDE, 0xB2, 0, 0 }, { 0x2B, 0xDC, '*', 0xB5, 0 },
  LL(0x2C, 'W', 'w'), { 0x32, 0xBC, ',', '?', 0 }, { 0x33, 0xBE, ';', '.', 0 }, { 0x34, 0xBF, ':', '/', 0 }, { 0x35, 0xDF, '!', 0xA7, 0 },
  { 0x56, 0xE2, '<', '>', 0 },
};
typedef struct { uint16_t langid; const LkEnt *t; int n; const char *name; } LkDef;
static const LkDef k_defs[] = { { 0x0409, NULL, 0, "US" }, { 0x0407, k_de, (int)(sizeof k_de / sizeof k_de[0]), "DE" }, { 0x040C, k_fr, (int)(sizeof k_fr / sizeof k_fr[0]), "FR" } };
static int g_kl = 0;   /* k_defs の index (0 = US) */
static void kbd_set_layout(uint32_t langid) { for (int i = 0; i < 3; i++) if (k_defs[i].langid == (langid & 0xFFFF)) { g_kl = i; return; } }
static const LkEnt *lk_by_sc(uint32_t sc) { const LkDef *d = &k_defs[g_kl]; for (int i = 0; i < d->n; i++) if (d->t[i].sc == sc) return &d->t[i]; return NULL; }
static const LkEnt *lk_by_vk(uint32_t vk) { const LkDef *d = &k_defs[g_kl]; for (int i = 0; i < d->n; i++) if (d->t[i].vk == vk) return &d->t[i]; return NULL; }
static uint32_t kbd_layout_vk(uint32_t sc, int ext) {   /* scancode -> VK (現配列)。0 = 不明 (呼出側は元の VK を使う) */
  if (ext) return 0;
  const LkEnt *e = lk_by_sc(sc); if (e) return e->vk;
  if (g_kl == 0) return 0;
  return vk_from_scan(sc, 0);
}
/* 配列込み: 状態配列 (GetKeyboardState 形式) + vk/sc から 1 文字。0 = 文字なし */
static int layout_to_char(uint32_t vk, uint32_t sc, const uint8_t *st) {
  if (g_kl == 0) return -1;   /* -1 = US 経路 (vk_to_char) へ */
  int shift = st && ((st[VK_SHIFT] | st[0xA0] | st[0xA1]) & 0x80), caps = st && (st[0x14] & 1);
  int ctrl = st && ((st[VK_CONTROL] | st[0xA2] | st[0xA3]) & 0x80), alt = st && ((st[VK_MENU] | st[0xA4] | st[0xA5]) & 0x80);
  const LkEnt *e = sc ? lk_by_sc(sc & 0xFF) : NULL; if (!e) e = lk_by_vk(vk);
  if (!e) return -1;
  if (ctrl && alt) return e->g;                                   /* AltGr = Ctrl+Alt */
  if (ctrl) return (e->n >= 'a' && e->n <= 'z') ? e->n - 'a' + 1 : 0;
  int up = shift; if (caps && e->s == e->n - 32) up = !shift;   /* Caps は「Shift 文字 = 無修飾文字の大文字」のキー (英字・DE の umlaut) だけ反転。FR の数字行 (é → 2) は近似で反転しない */
  return up ? e->s : e->n;
}
API GetKeyboardLayout(I64 tid) { (void)tid; uint32_t l = k_defs[g_kl].langid; return (I64)(((uint32_t)l << 16) | l); }
API ActivateKeyboardLayout(I64 h, I64 f) { (void)f; I64 old = GetKeyboardLayout(0); if (h > 1) kbd_set_layout((uint32_t)h & 0xFFFF); return old; }
API LoadKeyboardLayoutW(I64 s, I64 f) {   /* "0000040C" 形式の KLID */
  (void)f; const uint16_t *k = (const uint16_t *)P_(s); uint32_t v = 0;
  for (int i = 0; k && k[i] && i < 8; i++) { uint32_t c = k[i]; v = (v << 4) | (c <= '9' ? c - '0' : (c | 32) - 'a' + 10); }
  uint32_t l = v & 0xFFFF; for (int i = 0; i < 3; i++) if (k_defs[i].langid == l) return (I64)((l << 16) | l);
  gui_set_last_error(87); return 0;
}
API GetKeyboardLayoutList(I64 n, I64 list) {
  if (n < 0) { gui_set_last_error(87); return 0; }
  if (n == 0) return 1;
  *(U64 *)P_(list) = (U64)GetKeyboardLayout(0); return 1;   /* HKL は Win64 で 8B */
}
API GetKeyboardLayoutNameW(I64 buf) { char k[16]; snprintf(k, sizeof k, "%08X", k_defs[g_kl].langid); uint16_t *b = (uint16_t *)P_(buf); for (int i = 0; i < 9; i++) b[i] = (uint16_t)(uint8_t)k[i]; return 1; }   /* KL_NAMELENGTH 9 */
API MapVirtualKeyW(I64 code, I64 type) {
  uint32_t c = (uint32_t)code;
  switch ((int)type) {
    case 0: { const LkEnt *e = lk_by_vk(c); if (e) return e->sc;                                                  /* MAPVK_VK_TO_VSC */
              for (size_t i = 0; i < sizeof g_sc / sizeof g_sc[0]; i++) if (g_sc[i].ext == 0 && g_sc[i].vk == c) { if (g_kl && lk_by_sc(g_sc[i].sc)) continue; return g_sc[i].sc; } return 0; }
    case 1: case 3: { uint32_t v = kbd_layout_vk(c & 0xFF, (c >> 8) == 0xE0); if (v) return v; return vk_from_scan(c & 0xFF, (c >> 8) == 0xE0); }   /* MAPVK_VSC_TO_VK(_EX) */
    case 2: { uint8_t st[256] = { 0 }; int ch = layout_to_char(c, 0, st); if (ch < 0) ch = vk_to_char(c, st);
              if (c >= 'A' && c <= 'Z' && ch >= 'a' && ch <= 'z') ch -= 32;   /* MAPVK_VK_TO_CHAR: 英字は大文字 (US/DE/FR 共通) */
              return ch > 0 ? ch & 0x7FFFFFFF : 0; }
  }
  return 0;
}
/* US 配列: 状態配列 (GetKeyboardState 形式) から 1 文字へ。0 = 文字なし */
static int vk_to_char(uint32_t vk, const uint8_t *st) {
  int shift = st && ((st[VK_SHIFT] | st[0xA0] | st[0xA1]) & 0x80), ctrl = st && ((st[VK_CONTROL] | st[0xA2] | st[0xA3]) & 0x80), caps = st && (st[0x14] & 1);
  if (vk >= 'A' && vk <= 'Z') { int up = shift ^ caps; return ctrl ? (int)(vk - 'A' + 1) : (up ? (int)vk : (int)vk + 32); }
  if (vk >= '0' && vk <= '9') { static const char sym[] = ")!@#$%^&*("; return ctrl ? 0 : (shift ? sym[vk - '0'] : (int)vk); }
  if (vk >= 0x60 && vk <= 0x69) return '0' + (int)(vk - 0x60);
  switch (vk) {
    case VK_SPACE: return ' ';
    case VK_RETURN: return '\r'; case 9: return '\t'; case VK_BACK: return 8; case VK_ESCAPE: return 0x1B;
    case 0x6A: return '*'; case 0x6B: return '+'; case 0x6D: return '-'; case 0x6E: return '.'; case 0x6F: return '/';
    case 0xBA: return ctrl ? 0 : shift ? ':' : ';'; case 0xBB: return ctrl ? 0 : shift ? '+' : '='; case 0xBC: return ctrl ? 0 : shift ? '<' : ',';
    case 0xBD: return ctrl ? (shift ? 0x1F : 0) : shift ? '_' : '-'; case 0xBE: return ctrl ? 0 : shift ? '>' : '.'; case 0xBF: return ctrl ? 0 : shift ? '?' : '/';
    case 0xC0: return ctrl ? 0 : shift ? '~' : '`'; case 0xDB: return ctrl ? 0x1B : shift ? '{' : '[';
    case 0xDC: return ctrl ? 0x1C : shift ? '|' : '\\'; case 0xDD: return ctrl ? 0x1D : shift ? '}' : ']'; case 0xDE: return ctrl ? 0 : shift ? '"' : '\'';
  }
  return 0;
}
API ToUnicode(I64 vk, I64 sc, I64 state, I64 buf, I64 cch, I64 flags) {
  (void)flags; const uint8_t *st = (const uint8_t *)P_(state);
  int ch = layout_to_char((uint32_t)vk, (uint32_t)sc, st); if (ch < 0) ch = vk_to_char((uint32_t)vk, st);
  uint16_t *b = (uint16_t *)P_(buf);
  if (!ch || !b || (int32_t)cch < 1) return 0;
  b[0] = (uint16_t)ch; if ((int32_t)cch > 1) b[1] = 0;
  return 1;
}

/* ================= IME (GUI-6 #182): host の DOM composition → WM_IME_* + imm32 ================= *
 * host (gui.ts) が compositionstart/update/end を GUI_IN_IME (最大 4 UTF-16/レコードの連結) で送る。translate_input 内 (GUI スレッド) で
 * 即時 SendMessage するので、ハンドラが ImmGetCompositionStringW を呼ぶ時点の文字列は当該メッセージのもの。
 * 範囲: 変換候補ウィンドウ (CANDIDATEFORM) は位置を host へ通知するだけ。属性 (GCS_COMPATTR/COMPCLAUSE) は未提供 (長さ 0)。 */
#define WM_IME_STARTCOMPOSITION_ 0x10D
#define WM_IME_ENDCOMPOSITION_ 0x10E
#define WM_IME_COMPOSITION_ 0x10F
#define WM_IME_NOTIFY_ 0x282
#define GCS_COMPSTR_ 0x8
#define GCS_CURSORPOS_ 0x80
#define GCS_RESULTSTR_ 0x800
static uint16_t g_ime_comp[512], g_ime_res[512], g_ime_acc[512];
static int g_ime_ncomp, g_ime_nres, g_ime_nacc, g_ime_cursor, g_ime_composing, g_ime_open = 1;
static uint32_t g_ime_conv = 1 /* IME_CMODE_NATIVE */, g_ime_sent;
static void ime_input(const uint32_t *r) {
  uint32_t a = r[4], phase = a & 15, nu = (a >> 8) & 7, first = (a >> 12) & 1, last = (a >> 13) & 1;
  if (first) g_ime_nacc = 0;
  uint32_t u[4] = { r[2] & 0xFFFF, r[2] >> 16, r[3] & 0xFFFF, r[3] >> 16 };
  for (uint32_t i = 0; i < nu && i < 4 && g_ime_nacc < 511; i++) g_ime_acc[g_ime_nacc++] = (uint16_t)u[i];
  if (!last) return;
  Wnd *w = g_focus ? g_focus : g_active; if (!w) return;
  int cur = (int)r[5];
  g_ime_sent++;
  switch (phase) {
    case 1: g_ime_composing = 1; g_ime_ncomp = 0; send_message(w->h, WM_IME_STARTCOMPOSITION_, 0, 0); break;
    case 2:
      if (!g_ime_composing) { g_ime_composing = 1; send_message(w->h, WM_IME_STARTCOMPOSITION_, 0, 0); }
      memcpy(g_ime_comp, g_ime_acc, (size_t)g_ime_nacc * 2); g_ime_ncomp = g_ime_nacc; g_ime_cursor = cur > g_ime_ncomp ? g_ime_ncomp : cur;
      send_message(w->h, WM_IME_COMPOSITION_, 0, GCS_COMPSTR_ | GCS_CURSORPOS_); break;
    case 3:
      if (!g_ime_composing) { g_ime_composing = 1; send_message(w->h, WM_IME_STARTCOMPOSITION_, 0, 0); }
      memcpy(g_ime_res, g_ime_acc, (size_t)g_ime_nacc * 2); g_ime_nres = g_ime_nacc; g_ime_ncomp = 0; g_ime_cursor = 0;
      send_message(w->h, WM_IME_COMPOSITION_, 0, GCS_RESULTSTR_);
      g_ime_composing = 0; send_message(w->h, WM_IME_ENDCOMPOSITION_, 0, 0); break;
    case 4:
      if (!g_ime_composing) break;   /* composition 中でない cancel は無視 (START 無しの END を送らない) */
      g_ime_ncomp = 0; g_ime_cursor = 0;
      send_message(w->h, WM_IME_COMPOSITION_, 0, 0); g_ime_composing = 0; send_message(w->h, WM_IME_ENDCOMPOSITION_, 0, 0); break;
  }
}
uint32_t gui_ime_sent(void) { return g_ime_sent; }
#define HIMC_ 0x7D000001
API ImmGetContext(I64 h) { return wnd_from_h((U64)h) ? HIMC_ : 0; }
API ImmReleaseContext(I64 h, I64 himc) { (void)himc; return wnd_from_h((U64)h) != NULL; }
API ImmIsIME(I64 hkl) { (void)hkl; return 1; }
API ImmGetConversionStatus(I64 himc, I64 pconv, I64 psent) {
  if (himc != HIMC_) return 0;
  if (pconv) *(uint32_t *)P_(pconv) = g_ime_open ? g_ime_conv : 0; if (psent) *(uint32_t *)P_(psent) = 0; return 1;
}
API ImmSetConversionStatus(I64 himc, I64 conv, I64 sent) { (void)sent; if (himc != HIMC_) return 0; g_ime_conv = (uint32_t)conv; return 1; }
API ImmSetOpenStatus(I64 himc, I64 open) {
  if (himc != HIMC_) return 0;
  g_ime_open = open != 0;   /* host の OS IME は DOM から切替不可: 状態を保持するだけ (WM_IME_NOTIFY IMN_SETOPENSTATUS=8 を通知) */
  Wnd *w = g_focus ? g_focus : g_active; if (w) send_message(w->h, WM_IME_NOTIFY_, 8, 0);
  return 1;
}
API ImmAssociateContextEx(I64 h, I64 himc, I64 flags) { (void)himc; (void)flags; return wnd_from_h((U64)h) != NULL; }
/* ImmGetCompositionStringW(himc, GCS_*, buf, len): 返値 = バイト数。buf==NULL/len==0 は必要サイズのみ */
API ImmGetCompositionStringW(I64 himc, I64 idx, I64 buf, I64 len) {
  if (himc != HIMC_) return -1;
  const uint16_t *src = NULL; int n = 0;
  if (idx == GCS_COMPSTR_) { src = g_ime_comp; n = g_ime_ncomp; }
  else if (idx == GCS_RESULTSTR_) { src = g_ime_res; n = g_ime_nres; }
  else if (idx == GCS_CURSORPOS_) return g_ime_cursor;
  else return 0;
  int bytes = n * 2;
  if (buf && (int32_t)len > 0) { int c = bytes < (int32_t)len ? bytes : (int32_t)len; memcpy(P_(buf), src, (size_t)c); return c; }
  return bytes;
}
API ImmSetCompositionWindow(I64 himc, I64 cf) {   /* COMPOSITIONFORM: dwStyle(4) ptCurrentPos(8) rcArea(16) */
  if (himc != HIMC_ || !cf) return 0;
  const int32_t *p = (const int32_t *)P_(cf); Wnd *w = g_focus ? g_focus : g_active; int sx = 0, sy = 0; if (w) to_screen_origin(w, &sx, &sy);
  out_cmd(GUI_CMD_IME_POS, w && w->surf >= 0 ? (uint32_t)w->surf : 0, (uint32_t)(sx + p[1]), (uint32_t)(sy + p[2]), 0, 0, 0); return 1;
}
API ImmSetCandidateWindow(I64 himc, I64 cf) {   /* CANDIDATEFORM: dwIndex(4) dwStyle(4) ptCurrentPos(8) */
  if (himc != HIMC_ || !cf) return 0;
  const int32_t *p = (const int32_t *)P_(cf); Wnd *w = g_focus ? g_focus : g_active; int sx = 0, sy = 0; if (w) to_screen_origin(w, &sx, &sy);
  out_cmd(GUI_CMD_IME_POS, w && w->surf >= 0 ? (uint32_t)w->surf : 0, (uint32_t)(sx + p[2]), (uint32_t)(sy + p[3]), 0, 0, 0); return 1;
}
API ImmNotifyIME(I64 himc, I64 action, I64 index, I64 value) {   /* NI_COMPOSITIONSTR=0x15 のみ対応。index (CPS_CANCEL=4 / CPS_COMPLETE=1) は区別せず、常に表示中の composition をクリアする (DOM 側の確定・取消は host から行えないため表示状態の消去のみ) */
  (void)index; (void)value; if (himc != HIMC_) return 0;
  if (action == 0x15) { g_ime_ncomp = 0; g_ime_cursor = 0; return 1; }
  return 0;
}
API ImmGetOpenStatus(I64 himc) { return himc == HIMC_ && g_ime_open; }

/* ================= タッチ / ジェスチャ (GUI-6 #182) ================= *
 * host の PointerEvent (pointerType=touch) → GUI_IN_TOUCH。RegisterTouchWindow 済みの窓へは WM_TOUCH (GetTouchInputInfo)、
 * 未登録の窓へは primary 接触をマウス (WM_MOUSEMOVE/LBUTTON*) へ昇格 (Windows の既定動作)。2 本指の距離変化 → WM_GESTURE GID_ZOOM、
 * 1 本指移動 (SetGestureConfig で GID_PAN 許可の窓) → GID_PAN。WM_POINTER* は FL が import する API が無いため範囲外。 */
#define WM_TOUCH_ 0x240
#define WM_GESTURE_ 0x119
enum { GID_BEGIN_ = 1, GID_END_ = 2, GID_ZOOM_ = 3, GID_PAN_ = 4 };
enum { GF_BEGIN_ = 1, GF_INERTIA_ = 2, GF_END_ = 4 };
#define MAXTOUCH 10
typedef struct { int used; uint32_t id; int32_t x, y; } TPt;
static TPt g_tp[MAXTOUCH]; static U64 g_touch_wnd[32]; static int g_ntouch_wnd; static int g_primary_id = -1;
static U64 g_gest_wnd[32]; static uint32_t g_gest_want[32]; static int g_ngest;
static int g_zoom_on, g_zoom_dist, g_pan_on, g_pan_x, g_pan_y; static uint32_t g_gest_seq;
typedef struct { int32_t x, y; U64 src; uint32_t id, flags, mask, time; U64 extra; uint32_t cx, cy; } TouchIn;   /* TOUCHINPUT Win64 48B (x,y は 1/100 px) */
typedef struct { uint32_t cbSize, dwFlags, dwID; uint32_t _p; U64 hwnd; int16_t px, py; uint32_t inst, seq; U64 args; uint32_t cbExtra, _q; } GestInfo;   /* GESTUREINFO Win64 56B */
_Static_assert(sizeof(GestInfo) == 56 && sizeof(TouchIn) == 48, "win64 TOUCHINPUT/GESTUREINFO layout");
static TouchIn g_tin[MAXTOUCH]; static int g_ntin; static GestInfo g_gi;
static int touch_registered(U64 h) { for (int i = 0; i < g_ntouch_wnd; i++) if (g_touch_wnd[i] == h) return 1; return 0; }
API RegisterTouchWindow(I64 h, I64 flags) {
  (void)flags; if (!wnd_from_h((U64)h)) { gui_set_last_error(1400); return 0; }
  if (!touch_registered((U64)h) && g_ntouch_wnd < 32) g_touch_wnd[g_ntouch_wnd++] = (U64)h; return 1;
}
API SetGestureConfig(I64 h, I64 res, I64 c, I64 pcfg, I64 cb) {   /* GESTURECONFIG {dwID, dwWant, dwBlock} 12B */
  (void)res; if (!wnd_from_h((U64)h) || cb != 12) { gui_set_last_error(87); return 0; }
  const uint32_t *g = (const uint32_t *)P_(pcfg); uint32_t want = 0;
  for (int i = 0; i < (int)c; i++) { if (g[i * 3] == 0) { if (g[i * 3 + 1] & 1u) want = 0xFFFFFFFFu; } else if (g[i * 3] < 32) { if (g[i * 3 + 1] & 1u) want |= 1u << g[i * 3]; } }
  int k = -1; for (int i = 0; i < g_ngest; i++) if (g_gest_wnd[i] == (U64)h) k = i;
  if (k < 0 && g_ngest < 32) { k = g_ngest++; g_gest_wnd[k] = (U64)h; }
  if (k >= 0) g_gest_want[k] = want; return 1;
}
static uint32_t gest_want(U64 h) { for (int i = 0; i < g_ngest; i++) if (g_gest_wnd[i] == h) return g_gest_want[i]; return 0xFFFFFFFFu; }
API GetGestureInfo(I64 hgi, I64 pgi) {
  if (hgi != 0x7C000001 || !pgi) { gui_set_last_error(6); return 0; }
  GestInfo *o = (GestInfo *)P_(pgi); if (o->cbSize != sizeof(GestInfo)) { gui_set_last_error(87); return 0; }
  *o = g_gi; return 1;
}
API CloseGestureInfoHandle(I64 hgi) { return hgi == 0x7C000001; }
API RegisterTouchHitTestingWindow(I64 h, I64 v) { (void)v; return wnd_from_h((U64)h) != NULL; }
API GetTouchInputInfo(I64 h, I64 c, I64 pti, I64 cb) {
  if (h != 0x7B000001 || cb != (I64)sizeof(TouchIn) || !pti) { gui_set_last_error(87); return 0; }
  int n = (int)c < g_ntin ? (int)c : g_ntin; memcpy(P_(pti), g_tin, (size_t)n * sizeof(TouchIn)); return 1;
}
API CloseTouchInputHandle(I64 h) { return h == 0x7B000001; }
static TPt *tp_find(uint32_t id) { for (int i = 0; i < MAXTOUCH; i++) if (g_tp[i].used && g_tp[i].id == id) return &g_tp[i]; return NULL; }
static int tp_count(void) { int n = 0; for (int i = 0; i < MAXTOUCH; i++) n += g_tp[i].used; return n; }
static void send_gesture(Wnd *w, uint32_t id, uint32_t flags, int px, int py, U64 args) {
  memset(&g_gi, 0, sizeof g_gi); g_gi.cbSize = sizeof(GestInfo); g_gi.dwFlags = flags; g_gi.dwID = id; g_gi.hwnd = w->h;
  g_gi.px = (int16_t)px; g_gi.py = (int16_t)py; g_gi.seq = ++g_gest_seq; g_gi.args = args;
  I64 r = send_message(w->h, WM_GESTURE_, 0, 0x7C000001);
  if (!r) { /* 未処理 → 既定 (DefWindowProc は CloseGestureInfoHandle のみ) */ }
}
static void touch_input(const uint32_t *r) {
  GuiShared *sh = gui_sh();
  int x = (int32_t)r[2], y = (int32_t)r[3]; uint32_t a = r[4], id = a & 0xFF, phase = (a >> 8) & 15; int primary = (a >> 12) & 1; uint32_t t = r[6];
  int lx = 0, ly = 0; Wnd *w = g_capture; if (w) client_of_screen(w, x, y, &lx, &ly); else w = hit_test(x, y, &lx, &ly);
  TPt *p = tp_find(id);
  if (phase == 0) { if (!p) for (int i = 0; i < MAXTOUCH; i++) if (!g_tp[i].used) { p = &g_tp[i]; break; } if (p) { p->used = 1; p->id = id; } if (primary || g_primary_id < 0) g_primary_id = (int)id; }
  if (!p) return;
  int dx = x - p->x, dy = y - p->y; p->x = x; p->y = y;
  int wasprimary = (int)id == g_primary_id;
  if (!w) { if (phase >= 2) { p->used = 0; if (wasprimary) g_primary_id = -1; } return; }
  if (touch_registered(w->h)) {
    memset(g_tin, 0, sizeof g_tin); g_ntin = 0;
    for (int i = 0; i < MAXTOUCH; i++) if (g_tp[i].used) {
      TouchIn *o = &g_tin[g_ntin++]; o->x = g_tp[i].x * 100; o->y = g_tp[i].y * 100; o->id = g_tp[i].id; o->time = t; o->cx = o->cy = 0; o->mask = 0;
      o->flags = (g_tp[i].id == id ? (phase == 0 ? 0x2 /* DOWN */ : phase == 1 ? 0x1 /* MOVE */ : 0x4 /* UP */) : 0x1) | ((int)g_tp[i].id == g_primary_id ? 0x10 /* PRIMARY */ : 0);
    }
    send_message(w->h, WM_TOUCH_, (U64)g_ntin, 0x7B000001);
  } else if (wasprimary) {   /* マウス昇格 (primary 接触のみ) */
    uint32_t rec[8] = { phase == 0 ? GUI_IN_MOUSE_DOWN : phase == 1 ? GUI_IN_MOUSE_MOVE : GUI_IN_MOUSE_UP, 0, (uint32_t)x, (uint32_t)y, 0, 0, t, 0 };
    __atomic_store_n(&sh->cursor_x, x, __ATOMIC_RELAXED); __atomic_store_n(&sh->cursor_y, y, __ATOMIC_RELAXED);
    if (phase == 0) { if (phase == 0) { uint32_t mv[8] = { GUI_IN_MOUSE_MOVE, 0, (uint32_t)x, (uint32_t)y, 0, 0, t, 0 }; translate_input(mv); } sh->buttons |= 1; }
    else if (phase >= 2) { sh->buttons &= ~1u; rec[0] = GUI_IN_MOUSE_UP; }
    translate_input(rec);
  }
  /* ジェスチャ */
  int n = tp_count() - (phase >= 2 ? 1 : 0); uint32_t want = gest_want(w->h);   /* 離す接触は数えない (2 本指ズーム → 1 本になった時点で END) */
  if (n == 2 && (want & (1u << GID_ZOOM_))) {
    TPt *q[2]; int k = 0; for (int i = 0; i < MAXTOUCH && k < 2; i++) if (g_tp[i].used) q[k++] = &g_tp[i];
    int ddx = q[0]->x - q[1]->x, ddy = q[0]->y - q[1]->y, d = (int)(sqrt((double)ddx * ddx + (double)ddy * ddy) + 0.5), mx = (q[0]->x + q[1]->x) / 2, my = (q[0]->y + q[1]->y) / 2;
    if (!g_zoom_on) { g_zoom_on = 1; g_zoom_dist = d; send_gesture(w, GID_ZOOM_, GF_BEGIN_, mx, my, (U64)d); }
    else if (d != g_zoom_dist) { g_zoom_dist = d; send_gesture(w, GID_ZOOM_, 0, mx, my, (U64)d); }
  } else if (g_zoom_on) { g_zoom_on = 0; send_gesture(w, GID_ZOOM_, GF_END_, x, y, (U64)g_zoom_dist); }
  if (n == 1 && (want & (1u << GID_PAN_)) && phase == 1) {
    if (!g_pan_on) { g_pan_on = 1; send_gesture(w, GID_PAN_, GF_BEGIN_, x, y, 0); }
    else if (dx || dy) { (void)dx; (void)dy; send_gesture(w, GID_PAN_, 0, x, y, 0); }
  }
  if (phase >= 2) {
    if (g_pan_on && n <= 1) { g_pan_on = 0; send_gesture(w, GID_PAN_, GF_END_, x, y, 0); }
    p->used = 0; if (wasprimary) g_primary_id = -1;
  }
}
int gui_touch_count(void) { return tp_count(); }

/* ================= shell / ファイルダイアログ / D&D の Web 実装接続 (#172 SHX-T5) =================
 * kernel32/shell32 (shimx 担当) とは弱参照だけで結ぶ: shimx 無しの単体ビルドでも本 TU は解決できる。
 * Web 側 (window.open / File System Access) は main thread 専用なので gui_hostcall (include/gui_hostcall.h) で同期呼出する。
 * 選択ファイルは host が Emscripten FS の「ステージングディレクトリ」へ書き出し、FL へは Win パスで渡す。 */
#include "gui_hostcall.h"
#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#define GUI_EXPORT EMSCRIPTEN_KEEPALIVE
#else
#define GUI_EXPORT
#endif
extern int shimx_path_to_posix(const char *win, char *out, size_t cap) __attribute__((weak));
extern void shimx_set_notify_hook(void (*fn)(void)) __attribute__((weak));
extern void shimx_set_shell_execute_hook(int (*fn)(const char *, const char *, const char *)) __attribute__((weak));
extern void shimx_set_file_close_hook(void (*fn)(const char *)) __attribute__((weak));
extern int shimx_drag_accepts(size_t hwnd) __attribute__((weak));
extern size_t shimx_hdrop_create(const uint16_t *const *wpaths, uint32_t n, int x, int y, int nc) __attribute__((weak));
extern void DragFinish(size_t hdrop) __attribute__((weak));
extern void *shimx_get_drop_target(size_t hwnd) __attribute__((weak));
extern int shimx_drop_invoke(void *target, uint64_t hwnd, size_t hdrop, int x, int y) __attribute__((weak));

#define GUI_STAGE_WIN_DIR "C:\\Users\\webstudio\\Documents\\WebImport"
#define WM_DROPFILES_ 0x233
#define OFN_ALLOWMULTISELECT_ 0x200
#define OFN_ENABLEHOOK_ 0x20
#define OFN_ENABLETEMPLATE_ 0x40
#define OFN_ENABLETEMPLATEHANDLE_ 0x80
static uint32_t g_cderr;
API CommDlgExtendedError(void) { return g_cderr; }

static const char *stage_posix(char *buf, size_t cap) {
  if (shimx_path_to_posix && shimx_path_to_posix(GUI_STAGE_WIN_DIR, buf, cap) >= 0) return buf;
  snprintf(buf, cap, "/tmp/webimport"); return buf;
}
GUI_EXPORT const char *gui_stage_dir_posix(void) { static char b[512]; return stage_posix(b, sizeof b); }
GUI_EXPORT const char *gui_stage_dir_win(void) { return GUI_STAGE_WIN_DIR; }

/* ---- ShellExecute → window.open ---- */
static int url_ok(const char *u) { return u && (!strncasecmp(u, "http://", 7) || !strncasecmp(u, "https://", 8) || !strncasecmp(u, "mailto:", 7)); }
/* FL の Help (#554): OpenHelpTarget(0x10bdbe0) はローカルの Help パスを ShellExecuteW(NULL, NULL, path, NULL, NULL, SW_SHOW) で直接開く。
 * <FL>\Help\... と <FL>\System\Internet\error-offline.html だけを host の flHelp へ渡す (".." 等の検査は host の classifyTarget)。 */
#define GUI_FL_ROOT "C:\\Program Files\\Image-Line\\FL Studio 2026\\"
static int help_path_ok(const char *f) {
  if (!f || strncasecmp(f, GUI_FL_ROOT, sizeof GUI_FL_ROOT - 1)) return 0;
  f += sizeof GUI_FL_ROOT - 1;
  return !strncasecmp(f, "Help\\", 5) || !strcasecmp(f, "System\\Internet\\error-offline.html");
}
static int gui_shell_execute(const char *verb, const char *file, const char *params) {
  if (verb && *verb && strcasecmp(verb, "open")) return 0;
  if (help_path_ok(file)) {
    size_t n = strlen(file);
    if (n >= 1900) return 0;
    return gui_hostcall(GUI_HC_OPEN_HELP, 0, file, (uint32_t)n + 1, NULL, 0, NULL, 10000) == 1;
  }
  const char *u = url_ok(file) ? file : url_ok(params) ? params : NULL;   /* 旧式 ShellExecute("iexplore", url) 形も拾う */
  if (!u) return 0;
  size_t n = strlen(u);
  if (n >= 1900) return 0;
  return gui_hostcall(GUI_HC_OPEN_URL, 0, u, (uint32_t)n + 1, NULL, 0, NULL, 10000) == 1;
}

/* ---- GetOpenFileNameW / GetSaveFileNameW → File System Access ----
 * OPENFILENAMEW (Win64): lpstrFilter@24 nFilterIndex@44 lpstrFile@48 nMaxFile@56 lpstrFileTitle@64 nMaxFileTitle@72 lpstrInitialDir@80
 *   lpstrTitle@88 Flags@96 nFileOffset@100 nFileExtension@102 lpstrDefExt@104 (NT4 版 136B / 2000 版 152B)
 * hostcall in : title, initialDir, defExt, 現在のファイル名, ステージング(POSIX), ステージング(Win), Flags(10進), filterIndex の 8 項目 + (説明, パターン)* — NUL 区切り
 * hostcall out: 選択された base 名の列 (NUL 区切り, 末尾に空文字列)。result: 1 選択 / 0 キャンセル / <0 host エラー */
static uint64_t rd64(const uint8_t *p) { uint64_t v; memcpy(&v, p, 8); return v; }
static uint32_t rd32(const uint8_t *p) { uint32_t v; memcpy(&v, p, 4); return v; }
static int hc_put(char *buf, uint32_t cap, uint32_t *off, const char *s) {
  size_t l = strlen(s);
  if (*off + l + 1 > cap) return -1;
  memcpy(buf + *off, s, l + 1); *off += (uint32_t)l + 1; return 0;
}
static int hc_put_w(char *buf, uint32_t cap, uint32_t *off, U64 wp) {   /* UTF-16 引数 (NULL 可) を UTF-8 で積む */
  char t[512] = ""; if (wp >= 0x10000) u16_to_u8((const uint16_t *)P_(wp), t, sizeof t);
  return hc_put(buf, cap, off, t);
}
#define FD_NAMES_MAX 64
#define FD_W_CAP (GUI_HC_OUT + 700)   /* dir (<= 600) + host 応答 (< GUI_HC_OUT B; UTF-16 の単位数は UTF-8 のバイト数を超えない) */
static int fd_put(uint16_t *w, int *wl, const char *s, int sep) {   /* s を w の *wl 以降へ。0 = 全文が収まった / -1 = 収まらない (断片は返さない) */
  int cap = FD_W_CAP - *wl, tr = 0;
  if (cap < 1) return -1;
  int n = u8_to_u16x(s, w + *wl, cap, &tr);
  if (tr) return -1;
  *wl += n;
  if (sep) w[(*wl)++] = 0;   /* u8_to_u16x が書いた終端 (添字 <= cap-1) の位置 */
  return 0;
}
static I64 file_dialog(I64 ofnp, int save) {
  uint8_t *o = (uint8_t *)P_(ofnp);
  g_cderr = 0;
  if (!o || rd32(o) < 136) { g_cderr = 1; gui_set_last_error(87); return 0; }   /* CDERR_STRUCTSIZE */
  if (rd32(o + 96) & (OFN_ENABLEHOOK_ | OFN_ENABLETEMPLATE_ | OFN_ENABLETEMPLATEHANDLE_))
    gui_failfast(save ? "GetSaveFileNameW" : "GetOpenFileNameW", "lpfnHook / lpTemplateName (OFN_ENABLEHOOK / OFN_ENABLETEMPLATE) は未対応 (SHX-T14 #957)");   /* hook 付きの呼出しを黙って無視しない */
  uint16_t *file = (uint16_t *)P_(rd64(o + 48)); uint32_t maxfile = rd32(o + 56), flags = rd32(o + 96);
  if (!file || maxfile < 2) { g_cderr = 0x3002; gui_set_last_error(87); return 0; }   /* FNERR_INVALIDFILENAME */
  char in[GUI_HC_IN], sp[512]; uint32_t off = 0; int bad = 0;
  char cur[260]; u16_to_u8(file, cur, sizeof cur);
  char fi[16]; snprintf(fi, sizeof fi, "%u", rd32(o + 44));
  char fl[16]; snprintf(fl, sizeof fl, "%u", flags);
  bad |= hc_put_w(in, sizeof in, &off, rd64(o + 88));      /* title */
  bad |= hc_put_w(in, sizeof in, &off, rd64(o + 80));      /* initial dir */
  bad |= hc_put_w(in, sizeof in, &off, rd32(o) >= 112 ? rd64(o + 104) : 0);   /* defExt */
  bad |= hc_put(in, sizeof in, &off, cur);
  bad |= hc_put(in, sizeof in, &off, stage_posix(sp, sizeof sp));
  bad |= hc_put(in, sizeof in, &off, GUI_STAGE_WIN_DIR);
  bad |= hc_put(in, sizeof in, &off, fl);
  bad |= hc_put(in, sizeof in, &off, fi);
  for (const uint16_t *f = (const uint16_t *)P_(rd64(o + 24)); f && *f && !bad; ) {
    const uint16_t *d = f; while (*f) f++; f++;
    const uint16_t *pt = f; if (!*pt) break; while (*f) f++; f++;
    bad |= hc_put_w(in, sizeof in, &off, (U64)(uintptr_t)d);
    bad |= hc_put_w(in, sizeof in, &off, (U64)(uintptr_t)pt);
  }
  if (bad) { g_cderr = 2; gui_set_last_error(87); return 0; }   /* CDERR_INITIALIZATION (入力が hostcall 領域を超過) */
  char out[GUI_HC_OUT]; uint32_t on = 0;
  int rc = gui_hostcall(save ? GUI_HC_SAVE_FILE : GUI_HC_OPEN_FILE, flags, in, off, out, sizeof out - 2, &on, -1);
  if (rc == 0) return 0;                                        /* キャンセル (CommDlgExtendedError = 0) */
  if (rc != 1) { g_cderr = 2; gui_set_last_error(rc == -1 ? 1167 /* ERROR_DEVICE_NOT_CONNECTED: host 未接続 */ : 87); return 0; }
  out[on] = 0; out[on + 1] = 0;
  const char *names[FD_NAMES_MAX]; int nn = 0; const char *p = out;
  for (; *p && nn < FD_NAMES_MAX; p += strlen(p) + 1) names[nn++] = p;
  if (*p) { g_cderr = 2; gui_set_last_error(111); return 0; }   /* 65 件目以降は載らない: 黙って捨てず失敗 (CDERR_INITIALIZATION) */
  if (nn == 0) return 0;
  uint16_t w[FD_W_CAP]; int wl = u8_to_u16(GUI_STAGE_WIN_DIR, w, 600);
  uint32_t nfo; uint32_t total;
  if (nn == 1 || !(flags & OFN_ALLOWMULTISELECT_)) {            /* 単一: フルパス */
    w[wl++] = '\\'; nfo = (uint32_t)wl;
    if (fd_put(w, &wl, names[0], 0)) { g_cderr = 2; gui_set_last_error(111); return 0; }
    total = (uint32_t)wl + 1;
  } else {                                                      /* 複数 (OFN_EXPLORER 形式): dir\0name1\0name2\0\0 */
    w[wl++] = 0; nfo = (uint32_t)wl;
    for (int i = 0; i < nn; i++) if (fd_put(w, &wl, names[i], 1)) { g_cderr = 2; gui_set_last_error(111); return 0; }
    total = (uint32_t)wl + 1;
  }
  if (total > maxfile) { file[0] = (uint16_t)(total > 0xFFFF ? 0xFFFF : total); g_cderr = 0x3003; gui_set_last_error(111); return 0; }   /* FNERR_BUFFERTOOSMALL: 先頭 WORD に必要文字数 */
  memcpy(file, w, (size_t)wl * 2); file[wl] = 0;
  uint16_t *title = (uint16_t *)P_(rd64(o + 64)); uint32_t maxt = rd32(o + 72);
  if (title && maxt) { uint16_t t[300]; int tl = u8_to_u16(names[0], t, 260); if ((uint32_t)tl + 1 > maxt) tl = (int)maxt - 1; memcpy(title, t, (size_t)tl * 2); title[tl] = 0; }
  const uint16_t *nm = file + nfo; uint16_t ext = 0;
  for (uint16_t k = 0; nm[k]; k++) if (nm[k] == '.') ext = (uint16_t)(nfo + k + 1);
  uint16_t v16 = (uint16_t)nfo; memcpy(o + 100, &v16, 2); memcpy(o + 102, &ext, 2);
  return 1;
}
API GetOpenFileNameW(I64 p) { return file_dialog(p, 0); }
API GetSaveFileNameW(I64 p) { return file_dialog(p, 1); }

/* ---- Drag&Drop: host が FS へ書き出した名前の列を受け、WM_DROPFILES (DragAcceptFiles 済みの窓) か IDropTarget 経由で渡す ----
 * gui_drop_files は host (ブラウザ main thread) から呼ばれる。ウィンドウ木は GUI スレッド専有なので、ここでは要求を積んで doorbell を鳴らすだけにし、
 * 配送 (hit test / HDROP 生成 / 投函 / invoker 呼出) は GUI スレッドの pump_drops (try_get 入口) が行う。
 * 戻り: 1 = 受理 / -1 = shimx 未リンク / -3 = 要求が大きすぎる・キュー満杯。配送結果は gui_drop_last_result():
 *   1 = WM_DROPFILES 投函 / 2 = IDropTarget invoker が処理 / 0 = 受け手なし / -2 = HDROP 作成失敗 */
typedef int (*GuiDropInvoker)(void *target, uint64_t hwnd, size_t hdrop, int x, int y);
static GuiDropInvoker g_drop_invoker;
GUI_EXPORT void gui_set_drop_target_invoker(GuiDropInvoker fn) { g_drop_invoker = fn; }
#define DROP_Q 4
#define DROP_NAMES 2048
static struct { int x, y, n; char names[DROP_NAMES]; } g_dq[DROP_Q];
static uint32_t g_dq_h, g_dq_t;
static int g_drop_last = -9, g_drop_done;
GUI_EXPORT int gui_drop_last_result(void) { return __atomic_load_n(&g_drop_last, __ATOMIC_ACQUIRE); }
GUI_EXPORT int gui_drop_done_count(void) { return __atomic_load_n(&g_drop_done, __ATOMIC_ACQUIRE); }
GUI_EXPORT int gui_drop_files(int x, int y, int n, const char *names) {
  if (!shimx_hdrop_create || !shimx_drag_accepts) return -1;
  size_t len = 0; int k = 0;
  for (const char *p = names; p && *p && k < n; p += strlen(p) + 1, k++) len += strlen(p) + 1;
  if (len + 1 > DROP_NAMES) return -3;
  gui_sh();
  gui_lock();
  if (g_dq_t - g_dq_h >= DROP_Q) { gui_unlock(); return -3; }
  typeof(g_dq[0]) *r = &g_dq[g_dq_t % DROP_Q];
  r->x = x; r->y = y; r->n = k; if (len) memcpy(r->names, names, len); r->names[len] = 0;
  g_dq_t++;
  gui_unlock();
  gui_doorbell();
  return 1;
}
static int drop_deliver(int x, int y, int n, const char *names) {
  int lx, ly; Wnd *hit = hit_test(x, y, &lx, &ly);
  Wnd *acc = NULL; void *tgt = NULL;
  for (Wnd *w = hit; w && w != g_desktop; w = w->parent) {
    if (shimx_drag_accepts((size_t)w->h)) { acc = w; break; }
    if (shimx_get_drop_target && (tgt = shimx_get_drop_target((size_t)w->h)) != NULL) { acc = w; break; }
  }
  if (!acc) return 0;
  static uint16_t wbuf[64][300]; static const uint16_t *wp[64];   /* GUI スレッド専有 (スタックを食わない) */
  int k = 0; const char *p = names;
  for (; k < n && k < 64 && *p; k++, p += strlen(p) + 1) {
    int l = u8_to_u16(GUI_STAGE_WIN_DIR, wbuf[k], 200); wbuf[k][l++] = '\\'; u8_to_u16(p, wbuf[k] + l, 300 - l); wp[k] = wbuf[k];
  }
  int cx, cy; client_of_screen(acc, x, y, &cx, &cy);
  size_t hd = shimx_hdrop_create(wp, (uint32_t)k, cx, cy, 0);
  if (!hd) return -2;
  if (shimx_drag_accepts((size_t)acc->h)) {
    QMsg m = { acc->h, WM_DROPFILES_, (U64)hd, 0, gui_now_ms(), g_msg_pt, NULL };
    q_push(m);   /* HDROP の解放は受け手の DragFinish */
    return 1;
  }
  int handled = g_drop_invoker ? g_drop_invoker(tgt, acc->h, hd, cx, cy) : 0;
  if (DragFinish) DragFinish(hd);
  return handled ? 2 : 0;
}
static void pump_drops(void) {
  for (;;) {
    gui_lock();
    if (g_dq_h == g_dq_t) { gui_unlock(); return; }
    static typeof(g_dq[0]) cur;          /* GUI スレッド専有 (try_get は GUI スレッドのみ) */
    cur = g_dq[g_dq_h % DROP_Q]; g_dq_h++;
    gui_unlock();
    int r = drop_deliver(cur.x, cur.y, cur.n, cur.names);
    __atomic_store_n(&g_drop_last, r, __ATOMIC_RELEASE);
    __atomic_add_fetch(&g_drop_done, 1, __ATOMIC_RELEASE);
  }
}

/* #958: 書込み file の CloseHandle を stage 配下に限って host へ通知する (host は保存待ちの先なら実体へ反映する) */
static void gui_file_close(const char *posix) {
  const char *d = gui_stage_dir_posix();
  size_t n = strlen(d);
  if (strncmp(posix, d, n) != 0 || posix[n] != '/') return;
  size_t len = strlen(posix);
  if (len >= 1900) return;
  gui_hostcall(GUI_HC_FILE_CLOSED, 0, posix, (uint32_t)len + 1, NULL, 0, NULL, 30000);
}

/* ---- shimx 結線 (起動時に 1 回): bit0 = kernel object 通知→doorbell, bit1 = ShellExecute hook, bit3 = file close→host (#958) ---- */
GUI_EXPORT int gui_shimx_attach(void) {
  int m = 0;
  if (shimx_set_notify_hook) { shimx_set_notify_hook(gui_doorbell); g_kernel_notify_attached = 1; m |= 1; }
  if (shimx_set_shell_execute_hook) { shimx_set_shell_execute_hook(gui_shell_execute); m |= 2; }
  if (shimx_drop_invoke) { gui_set_drop_target_invoker(shimx_drop_invoke); m |= 4; }   /* #1388 SHX-T23: RegisterDragDrop 窓の IDropTarget 呼出し */
  if (shimx_set_file_close_hook) { shimx_set_file_close_hook(gui_file_close); m |= 8; }
  return m;
}
