/* trace235.c — 0x180d235b0 の命令前レジスタトレース (native, int3 + TF シングルステップ)。
 *   ./trace235 <core> <iat> <pokes> <insns.txt> <count> <order2>
 * insns.txt: トレース対象 VA の 16進リスト (mlift cov_map と同じ集合。python で生成)。
 * 出力: mlift --trace (@fa_trace) と同形式 (33 x u64/行 = VA + GPR16 + XMM16x4lane)、16進 1 行 1 命令実行。 */
#include "pe_map.h"
#include "native_shim.h"

typedef uint64_t (__attribute__((ms_abi)) *fn_t)(uint64_t, double, double, double, double, uint64_t, void*);
typedef double (__attribute__((ms_abi)) *fnd_t)(double);

#define MAXVA 16384
static unsigned long long g_vas[MAXVA]; static int g_nva;
static unsigned char g_origbyte[MAXVA];
static unsigned long long g_rows[81 * 200000]; static unsigned long long g_nrow;
static int g_restored[16384]; static int g_nrestored;   /* 一時 restore 中の VA index */
static uint8_t* g_im;
static unsigned long long ulVa;

static void log_row(ucontext_t* uc) {
    static const int mlift[16] = {REG_RAX, REG_RCX, REG_RDX, REG_RBX, REG_RSP, REG_RBP, REG_RSI, REG_RDI,
                                  REG_R8, REG_R9, REG_R10, REG_R11, REG_R12, REG_R13, REG_R14, REG_R15};
    unsigned long long* row = g_rows + g_nrow * 81;
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
    unsigned long long va = uc->uc_mcontext.gregs[REG_RIP] - 1;
    for (int k = 0; k < g_nva; k++) {
        if (g_vas[k] == va) {
            if (g_nrow < 200000) log_row(uc);
            uc->uc_mcontext.gregs[REG_RIP] = va;
            *(unsigned char*)va = g_origbyte[k];          /* restore して実行 */
            /* 他の restore 中 insn を再 patch (loop back 対策) */
            for (int j = 0; j < g_nrestored; j++)
                if (g_restored[j] != k) g_im[g_vas[g_restored[j]] - 0x180000000ULL] = 0xCC;
            g_nrestored = 0;
            g_restored[g_nrestored++] = k;
            { static int dbg = 0; if (dbg++ < 4) { FILE* e = fopen("dbg_hit.txt", "a"); if (e) { fprintf(e, "hit k=%d va=%llx rip=%llx g_nva=%d\n", k, (unsigned long long)va, (unsigned long long)uc->uc_mcontext.gregs[REG_RIP], g_nva); fclose(e); } } }
            return;
        }
    }
    {   /* foreign SIGTRAP: 診情報を出して継続 (rip 進めない) */
        static int nf = 0;
        if (nf++ < 3) {
            char buf[256];
            int fd = open("/proc/self/maps", O_RDONLY);
            FILE* e = fopen("foreign_trap.txt", "a");
            if (e) {
                fprintf(e, "foreign SIGTRAP rip=%llx\n", (unsigned long long)uc->uc_mcontext.gregs[REG_RIP]);
                while (fd >= 0 && read(fd, buf, sizeof buf) > 0) fprintf(e, "%.*s", (int)sizeof buf, buf);
                fclose(e);
            }
            if (fd >= 0) close(fd);
        }
        return;
    }
    _exit(98);
}

int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]); g_im = im;
    patch_iat(argc > 2 ? argv[2] : "iat_slots.txt");
    patch_pokes(argc > 3 ? argv[3] : "pokes.txt");
    FILE* fp = fopen(argv[5], "r");
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
    ulVa = strtoull(argv[4], 0, 16);
    int count = argc > 5 ? atoi(argv[6]) : 0;
    int order2 = argc > 6 ? atoi(argv[7]) : 2;
    static uint8_t out[0x40];
    memset(out, 0xCC, sizeof out);
    {   /* fma flag (0x1813070f8) を pokes の後に設定 */
        int fma = argc > 10 ? atoi(argv[10]) : 0;
        *(volatile int*)0x1813070f8ULL = fma;
    }
    if (argc > 8 && argv[8][0] == 'd') {
        fnd_t fnd = (fnd_t)ulVa;
        volatile double x = argc > 9 ? atof(argv[9]) : 1.0;
        fnd(x);
    } else {
        fn_t fn = (fn_t)ulVa;
        fn((uint64_t)count, 48000.0, 1000.0, 0.7071067811865476, 0.5, (uint64_t)order2, out);
    }
    { FILE* e = fopen("dbg_rows.txt", "w"); if (e) { for (int r = 0; r < 6 && (unsigned long long)r < g_nrow; r++) fprintf(e, "row%d va=%llx g_nrow=%llu\n", r, (unsigned long long)g_rows[r * 81], (unsigned long long)g_nrow); fclose(e); } }
    for (unsigned long long r = 0; r < g_nrow; r++) {
        unsigned long long* row = g_rows + r * 81;
        for (int k = 0; k < 81; k++) printf("%llx%c", row[k], k == 80 ? '\n' : ' ');
    }
    return 0;
}
