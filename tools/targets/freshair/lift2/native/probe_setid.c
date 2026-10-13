/* probe_setid.c — FA-7: 実 ctor (0x180b4c040) で構築した Filter モデル M に対し、実機 setter 0x1803debc0(M,id,value) を呼び
 *   (a) M (0xa400B) のどのバイトが変わるか (b) Filter process (0x180b6f050) の出力が変わるか を実測する。
 *   ./probe_setid <core> <id_hex>... ; 値は f32 0.5 / 0.25 / 0.9 の 3 水準。stdout: 1 行/ID。
 *   (b) は sr=48000, 型 enum M+0x9dc4 = type (環境変数 FA_TYPE, 既定 ctor 値) で 64 sample の疑似ノイズを処理し L/R の FNV-1a を比較。 */
#include "pe_map.h"
#include "native_shim.h"
#include <sys/wait.h>
typedef long long (__attribute__((ms_abi)) *ctor_t)(void*, void*);
typedef void (__attribute__((ms_abi)) *set_t)(void*, int, unsigned);
typedef void (__attribute__((ms_abi)) *proc_t)(void*, void*);
#define MS 0xa400
static unsigned char *M0;
static uint64_t fnv(const void* p, size_t n);
static uint64_t run_proc(unsigned char* M, unsigned type, int* err);
/* 測定は fork 子で隔離 (process が image 内グローバルを書き換えるため親状態を汚さない)。id<0 は setter 無し。 */
static int g_poff = -1; static unsigned g_pval;
static uint64_t measure(int id, unsigned val, unsigned type, int* serr, int* perr, int* diffB, int* offs) {
    uint64_t* sh = mmap(0, 4096, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    pid_t pid = fork();
    if (pid == 0) {
        unsigned char* T = gr_alloc(0xa400); memcpy(T, M0, 0xa400); int s2 = 0; if (g_poff >= 0) memcpy(T + g_poff, &g_pval, 4);
        if (id >= 0) { g_in_guard = 1; s2 = sigsetjmp(g_jb, 1); if (s2 == 0) ((void (__attribute__((ms_abi))*)(void*, int, unsigned))0x1803debc0ULL)(T, id, val); g_in_guard = 0; }
        int nd = 0; for (int i = 0; i < 0xa400; i++) if (T[i] != M0[i]) { if (nd < 8) ((int*)(sh + 4))[nd] = i; nd++; }
        int e; uint64_t h = run_proc(T, type, &e);
        sh[0] = h; ((int*)sh)[2] = s2; ((int*)sh)[3] = e; ((int*)sh)[4 + 16] = nd; _exit(0);
    }
    int st; waitpid(pid, &st, 0);
    uint64_t h = sh[0]; *serr = ((int*)sh)[2]; *perr = ((int*)sh)[3]; *diffB = ((int*)sh)[4 + 16];
    for (int i = 0; i < 8; i++) offs[i] = ((int*)(sh + 4))[i];
    munmap(sh, 4096); return h;
}
static uint64_t fnv(const void* p, size_t n) { uint64_t h = 1469598103934665603ULL; const uint8_t* b = p; for (size_t i = 0; i < n; i++) { h ^= b[i]; h *= 1099511628211ULL; } return h; }
static uint64_t run_proc(unsigned char* M, unsigned type, int* err) {
    unsigned char* S = gr_alloc(0x1400); unsigned char* ctx = gr_alloc(0x80); int n = 64;
    float* L = (float*)gr_alloc(n * 4 + 4); float* R = (float*)gr_alloc(n * 4 + 4);
    unsigned r = 12345; for (int i = 0; i < n; i++) { r = r * 1664525u + 1013904223u; L[i] = ((int)(r >> 8) - 8388608) / 8388608.0f * 0.5f; R[i] = -L[i] * 0.7f + 0.01f; }
    float sr = 48000.0f; memcpy(S + 0x98, &sr, 4); *(uint64_t*)(S + 0x90) = (uint64_t)M;
    if (type != 0xffffffffu) memcpy(M + 0x9dc4, &type, 4);
    *(uint64_t*)(ctx + 0) = (uint64_t)L; *(uint64_t*)(ctx + 8) = (uint64_t)R; *(int32_t*)(ctx + 0x28) = n;
    g_in_guard = 1; int s = sigsetjmp(g_jb, 1); *err = s;
    for (int rep = 0; rep < 3 && s == 0; rep++) ((proc_t)0x180b6f050ULL)(S, ctx);
    g_in_guard = 0;
    uint64_t h = fnv(L, n * 4) * 31 + fnv(R, n * 4);
    if (getenv("FA_SHOW")) { unsigned r2 = 12345; int diff = 0; float mx = 0; for (int i = 0; i < n; i++) { r2 = r2 * 1664525u + 1013904223u; float in = ((int)(r2 >> 8) - 8388608) / 8388608.0f * 0.5f; if (L[i] != in) diff++; float d = L[i] - in; if (d < 0) d = -d; if (d > mx) mx = d; } fprintf(stderr, "SHOW type=%u L!=in %d/%d maxabsdiff=%g\n", type, diff, n, mx); }
    return h;
}
int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]); guard_install();
    static const unsigned long long stubs[] = {0x18103d37c, 0x18103d47c, 0x18102f728};
    for (unsigned k = 0; k < sizeof stubs / sizeof *stubs; k++) im[stubs[k] - 0x180000000ULL] = 0xCC;
    { unsigned char* p = im + (0x18100c72cULL - 0x180000000ULL);
      if (p[0] == 0x65 && p[1] == 0x4c && p[2] == 0x8b && p[3] == 0x1c) { static const unsigned char G[9] = {0x4d,0x31,0xdb,0x90,0x90,0x90,0x90,0x90,0x90}; memcpy(p, G, 9); }
      unsigned char* q = im + (0x18100c738ULL - 0x180000000ULL); if (q[0] == 0x73) q[0] = 0xEB; }
    g_heap_zero = 1; patch_iat("iat_slots.txt"); patch_pokes("pokes.txt");
    static unsigned long long dummy[4];
    M0 = gr_alloc(MS);
    g_in_guard = 1; int s = sigsetjmp(g_jb, 1);
    if (s == 0) ((ctor_t)0x180b4c040ULL)(M0, dummy);
    g_in_guard = 0; if (s) { fprintf(stderr, "ctor ERR\n"); return 3; }
    unsigned type = getenv("FA_TYPE") ? (unsigned)atoi(getenv("FA_TYPE")) : 0xffffffffu;
    unsigned lv[3]; float fl[3] = {0.5f, 0.25f, 0.9f}; memcpy(lv, fl, 12);
    int se, pe, nd, of[8]; uint64_t base_h = measure(-1, 0, type, &se, &pe, &nd, of);
    uint64_t base_h2 = measure(-1, 0, type, &se, &pe, &nd, of);
    printf("# type=%s base_out_hash=%016llx base_rerun_hash=%016llx deterministic=%d perr=%d\n", type == 0xffffffffu ? "ctor-default" : getenv("FA_TYPE"),
           (unsigned long long)base_h, (unsigned long long)base_h2, base_h == base_h2, pe);
    for (int a = 2; a < argc; a++) {
        if (argv[a][0] == 'P') {   /* 陽性対照: M+off へ f32 を直書き (setter 経由なし) */
            char* eq = strchr(argv[a], '='); g_poff = (int)strtol(argv[a] + 1, 0, 16); float f = strtof(eq + 1, 0); memcpy(&g_pval, &f, 4);
            uint64_t h = measure(-1, 0, type, &se, &pe, &nd, of); printf("POKE M+0x%x=%g: diffB=%d outChanged=%d perr=%d\n", g_poff, f, nd, h != base_h, pe); g_poff = -1; continue; }
        int id = (int)strtol(argv[a], 0, 16); printf("ID 0x%x:", id);
        for (int k = 0; k < 3; k++) {
            uint64_t h = measure(id, lv[k], type, &se, &pe, &nd, of);
            printf(" [v=%.2f setErr=%d diffB=%d", fl[k], se, nd);
            if (nd) { printf(" off="); for (int i = 0; i < nd && i < 8; i++) printf("%x,", of[i]); }
            printf(" outChanged=%d perr=%d]", h != base_h, pe);
        }
        printf("\n");
    }
    return 0;
}
