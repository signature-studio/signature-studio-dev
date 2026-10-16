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
static uint64_t g_gpr[4];

#define ITRN 300000
static uint64_t g_trace_fn, g_trace_on, g_itr_n, g_trace_orig;
static volatile int g_trace_stop;
static greg_t g_itr[ITRN][19];

static void itr_record(ucontext_t* uc) {
    greg_t* r = g_itr[g_itr_n++ % ITRN];
    memcpy(r, uc->uc_mcontext.gregs, 18 * sizeof(greg_t));
    r[18] = *(greg_t*)(uc->uc_mcontext.gregs[REG_RSP] + 0x28);
}

static void itr_dump(void) {
    const char* p = getenv("SLOT_TRACE_OUT");
    FILE* f = fopen(p ? p : "slot_trace_insn.txt", "w");
    if (!f) return;
    uint64_t s = g_itr_n > ITRN ? g_itr_n - ITRN : 0;
    for (uint64_t i = s; i < g_itr_n; i++) {
        greg_t* r = g_itr[i % ITRN];
        fprintf(f, "I %llx", (unsigned long long)r[REG_RIP]);
        static const int ord[] = {REG_RAX, REG_RBX, REG_RCX, REG_RDX, REG_RSI, REG_RDI, REG_RBP, REG_RSP,
                                  REG_R8, REG_R9, REG_R10, REG_R11, REG_R12, REG_R13, REG_R14, REG_R15};
        for (int k = 0; k < 16; k++) fprintf(f, " %llx", (unsigned long long)r[ord[k]]);
        fprintf(f, " s28=%llx\n", (unsigned long long)r[18]);
    }
    fclose(f);
}

static void dump_at_exit(void) {
    if (!g_trace_on) return;
    g_trace_stop = 1;
    itr_dump();
}

static void record(uint64_t a, uint64_t rip) {
    for (int i = 0; i < g_nacc; i++)
        if (g_acc_addr[i] == a && g_acc_rip[i] == rip) { g_acc_cnt[i]++; return; }
    if (g_nacc < MAXACC) { g_acc_addr[g_nacc] = a; g_acc_rip[g_nacc] = rip; g_acc_cnt[g_nacc] = 1; g_nacc++; }
}

static void on_acc(int sig, siginfo_t* si, void* uc_) {
    ucontext_t* uc = (ucontext_t*)uc_;
    greg_t* g = uc->uc_mcontext.gregs;
    uint64_t a = (uint64_t)si->si_addr;
    if (sig == SIGTRAP && g_trace_stop) { g[REG_EFL] &= ~0x100; return; }
    if (sig == SIGTRAP && g_trace_fn && !g_trace_on && g[REG_RIP] == g_trace_fn + 1) {
        g_trace_on = 1;
        *(uint8_t*)g_trace_fn = (uint8_t)g_trace_orig;
        g[REG_RIP] = (greg_t)g_trace_fn;
        itr_record(uc);
        g[REG_EFL] |= 0x100;
        return;
    }
    if (sig == SIGTRAP && g_trace_on) {
        itr_record(uc);
        if (g_armed) { mprotect((void*)g_armed, 4096, PROT_NONE); g_armed = 0; }
        g[REG_EFL] |= 0x100;
        return;
    }
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
    fprintf(stderr, "[slot_trace] regs rax=%#llx rcx=%#llx rdx=%#llx rsp=%#llx rbp=%#llx r8=%#llx r9=%#llx\n",
            (unsigned long long)g[REG_RAX], (unsigned long long)g[REG_RCX], (unsigned long long)g[REG_RDX],
            (unsigned long long)g[REG_RSP], (unsigned long long)g[REG_RBP], (unsigned long long)g[REG_R8], (unsigned long long)g[REG_R9]);
    fprintf(stderr, "[slot_trace] heap_args %#llx %#llx %#llx %#llx\n", (unsigned long long)g_gpr[0], (unsigned long long)g_gpr[1],
            (unsigned long long)g_gpr[2], (unsigned long long)g_gpr[3]);
    if (g_trace_on) itr_dump();
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
    for (int i = 0; i < 4; i++) g_gpr[i] = gpr[i] = (uint64_t)heap_alloc(0x400, 1);
    double x = 1.5; memcpy(&xmm[0], &x, 8);
    struct sigaction sa; memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = on_acc; sa.sa_flags = SA_SIGINFO; sigemptyset(&sa.sa_mask);
    if (getenv("SLOT_ENC_INIT")) {
        static const uint64_t enc[] = {0x1813068d0, 0x1813068f8, 0x181306900, 0x181306908, 0x181306910, 0x1813072b0,
                                       0x1813073f0, 0x1813073f8, 0x181307400, 0x181307408, 0x181307410, 0x181307418};
        ott_enc_slots(0x18125eaa8, enc, 12);
    }
    if (getenv("SLOT_T2_INIT")) {
        uint64_t t2[34];
        for (int i = 0; i < 34; i++) t2[i] = 0x1813071a0ULL + 8 * i;
        ott_enc_slots(0x18125eaa8, t2, 34);
    }
    if (getenv("SLOT_STUB_VA")) {
        g_stub_va = strtoull(getenv("SLOT_STUB_VA"), NULL, 16);
        g_stub_ret = 1;
    }
    if (getenv("SLOT_TRACE_FN")) {
        g_trace_fn = strtoull(getenv("SLOT_TRACE_FN"), NULL, 16);
        uint64_t pg = g_trace_fn & ~0xfffULL;
        mprotect((void*)pg, 4096, PROT_READ | PROT_WRITE | PROT_EXEC);
        g_trace_orig = *(uint8_t*)g_trace_fn;
        *(uint8_t*)g_trace_fn = 0xcc;
        atexit(dump_at_exit);
    }
    mprotect((void*)ZLO, ZHI - ZLO, PROT_NONE);
    sigaction(SIGSEGV, &sa, NULL);
    sigaction(SIGTRAP, &sa, NULL);
    uint64_t stk5[1] = {getenv("SLOT_STK5") ? strtoull(getenv("SLOT_STK5"), NULL, 16) : 0};
    if (getenv("SLOT_STK5")) ott_call(fn, gpr, xmm, stk5, 1, out);
    else ott_call(fn, gpr, xmm, NULL, 0, out);
    mprotect((void*)ZLO, ZHI - ZLO, PROT_READ | PROT_WRITE);
    for (int i = 0; i < g_nacc; i++)
        printf("ACC %llx %llx %llu\n", (unsigned long long)g_acc_addr[i], (unsigned long long)g_acc_rip[i], (unsigned long long)g_acc_cnt[i]);
    if (g_stubbed) printf("STUB %d\n", g_stubbed);
    printf("DONE %llx\n", (unsigned long long)fn);
    return 0;
}
