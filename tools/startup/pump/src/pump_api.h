/* pump_api.h — pump shim が強定義する user32 API のプロトタイプ (winstubs weak と同一シグネチャ)。
 * winstubs.h は宣言を持たない (定義のみ) ため、テスト/ドライバ側はこれを include する。 */
#ifndef PUMP_API_H
#define PUMP_API_H

#include "../../winstubs/src/winstubs.h"

#ifdef __cplusplus
extern "C" {
#endif

BOOL     PeekMessageW(LPVOID msg, HWND h, UINT lo, UINT hi, UINT rm);
LONG     GetMessageW(LPVOID msg, HWND h, UINT lo, UINT hi);
BOOL     TranslateMessage(const void* msg);
LONG     DispatchMessageW(const void* msg);
BOOL     PostMessageW(HWND h, UINT m, UINT_PTR_T wp, LPARAM_T lp);
LRESULT_T SendMessageW(HWND h, UINT m, UINT_PTR_T wp, LPARAM_T lp);
void     PostQuitMessage(int code);
UINT_PTR_T SetTimer(HWND h, UINT_PTR_T id, UINT ms, LPVOID fn);
BOOL     KillTimer(HWND h, UINT_PTR_T id);
BOOL     WaitMessage(void);

BOOL     PeekMessageA(LPVOID msg, HWND h, UINT lo, UINT hi, UINT rm);
LONG     GetMessageA(LPVOID msg, HWND h, UINT lo, UINT hi);
BOOL     PostMessageA(HWND h, UINT m, UINT_PTR_T wp, LPARAM_T lp);
LONG     DispatchMessageA(const void* msg);
BOOL     PostThreadMessageW(DWORD tid, UINT m, UINT_PTR_T wp, LPARAM_T lp);
DWORD    MsgWaitForMultipleObjects(DWORD n, const HANDLE* hs, BOOL all, DWORD ms, DWORD mask);
DWORD    MsgWaitForMultipleObjectsEx(DWORD n, const HANDLE* hs, DWORD ms, DWORD mask, DWORD flags);
BOOL     InvalidateRect(HWND h, const void* rect, BOOL erase);

/* ホスト結線 export (pump_host.c / pump_ctrl.c / pump_stats.c) */
int      pump_ring_addr(void);
int      pump_ring_capacity(void);
int      pump_ctrl_req_addr(void);
int      pump_ctrl_resp_addr(void);
void     pump_set_wait_mode(int mode);
int      pump_get_wait_mode(void);
void     pump_set_slice_ms_e(int ms);
void     pump_set_wait_cap_ms_e(int ms);
void     pump_set_ctrl_timeout_ms_e(double ms);
int      pump_step(void* msg);
double   pump_wait_ms(void);
int      pump_stats_addr(void);
void     pump_stats_reset_e(void);
int      pump_pop_log_addr(void);
int      pump_pop_log_count(void);
void     pump_calibrate_e(void);
double   pump_clock_offset_e(void);
int      pump_clock_calibrated_e(void);
void     pump_set_wndproc_e(void* hwnd, void* proc);
int      pump_scratch_addr(void);
void     pump_t_post_quit(int code);
int      pump_t_pending(void);
int      pump_t_quit_posted(void);
double   pump_ctrl_rtt(int i);
uint32_t pump_ctrl_rtt_count(void);

/* e2e ドライバ (test/pump_e2e.c) */
void     e2e_setup(void);
int      e2e_setup_timer(HWND hwnd, UINT_PTR_T id, UINT ms, int use_proc);
uint32_t e2e_tproc_sum(void);
int      e2e_consumer_run(double max_ms);
uint32_t e2e_poll_once(void);
int      e2e_ctrl_probe(int n);
int      e2e_ctrl_async_req(void);
double   e2e_ctrl_take_done(void);

#ifdef __cplusplus
}
#endif
#endif
