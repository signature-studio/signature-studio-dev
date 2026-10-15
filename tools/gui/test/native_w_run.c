/* native_w_run.c — W 版ゲスト (gui_app_w.c の lift 産物) を native (gcc) で shim + headless host 上で動かし、
 * 最終フレームの統計 (w×h・非背景画素数・厳密な色数・sha256; gui_hl_stats) を取る (#3460 受入 3 の前段)。
 * 最終 surface は ppm に書く (オラクル比較は別 step)。PNG・PPM は repo に置かない (work/ 配下に出す)。 */
#define _GNU_SOURCE
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "gui_internal.h"
#include "gui_headless.h"

extern int gui_lift_app_main(void);
static void *app_thread(void *a) { (void)a; gui_lift_app_main(); return NULL; }

#define GW 320
#define GH 200
static int fails;
#define NEED(c, ...) do { if (!(c)) { fails++; fprintf(stderr, "[native_w_run] FAIL: " __VA_ARGS__); fprintf(stderr, "\n"); } } while (0)
#define WAIT(line) NEED(gui_hl_wait_line(line, 10000), "timeout waiting for '%s'", line)

int main(int argc, char **argv) {
  const char *actual = argc > 1 ? argv[1] : "w_actual.ppm";
  gui_hl_start(GW, GH, 1);
  pthread_t th; pthread_create(&th, NULL, app_thread, NULL);
  WAIT("w: subclass ok");
  WAIT("w: nccreate ok");
  WAIT("w: cs ok");
  WAIT("w: created");
  WAIT("w: paint");
  WAIT("w: roundtrip ok");

  uint32_t *d = gui_hl_desktop();
  GuiHlStats st;
  gui_hl_stats(d, GW, GH, d[0] & 0xFFFFFFu, &st);   /* 背景 = 左上画素 */
  char hex[65]; for (int i = 0; i < 32; i++) sprintf(hex + 2 * i, "%02x", st.sha256[i]);
  printf("[native_w_run] surface w=%u h=%u bg=%06x nonbg=%llu colors=%u sha256=%s nontrivial=%d\n",
         st.w, st.h, st.bg, (unsigned long long)st.nonbg, st.colors, hex, gui_hl_nontrivial(&st));
  NEED(gui_hl_nontrivial(&st), "final surface is trivial (nonbg=%llu colors=%u)", (unsigned long long)st.nonbg, st.colors);
  gui_hl_dump_ppm(actual);

  gui_hl_input(GUI_IN_KEY_DOWN, 0, 0, 0, 0x1B, 0);
  WAIT("w: destroy");
  if (fails) { printf("[native_w_run] FAILED (%d)\n", fails); fflush(stdout); _exit(1); }
  printf("[native_w_run] PASS (W 版ゲスト: 窓・メッセージループ・WM_PAINT・GDI・W 文字列往復; 終了は ExitProcess)\n");
  fflush(stdout);
  pthread_join(th, NULL);
  return 0;
}
