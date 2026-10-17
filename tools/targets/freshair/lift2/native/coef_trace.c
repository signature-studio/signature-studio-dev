/* coef_trace.c — Filter の係数計算関数 (SC 0x180b7fa80 / KH 0x180469d40) と、その直下の呼出し先の入口スカラ引数・出口の戻り値を記録する参照プローブ。
 *   ./coef_trace sc <SlateCore.core_64> <scen.txt> <out.txt> [fma]   (IAT は FA_IAT_ALL=1 で全束縛)
 *   ./coef_trace kh <HeartCore.core_64> <scen.txt> <out.txt>
 * 記録: "P <sidx> <c>" (処理 call の始まり)、"C <name> r8=.. x0=.. x1=.. x2=.. x3=.." (入口)、"R <name> rax=.. x0=.." (出口)。
 * 方式: 各 trap の入口に int3 → 引数を記録し戻り番地に int3 → 出口で戻り値を記録。入口の元命令は TF で 1 命令実行してから再武装する。
 * ポインタ引数 (rcx/rdx) は両側で値が異なるため記録しない。 */
#define _GNU_SOURCE
#include "pe_map.h"
#include "native_shim.h"
#include <ucontext.h>
#include <signal.h>

#define SUM_VA 0x200000000ULL
#define ST_SIZE 0x1400
#define MAXTOK (1 << 20)
#define NT 8

static uint64_t tva[NT], tret[NT]; static uint8_t torig[NT], tretb[NT]; static const char* tname[NT]; static int nt;
static int tarmed[NT]; static int tret_armed[NT];
static FILE* hk_out;

static void arm_all(void) { for (int i = 0; i < nt; i++) if (tarmed[i]) *(uint8_t*)tva[i] = 0xCC; }

static void hk_on_trap(int s, siginfo_t* si, void* uc_) {
    ucontext_t* uc = uc_; greg_t* g = uc->uc_mcontext.gregs;
    if (g[REG_EFL] & 0x100) { g[REG_EFL] &= ~0x100ULL; arm_all(); return; }
    if (s != SIGTRAP) _exit(98);
    unsigned long long rip = g[REG_RIP] - 1;
    for (int i = 0; i < nt; i++) {
        if (tarmed[i] && rip == tva[i]) {
            uint64_t rsp = g[REG_RSP];
            uint32_t x[4]; for (int k = 0; k < 4; k++) memcpy(&x[k], &uc->uc_mcontext.fpregs->_xmm[k], 4);
            fprintf(hk_out, "C %s r8=%llx x0=%08x x1=%08x x2=%08x x3=%08x\n", tname[i],
                    (unsigned long long)(uint32_t)g[REG_R8], x[0], x[1], x[2], x[3]);
            tret[i] = *(uint64_t*)rsp; tretb[i] = *(uint8_t*)tret[i]; *(uint8_t*)tret[i] = 0xCC; tret_armed[i] = 1;
            *(uint8_t*)tva[i] = torig[i]; tarmed[i] = 0;
            g[REG_RIP] = tva[i]; g[REG_EFL] |= 0x100; return;
        }
    }
    for (int i = 0; i < nt; i++) {
        if (tret_armed[i] && rip == tret[i]) {
            *(uint8_t*)tret[i] = tretb[i]; tret_armed[i] = 0;
            uint32_t x0; memcpy(&x0, &uc->uc_mcontext.fpregs->_xmm[0], 4);
            fprintf(hk_out, "R %s rax=%llx x0=%08x\n", tname[i], (unsigned long long)g[REG_RAX], x0);
            tarmed[i] = 1;
            g[REG_RIP] = tret[i]; g[REG_EFL] |= 0x100; return;
        }
    }
    _exit(99);
}

static void hk_add(uint64_t va, const char* name) {
    tva[nt] = va; tname[nt] = name; torig[nt] = *(uint8_t*)va; tarmed[nt] = 1; nt++;
}

static void hk_install(void) {
    struct sigaction sa; memset(&sa, 0, sizeof sa); sa.sa_sigaction = hk_on_trap; sa.sa_flags = SA_NODEFER | SA_SIGINFO;
    sigaction(SIGTRAP, &sa, 0);
    arm_all();
}

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
    hk_add(0x180b7fa80ULL, "COEF");
    hk_add(0x180b7fa10ULL, "SUB_a10");
    hk_add(0x180d22850ULL, "SUB_d22850");
    hk_add(0x180d235b0ULL, "SUB_d235b0");
    hk_add(0x18100c1e0ULL, "SUB_100c1e0");
    hk_add(0x18103fd60ULL, "SUB_103fd60");
    hk_install();
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
    hk_add(0x180469d40ULL, "COEF");
    hk_add(0x180bac490ULL, "SUB_bac490");
    hk_add(0x180ba9f10ULL, "SUB_ba9f10");
    hk_install();
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
            ((fn_t)0x1804655e0ULL)(self, ctx, aud);
        }
    }
    return 0;
}

int main(int argc, char** argv) {
    if (argc < 5) { fprintf(stderr, "usage: coef_trace sc|kh <core> <scen> <out> [fma]\n"); return 2; }
    hk_out = fopen(argv[4], "w"); if (!hk_out) { perror("out"); return 2; }
    int rc = !strcmp(argv[1], "sc") ? run_sc(argv[2], argv[3], argc > 5 ? argv[5] : "0") : run_kh(argv[2], argv[3]);
    fclose(hk_out);
    return rc;
}
