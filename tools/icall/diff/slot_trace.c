/* slot_trace.c — SlateCore.core_64 の .data zero-fill 域 (encoded slot 候補) への実行時アクセスを記録する (ICALL-59)。
 *  - 域を PROT_NONE にし、アクセスごとに SIGSEGV で 1 ページ開け、TF 単歩の SIGTRAP で閉じ直す。
 *  - 1 回の呼出しで (access VA, RIP) の組を重複除去して出力する: "ACC <addr> <rip> <count>"。
 *  - ロード・MS ABI 呼出しは ott_native.c をそのまま使う (native 参照と同一経路)。
 * 用法: slot_trace <SlateCore.core_64> <FN_VA hex> [heap 引数は 0 埋めの 0x400 バイト ×4, xmm0 = 1.5]
 */
#include "../../ott/native/ott_native.c"

#define ZLO 0x18128f000ULL
#define ZHI 0x18130a000ULL
#define MAXACC 4096

static uint64_t g_armed;
static uint64_t g_acc_addr[MAXACC], g_acc_rip[MAXACC], g_acc_cnt[MAXACC];
static int g_nacc;
static uint64_t g_stub_va;
static int g_stub_ret, g_stubbed;

static void record(uint64_t a, uint64_t rip) {
    for (int i = 0; i < g_nacc; i++)
        if (g_acc_addr[i] == a && g_acc_rip[i] == rip) { g_acc_cnt[i]++; return; }
    if (g_nacc < MAXACC) { g_acc_addr[g_nacc] = a; g_acc_rip[g_nacc] = rip; g_acc_cnt[g_nacc] = 1; g_nacc++; }
}

static void on_acc(int sig, siginfo_t* si, void* uc_) {
    ucontext_t* uc = (ucontext_t*)uc_;
    greg_t* g = uc->uc_mcontext.gregs;
    uint64_t a = (uint64_t)si->si_addr;
    if (sig == SIGSEGV && a >= ZLO && a < ZHI) {
        record(a, (uint64_t)g[REG_RIP]);
        uint64_t pg = a & ~0xfffULL;
        mprotect((void*)pg, 4096, PROT_READ | PROT_WRITE);
        g_armed = pg;
        g[REG_EFL] |= 0x100;
        return;
    }
    if (sig == SIGTRAP && g_armed) {
        mprotect((void*)g_armed, 4096, PROT_NONE);
        g_armed = 0;
        g[REG_EFL] &= ~0x100;
        return;
    }
    if (sig == SIGSEGV && g_stub_ret && g[REG_RIP] == g_stub_va) {
        uint64_t* sp = (uint64_t*)g[REG_RSP];
        g_stubbed++;
        g[REG_RIP] = (greg_t)sp[0];
        g[REG_RSP] += 8;
        g[REG_RAX] = 0;
        return;
    }
    fprintf(stderr, "[slot_trace] fatal sig=%d rip=%#llx addr=%p\n", sig, (unsigned long long)g[REG_RIP], si->si_addr);
    for (int i = 0; i < g_nacc; i++)
        printf("ACC %llx %llx %llu\n", (unsigned long long)g_acc_addr[i], (unsigned long long)g_acc_rip[i], (unsigned long long)g_acc_cnt[i]);
    fflush(stdout);
    _exit(95);
}

int main(int argc, char** argv) {
    if (argc < 3) { fprintf(stderr, "usage: slot_trace <dll> <fn_va_hex>\n"); return 2; }
    if (ott_load(argv[1]) != 0) return 3;
    uint64_t fn = strtoull(argv[2], NULL, 16);
    uint64_t gpr[4], xmm[4] = {0, 0, 0, 0}, out[2] = {0, 0};
    for (int i = 0; i < 4; i++) gpr[i] = (uint64_t)heap_alloc(0x400, 1);
    double x = 1.5; memcpy(&xmm[0], &x, 8);
    struct sigaction sa; memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = on_acc; sa.sa_flags = SA_SIGINFO; sigemptyset(&sa.sa_mask);
    if (getenv("SLOT_ENC_INIT")) {
        static const uint64_t enc[] = {0x1813068d0, 0x1813068f8, 0x181306900, 0x181306908, 0x181306910, 0x1813072b0,
                                       0x1813073f0, 0x1813073f8, 0x181307400, 0x181307408, 0x181307410, 0x181307418};
        ott_enc_slots(0x18125eaa8, enc, 12);
    }
    if (getenv("SLOT_STUB_VA")) {
        g_stub_va = strtoull(getenv("SLOT_STUB_VA"), NULL, 16);
        g_stub_ret = 1;
    }
    mprotect((void*)ZLO, ZHI - ZLO, PROT_NONE);
    sigaction(SIGSEGV, &sa, NULL);
    sigaction(SIGTRAP, &sa, NULL);
    ott_call(fn, gpr, xmm, NULL, 0, out);
    mprotect((void*)ZLO, ZHI - ZLO, PROT_READ | PROT_WRITE);
    for (int i = 0; i < g_nacc; i++)
        printf("ACC %llx %llx %llu\n", (unsigned long long)g_acc_addr[i], (unsigned long long)g_acc_rip[i], (unsigned long long)g_acc_cnt[i]);
    if (g_stubbed) printf("STUB %d\n", g_stubbed);
    printf("DONE %llx\n", (unsigned long long)fn);
    return 0;
}
