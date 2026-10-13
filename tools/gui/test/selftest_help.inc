/* selftest_help.inc — #554 ShellExecuteW(Help パス) → GUI_HC_OPEN_HELP の結線テスト (selftest.c から #include; CHK を共有)。
 * shimx_set_shell_execute_hook をテスト側の強定義で奪い、gui_shimx_attach() が登録した hook (= gui_shell_execute) を直接呼ぶ。
 * host 役スレッドは gui_hostcall_native() を見て op/in を記録し、g_help_reply を result として返す。 */
#include "gui_hostcall.h"
extern int gui_shimx_attach(void);

static int (*g_help_hook)(const char *, const char *, const char *);
void shimx_set_shell_execute_hook(int (*fn)(const char *, const char *, const char *)) { g_help_hook = fn; }

static volatile int g_help_stop, g_help_reply, g_help_calls;
static char g_help_last[GUI_HC_IN];
static uint32_t g_help_last_op;

static void *help_host(void *arg) {
  (void)arg;
  GuiHostCall *hc = gui_hostcall_native();
  uint32_t seen = __atomic_load_n(&hc->req_seq, __ATOMIC_ACQUIRE);
  __atomic_store_n(&hc->host_ready, 1, __ATOMIC_RELEASE);
  while (!g_help_stop) {
    uint32_t rq = __atomic_load_n(&hc->req_seq, __ATOMIC_ACQUIRE);
    if (rq == seen) { gui_futex_wait(&hc->req_seq, rq, 5); continue; }
    seen = rq;
    g_help_last_op = hc->op;
    memcpy(g_help_last, hc->in, hc->in_len); g_help_last[hc->in_len] = 0;
    g_help_calls++;
    hc->out_len = 0; hc->result = g_help_reply;
    __atomic_store_n(&hc->resp_seq, rq, __ATOMIC_RELEASE);
    gui_futex_wake(&hc->resp_seq);
  }
  return NULL;
}

static void run_help_wiring(void) {
  SECTION("ShellExecuteW(Help) → GUI_HC_OPEN_HELP (#554)");
  int bits = gui_shimx_attach();
  CHK((bits & 2) && g_help_hook, "gui_shimx_attach が shell hook を登録 (bits=%d)", bits);
  if (!g_help_hook) return;
  pthread_t th; g_help_stop = 0; g_help_reply = 1; g_help_calls = 0; pthread_create(&th, NULL, help_host, NULL);
  while (!__atomic_load_n(&gui_hostcall_native()->host_ready, __ATOMIC_ACQUIRE)) usleep(1000);
  const char *R = "C:\\Program Files\\Image-Line\\FL Studio 2026\\";
  char p[512];
  static const char *accept[] = { "Help\\index_offline.html", "Help\\WhatsNew.htm", "Help\\html\\FD\\web\\documents\\productinfo.html", "System\\Internet\\error-offline.html" };
  for (size_t i = 0; i < sizeof accept / sizeof accept[0]; i++) {
    snprintf(p, sizeof p, "%s%s", R, accept[i]);
    int c0 = g_help_calls;
    int r = g_help_hook(NULL, p, NULL);   /* OpenHelpTarget は動詞 NULL。shimx は NULL を "open" に正規化して hook を呼ぶので "open" も試す */
    CHK(r == 1 && g_help_calls == c0 + 1 && g_help_last_op == GUI_HC_OPEN_HELP && !strcmp(g_help_last, p), "Help パス受理: %s (r=%d op=%u in=%s)", accept[i], r, g_help_last_op, g_help_last);
  }
  { int c0 = g_help_calls; snprintf(p, sizeof p, "%s%s", R, "Help\\index_offline.html");
    int r = g_help_hook("open", p, NULL);
    CHK(r == 1 && g_help_calls == c0 + 1, "verb=open でも Help を受理 (r=%d)", r);
    snprintf(p, sizeof p, "c:\\program files\\image-line\\fl studio 2026\\HELP\\index_offline.html");
    r = g_help_hook("open", p, NULL);
    CHK(r == 1 && g_help_calls == c0 + 2, "大文字小文字を区別しない (r=%d)", r); }
  /* host が拒否 (result 0) → hook は 0 (= SE_ERR_FNF) */
  { g_help_reply = 0; int c0 = g_help_calls; snprintf(p, sizeof p, "%s%s", R, "Help\\x.html");
    int r = g_help_hook(NULL, p, NULL);
    CHK(r == 0 && g_help_calls == c0 + 1, "host が拒否 (result=0) → hook 0 (r=%d)", r); g_help_reply = 1; }
  /* host に渡してはならないもの (呼出数が増えない) */
  static const char *reject[] = {
    "C:\\Windows\\notepad.exe", "C:\\Program Files\\Image-Line\\FL Studio 2026\\Help", "C:\\Program Files\\Image-Line\\FL Studio 2026\\Helpx\\a.html",
    "C:\\Program Files\\Image-Line\\FL Studio 2026\\System\\Internet\\other.html", "C:\\Program Files\\Image-Line\\FL Studio 2026\\FL64.exe",
    "D:\\Program Files\\Image-Line\\FL Studio 2026\\Help\\index_offline.html", "C:\\Program Files\\Image-Line\\FL Studio 2025\\Help\\index_offline.html", "",
  };
  for (size_t i = 0; i < sizeof reject / sizeof reject[0]; i++) {
    int c0 = g_help_calls; int r = g_help_hook(NULL, reject[i], NULL);
    CHK(r == 0 && g_help_calls == c0, "Help 以外は host に渡さない/失敗: '%s' (r=%d calls+%d)", reject[i], r, g_help_calls - c0);
  }
  { int c0 = g_help_calls; snprintf(p, sizeof p, "%s%s", R, "Help\\index_offline.html");
    int r = g_help_hook("print", p, NULL);
    CHK(r == 0 && g_help_calls == c0, "verb=print は拒否 (r=%d)", r);
    r = g_help_hook("runas", p, NULL);
    CHK(r == 0 && g_help_calls == c0, "verb=runas は拒否 (r=%d)", r); }
  /* 回帰: https は従来どおり GUI_HC_OPEN_URL */
  { int c0 = g_help_calls; int r = g_help_hook(NULL, "https://example.com/x", NULL);
    CHK(r == 1 && g_help_calls == c0 + 1 && g_help_last_op == GUI_HC_OPEN_URL && !strcmp(g_help_last, "https://example.com/x"), "https は OPEN_URL のまま (r=%d op=%u)", r, g_help_last_op); }
  g_help_stop = 1; pthread_join(th, NULL);
  __atomic_store_n(&gui_hostcall_native()->host_ready, 0, __ATOMIC_RELEASE);
  /* host 未接続 → 待たずに失敗 */
  snprintf(p, sizeof p, "%s%s", R, "Help\\index_offline.html");
  CHK(g_help_hook(NULL, p, NULL) == 0, "host 未接続は失敗 (待たない)");
}
