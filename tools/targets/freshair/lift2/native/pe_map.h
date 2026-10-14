/* pe_map.h — PE32+ を ImageBase に MAP_FIXED 敷設 (m5 native_fx / lift/native_gain.c 方式)。
 * 実機 x86-64 機械語をそのまま実行する参照側ヘルパ。lift 側 (mlift/wasm) と独立。 */
#ifndef PE_MAP_H
#define PE_MAP_H
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <setjmp.h>
#define _GNU_SOURCE
#include <signal.h>
#include <ucontext.h>

static uint8_t* pe_map(const char* path) {
    int fd = open(path, O_RDONLY); if (fd < 0) { perror("open"); exit(2); }
    off_t sz = lseek(fd, 0, SEEK_END);
    uint8_t* f = mmap(NULL, sz, PROT_READ, MAP_PRIVATE, fd, 0);
    uint32_t pe; memcpy(&pe, f + 0x3c, 4);
    uint16_t ns, osz; memcpy(&ns, f + pe + 6, 2); memcpy(&osz, f + pe + 20, 2);
    uint64_t base; memcpy(&base, f + pe + 24 + 24, 8);
    uint32_t img; memcpy(&img, f + pe + 24 + 56, 4);
    uint8_t* m = mmap((void*)base, (img + 4095) & ~4095UL, PROT_READ | PROT_WRITE | PROT_EXEC,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (m != (void*)base) { fprintf(stderr, "map fail %p\n", m); exit(3); }
    uint32_t hdr; memcpy(&hdr, f + pe + 24 + 60, 4);
    memcpy(m, f, hdr);
    for (int i = 0; i < ns; i++) {
        uint8_t* s = f + pe + 24 + osz + i * 40;
        uint32_t vs, va, rs, rp; memcpy(&vs, s + 8, 4); memcpy(&va, s + 12, 4); memcpy(&rs, s + 16, 4); memcpy(&rp, s + 20, 4);
        memcpy(m + va, f + rp, rs < vs ? rs : vs);
    }
    return m;
}
static void hexdump(const void* p, size_t n) { const uint8_t* b = p; for (size_t i = 0; i < n; i++) printf("%02x", b[i]); }

/* 捕捉用: 機械語の error/未解決 call を int3 に置換し SIGTRAP/SIGSEGV を siglongjmp で受ける */
static sigjmp_buf g_jb; static volatile int g_in_guard;
static unsigned long long g_fault_rip, g_fault_addr; static int g_fault_sig; static unsigned long long g_fault_ret; static float g_x0, g_x1; static unsigned long long g_rcx, g_rdx, g_r8;
static void on_sig(int s, siginfo_t* si, void* uc) {
    ucontext_t* u = uc; g_fault_rip = u->uc_mcontext.gregs[REG_RIP]; g_fault_addr = (unsigned long long)si->si_addr; g_fault_sig = s; g_fault_ret = *(unsigned long long*)u->uc_mcontext.gregs[REG_RSP]; { float xf[4]; memcpy(xf, &u->uc_mcontext.fpregs->_xmm[0], 16); g_x0 = xf[0]; memcpy(xf, &u->uc_mcontext.fpregs->_xmm[1], 16); g_x1 = xf[0]; } g_rcx = u->uc_mcontext.gregs[REG_RCX]; g_rdx = u->uc_mcontext.gregs[REG_RDX]; g_r8 = u->uc_mcontext.gregs[REG_R8]; if (getenv("FA_REGS")) fprintf(stderr, "REGS rax=%llx rcx=%llx rdx=%llx r8=%llx rsi=%llx rdi=%llx\n", (unsigned long long)u->uc_mcontext.gregs[REG_RAX], (unsigned long long)u->uc_mcontext.gregs[REG_RCX], (unsigned long long)u->uc_mcontext.gregs[REG_RDX], (unsigned long long)u->uc_mcontext.gregs[REG_R8], (unsigned long long)u->uc_mcontext.gregs[REG_RSI], (unsigned long long)u->uc_mcontext.gregs[REG_RDI]);
    if (getenv("FA_BT")) { /* スタック上の text 戻りアドレスを最大 12 個表示 (簡易 backtrace) */
        unsigned long long* sp = (unsigned long long*)u->uc_mcontext.gregs[REG_RSP];
        int found = 0;
        fprintf(stderr, "BT rip=%llx addr=%llx rax=%llx rbx=%llx rcx=%llx rdx=%llx rsi=%llx rdi=%llx rbp=%llx rsp=%llx r8=%llx r9=%llx\n",
            g_fault_rip, g_fault_addr, (unsigned long long)u->uc_mcontext.gregs[REG_RAX], (unsigned long long)u->uc_mcontext.gregs[REG_RBX],
            g_rcx, g_rdx, (unsigned long long)u->uc_mcontext.gregs[REG_RSI], (unsigned long long)u->uc_mcontext.gregs[REG_RDI],
            (unsigned long long)u->uc_mcontext.gregs[REG_RBP], (unsigned long long)u->uc_mcontext.gregs[REG_RSP],
            g_r8, (unsigned long long)u->uc_mcontext.gregs[REG_R9]);
        { unsigned long long rdi = u->uc_mcontext.gregs[REG_RDI]; if (rdi > 0x1000 && rdi < 0x7fffffffffffULL) { unsigned long long* q = (unsigned long long*)rdi; fprintf(stderr, "  [rdi+0]=%llx [rdi+8]=%llx [rdi+0x10]=%llx [rdi+0x90]=%llx\n", q[0], q[1], q[2], q[0x12]); } }
        for (int k = 0; k < 24; k++) fprintf(stderr, "  rsp[%d]=%llx\n", k, sp[k]);
        for (int k = 0; k < 4096 && found < 12; k++) {
            unsigned long long v = sp[k];
            if (v >= 0x180000001ULL && v < 0x181300000ULL) { fprintf(stderr, "  [%d] ret=%llx\n", k, v); found++; }
        }
    }
    if (getenv("FA_OUT0") && g_fault_rip == 0x180c9d741ULL) { /* FA-25: probe 無しで setter の [rsp+0x48] (= out[0]) を実読 */
        unsigned long long o0 = *(unsigned long long*)(u->uc_mcontext.gregs[REG_RSP] + 0x48);
        fprintf(stderr, "OUT0 rip=%llx out0=%llx\n", g_fault_rip, o0); }
    if (g_in_guard) siglongjmp(g_jb, s); _exit(99); }
static void guard_install(void) {
    struct sigaction sa; memset(&sa, 0, sizeof sa); sa.sa_sigaction = on_sig; sa.sa_flags = SA_NODEFER | SA_SIGINFO;
    sigaction(SIGTRAP, &sa, 0); sigaction(SIGSEGV, &sa, 0); sigaction(SIGILL, &sa, 0); sigaction(SIGFPE, &sa, 0); sigaction(SIGBUS, &sa, 0);
}
#endif
