/* selftest_fd.inc — #172 GetOpenFileNameW 複数選択の境界テスト (selftest.c から #include; CHK を共有)。
 * 対象: gui_core_ext.inc file_dialog() の w[] 容量 / 名前の切り詰め / names[64] の黙殺。
 * host 役スレッドが gui_hostcall_native() の req_seq を見て out に「n 件 × nlen 文字」の名前列を書く。
 * lpstrFile は nMaxFile 要素ちょうどの heap (ASan が境界外 R/W を検出) / w[] はスタック (UBSan が添字境界を検出)。 */
#include <stdlib.h>
#include "gui_hostcall.h"
extern const char *gui_stage_dir_win(void);
#define FD_FLAGS (0x00080000u | 0x200u)   /* OFN_EXPLORER | OFN_ALLOWMULTISELECT */

static volatile int g_fd_stop;
static int g_fd_n, g_fd_nlen, g_fd_wide;   /* host 応答の仕様 */

/* i 番目の名前: "n%03d_" + (nlen-5) 文字。narrow は 'a'+i%26、wide は U+3042 (UTF-8 3 byte / UTF-16 1 unit)。UTF-8 と UTF-16 を同じ規則で作る */
static int fd_name8(char *d, int i, int nlen, int wide) {
  int l = snprintf(d, 8, "n%03d_", i % 1000);
  for (int k = 5; k < nlen; k++) { if (wide) { memcpy(d + l, "\xE3\x81\x82", 3); l += 3; } else d[l++] = (char)('a' + i % 26); }
  d[l] = 0; return l;
}
static int fd_name16(uint16_t *d, int i, int nlen, int wide) {
  char t[8]; snprintf(t, sizeof t, "n%03d_", i % 1000); int l = 0;
  for (; t[l]; l++) d[l] = (uint8_t)t[l];
  for (int k = 5; k < nlen; k++) d[l++] = wide ? 0x3042 : (uint16_t)('a' + i % 26);
  d[l] = 0; return l;
}

static void *fd_host(void *arg) {
  (void)arg;
  GuiHostCall *hc = gui_hostcall_native();
  uint32_t seen = __atomic_load_n(&hc->req_seq, __ATOMIC_ACQUIRE);
  __atomic_store_n(&hc->host_ready, 1, __ATOMIC_RELEASE);
  while (!g_fd_stop) {
    uint32_t rq = __atomic_load_n(&hc->req_seq, __ATOMIC_ACQUIRE);
    if (rq == seen) { gui_futex_wait(&hc->req_seq, rq, 5); continue; }
    seen = rq;
    uint32_t len = 0;
    for (int i = 0; i < g_fd_n; i++) len += (uint32_t)fd_name8(hc->out + len, i, g_fd_nlen, g_fd_wide) + 1;
    hc->out[len] = 0;
    hc->out_len = len; hc->result = 1;
    __atomic_store_n(&hc->resp_seq, rq, __ATOMIC_RELEASE);
    gui_futex_wake(&hc->resp_seq);
  }
  return NULL;
}

/* 期待する lpstrFile の必要文字数 (dir\0 name\0 ... \0) */
static uint32_t fd_need(int n, int nlen, int wide) {
  uint16_t t[600]; uint32_t need = (uint32_t)strlen(gui_stage_dir_win()) + 1;
  for (int i = 0; i < n; i++) need += (uint32_t)fd_name16(t, i, nlen, wide) + 1;
  return need + 1;
}

/* 1 回呼ぶ。maxfile 要素ちょうどの heap を lpstrFile にする。戻り: file (呼出側が free)。*ret / *cderr / *nfo は GetOpenFileNameW の結果 */
static uint16_t *fd_call(int n, int nlen, int wide, uint32_t maxfile, int64_t *ret, uint32_t *cderr, uint16_t *nfo) {
  uint8_t o[152]; memset(o, 0, sizeof o);
  uint16_t *file = malloc((size_t)maxfile * 2); for (uint32_t k = 0; k < maxfile; k++) file[k] = 0x7777;
  *(uint32_t *)o = 152; *(uint64_t *)(o + 48) = (uint64_t)(uintptr_t)file; *(uint32_t *)(o + 56) = maxfile; *(uint32_t *)(o + 96) = FD_FLAGS;
  g_fd_n = n; g_fd_nlen = nlen; g_fd_wide = wide;
  *ret = GetOpenFileNameW((int64_t)(uintptr_t)o); *cderr = (uint32_t)CommDlgExtendedError(); memcpy(nfo, o + 100, 2);
  return file;
}

