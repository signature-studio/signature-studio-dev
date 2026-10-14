/* side_host.c: SIDE_MODULE (side_build.sh の side.wasm) を dlopen して lifted 関数を呼ぶ薄い MAIN_MODULE host (PERF-P8 real / #1201) */
#include <dlfcn.h>
#include <math.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <emscripten.h>

typedef uint64_t (*run_t)(uint32_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);
typedef void (*set_gbase_t)(uint64_t);
typedef void (*data_install_t)(void);

static run_t p_run;
static set_gbase_t p_set_gbase;
static data_install_t p_data_install;

/* side module が import する libc / builtin を main に残す (dlopen の RTLD_NOW 解決用)。fiprintf は emscripten libc に無いので vfprintf で定義 */
int fiprintf(FILE *f, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int r = vfprintf(f, fmt, ap);
    va_end(ap);
    return r;
}
void *volatile host_keep[] = { (void *)fma, (void *)fiprintf, (void *)calloc, (void *)malloc, (void *)abort };
EMSCRIPTEN_KEEPALIVE FILE *side_stderr(void) { return stderr; }
/* __multi3 (128bit 乗算) を main に残すための参照。JS からは使わない */
EMSCRIPTEN_KEEPALIVE __int128 host_mul128(__int128 a, __int128 b) { return a * b; }

EMSCRIPTEN_KEEPALIVE const char *host_error(void) { return dlerror(); }

EMSCRIPTEN_KEEPALIVE int host_load(void) {
    void *h = dlopen("/side.wasm", RTLD_NOW | RTLD_GLOBAL);
    if (!h) return 0;
    p_run = (run_t)dlsym(h, "ott_run");
    p_set_gbase = (set_gbase_t)dlsym(h, "ott_set_gbase");
    p_data_install = (data_install_t)dlsym(h, "ott_data_install");
    return p_run && p_set_gbase && p_data_install;
}
EMSCRIPTEN_KEEPALIVE void host_set_gbase(uint64_t b) { p_set_gbase(b); }
EMSCRIPTEN_KEEPALIVE void host_data_install(void) { p_data_install(); }
EMSCRIPTEN_KEEPALIVE uint64_t host_run(uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3,
                                       uint64_t x0, uint64_t x1, uint64_t x2, uint64_t x3) {
    return p_run(va, a0, a1, a2, a3, x0, x1, x2, x3);
}
