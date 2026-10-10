/* shimx 呼出トレース実行時 (CAB-166): lifted コードからの shimx/GUI-stub 呼出を計数する。
 * ラッパ (__sxt_<name>) は gen_link.py が生成し sxt_enter(idx) を呼ぶ。
 * 現在 unit = System.InitContext の InitCount (VA 0x15eac98 = LVA 0x11eac98; InitUnits ループが i+1 を書く)。
 * 0 = InitUnits 開始前 (_StartLib/_InitLib 段階)。 */
#include <stdint.h>
#include <stdio.h>
#include <emscripten.h>

extern const int sxt_n_names;
extern const char* const sxt_names[];
extern const unsigned char sxt_is_gui[];

#define MAXN 1024
#define LOGCAP (1u << 21)
static uint32_t g_cnt[MAXN], g_first_unit[MAXN], g_last_unit[MAXN];
static uint64_t g_first_seq[MAXN], g_seq;
static uint32_t g_log[LOGCAP];   /* idx<<16 | unit */
static uint32_t g_log_n, g_dropped;
static int g_print;

void sxt_enter(int idx) {
    uint32_t unit = *(volatile uint32_t*)(uintptr_t)0x11eac98u;
    if (g_cnt[idx]++ == 0) { g_first_unit[idx] = unit; g_first_seq[idx] = g_seq; }
    g_last_unit[idx] = unit;
    if (g_log_n < LOGCAP) g_log[g_log_n++] = ((uint32_t)idx << 16) | (unit & 0xffffu); else g_dropped++;
    g_seq++;
    if (g_print) fprintf(stderr, "[sxt] #%llu unit=%u %s%s\n", (unsigned long long)g_seq, unit, sxt_names[idx], sxt_is_gui[idx] ? " (GUI/audio stub)" : "");
}

EMSCRIPTEN_KEEPALIVE void sxt_set_print(int v) { g_print = v; }
EMSCRIPTEN_KEEPALIVE int sxt_n(void) { return sxt_n_names; }
EMSCRIPTEN_KEEPALIVE const char* sxt_name(int i) { return sxt_names[i]; }
EMSCRIPTEN_KEEPALIVE int sxt_gui(int i) { return sxt_is_gui[i]; }
EMSCRIPTEN_KEEPALIVE uint32_t sxt_count(int i) { return g_cnt[i]; }
EMSCRIPTEN_KEEPALIVE uint32_t sxt_first_unit(int i) { return g_first_unit[i]; }
EMSCRIPTEN_KEEPALIVE uint32_t sxt_last_unit(int i) { return g_last_unit[i]; }
EMSCRIPTEN_KEEPALIVE double sxt_first_seq(int i) { return (double)g_first_seq[i]; }
EMSCRIPTEN_KEEPALIVE uint32_t sxt_log_n(void) { return g_log_n; }
EMSCRIPTEN_KEEPALIVE uint32_t sxt_log_at(uint32_t k) { return k < g_log_n ? g_log[k] : 0xffffffffu; }
EMSCRIPTEN_KEEPALIVE uint32_t sxt_dropped(void) { return g_dropped; }
