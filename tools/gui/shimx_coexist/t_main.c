/* shimx + gui 共存リンクテスト (#172 SHX-T5)。PROXY_TO_PTHREAD の worker 上で走り、JS (run.mjs) が host (HostCallBridge) を担う。 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "shimx.h"
#include "../include/gui_hostcall.h"

extern int gui_shimx_attach(void);
extern int gui_drop_files(int x, int y, int n, const char *names);
extern const char *gui_stage_dir_posix(void);
extern int64_t gui_impl_GetOpenFileNameW(int64_t);
extern int64_t gui_impl_GetSaveFileNameW(int64_t);
extern int64_t gui_impl_CommDlgExtendedError(void);
extern int64_t t_make_window(int, int, int, int);
extern int64_t t_make_child(int64_t, int, int, int, int);
extern void t_post_thread_msg(uint32_t);
extern int t_peek(uint32_t *, int64_t *, int64_t *, int64_t *);
extern void gui_headless_attach(unsigned, unsigned);
extern int gui_reach_calls(const char *name);

/* ---- 公開名 (shimx weak 9 本。IR 宣言を持つ 6 本は gui adapter が強定義するはず) を C 署名で直呼び ---- */

static int g_pass, g_fail;
#define CHK(c, ...) do { if (c) g_pass++; else { g_fail++; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)
static double now_ms(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec * 1000.0 + t.tv_nsec / 1e6; }

static void w2u(const unsigned short *w, char *o, int cap) { int i = 0; for (; w[i] && i < cap - 1; i++) o[i] = w[i] < 128 ? (char)w[i] : '?'; o[i] = 0; }
static int weq(const unsigned short *w, const char *s) { int i = 0; for (; s[i]; i++) if (w[i] != (unsigned char)s[i]) return 0; return w[i] == 0; }
static void u2w(const char *s, unsigned short *w) { int i = 0; for (; s[i]; i++) w[i] = (unsigned char)s[i]; w[i] = 0; }

/* ---- reach 計数: adapter (gui 強定義) が実行されたか。-DGUI_REACH_LOG の adapter は呼出ごとに gui_reach_hit する ---- */
static int hits(const char *n) { return gui_reach_calls(n); }

static void test_char(void) {
  int a0 = hits("CharUpperW"), b0 = hits("CharLowerW"), c0 = hits("CharUpperBuffW"), d0 = hits("CharLowerBuffW"), e0 = hits("CharNextW");
  unsigned short s[8] = { 'a', 0xE9, 0x3B1, 0x430, 'z', 0 };
  CHK((uintptr_t)CharUpperW((LPWSTR)(uintptr_t)'a') == 'A', "CharUpperW single");
  CharUpperW(s); CHK(s[0] == 'A' && s[1] == 0xC9 && s[2] == 0x391 && s[3] == 0x410 && s[4] == 'Z', "CharUpperW string");
  CharLowerW(s); CHK(s[0] == 'a' && s[1] == 0xE9 && s[2] == 0x3B1 && s[3] == 0x430 && s[4] == 'z', "CharLowerW string");
  CHK((uintptr_t)CharLowerW((LPWSTR)(uintptr_t)0x130) == 'i', "CharLowerW U+0130");
  CHK(CharUpperBuffW(s, 3) == 3 && s[0] == 'A' && s[2] == 0x391 && s[3] == 0x430, "CharUpperBuffW");
  CHK(CharLowerBuffW(s, 3) == 3 && s[0] == 'a', "CharLowerBuffW");
  unsigned short sp[3] = { 0xD83D, 0xDE00, 0 };
  CHK(CharNextW(sp) == sp + 2 && CharNextW(sp + 2) == sp + 2, "CharNextW surrogate/NUL");
  CHK(hits("CharUpperW") > a0 && hits("CharLowerW") > b0 && hits("CharUpperBuffW") > c0 && hits("CharLowerBuffW") > d0 && hits("CharNextW") > e0,
      "IR 宣言あり 5 本の公開名が gui adapter (強定義) を経由している");
  const char *ab = "ab"; CHK(CharNextExA(1252, ab, 0) == (LPSTR)ab + 1 && CharNextExA(1252, ab + 2, 0) == (LPSTR)ab + 2, "CharNextExA advance/NUL (shimx weak)");
  unsigned short oem[4] = { 'A', 0xE9, 0x3B1, 0x4E2D }; char od[4];
  CHK(CharToOemBuffW(oem, od, 4) == 1 && od[0] == 'A' && (unsigned char)od[1] == 0xE9 && od[2] == '?' && od[3] == '?', "CharToOemBuffW (shimx の OEM = Latin-1 近似: é=0xE9, α/CJK='?')");
}

