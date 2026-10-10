/* trace235.c — 0x180d235b0 の命令前レジスタトレース (native, int3 + TF シングルステップ)。
 *   ./trace235 <core> <iat> <pokes> <insns.txt> <count> <order2>
 * insns.txt: トレース対象 VA の 16進リスト (mlift cov_map と同じ集合。python で生成)。
 * 出力: mlift --trace (@fa_trace) と同形式 (33 x u64/行 = VA + GPR16 + XMM16x4lane)、16進 1 行 1 命令実行。 */
#include "pe_map.h"
#include "native_shim.h"

typedef uint64_t (__attribute__((ms_abi)) *fn_t)(uint64_t, double, double, double, double, uint64_t, void*);

#define MAXVA 8192
static unsigned long long g_vas[MAXVA]; static int g_nva;
static unsigned char g_origbyte[MAXVA];
static unsigned long long g_rows[33 * 400000]; static unsigned long long g_nrow;
static int g_ss;

static void log_row(ucontext_t* uc) {
    static const int mlift[16] = {REG_RAX, REG_RCX, REG_RDX, REG_RBX, REG_RSP, REG_RBP, REG_RSI, REG_RDI,
                                  REG_R8, REG_R9, REG_R10, REG_R11, REG_R12, REG_R13, REG_R14, REG_R15};
    unsigned long long* row = g_rows + g_nrow * 33;
    row[0] = uc->uc_mcontext.gregs[REG_RIP] - 1;
    for (int k = 0; k < 16; k++) row[1 + k] = uc->uc_mcontext.gregs[mlift[k]];
    for (int k = 0; k < 16; k++) {
        unsigned int* l = (unsigned int*)&uc->uc_mcontext.fpregs->_xmm[k];
        for (int lane = 0; lane < 4; lane++) row[17 + k * 4 + lane] = l[lane];
    }
    g_nrow++;
}

static void on_sig_trace(int s, siginfo_t* si, void* uc_) {
    ucontext_t* uc = (ucontext_t*)uc_;
    unsigned long long rip = uc->uc_mcontext.gregs[REG_RIP];
    if (s == SIGTRAP && !g_ss) {
        unsigned long long va = rip - 1;
        for (int k = 0; k < g_nva; k++) {
            if (g_vas[k] == va) {
                if (g_nrow < 400000) log_row(uc);
                uc->uc_mcontext.gregs[REG_RIP] = va;
                *(unsigned char*)va = g_origbyte[k];
                uc->uc_mcontext.gregs[REG_EFL] |= 0x100;
                g_ss = 1;
                return;
            }
        }
    }
    if (s == SIGTRAP && g_ss) {
        g_ss = 0;
        uc->uc_mcontext.gregs[REG_EFL] &= ~0x100ULL;
        return;
    }
    _exit(98);
}

int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]);
    patch_iat(argc > 2 ? argv[2] : "iat_slots.txt");
    patch_pokes(argc > 3 ? argv[3] : "pokes.txt");
    FILE* fp = fopen(argv[4], "r");
    if (!fp) { perror("insns"); return 2; }
    while (g_nva < MAXVA && fscanf(fp, "%llx", &g_vas[g_nva]) == 1) g_nva++;
    fclose(fp);
    for (int k = 0; k < g_nva; k++) {
        g_origbyte[k] = im[g_vas[k] - 0x180000000ULL];
        im[g_vas[k] - 0x180000000ULL] = 0xCC;
    }
    struct sigaction sa; memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = on_sig_trace; sa.sa_flags = SA_NODEFER | SA_SIGINFO;
    sigaction(SIGTRAP, &sa, 0);
    int count = argc > 5 ? atoi(argv[5]) : 0;
    int order2 = argc > 6 ? atoi(argv[6]) : 2;
    static uint8_t out[0x40];
    memset(out, 0xCC, sizeof out);
    fn_t fn = (fn_t)0x180d235b0ULL;
    fn((uint64_t)count, 48000.0, 1000.0, 0.7071067811865476, 0.5, (uint64_t)order2, out);
    for (unsigned long long r = 0; r < g_nrow; r++) {
        unsigned long long* row = g_rows + r * 33;
        for (int k = 0; k < 33; k++) printf("%llx%c", row[k], k == 32 ? '\n' : ' ');
    }
    return 0;
}
