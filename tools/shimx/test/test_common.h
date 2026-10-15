/* shimx テスト共通ヘルパ */
#ifndef TEST_COMMON_H
#define TEST_COMMON_H
#include "../src/shimx.h"
#include <sys/stat.h>
#include <errno.h>
#include <unistd.h>
#include <fcntl.h>

#define CHECK(cond) \
    do { if (!(cond)) { \
        fprintf(stderr, "[shimx-test] FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
        fflush(stderr); \
        exit(1); \
    } } while (0)

/* ASCII/UTF-8 文字列 → UTF-16 (8 本のリングバッファ。スレッド非安全: メインスレッド専用) */
static inline const WCHAR* W(const char* s) {
    static WCHAR ring[16][1024];
    static int idx;
    WCHAR* w = ring[idx++ & 15];
    int n = shimx_utf8_to_utf16(s, -1, w, 1023);
    w[n < 0 ? 0 : n] = 0;
    return w;
}
/* UTF-16 → UTF-8 (比較用, リングバッファ) */
static inline const char* U8(const WCHAR* w) {
    static char ring[16][2048];
    static int idx;
    char* s = ring[idx++ & 15];
    if (shimx_utf16_to_utf8(w, -1, s, 2048) < 0) s[0] = 0;
    return s;
}
static inline int wstr_eq(const WCHAR* w, const char* s) { return strcmp(U8(w), s) == 0; }
static inline double now_ms(void) { return emscripten_get_now(); }

void run_core_tests(int multithread);
void run_fh3_tests(void);
void run_sys_tests(void);
void run_ole_shell_tests(void);
void run_link_tests(int multithread);
void run_cbtrans_tests(int multithread);
void run_midi_tests(int multithread);
void run_seh_tests(void);
void run_absent_path_tests(void);
void seh_failfast_nomatch(void);
void seh_failfast_badtarget(void);
#endif