typedef struct { volatile HANDLE ev; unsigned delay_ms; int post_msg; } SetterArg;
static void *setter(void *p) {
  SetterArg *a = p; struct timespec t = { a->delay_ms / 1000, (long)(a->delay_ms % 1000) * 1000000L }; nanosleep(&t, NULL);
  if (a->post_msg) t_post_thread_msg(0x555); else SetEvent(a->ev);
  return NULL;
}
#include <pthread.h>
static void test_msgwait(void) {
  int m0 = hits("MsgWaitForMultipleObjects");
  HANDLE ev = CreateEventW(NULL, FALSE, FALSE, NULL);
  uint32_t msg; int64_t wp, lp, hw;
  while (t_peek(&msg, &wp, &lp, &hw)) {}
  double t0 = now_ms();
  CHK(MsgWaitForMultipleObjects(1, &ev, 0, 40, 0x4FF) == WAIT_TIMEOUT && now_ms() - t0 >= 35, "MsgWait timeout (handle+no msg)");
  CHK(MsgWaitForMultipleObjects(0, NULL, 0, 30, 0x4FF) == WAIT_TIMEOUT, "MsgWait nCount=0 timeout");
  SetEvent(ev);
  CHK(MsgWaitForMultipleObjects(1, &ev, 0, 1000, 0x4FF) == WAIT_OBJECT_0, "MsgWait: signaled handle wins (WAIT_OBJECT_0)");
  CHK(WaitForSingleObject(ev, 0) == WAIT_TIMEOUT, "auto-reset event consumed by MsgWait");
  pthread_t th; SetterArg a = { ev, 60, 0 };
  pthread_create(&th, NULL, setter, &a); t0 = now_ms();
  CHK(MsgWaitForMultipleObjects(1, &ev, 0, 5000, 0x4FF) == WAIT_OBJECT_0 && now_ms() - t0 < 1500, "MsgWait wakes on SetEvent from other thread (%.0f ms)", now_ms() - t0);
  pthread_join(th, NULL);
  SetterArg b = { ev, 60, 1 };
  pthread_create(&th, NULL, setter, &b); t0 = now_ms();
  CHK(MsgWaitForMultipleObjects(1, &ev, 0, 5000, 0x4FF) == WAIT_OBJECT_0 + 1 && now_ms() - t0 < 1500, "MsgWait returns nCount on message arrival (%.0f ms)", now_ms() - t0);
  pthread_join(th, NULL);
  CHK(t_peek(&msg, &wp, &lp, &hw) && msg == 0x555 && wp == 1 && lp == 2, "message still in queue after MsgWait");
  /* Ex: shimx weak の Ex は MsgWaitForMultipleObjects (= gui 強定義) へ委譲する */
  SetEvent(ev);
  CHK(MsgWaitForMultipleObjectsEx(1, &ev, 1000, 0x4FF, 0) == WAIT_OBJECT_0, "MsgWaitEx handle");
  t_post_thread_msg(0x556);
  CHK(MsgWaitForMultipleObjectsEx(1, &ev, 1000, 0x4FF, 0) == WAIT_OBJECT_0 + 1, "MsgWaitEx message");
  while (t_peek(&msg, &wp, &lp, &hw)) {}
  /* WAITALL: 全 object signaled かつ入力あり */
  HANDLE two[2] = { ev, CreateEventW(NULL, TRUE, TRUE, NULL) };
  t_post_thread_msg(0x557);
  CHK(MsgWaitForMultipleObjects(2, two, 1, 50, 0x4FF) == WAIT_TIMEOUT, "WAITALL: msg あり・ev 未 signaled → 待ち続けて TIMEOUT");
  SetEvent(ev);
  CHK(MsgWaitForMultipleObjects(2, two, 1, 1000, 0x4FF) == WAIT_OBJECT_0, "WAITALL: 全 signaled + msg → WAIT_OBJECT_0");
  while (t_peek(&msg, &wp, &lp, &hw)) {}
  CHK(MsgWaitForMultipleObjects(2, two, 1, 40, 0x4FF) == WAIT_TIMEOUT, "WAITALL: msg 無しなら全 signaled でも待つ");
  HANDLE bad = (HANDLE)0x7777;
  CHK(MsgWaitForMultipleObjects(1, &bad, 0, 10, 0x4FF) == WAIT_FAILED, "invalid handle → WAIT_FAILED");
  CHK(hits("MsgWaitForMultipleObjects") > m0, "MsgWaitForMultipleObjects の公開名が gui adapter 経由");
  CloseHandle(ev); CloseHandle(two[1]);
}

