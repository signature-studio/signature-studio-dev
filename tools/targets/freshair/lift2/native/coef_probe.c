/* coef_probe.c — Filter の係数計算関数 (SC 0x180b7fa80 / KH 0x180469d40) の入口引数と出口の係数ブロックを記録する参照プローブ。
 *   ./coef_probe sc <SlateCore.core_64> <scen.txt> <out.txt> [fma]   (IAT は FA_IAT_ALL=1 で全束縛)
 *   ./coef_probe kh <HeartCore.core_64> <scen.txt> <out.txt>
 * 入口 (MS x64): edx=type, r8d=2*order (SC/KH とも呼出し位置の値), xmm3=freq, [rsp+0x28]=Q, [rsp+0x30]=gain, [rsp+0x38]=sr
 *   (呼出し位置の [rsp+0x20..0x30] に対応。ret 番地が [rsp] のため +8)。
 * 方式: 入口に int3 → 引数を記録し戻り番地に int3 → 出口で rcx のブロック (0x320 B) を記録 → TF で 1 命令進めて入口を再武装。
 * 出力: 処理 call ごとに "P <sidx> <c>" (処理の始まり)、係数計算が呼ばれた場合 "E ty= o2= f= q= g= sr= blk=<hex>"。 */
#define _GNU_SOURCE
#include "pe_map.h"
#include "native_shim.h"
#include <ucontext.h>
#include <signal.h>

#define COEF_BLK 0x320
#define VA_SC_COEF 0x180b7fa80ULL
#define VA_KH_COEF 0x180469d40ULL
#define VA_KH_FILTER 0x1804655e0ULL
#define SUM_VA 0x200000000ULL
#define ST_SIZE 0x1400
#define MAXTOK (1 << 20)

static uint64_t hk_entry, hk_ret, hk_blk; static uint8_t hk_entry_b, hk_ret_b;
static uint32_t hk_ty, hk_o2, hk_f, hk_q, hk_g, hk_sr;
static FILE* hk_out;

static void hk_hex(const void* p, size_t n) { const uint8_t* b = p; for (size_t i = 0; i < n; i++) fprintf(hk_out, "%02x", b[i]); }

static void hk_on_trap(int s, siginfo_t* si, void* uc_) {
    ucontext_t* uc = uc_; greg_t* g = uc->uc_mcontext.gregs;
    if (g[REG_EFL] & 0x100) { g[REG_EFL] &= ~0x100ULL; *(uint8_t*)hk_entry = 0xCC; return; }
    if (s != SIGTRAP) _exit(98);
    unsigned long long rip = g[REG_RIP] - 1;
    if (rip == hk_entry) {
        unsigned long long rsp = g[REG_RSP];
        uint32_t f3; memcpy(&f3, &uc->uc_mcontext.fpregs->_xmm[3], 4);
        hk_ty = (uint32_t)g[REG_RDX]; hk_o2 = (uint32_t)g[REG_R8]; hk_f = f3;
        memcpy(&hk_q, (void*)(rsp + 0x28), 4); memcpy(&hk_g, (void*)(rsp + 0x30), 4); memcpy(&hk_sr, (void*)(rsp + 0x38), 4);
        hk_blk = g[REG_RCX];
        fprintf(hk_out, "I blk="); hk_hex((void*)hk_blk, COEF_BLK); fprintf(hk_out, "\n");
        hk_ret = *(uint64_t*)rsp; hk_ret_b = *(uint8_t*)hk_ret; *(uint8_t*)hk_ret = 0xCC;
        *(uint8_t*)hk_entry = hk_entry_b;
        g[REG_RIP] = hk_entry; g[REG_EFL] |= 0x100; return;
    }
    if (rip == hk_ret) {
        *(uint8_t*)hk_ret = hk_ret_b;
        fprintf(hk_out, "E ty=%u o2=%u f=%08x q=%08x g=%08x sr=%08x blk=", hk_ty, hk_o2, hk_f, hk_q, hk_g, hk_sr);
        hk_hex((void*)hk_blk, COEF_BLK); fprintf(hk_out, "\n");
        g[REG_RIP] = hk_ret; g[REG_EFL] |= 0x100; return;
    }
    _exit(99);
}

static void hk_install(uint64_t entry) {
    hk_entry = entry; hk_entry_b = *(uint8_t*)entry; *(uint8_t*)entry = 0xCC;
    struct sigaction sa; memset(&sa, 0, sizeof sa); sa.sa_sigaction = hk_on_trap; sa.sa_flags = SA_NODEFER | SA_SIGINFO;
    sigaction(SIGTRAP, &sa, 0);
}

/* ---- シナリオ読込 (native_filter.c と同じ形式) ---- */
static unsigned long tok[MAXTOK];
static char line[1 << 22];

