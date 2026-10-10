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
API GetKeyboardLayoutList(I64 n, I64 list) {
  if (n < 0) { gui_set_last_error(87); return 0; }
  if (n == 0) return 1;
  *(U64 *)P_(list) = 0x04090409; return 1;   /* HKL は Win64 で 8B */
}
API GetKeyboardLayoutNameW(I64 buf) { static const char k[] = "00000409"; uint16_t *b = (uint16_t *)P_(buf); for (int i = 0; i < 9; i++) b[i] = (uint16_t)k[i]; return 1; }   /* KL_NAMELENGTH 9 */
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
  (void)sc; (void)flags; int ch = vk_to_char((uint32_t)vk, (const uint8_t *)P_(state));
  uint16_t *b = (uint16_t *)P_(buf);
  if (!ch || !b || (int32_t)cch < 1) return 0;
  b[0] = (uint16_t)ch; if ((int32_t)cch > 1) b[1] = 0;
  return 1;
}