static void test_shell(void) {
  HINSTANCE r;
  unsigned short v[8], f[128], e[1] = { 0 };
  u2w("open", v);
  u2w("https://example.com/a?b=1", f); r = ShellExecuteW(0, v, f, NULL, NULL, 1); CHK((uintptr_t)r > 32, "ShellExecute https → >32");
  u2w("mailto:x@example.com", f); r = ShellExecuteW(0, v, f, NULL, NULL, 1); CHK((uintptr_t)r > 32, "ShellExecute mailto");
  u2w("iexplore.exe", f); { unsigned short p[64]; u2w("http://example.com/old-style", p); r = ShellExecuteW(0, v, f, p, NULL, 1); CHK((uintptr_t)r > 32, "ShellExecute(prog, url param)"); }
  u2w("javascript:alert(1)", f); r = ShellExecuteW(0, v, f, NULL, NULL, 1); CHK((uintptr_t)r <= 32, "javascript: 拒否");
  u2w("C:\\Windows\\notepad.exe", f); r = ShellExecuteW(0, v, f, e, NULL, 1); CHK((uintptr_t)r <= 32, "ローカル exe 拒否 (SE_ERR<=32)");
  u2w("file:///etc/passwd", f); r = ShellExecuteW(0, v, f, NULL, NULL, 1); CHK((uintptr_t)r <= 32, "file: 拒否");
  u2w("print", v); u2w("https://example.com/print", f); r = ShellExecuteW(0, v, f, NULL, NULL, 1); CHK((uintptr_t)r <= 32, "verb=print 拒否");
  u2w("open", v); u2w("https://blocked.example/", f); r = ShellExecuteW(0, v, f, NULL, NULL, 1); CHK((uintptr_t)r <= 32, "host が open できない (ポップアップブロック) → 失敗");
}

