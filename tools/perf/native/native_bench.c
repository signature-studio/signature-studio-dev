/* native_bench.c — OTT_vst2_win64.dll の実機械語 (tools/ott/native の libottnative.so が VA 通りに敷設) で
 * processReplacing(128f) を計時する。 wasm 側 (harness/x64c_core.mjs) と同一の入力・パラメータ・署名手順。
 *   native_bench [dll] [libottnative.so] [iters]   → JSON 1 行 (setarch x86_64 -R 下で実行すること: native_bench.sh)
 * 計時対象は ott_call 1 回 (MS x64 ABI trampoline ms_call.S + 実機械語)。 trampoline の固定費は数十 ns で p50 の 0.1% 未満。 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
typedef uint64_t u64;
#define N 128
#define OBJ 0x30310000ull
#define IN_A 0x30320000ull
#define OU_A 0x30330000ull
#define BUF 0x30340000ull
static u64 (*ott_call)(u64, const u64*, const u64*, const u64*, long, u64*);
static double now_us(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec * 1e6 + t.tv_nsec / 1e3; }
static int cmp(const void* a, const void* b) { double x = *(const double*)a, y = *(const double*)b; return x < y ? -1 : x > y; }
static u64 call4(u64 fn, u64 a0, u64 a1, u64 a2, u64 a3, u64 x2) {
    u64 g[4] = {a0, a1, a2, a3}, x[4] = {0, 0, x2, 0}, s[1] = {0}, o[2];
    return ott_call(fn, g, x, s, 0, o);
}
int main(int argc, char** argv) {
    const char* dll = argc > 1 ? argv[1] : "OTT_vst2_win64.dll";
    const char* lib = argc > 2 ? argv[2] : "libottnative.so";
    int iters = argc > 3 ? atoi(argv[3]) : 20000;
    void* h = dlopen(lib, RTLD_NOW);
    if (!h) { fprintf(stderr, "dlopen %s: %s\n", lib, dlerror()); return 2; }
    int (*load)(const char*) = dlsym(h, "ott_load");
    void (*segv)(void) = dlsym(h, "ott_install_segv");
    int (*map_range)(u64, u64) = dlsym(h, "ott_map_range");
    ott_call = dlsym(h, "ott_call");
    segv();
    if (load(dll) != 0) { fprintf(stderr, "ott_load failed\n"); return 2; }
    if (map_range(0x30300000ull, 0x30400000ull) != 0) { fprintf(stderr, "map_range failed\n"); return 2; }
    float half = 0.5f; uint32_t hb; memcpy(&hb, &half, 4);
    call4(0x18011d400ull, OBJ, 0, 0, 0, 0);
    for (int i = 0; i < 19; i++) call4(0x180120af0ull, OBJ, i, 0, 0, hb);
    call4(0x180120800ull, OBJ, 0, 0, 0, 0);
    float* f = (float*)BUF;
    for (int i = 0; i < N * 2; i++) f[i] = (float)(sin(i * 0.05) * 0.5);
    u64* in = (u64*)IN_A; u64* ou = (u64*)OU_A;
    in[0] = BUF; in[1] = BUF + N * 4; ou[0] = BUF + N * 8; ou[1] = BUF + N * 12;
    uint32_t hsh = 0x811c9dc5u; uint32_t* U = (uint32_t*)BUF;
    for (int k = 1; k <= 1000; k++) {
        call4(0x18011ec20ull, OBJ, IN_A, OU_A, N, 0);
        if (k <= 8 || k == 1000) for (int i = 0; i < 2 * N; i++) hsh = (hsh ^ U[2 * N + i]) * 16777619u;
    }
    int nz = 0; for (int i = 0; i < 2 * N; i++) if (f[2 * N + i] != 0.0f) nz++;
    for (int k = 0; k < 300; k++) call4(0x18011ec20ull, OBJ, IN_A, OU_A, N, 0);
    double* per = malloc(sizeof(double) * iters);
    for (int k = 0; k < iters; k++) { double t = now_us(); call4(0x18011ec20ull, OBJ, IN_A, OU_A, N, 0); per[k] = now_us() - t; }
    qsort(per, iters, sizeof(double), cmp);
    double b[100];
    for (int i = 0; i < 100; i++) { double t = now_us(); for (int k = 0; k < 64; k++) call4(0x18011ec20ull, OBJ, IN_A, OU_A, N, 0); b[i] = (now_us() - t) / 64; }
    qsort(b, 100, sizeof(double), cmp);
    FILE* lf = fopen("/proc/loadavg", "r"); double la = 0; if (lf) { if (fscanf(lf, "%lf", &la) != 1) la = 0; fclose(lf); }
    printf("{\"env\":\"native-x64\",\"sig\":\"%x\",\"nonzeroOut\":%d,\"p50us\":%.2f,\"p99us\":%.2f,\"maxus\":%.2f,\"minus\":%.2f,\"batch64p50us\":%.2f,\"rtf44\":%.5f,\"load\":%.2f}\n",
           hsh, nz, per[iters / 2], per[(int)(iters * 0.99)], per[iters - 1], per[0], b[50], per[iters / 2] / (128 / 44.1 * 1000), la);
    return 0;
}
