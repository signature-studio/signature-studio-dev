/* nc_pe_run.c — test/gui_nc_app.c を lift した native 版 (shim + headless host) を動かし、デスクトップを PPM に出す。
 * app (lifted WinMain) は main スレッドで走らせる (別スレッドだと起動直後に終了するため)。watcher スレッドが
 * "nc: paint" を待って描画完了を確認し PPM を書いて _exit する。期待画像の比較は golden/gen_golden_ncpe.py (独立オラクル) が行う。
 * usage: nc_pe_run <out.ppm> */
#define _GNU_SOURCE
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include "gui_internal.h"
#include "gui_headless.h"

extern int gui_lift_app_main(void);
extern GuiShared *gui_shared_native(void);
static const char *g_out;

static int has_line(const char *prefix) {
  for (int j = 0; gui_hl_line(j); j++) if (!strncmp(gui_hl_line(j), prefix, strlen(prefix))) return 1;
  return 0;
}

static void *watcher(void *a) {
  (void)a;
  for (int i = 0; i < 4000 && !has_line("nc: paint"); i++) { gui_hl_drain(); usleep(5000); }
  if (!has_line("nc: paint")) { fprintf(stderr, "[nc_pe_run] FAIL: no 'nc: paint' line\n"); _exit(1); }
  GuiShared *S = gui_shared_native();
  for (int i = 0; i < 400; i++) {
    uint32_t head = __atomic_load_n(&S->out_ring.head, __ATOMIC_SEQ_CST), tail = __atomic_load_n(&S->out_ring.tail, __ATOMIC_SEQ_CST);
    if (head == tail) break;
    usleep(5000);
  }
  if (!gui_hl_dump_ppm(g_out)) { fprintf(stderr, "[nc_pe_run] FAIL: cannot write %s\n", g_out); _exit(1); }
  printf("[nc_pe_run] dumped %s\n", g_out);
  fflush(stdout);
  _exit(0);
  return NULL;
}

int main(int argc, char **argv) {
  if (argc < 2) return 2;
  g_out = argv[1];
  gui_hl_start(200, 140, 0);
  pthread_t th; pthread_create(&th, NULL, watcher, NULL);
  gui_lift_app_main();
  return 0;
}