static int run_sc(const char* core, const char* scen, const char* fma_s) {
    uint8_t* im = pe_map(core);
    (void)im;
    static const unsigned long long stubs[] = {0x18103d37c, 0x18103d47c, 0x18102f728};
    for (unsigned k = 0; k < sizeof stubs / sizeof *stubs; k++) im[stubs[k] - 0x180000000ULL] = 0xCC;
    if (getenv("FA_IAT_ALL")) patch_iat_all(); else patch_iat(getenv("FA_IAT") ? getenv("FA_IAT") : "iat_slots.txt");
    patch_pokes(getenv("FA_POKES") ? getenv("FA_POKES") : "pokes.txt");
    volatile int* fma = (int*)0x1813070f8ULL; *fma = atoi(fma_s);
    hk_install(VA_SC_COEF);
    typedef long long (__attribute__((ms_abi)) *proc_t)(void*, void*);
    proc_t fn = (proc_t)0x180b6f050ULL;
    FILE* fp = fopen(scen, "r"); if (!fp) { perror("scen"); return 2; }
    while (fgets(line, sizeof line, fp)) {
        int k = 0; char* p = strtok(line, " \n"); while (p) { tok[k++] = strtoul(p, NULL, 16); p = strtok(NULL, " \n"); }
        int ti = 0; int sidx = (int)tok[ti++]; int ncalls = (int)tok[ti++];
        unsigned char* S = calloc(1, ST_SIZE); unsigned char* P = calloc(1, 0xa400); unsigned char* ctx = calloc(1, 0x80);
        *(uint64_t*)(S + 0x90) = (uint64_t)P;
        for (int c = 0; c < ncalls; c++) {
            int nW = (int)tok[ti++];
            for (int w = 0; w < nW; w++) {
                int rg = (int)tok[ti++]; unsigned off = (unsigned)tok[ti++]; uint32_t val = (uint32_t)tok[ti++];
                int bw = rg >= 0x10; rg &= 0xf; uint8_t* base = rg == 0 ? S : rg == 1 ? P : ctx;
                memcpy(base + off, &val, bw ? 1 : 4);
            }
            int n = (int)tok[ti++];
            float* L = calloc(n + 1, 4); float* R = calloc(n + 1, 4);
            for (int i = 0; i < n; i++) { uint32_t b = tok[ti + i]; memcpy(&L[i], &b, 4); b = tok[ti + n + i]; memcpy(&R[i], &b, 4); }
            ti += 2 * n;
            *(uint64_t*)(ctx + 0) = (uint64_t)L; *(uint64_t*)(ctx + 8) = (uint64_t)R; *(int32_t*)(ctx + 0x28) = n; ctx[0x60] = 0;
            fprintf(hk_out, "P %d %d\n", sidx, c);
            fn(S, ctx);
        }
    }
    return 0;
}

static int run_kh(const char* core, const char* scen) {
    pe_map(core);
    if (mmap((void*)SUM_VA, 0x1000, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) != (void*)SUM_VA) { fprintf(stderr, "sum map fail\n"); return 3; }
    hk_install(VA_KH_COEF);
    typedef long long (__attribute__((ms_abi)) *fn_t)(void*, void*, void*);
    FILE* fp = fopen(scen, "r"); if (!fp) { perror("scen"); return 2; }
    while (fgets(line, sizeof line, fp)) {
        int k = 0; char* p = strtok(line, " \n"); while (p) { tok[k++] = strtoul(p, NULL, 16); p = strtok(NULL, " \n"); }
        int ti = 0; int sidx = (int)tok[ti++]; int ncalls = (int)tok[ti++];
        uint8_t* self = calloc(1, ST_SIZE); uint8_t* P = calloc(1, 0x20); uint8_t* ctx = calloc(1, 0x3200);
        *(void**)(ctx + 0x3188) = P;
        *(void**)(self + 0x12d8) = (uint8_t*)SUM_VA - 0x28;
        for (int c = 0; c < ncalls; c++) {
            int nW = (int)tok[ti++];
            for (int w = 0; w < nW; w++) {
                int rg = (int)tok[ti++]; unsigned off = (unsigned)tok[ti++]; uint32_t val = (uint32_t)tok[ti++];
                if (rg == 0 && off == 0x98) memcpy(self + 0x60, &val, 4);
                else if (rg == 1 && off == 0x9dc4) memcpy(P + 0, &val, 4);
                else if (rg == 1 && off == 0x9e0c) memcpy(P + 4, &val, 4);
                else if (rg == 1 && off == 0x9e54) memcpy(P + 8, &val, 4);
                else if (rg == 1 && off == 0x9e9c) memcpy(P + 0xc, &val, 4);
                else if (rg == 1 && off == 0x9ee4) memcpy(P + 0x10, &val, 4);
                else { fprintf(stderr, "unmapped write rg=%d off=%x\n", rg, off); return 4; }
            }
            int n = (int)tok[ti++];
            float* L = calloc(129, 4); float* R = calloc(129, 4);
            for (int i = 0; i < n; i++) { uint32_t b = (uint32_t)tok[ti + i]; memcpy(&L[i], &b, 4); b = (uint32_t)tok[ti + n + i]; memcpy(&R[i], &b, 4); }
            ti += 2 * n;
            uint8_t* aud = calloc(1, 0x40);
            *(float**)(aud + 0) = L; *(float**)(aud + 8) = R; *(int*)(aud + 0x28) = n;
            memset((void*)SUM_VA, 0, 0x1000);
            fprintf(hk_out, "P %d %d\n", sidx, c);
            ((fn_t)VA_KH_FILTER)(self, ctx, aud);
        }
    }
    return 0;
}

int main(int argc, char** argv) {
    if (argc < 5) { fprintf(stderr, "usage: coef_probe sc|kh <core> <scen> <out> [fma]\n"); return 2; }
    hk_out = fopen(argv[4], "w"); if (!hk_out) { perror("out"); return 2; }
    int rc = !strcmp(argv[1], "sc") ? run_sc(argv[2], argv[3], argc > 5 ? argv[5] : "0") : run_kh(argv[2], argv[3]);
    fclose(hk_out);
    return rc;
}
