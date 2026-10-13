/* native_setter.c — FA-8: Filter model ctor (0x180b4c040) → setter 0x1803debc0(M,id,v) 列 → Filter process (0x180b6f050) を実機機械語で実行し、
 *   出力 L/R と M の param 領域を hex で出す。wasm 側 (setter_harness.mjs) と同一シナリオで bit-exact 比較する。
 *   ./native_setter <core> <scen.txt> [fma]
 * シナリオ (全て hex): sidx type nset {id val_bits}*  ncalls  (n 64 サンプル疑似乱数 seed) …
 *   → 各 process 呼出後に L/R (64 f32) + M+0x9dc4/0x9e0c/0x9e54/0x9e9c/0x9ee4 の dword + 対象 descriptor 先頭 0x28B を出力。
 * ポインタを含む M 領域は比較しない (native/wasm でアドレスが異なるため)。シナリオ毎に fork (process が image 内グローバルを書き換える)。 */
#include "pe_map.h"
#include "native_shim.h"
#include <sys/wait.h>
typedef long long (__attribute__((ms_abi)) *ctor_t)(void*, void*);
typedef void (__attribute__((ms_abi)) *set_t)(void*, int, unsigned);
typedef void (__attribute__((ms_abi)) *proc_t)(void*, void*);
static unsigned long long rng(unsigned long long* s) { *s = *s * 6364136223846793005ULL + 1442695040888963407ULL; return *s >> 33; }
static void run_one(unsigned long* tok, int fma) {
    int ti = 0; int sidx = (int)tok[ti++]; unsigned type = (unsigned)tok[ti++]; int nset = (int)tok[ti++];
    unsigned char* M = gr_alloc(0xa400); static unsigned long long dummy[4];
    g_in_guard = 1; int s = sigsetjmp(g_jb, 1);
    if (s == 0) ((ctor_t)0x180b4c040ULL)(M, dummy);
    g_in_guard = 0; if (s) { printf("S%d |CTORERR\n", sidx); return; }
    printf("S%d", sidx);
    for (int k = 0; k < nset; k++) {
        int id = (int)tok[ti++]; unsigned v = (unsigned)tok[ti++];
        g_in_guard = 1; s = sigsetjmp(g_jb, 1);
        if (s == 0) ((set_t)0x1803debc0ULL)(M, id, v);
        g_in_guard = 0; if (s) { printf(" |SETERR"); }
    }
    int ncalls = (int)tok[ti++]; unsigned long long seed = tok[ti++];
    unsigned char* S = gr_alloc(0x1400); unsigned char* ctx = gr_alloc(0x80); int n = 64;
    float sr = 48000.0f; memcpy(S + 0x98, &sr, 4); *(uint64_t*)(S + 0x90) = (uint64_t)M; memcpy(M + 0x9dc4, &type, 4);
    *(volatile int*)0x1813070f8ULL = fma;
    for (int c = 0; c < ncalls; c++) {
        float* L = (float*)gr_alloc(n * 4 + 4); float* R = (float*)gr_alloc(n * 4 + 4);
        for (int i = 0; i < n; i++) { L[i] = ((int)(rng(&seed) & 0xffffff) - 8388608) / 8388608.0f * 0.5f; R[i] = -L[i] * 0.7f + 0.01f; }
        *(uint64_t*)(ctx + 0) = (uint64_t)L; *(uint64_t*)(ctx + 8) = (uint64_t)R; *(int32_t*)(ctx + 0x28) = n; ctx[0x60] = 0;
        g_in_guard = 1; s = sigsetjmp(g_jb, 1);
        if (s == 0) ((proc_t)0x180b6f050ULL)(S, ctx);
        g_in_guard = 0; if (s) { printf(" |PROCERR"); break; }
        printf(" |"); hexdump(L, n * 4); printf(" "); hexdump(R, n * 4);
        printf(" "); static const unsigned o[5] = {0x9dc4, 0x9e0c, 0x9e54, 0x9e9c, 0x9ee4}; for (int i = 0; i < 5; i++) hexdump(M + o[i], 4);
    }
    printf("\n");
}
int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]); guard_install();
    static const unsigned long long stubs[] = {0x18103d37c, 0x18103d47c, 0x18102f728};
    for (unsigned k = 0; k < sizeof stubs / sizeof *stubs; k++) im[stubs[k] - 0x180000000ULL] = 0xCC;
    { unsigned char* p = im + (0x18100c72cULL - 0x180000000ULL);
      if (p[0] == 0x65 && p[1] == 0x4c && p[2] == 0x8b && p[3] == 0x1c) { static const unsigned char G[9] = {0x4d,0x31,0xdb,0x90,0x90,0x90,0x90,0x90,0x90}; memcpy(p, G, 9); }
      unsigned char* q = im + (0x18100c738ULL - 0x180000000ULL); if (q[0] == 0x73) q[0] = 0xEB; }
    g_heap_zero = 1; patch_iat("iat_slots.txt"); patch_pokes("pokes.txt");
    int fma = argc > 3 ? atoi(argv[3]) : 0;
    FILE* fp = fopen(argv[2], "r"); if (!fp) { perror("scen"); return 2; }
    static char line[1 << 16]; static unsigned long tok[1 << 12];
    while (fgets(line, sizeof line, fp)) {
        int k = 0; char* p = strtok(line, " \n"); while (p) { tok[k++] = strtoul(p, NULL, 16); p = strtok(NULL, " \n"); }
        fflush(stdout); pid_t pid = fork();
        if (pid == 0) { run_one(tok, fma); fflush(stdout); _exit(0); }
        int st; waitpid(pid, &st, 0); if (!WIFEXITED(st) || WEXITSTATUS(st)) printf("S%lx |CHILDFAIL\n", tok[0]);
    }
    return 0;
}