/* Win64 OPENFILENAMEW を手組み */
typedef struct { uint8_t b[152]; } OFN;
static void ofn_init(OFN *o, unsigned short *file, unsigned maxfile, unsigned short *title, unsigned maxtitle, const unsigned short *filter, unsigned flags) {
  memset(o, 0, sizeof *o);
  *(uint32_t *)(o->b) = 152; *(uint64_t *)(o->b + 24) = (uintptr_t)filter; *(uint32_t *)(o->b + 44) = 1;
  *(uint64_t *)(o->b + 48) = (uintptr_t)file; *(uint32_t *)(o->b + 56) = maxfile;
  *(uint64_t *)(o->b + 64) = (uintptr_t)title; *(uint32_t *)(o->b + 72) = maxtitle; *(uint32_t *)(o->b + 96) = flags;
}
static unsigned short g_filter[] = { 'W','A','V',' ','(','*','.','w','a','v',')',0, '*','.','w','a','v',0, 'A','l','l',0, '*','.','*',0, 0 };
static void test_dialog(void) {
  unsigned short file[260], ft[64]; OFN o; char u[300];
  file[0] = 0; ofn_init(&o, file, 260, ft, 64, g_filter, 0x00080000 /* OFN_EXPLORER */);
  CHK(gui_impl_GetOpenFileNameW((int64_t)(uintptr_t)&o) == 1, "GetOpenFileNameW → TRUE");
  w2u(file, u, sizeof u);
  CHK(weq(file, "C:\\Users\\webstudio\\Documents\\WebImport\\kick.wav"), "lpstrFile=%s", u);
  CHK(weq(ft, "kick.wav"), "lpstrFileTitle");
  uint16_t off = *(uint16_t *)(o.b + 100), ext = *(uint16_t *)(o.b + 102);
  CHK(off == 39 && file[off] == 'k' && ext == 44 && file[ext] == 'w', "nFileOffset=%u nFileExtension=%u", off, ext);
  /* cancel */
  file[0] = 0; ofn_init(&o, file, 260, ft, 64, g_filter, 0);
  CHK(gui_impl_GetOpenFileNameW((int64_t)(uintptr_t)&o) == 0 && gui_impl_CommDlgExtendedError() == 0, "cancel → FALSE, CommDlgExtendedError=0");
  /* multi */
  file[0] = 0; ofn_init(&o, file, 260, ft, 64, g_filter, 0x00080000 | 0x200);
  CHK(gui_impl_GetOpenFileNameW((int64_t)(uintptr_t)&o) == 1, "multi → TRUE");
  { const unsigned short *p = file; const char *want[4] = { "C:\\Users\\webstudio\\Documents\\WebImport", "a.wav", "b.wav", "c.mid" }; int ok = 1;
    for (int i = 0; i < 4; i++) { ok &= weq(p, want[i]); while (*p) p++; p++; } ok &= (*p == 0);
    CHK(ok, "multi-select: dir\\0name\\0name\\0name\\0\\0"); CHK(*(uint16_t *)(o.b + 100) == 39, "multi nFileOffset=%u", *(uint16_t *)(o.b + 100)); }
  /* buffer too small → FNERR_BUFFERTOOSMALL + 先頭 WORD に必要数 */
  unsigned short small[8] = { 0 }; ofn_init(&o, small, 8, ft, 64, g_filter, 0);
  CHK(gui_impl_GetOpenFileNameW((int64_t)(uintptr_t)&o) == 0 && gui_impl_CommDlgExtendedError() == 0x3003 && small[0] == 48, "buffer too small → 0x3003 (need=%u)", small[0]);
  /* host error */
  file[0] = 0; ofn_init(&o, file, 260, ft, 64, g_filter, 0);
  CHK(gui_impl_GetOpenFileNameW((int64_t)(uintptr_t)&o) == 0 && gui_impl_CommDlgExtendedError() == 2, "host error → FALSE, CDERR_INITIALIZATION");
  /* save */
  file[0] = 's'; file[1] = 0; ofn_init(&o, file, 260, ft, 64, g_filter, 0x00080000 | 2 /* OFN_OVERWRITEPROMPT */);
  CHK(gui_impl_GetSaveFileNameW((int64_t)(uintptr_t)&o) == 1 && weq(file, "C:\\Users\\webstudio\\Documents\\WebImport\\song.flp"), "GetSaveFileNameW");
  { /* FL の保存: 返された Win パスへ CreateFileW → WriteFile → CloseHandle。閉じた時点で host へ反映される (#958) */
    DWORD nw = 0; HANDLE hf = CreateFileW(file, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    CHK(hf != INVALID_HANDLE_VALUE, "save 先を CreateFileW で開ける");
    if (hf != INVALID_HANDLE_VALUE) { CHK(WriteFile(hf, "FLP-DATA", 8, &nw, NULL) && nw == 8, "save へ書ける"); CloseHandle(hf); }
    printf("STAGE %s\n", gui_stage_dir_posix()); }
  { OFN bad; memset(&bad, 0, sizeof bad); *(uint32_t *)bad.b = 20; CHK(gui_impl_GetOpenFileNameW((int64_t)(uintptr_t)&bad) == 0 && gui_impl_CommDlgExtendedError() == 1, "lStructSize 不正 → CDERR_STRUCTSIZE"); }
}

extern int gui_drop_last_result(void);
extern int gui_drop_done_count(void);
/* host(別スレッド相当) から要求 → GUI スレッド (この関数) の PeekMessage が配送する。戻り = 配送結果 (gui_drop_last_result) */
static int drop_and_wait(int x, int y, int n, const char *names, int *got_drop, int64_t *wp_out, int64_t *hw_out) {
  int before = gui_drop_done_count(); uint32_t m; int64_t w, l, h; *got_drop = 0;
#define TAKE() do { if (t_peek(&m, &w, &l, &h) && m == 0x233) { *got_drop = 1; *wp_out = w; *hw_out = h; } } while (0)
  if (gui_drop_files(x, y, n, names) != 1) return -100;
  for (int i = 0; i < 500 && gui_drop_done_count() == before; i++) {
    TAKE();
    if (gui_drop_done_count() == before) { struct timespec t = { 0, 2000000 }; nanosleep(&t, NULL); }
  }
  for (int i = 0; i < 20; i++) TAKE();   /* WM_PAINT は Dispatch しないので無限に返る → 回数で打切り */
#undef TAKE
  return gui_drop_done_count() > before ? gui_drop_last_result() : -101;
}
static void test_drop(void) {
  int64_t top = t_make_window(10, 20, 300, 200), kid = t_make_child(top, 50, 40, 100, 100);
  CHK(top && kid, "window create");
  int got; int64_t wp = 0, hw = 0;
  CHK(drop_and_wait(60, 60, 1, "a.wav\0", &got, &wp, &hw) == 0 && !got, "未登録窓 → 配送結果 0 (WM_DROPFILES なし)");
  DragAcceptFiles((HWND)(uintptr_t)top, TRUE);
  CHK(shimx_drag_accepts((HWND)(uintptr_t)top) == 1, "shimx_drag_accepts");
  CHK(drop_and_wait(110, 100, 2, "a.wav\0b.mid\0", &got, &wp, &hw) == 1 && got && hw == top, "子窓の上に drop → 祖先 (top) へ WM_DROPFILES");
  HANDLE hd = (HANDLE)(uintptr_t)wp;
  CHK(DragQueryFileW(hd, 0xFFFFFFFFu, NULL, 0) == 2, "DragQueryFile count");
  unsigned short buf[300];
  CHK(DragQueryFileW(hd, 0, NULL, 0) == 44, "DragQueryFile len(0)");
  CHK(DragQueryFileW(hd, 1, buf, 300) == 44 && weq(buf, "C:\\Users\\webstudio\\Documents\\WebImport\\b.mid"), "DragQueryFile(1)");
  CHK(DragQueryFileW(hd, 0, buf, 10) == 9 && buf[9] == 0, "cch 切詰め");
  struct { int x, y; } pt = { -1, -1 };
  CHK(DragQueryPoint(hd, &pt) == TRUE && pt.x == 100 && pt.y == 80, "DragQueryPoint=(%d,%d) (top client 座標 期待 (100,80))", pt.x, pt.y);
  DragFinish(hd);
  CHK(DragQueryFileW(hd, 0xFFFFFFFFu, NULL, 0) == 0, "DragFinish 後は無効ハンドル");
  DragAcceptFiles((HWND)(uintptr_t)top, FALSE);
  CHK(drop_and_wait(110, 100, 1, "a.wav\0", &got, &wp, &hw) == 0 && !got, "DragAcceptFiles(FALSE) 後は 0");
  CHK(drop_and_wait(900, 900, 1, "a.wav\0", &got, &wp, &hw) == 0 && !got, "窓の外は 0");
}

/* ---- SHX-T23 (#1388): RegisterDragDrop 窓。偽 guest の IDropTarget (vtable = VA 4 個) を mock invoke が C 関数として呼ぶ。
 * IDataObject の呼出しは lifttab トークン経由 (guest→C 経路)。C→guest 経路は shimx_cbtrans_set_invoke の mock で代替。 */
static uint64_t g_idt_vt[7];
static struct { uint64_t vt; } g_idt_obj;
static int g_idt_calls[4], g_idt_eff, g_idt_qgd_ok, g_idt_qgd_bad, g_idt_blk_len;
static uint8_t g_idt_blk[512];
static unsigned long long idt_invoke(unsigned long long va, unsigned long long a0, unsigned long long a1, unsigned long long a2,
                                     unsigned long long a3, unsigned long long a4, unsigned long long a5, unsigned long long a6, unsigned long long a7) {
  (void)a0; (void)a2; (void)a5; (void)a6; (void)a7;
  if (va == 0x1001) { g_idt_calls[0]++; *(uint32_t *)(uintptr_t)a4 = 1; return 0; }   /* DragEnter(this, pDataObj, grfKeyState, pt, pdwEffect) */
  if (va == 0x1002) { g_idt_calls[1]++; *(uint32_t *)(uintptr_t)a3 = 1; return 0; }   /* DragOver(this, grfKeyState, pt, pdwEffect) */
  if (va == 0x1003) { g_idt_calls[2]++; return 0; }                                    /* DragLeave(this) */
  if (va != 0x1004) return 0x80004005u;
  g_idt_calls[3]++;
  uint64_t *tv = (uint64_t *)(uintptr_t)*(uint64_t *)(uintptr_t)a1;   /* IDataObject の vtable (lifttab トークン) */
  uint8_t fe[32], sm[24];
  memset(fe, 0, sizeof fe); memset(sm, 0, sizeof sm);
  *(uint16_t *)fe = 15; *(uint32_t *)(fe + 16) = 1; *(int32_t *)(fe + 20) = -1; *(uint32_t *)(fe + 24) = 1;   /* CF_HDROP, DVASPECT_CONTENT, lindex -1, TYMED_HGLOBAL */
  shimx_lift_thunk_fn qgd = shimx_lifttab_trampoline((unsigned)tv[5]);
  g_idt_qgd_ok = qgd((uintptr_t)a1, (uintptr_t)fe, 0, 0, 0, 0, 0, 0) == 0;
  uint8_t bad[32]; memcpy(bad, fe, 32); *(uint16_t *)bad = 1;
  g_idt_qgd_bad = qgd((uintptr_t)a1, (uintptr_t)bad, 0, 0, 0, 0, 0, 0) == 0x80040064ull;
  shimx_lift_thunk_fn gd = shimx_lifttab_trampoline((unsigned)tv[3]);
  if (gd((uintptr_t)a1, (uintptr_t)fe, (uintptr_t)sm, 0, 0, 0, 0, 0) == 0 && *(uint32_t *)sm == 1) {
    HGLOBAL h = (HGLOBAL)(uintptr_t)*(uint64_t *)(sm + 8);
    size_t n = GlobalSize(h); if (n > sizeof g_idt_blk) n = sizeof g_idt_blk;
    memcpy(g_idt_blk, GlobalLock(h), n); GlobalUnlock(h);
    g_idt_blk_len = (int)n;
  }
  *(uint32_t *)(uintptr_t)a4 = 1; g_idt_eff = 1;
  return 0;
}
static const unsigned short *wnext(const unsigned short *p) { while (*p) p++; return p + 1; }
static void test_idt(void) {
  shimx_cbtrans_set_invoke(idt_invoke);
  g_idt_vt[3] = 0x1001; g_idt_vt[4] = 0x1002; g_idt_vt[5] = 0x1003; g_idt_vt[6] = 0x1004;
  g_idt_obj.vt = (uint64_t)(uintptr_t)g_idt_vt;
  int64_t w2 = t_make_window(400, 20, 200, 200);
  CHK(w2 != 0, "window2 create");
  CHK(RegisterDragDrop((HWND)(uintptr_t)w2, &g_idt_obj) == S_OK && shimx_get_drop_target((HWND)(uintptr_t)w2) == (LPVOID)&g_idt_obj, "RegisterDragDrop (window2)");
  int got; int64_t wp = 0, hw = 0;
  CHK(drop_and_wait(450, 60, 2, "a.wav\0b.mid\0", &got, &wp, &hw) == 2 && !got, "RegisterDragDrop 窓への drop → IDropTarget が処理 (配送結果 2・WM_DROPFILES なし)");
  CHK(g_idt_calls[0] == 1 && g_idt_calls[1] == 1 && g_idt_calls[2] == 0 && g_idt_calls[3] == 1,
      "DragEnter/DragOver/Drop の順に 1 回ずつ (DragLeave は受理時に呼ばない): got %d/%d/%d/%d", g_idt_calls[0], g_idt_calls[1], g_idt_calls[2], g_idt_calls[3]);
  CHK(g_idt_eff == 1, "pdwEffect が guest に書かれた");
  CHK(g_idt_qgd_ok && g_idt_qgd_bad, "IDataObject::QueryGetData: CF_HDROP/HGLOBAL は S_OK、他 cf は DV_E_FORMATETC");
  CHK(g_idt_blk_len >= 20 && *(uint32_t *)g_idt_blk == 20 && g_idt_blk[16] == 1, "GetData: DROPFILES ブロック (pFiles=20, fWide=1)");
  const unsigned short *p0 = (const unsigned short *)(g_idt_blk + 20), *p1 = wnext(p0);
  CHK(weq(p0, "C:\\Users\\webstudio\\Documents\\WebImport\\a.wav"), "GetData: 1 件目のファイル名 (HDROP 由来)");
  CHK(weq(p1, "C:\\Users\\webstudio\\Documents\\WebImport\\b.mid"), "GetData: 2 件目のファイル名 (HDROP 由来)");
  RevokeDragDrop((HWND)(uintptr_t)w2);
  CHK(drop_and_wait(450, 60, 1, "a.wav\0", &got, &wp, &hw) == 0 && !got, "RevokeDragDrop 後は 0");
  shimx_cbtrans_set_invoke(NULL);
}

int main(void) {
  setvbuf(stdout, NULL, _IONBF, 0);
  gui_headless_attach(800, 600);
  int att = gui_shimx_attach();
  CHK(att == 15, "gui_shimx_attach bits=%d", att);
  test_char(); test_msgwait(); test_shell(); test_dialog(); test_drop(); test_idt();
  printf("RESULT pass=%d fail=%d\n", g_pass, g_fail);
  return g_fail ? 1 : 0;
}
