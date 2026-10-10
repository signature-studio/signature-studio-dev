/* native_run.c — lift した gui_app を native (gcc) で shim + headless host 上で動かす E2E ドライバ。
 * Chrome E2E (e2e/e2e.mjs) と同一シナリオ・同一 golden。lifter 産コード + shim の論理検証を高速に回す開発ループ用。 */
#define _GNU_SOURCE
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include "gui_internal.h"
#include "gui_headless.h"

extern int gui_lift_app_main(void);
static void *app_thread(void *a) { (void)a; gui_lift_app_main(); return NULL; }

static int fails;
#define NEED(c, ...) do { if (!(c)) { fails++; fprintf(stderr, "[native_run] FAIL: " __VA_ARGS__); fprintf(stderr, "\n"); } } while (0)

static int sync_paint(int ev) {
  char b[32]; snprintf(b, sizeof b, "paint ev=%d", ev);
  int ok = gui_hl_wait_line(b, 10000);
  NEED(ok, "timeout waiting for '%s'", b);
  return ok;
}
static void click(int x, int y, int ev_down) {
  gui_hl_input(GUI_IN_MOUSE_DOWN, 0, x, y, 0, 0); sync_paint(ev_down);
  gui_hl_input(GUI_IN_MOUSE_UP, 0, x, y, 0, 0); sync_paint(ev_down + 1);
}
int main(int argc, char **argv) {
  const char *golden = argc > 1 ? argv[1] : "golden/final.ppm";
  const char *actual = argc > 2 ? argv[2] : "actual.ppm";
  gui_hl_start(320, 200, 1);
  pthread_t th; pthread_create(&th, NULL, app_thread, NULL);
  NEED(gui_hl_wait_line("app: created", 10000), "app: created");
  NEED(gui_hl_wait_line("app: timer-done", 10000), "timer-done (SetTimer/WM_TIMER x3 + KillTimer)");
  click(200, 150, 1);                      /* ev 1,2 */
  click(210, 150, 3);                      /* ev 3,4 */
  gui_hl_input(GUI_IN_MOUSE_DOWN, 0, 30, 150, 0, 0); sync_paint(5);   /* drag 開始 (SetCapture) */
  gui_hl_input(GUI_IN_MOUSE_MOVE, 0, 100, 170, 0, 0); sync_paint(6);
  gui_hl_input(GUI_IN_MOUSE_MOVE, 0, 150, 180, 0, 0); sync_paint(7);
  gui_hl_input(GUI_IN_MOUSE_UP, 0, 150, 180, 0, 0); sync_paint(8);
  gui_hl_input(GUI_IN_KEY_DOWN, 0, 0, 0, 0x41, 0); gui_hl_input(GUI_IN_CHAR, 0, 0, 0, 'A', 0); gui_hl_input(GUI_IN_KEY_UP, 0, 0, 0, 0x41, 0); sync_paint(9);
  gui_hl_input(GUI_IN_KEY_DOWN, 0, 0, 0, 0x42, 0); gui_hl_input(GUI_IN_CHAR, 0, 0, 0, 'b', 0); gui_hl_input(GUI_IN_KEY_UP, 0, 0, 0, 0x42, 0); sync_paint(10);

  /* golden 比較 */
  FILE *f = fopen(golden, "rb");
  NEED(f != NULL, "cannot open golden %s", golden);
  long diff = 0; int fx = -1, fy = -1; uint32_t got = 0, want = 0;
  if (f) {
    int w, h, mx; if (fscanf(f, "P6 %d %d %d", &w, &h, &mx) != 3 || w != 320 || h != 200) { NEED(0, "bad golden header"); }
    fgetc(f);
    uint32_t *d = gui_hl_desktop();
    for (int y = 0; y < 200; y++) for (int x = 0; x < 320; x++) {
      unsigned char c[3]; if (fread(c, 1, 3, f) != 3) { NEED(0, "short golden"); y = 200; break; }
      uint32_t wantc = (uint32_t)c[0] << 16 | c[1] << 8 | c[2], gotc = d[y * 320 + x] & 0xFFFFFF;
      if (wantc != gotc) { if (!diff) { fx = x; fy = y; got = gotc; want = wantc; } diff++; }
    }
    fclose(f);
  }
  gui_hl_dump_ppm(actual);
  NEED(diff == 0, "golden mismatch: %ld pixels differ (first at %d,%d got %06x want %06x) — actual: %s", diff, fx, fy, got, want, actual);
  printf("[native_run] golden compare: %s (%ld differing pixels of 64000)\n", diff == 0 ? "EXACT MATCH" : "MISMATCH", diff);
  if (fails) { printf("[native_run] FAILED (%d)\n", fails); fflush(stdout); _exit(1); }
  /* 終了シーケンス: ESC -> DestroyWindow -> WM_DESTROY -> PostQuitMessage -> ExitProcess(0) */
  gui_hl_input(GUI_IN_KEY_DOWN, 0, 0, 0, 0x1B, 0);
  NEED(gui_hl_wait_line("app: destroy", 10000), "app: destroy");
  printf("[native_run] PASS (scenario complete, window destroyed, app exiting via ExitProcess)\n"); fflush(stdout);
  pthread_join(th, NULL);   /* app thread は ExitProcess -> exit() で process ごと終了 */
  return 0;
}
