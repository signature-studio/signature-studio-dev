/* reach_test.c — 到達 API ログ (lift ABI wrapper 経路; gen_api.py 産 gui_wrap_i64.c) の native 検証 */
#define _GNU_SOURCE
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>
#include "gui_api.h"
#include "gui_internal.h"
#include "gui_headless.h"

int gui_reach_distinct(void);
int gui_reach_calls(const char *);
int gui_reach_json(char *, int);
static int g_pass, g_fail;
#define CHK(c, ...) do { if (c) g_pass++; else { g_fail++; printf("  FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

int main(void) {
  gui_hl_start(640, 480, 1);
  CHK(gui_reach_distinct() == 0, "no hits before any call");
  GetDoubleClickTime(); GetDoubleClickTime(); GetDoubleClickTime();
  GetSysColor(5);
  int64_t dc = CreateCompatibleDC(0), bmp = CreateCompatibleBitmap(dc, 64, 64);
  SelectObject(dc, bmp);
  WRECT sr = { 0, 0, 32, 32 };
  CHK(ScrollDC(dc, 4, 0, (int64_t)(uintptr_t)&sr, 0, 0, 0) == 1, "ScrollDC works through wrapper");
  CHK(gui_reach_calls("GetDoubleClickTime") == 3 && gui_reach_calls("GetSysColor") == 1, "per-API call counts (%d %d)", gui_reach_calls("GetDoubleClickTime"), gui_reach_calls("GetSysColor"));
  CHK(gui_reach_calls("ScrollDC") == 1 && gui_reach_calls("BitBlt") == 0, "shim-internal call (ScrollDC -> BitBlt) is not counted as reach (BitBlt=%d)", gui_reach_calls("BitBlt"));
  CHK(gui_reach_calls("CreateCompatibleBitmap") == 1 && gui_reach_calls("Ellipse") == 0, "unreached API = 0");
  CHK(gui_reach_distinct() == 6, "distinct = 6 (%d)", gui_reach_distinct());
  char js[512]; int n = gui_reach_json(js, sizeof js);
  CHK(n > 0 && js[0] == '{' && strstr(js, "\"GetDoubleClickTime\":3") && strstr(js, "\"ScrollDC\":1") && strstr(js, "\"GetSysColor\":1") && strncmp(js + 1, "\"GetDoubleClickTime\"", 20) == 0,
      "json lists in first-reach order: %s", js);
  char tiny[24]; n = gui_reach_json(tiny, sizeof tiny);
  CHK(n > 0 && tiny[n - 1] == '}' && tiny[n] == 0, "json truncation keeps well-formed object: %s", tiny);

  /* stub に到達 -> failfast で GUI-REACH を吐いてから SIGABRT */
  int pfd[2]; pipe(pfd);
  pid_t pid = fork();
  if (pid == 0) { dup2(pfd[1], 2); close(pfd[0]); GetSysColor(1); Ellipse(0, 0, 0, 0, 0); _exit(0); }
  close(pfd[1]);
  char buf[4096] = { 0 }; ssize_t nr = 0, t; while ((t = read(pfd[0], buf + nr, sizeof buf - 1 - nr)) > 0) nr += t;
  int st = 0; waitpid(pid, &st, 0);
  CHK(WIFSIGNALED(st) && WTERMSIG(st) == SIGABRT, "stub aborts");
  CHK(strstr(buf, "GUI-REACH 1 GetDoubleClickTime 3 IMPL P2") && strstr(buf, "GUI-REACH 2 GetSysColor 2 IMPL P") && strstr(buf, "GUI-REACH 7 Ellipse 1 STUB P3") && strstr(buf, "GUI-REACH-SUMMARY reached=7 impl=6 stub=1"),
      "failfast dumps reach log incl. the STUB hit:\n%s", buf);
  CHK(strstr(buf, "FAIL-FAST: unimplemented Win32 API: Ellipse") != NULL, "fail-fast message kept");
  gui_hl_stop();
  printf("[reach_test] %d passed, %d failed\n", g_pass, g_fail);
  return g_fail ? 1 : 0;
}
