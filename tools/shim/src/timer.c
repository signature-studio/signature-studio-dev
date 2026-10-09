/* timer / time 相当 (§3 #3 の P0 最小面)。
 * クロック源は emscripten_get_now() (_performance.now 相当, 単調・ミリ秒)。
 * - QueryPerformanceFrequency は 1e6 (QPC = マイクロ秒粒度) に固定。
 *   オーディオクロックのマスターは worklet 側 sample position 前提のため
 *   (survey §4.3 / strategy §5.4)、ここでの bit 厳密一致は要求しない。
 * - Sleep は futex_wait ベース (SAB 上の待機)。シングルスレッド (SAB 無し)
 *   ビルドでは待機せず即 return する (制限: inventory.md 参照)。
 */
#include "shim.h"
#include <time.h>

#define SHIM_QPF 1000000LL /* QPC の秒あたり tick 数 = 1MHz */

double shim_now_ms(void) {
    return emscripten_get_now();
}

uint64_t GetTickCount64(void) {
    /* 起動 (モジュール時刻 0) 起点の ms。double→uint64 丸め */
    double now = shim_now_ms();
    return (uint64_t)(now > 0.0 ? now : 0.0);
}

DWORD GetTickCount(void) {
    return (DWORD)GetTickCount64();
}

DWORD timeGetTime(void) {
    /* winmm の timeGetTime と GetTickCount は同一時計として扱う */
    return (DWORD)GetTickCount64();
}

BOOL QueryPerformanceCounter(LARGE_INTEGER* out) {
    if (!out) return FALSE;
    out->QuadPart = (int64_t)(shim_now_ms() * 1000.0); /* us 粒度 */
    return TRUE;
}

BOOL QueryPerformanceFrequency(LARGE_INTEGER* out) {
    if (!out) return FALSE;
    out->QuadPart = SHIM_QPF;
    return TRUE;
}

void Sleep(DWORD ms) {
    if (ms == 0) return;
#if defined(__EMSCRIPTEN__)
    {
        /* プロセス固有トークン (他スレッドから wake されない番地) */
        static volatile uint32_t sleep_token;
        uint32_t snap = sleep_token;
        double deadline = shim_now_ms() + (double)ms;
        for (;;) {
            double remain = deadline - shim_now_ms();
            if (remain <= 0.0) break;
            /* 返り値: 0 = wake, 負値 = timeout/notsup。wake 要因が無いため
             * 基本は timeout まで待つ。 */
            emscripten_futex_wait((volatile void*)&sleep_token, snap, remain);
            snap = sleep_token;
        }
    }
#else
    /* ホスト通常ビルド (デバッグ用) */
    {
        struct timespec ts;
        ts.tv_sec  = (time_t)(ms / 1000u);
        ts.tv_nsec = (long)(ms % 1000u) * 1000000L;
        nanosleep(&ts, NULL);
    }
#endif
}