/* file が dir\0 name0\0 ... name(n-1)\0 \0 の完全一致か */
static int fd_match(const uint16_t *file, int n, int nlen, int wide, uint16_t nfo) {
  uint16_t want[600]; const uint16_t *p = file; const char *dir = gui_stage_dir_win();
  for (size_t k = 0; dir[k]; k++, p++) if (*p != (uint8_t)dir[k]) return 0;
  if (*p++ != 0 || nfo != (uint16_t)(p - file)) return 0;
  for (int i = 0; i < n; i++) {
    int l = fd_name16(want, i, nlen, wide);
    if (memcmp(p, want, (size_t)l * 2) || p[l] != 0) return 0;
    p += l + 1;
  }
  return *p == 0;
}

static void run_fd_bounds(void) {
  SECTION("GetOpenFileNameW 複数選択の境界 (#172 review: w[] / 切り詰め / names[64])");
  pthread_t th; g_fd_stop = 0; pthread_create(&th, NULL, fd_host, NULL);
  while (!__atomic_load_n(&gui_hostcall_native()->host_ready, __ATOMIC_ACQUIRE)) usleep(1000);
  /* 成功すべき組: 旧実装は n=52..56 で切り詰めた断片名を TRUE で返し、n>=58 で w[1024] を超えて書く。 */
  static const struct { int n, nlen, wide; } ok_cases[] = {
    { 3, 18, 0 }, { 50, 18, 0 }, { 52, 18, 0 }, { 56, 18, 0 }, { 58, 18, 0 }, { 60, 18, 0 }, { 63, 18, 0 }, { 64, 18, 0 },
    { 64, 60, 0 }, { 40, 100, 0 }, { 60, 20, 1 }, { 64, 20, 1 },
  };
  for (size_t c = 0; c < sizeof ok_cases / sizeof ok_cases[0]; c++) {
    int n = ok_cases[c].n, nlen = ok_cases[c].nlen, wide = ok_cases[c].wide;
    uint32_t need = fd_need(n, nlen, wide); int64_t ret; uint32_t cd; uint16_t nfo;
    uint16_t *file = fd_call(n, nlen, wide, need, &ret, &cd, &nfo);   /* nMaxFile = 必要数ちょうど */
    CHK(ret == 1 && fd_match(file, n, nlen, wide, nfo), "multi n=%d nlen=%d wide=%d maxfile=need=%u → TRUE, 全 %d 名が完全一致 (ret=%lld cderr=%u)", n, nlen, wide, need, n, (long long)ret, cd);
    free(file);
    file = fd_call(n, nlen, wide, need - 1, &ret, &cd, &nfo);          /* 1 要素足りない → FNERR_BUFFERTOOSMALL + 先頭 WORD に必要数 */
    CHK(ret == 0 && cd == 0x3003 && file[0] == need, "multi n=%d nlen=%d wide=%d maxfile=need-1 → FALSE 0x3003 need=%u (ret=%lld cderr=%x first=%u)", n, nlen, wide, need, (long long)ret, cd, file[0]);
    free(file);
  }
  /* 65 件以上は names[64] に載らない → 黙って捨てず失敗として返す (lpstrFile は不変) */
  static const struct { int n, nlen; } over_cases[] = { { 65, 18 }, { 70, 18 }, { 65, 5 }, { 200, 5 } };
  for (size_t c = 0; c < sizeof over_cases / sizeof over_cases[0]; c++) {
    int64_t ret; uint32_t cd; uint16_t nfo; uint32_t mf = 65536;
    uint16_t *file = fd_call(over_cases[c].n, over_cases[c].nlen, 0, mf, &ret, &cd, &nfo);
    CHK(ret == 0 && cd == 2 && file[0] == 0x7777 && file[mf - 1] == 0x7777, "multi n=%d nlen=%d (> 64 件) → FALSE CDERR_INITIALIZATION, lpstrFile 不変 (ret=%lld cderr=%u first=%x)", over_cases[c].n, over_cases[c].nlen, (long long)ret, cd, file[0]);
    free(file);
  }
  g_fd_stop = 1; pthread_join(th, NULL);
  __atomic_store_n(&gui_hostcall_native()->host_ready, 0, __ATOMIC_RELEASE);
}
