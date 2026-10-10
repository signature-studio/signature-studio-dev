/* pump_stats.c — 統計実体と pop ログ。
 * pop ログ: 遅延計測用 (t_post = producer 投稿時刻 (エポック基準に較正) / TIMER は期待時刻 due)。
 * 8192 件 = 128KB 静的。2000 件ストレス + WM_TIMER + e2e 反復に十分。 */
#include "pump_internal.h"

PumpStats g_pstat;

#define PLOG_N 8192
static PumpPopLog g_log[PLOG_N];
static uint32_t g_log_n;

void plog_record(uint32_t msg, double t_pop, double t_post, uint32_t aux) {
    if (g_log_n >= PLOG_N) return;   /* 満杯は捨てる (統計用) */
    /* C clock → host epoch 基準へ較正 (未較正 = オフセット 0) */
    g_log[g_log_n].t_pop = t_pop + pump_clock_offset();
    g_log[g_log_n].t_post = t_post;
    g_log[g_log_n].message = msg;
    g_log[g_log_n].aux = aux;   /* ring 由来メッセージは producer 通し番号 (pt.x) */
    g_log_n++;
}

__attribute__((export_name("pump_pop_log_addr"))) int pump_pop_log_addr(void) {
    return (int)(uintptr_t)g_log;
}
__attribute__((export_name("pump_pop_log_count"))) int pump_pop_log_count(void) {
    return (int)g_log_n;
}
