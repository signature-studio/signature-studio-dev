/* pathreg テスト共通ヘルパ */
#ifndef PATHREG_TEST_COMMON_H
#define PATHREG_TEST_COMMON_H
#include "../include/pathreg.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>

#define CHECK(cond) \
    do { if (!(cond)) { \
        fprintf(stderr, "[pathreg-test] FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
        fflush(stderr); exit(1); \
    } } while (0)

/* ASCII/UTF-8 → UTF-16 (リングバッファ, メインスレッド専用) */
static inline const WCHAR* W(const char* s) {
    static WCHAR ring[16][1024];
    static int idx;
    WCHAR* w = ring[idx++ & 15];
    int n = shimx_utf8_to_utf16(s, -1, w, 1023);
    w[n < 0 ? 0 : n] = 0;
    return w;
}
static inline const char* U8(const WCHAR* w) {
    static char ring[16][2048];
    static int idx;
    char* s = ring[idx++ & 15];
    if (shimx_utf16_to_utf8(w, -1, s, 2048) < 0) s[0] = 0;
    return s;
}

/* mkdir -p */
static inline void mkdir_p(const char* posixPath) {
    char buf[1024];
    snprintf(buf, sizeof buf, "%s", posixPath);
    for (char* p = buf + 1; *p; p++) {
        if (*p == '/') { *p = 0; mkdir(buf, 0777); *p = '/'; }
    }
    mkdir(buf, 0777);
}

#endif /* PATHREG_TEST_COMMON_H */
