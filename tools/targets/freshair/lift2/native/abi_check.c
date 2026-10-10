/* abi_check.c — MS x64 ABI 遵守の単発検査 (CAB-48 FA-2)。
 *   ./abi_check <core> <target:comp|filter>
 * 本番 harness (native_*.c) と同じ初期化 (PE 敷設 + IAT 差替 + pokes + fma flag) で 1 シナリオを構成し,
 * rbx/rbp/rsi/rdi/r12-r15 (両 ABI で callee-saved) が process 呼出の前後で保存されることを
 * 1 つの asm ブロック内で capture → call → compare して検査する。
 * 注: ホストは Linux (SysV) のため xmm6-15 は周囲 C コードが自由に壊す (SysV では volatile)。
 * xmm6-15 の保存は機械語の静的構造 (prologue の movaps 退避 / 未使用) で確認し REPORT に記録する。 */
#include "pe_map.h"
#include "native_shim.h"

static volatile unsigned long long abi_pre[8], abi_post[8];

typedef long long (__attribute__((ms_abi)) *proc_t)(void*, void*);

static int run_check(const char* core, int target) {
    uint8_t* im = pe_map(core); guard_install();
    static const unsigned long long stubs[] = {0x18103d37c, 0x18103d47c, 0x18102f728};
    for (unsigned k = 0; k < sizeof stubs / sizeof *stubs; k++) im[stubs[k] - 0x180000000ULL] = 0xCC;
    patch_iat("iat_slots.txt");
    patch_pokes("pokes.txt");
    *(volatile int*)0x1813070f8ULL = 0;
    unsigned long long proc_va = target == 0 ? 0x180775220ULL : 0x180b6f050ULL;
    size_t s_sz = target == 0 ? 0x200 : 0x1400;
    static unsigned char* S; static unsigned char* P; static unsigned char* ctx;
    static unsigned char* Q; static unsigned char* vbuf; static float* L; static float* R;
    S = gr_alloc(s_sz); P = gr_alloc(0xa400); ctx = gr_alloc(0x80);
    Q = 0; vbuf = 0;
    static uint64_t VT[32];
    if (target == 0) {
        Q = gr_alloc(0x80); vbuf = (unsigned char*)calloc(1, 64);
        VT[12] = (uint64_t)(uintptr_t)&host_get_stub;
        *(uint64_t*)(P + 0xa098) = (uint64_t)VT; *(uint64_t*)(P + 0xa128) = (uint64_t)Q;
        *(uint64_t*)(Q + 0x28) = (uint64_t)vbuf; *(uint64_t*)(Q + 0x30) = (uint64_t)vbuf; *(uint64_t*)(Q + 0x38) = (uint64_t)(vbuf + 64);
        *(int32_t*)(P + 0xa118) = -1;
    }
    *(uint64_t*)(S + 0x90) = (uint64_t)P;
    /* 入力: comp = n=8 の簡単なトーン, filter = type0/order1 (2次 IIR) + 8 サンプル */
    L = (float*)gr_alloc(16); R = (float*)gr_alloc(16);
    for (int i = 0; i < 4; i++) { L[i] = 0.25f - 0.1f * i; R[i] = -0.5f + 0.1f * i; }
    if (target == 0) {
        *(uint32_t*)(P + 0x9dc4) = 0; *(uint32_t*)(P + 0x9e0c) = 0x3f8ccccd; *(uint32_t*)(P + 0x9e54) = 0x3f4ccccd;
        *(uint32_t*)(P + 0x9e9c) = 0x3f000000; *(uint32_t*)(P + 0x9ea8) = 0; *(uint32_t*)(P + 0x9f2c) = 0;
    } else {
        *(uint32_t*)(P + 0x9dc4) = 0; *(uint32_t*)(P + 0x9ee4) = 1;
        *(uint32_t*)(P + 0x9e0c) = 0x447a0000; *(uint32_t*)(P + 0x9e54) = 0x3f3504f3; *(uint32_t*)(P + 0x9e9c) = 0x3f000000;
    }
    *(uint32_t*)(S + 0x98) = 0x447a0000;    /* 48000 Hz */
    *(uint64_t*)(ctx + 0) = (uint64_t)L; *(uint64_t*)(ctx + 8) = (uint64_t)R; *(int32_t*)(ctx + 0x28) = 4;
    if (target == 1) ctx[0x60] = 0;
    int viol = 0;
    g_in_guard = 1;
    int s = sigsetjmp(g_jb, 1);
    if (getenv("FA_ABI_DBG")) fprintf(stderr, "abi_check: call target=%llx S=%p ctx=%p s=%d\n", (unsigned long long)proc_va, (void*)S, (void*)ctx, s);
    void* fn = (void*)proc_va;
    if (s == 0) __asm__ volatile(
        "leaq abi_pre(%%rip), %%r10;"
        "movq %%rbx,0(%%r10); movq %%rbp,8(%%r10); movq %%rsi,16(%%r10); movq %%rdi,24(%%r10);"
        "movq %%r12,32(%%r10); movq %%r13,40(%%r10); movq %%r14,48(%%r10); movq %%r15,56(%%r10);"
        "movq %%rsp, %%r11; subq $0x200, %%rsp; andq $-16, %%rsp;"
        "movq %1, %%rcx; movq %2, %%rdx; movq %%rcx, 0(%%rsp); movq %%rdx, 8(%%rsp); xorl %%r9d, %%r9d; movq %%r9, 16(%%rsp); movq %%r9, 24(%%rsp);"
        "call *%q0;"
        "movq %%r11, %%rsp;"
        "leaq abi_post(%%rip), %%r10;"
        "movq %%rbx,0(%%r10); movq %%rbp,8(%%r10); movq %%rsi,16(%%r10); movq %%rdi,24(%%r10);"
        "movq %%r12,32(%%r10); movq %%r13,40(%%r10); movq %%r14,48(%%r10); movq %%r15,56(%%r10)"
        : : "r"(fn), "r"(S), "r"(ctx)
        : "rax", "rcx", "rdx", "r8", "r9", "r10", "r11", "memory", "cc");
    g_in_guard = 0;
    static const char* gn[8] = {"rbx","rbp","rsi","rdi","r12","r13","r14","r15"};
    for (int i = 0; i < 8; i++) if (abi_pre[i] != abi_post[i]) { fprintf(stderr, "ABI %s: before=%llx after=%llx\n", gn[i], (unsigned long long)abi_pre[i], (unsigned long long)abi_post[i]); viol++; }
    fprintf(stderr, "ABI GPR check (%s process): violations=%d\n", target == 0 ? "Compressor" : "Filter", viol);
    /* 1 回限りの probe のため故意に解放しない (machine 側 HeapFree/_guard の相互作用と exit 前の後始末を避ける) */
    return viol;
}

int main(int argc, char** argv) {
    /* Compressor は本 harness の最小構成で検査可能。Filter は CRT/param 初期化が多いため
     * main harness (native_filter.c) 側の FA_ABI_CHECK=1 で検査する (abi_check では対象外)。 */
    {
        int bad = run_check(argv[1], 0);
        /* _exit: 後発 fault (machine 側遅延 SEGV) と atexit/stdio 後始末の相互作用を回避 */
        _exit(bad ? 3 : 0);
    }
}
