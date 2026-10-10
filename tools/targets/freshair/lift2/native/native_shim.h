/* native_shim.h — native 参照側: lift 対象が使う IAT スロットを C 実装 (shim/fa_win_shim.h と同一本体) に差替える。
 * iat_slots.txt (mlift report 由来): 各行 "<slotVA hex> <dll!name>"。未知の import は int3 に差替え (使われたら ERR)。 */
#include "../shim/fa_win_shim.h"
#define X(name, body) static u64 __attribute__((ms_abi)) nat_##name(u64 a, u64 b, u64 c, u64 d) { return body(a, b, c, d); }
FA_SHIM_TABLE(X)
#undef X
static void patch_iat(const char* path) {
    FILE* fp = fopen(path, "r"); if (!fp) { perror("iat_slots"); exit(2); }
    char line[256];
    while (fgets(line, sizeof line, fp)) {
        unsigned long long va; char nm[200]; if (sscanf(line, "%llx %199s", &va, nm) != 2) continue;
        const char* bang = strchr(nm, '!'); const char* fn = bang ? bang + 1 : nm; u64 ptr = 0;
#define X(name, body) if (!strcmp(fn, #name)) ptr = (u64)(uintptr_t)&nat_##name;
        FA_SHIM_TABLE(X)
#undef X
        if (!ptr) { static uint8_t trapcode[16] = {0xCC}; ptr = (u64)(uintptr_t)trapcode; }
        *(u64*)va = ptr;
    }
    fclose(fp);
}

static void patch_pokes(const char* path) {   /* pokes.txt: "<VA hex> <size> <value hex>" ('#' 行は無視) */
    FILE* fp = fopen(path, "r"); if (!fp) return;
    char line[256];
    while (fgets(line, sizeof line, fp)) {
        unsigned long long va, val; int sz; if (line[0] == '#' || sscanf(line, "%llx %d %llx", &va, &sz, &val) != 3) continue;
        memcpy((void*)va, &val, sz);
    }
    fclose(fp);
}

/* ---- ABI 検査: callee-saved (rbx,rbp,rsi,rdi,r12-r15, xmm6-15) の保存確認 (MS x64 ABI) ---- */
static int abi_viol;

/* ABI 検査: capture → (ms_abi 間接 call) → compare を 1 つの asm ブロックで完結させる
 * (compiler の割込み・red zone・libc 呼出の影響を排除)。検査対象 = 両 ABI で callee-saved な
 * rbx, rbp, rsi, rdi, r12-r15。ホストが Linux (SysV) のため xmm6-15 は周囲 C が自由に壊す → 対象外。
 * 戻り値 = 違反レジスタ数。FA_ABI_DBG=1 で各違反の前後値を stderr へ。 */
static volatile unsigned long long abi_gpr[8];
static volatile unsigned long long abi_gpr2[8];
static __attribute__((noinline)) int abi_call_and_check(void* fn, void* a, void* b) {
    int viol = 0;
    __asm__ volatile(
        "leaq abi_gpr(%%rip), %%r10;"
        "movq %%rbx,0(%%r10); movq %%rbp,8(%%r10); movq %%rsi,16(%%r10); movq %%rdi,24(%%r10);"
        "movq %%r12,32(%%r10); movq %%r13,40(%%r10); movq %%r14,48(%%r10); movq %%r15,56(%%r10);"
        "movq %%rsp, %%r11; subq $0x200, %%rsp; andq $-16, %%rsp;"
        "movq %2, %%rcx; movq %3, %%rdx; movq %%rcx, 0(%%rsp); movq %%rdx, 8(%%rsp); movq %%r9, 16(%%rsp); movq %%r9, 24(%%rsp);"
        "call *%q1;"
        "movq %%r11, %%rsp;"
        "leaq abi_gpr2(%%rip), %%r10;"
        "movq %%rbx,0(%%r10); movq %%rbp,8(%%r10); movq %%rsi,16(%%r10); movq %%rdi,24(%%r10);"
        "movq %%r12,32(%%r10); movq %%r13,40(%%r10); movq %%r14,48(%%r10); movq %%r15,56(%%r10);"
        "xorl %%eax, %%eax; movl $8, %%ecx; leaq abi_gpr(%%rip), %%rdx; leaq abi_gpr2(%%rip), %%r8;"
        "1: movq (%%rdx), %%r9; cmpq (%%r8), %%r9; je 2f; incl %%eax;"
        "2: addq $8, %%rdx; addq $8, %%r8; decl %%ecx; jnz 1b;"
        : "=r"(viol)
        : "r"(fn), "r"(a), "r"(b)
        : "rax", "rcx", "rdx", "r8", "r9", "r10", "r11", "memory", "cc");
    if (viol && getenv("FA_ABI_DBG")) {
        static const char* gn[8] = {"rbx","rbp","rsi","rdi","r12","r13","r14","r15"};
        for (int i = 0; i < 8; i++) if (abi_gpr[i] != abi_gpr2[i]) fprintf(stderr, "ABI %s: before=%llx after=%llx\n", gn[i], (unsigned long long)abi_gpr[i], (unsigned long long)abi_gpr2[i]);
    }
    return viol;
}

static float __attribute__((ms_abi)) host_get_stub(void* self) { float f; memcpy(&f, (char*)self + 8, 4); return f; }

/* ---- メモリ閉込 (canary): 領域前後 64B を 0xA5 で埋め, 呼出後に検査 ---- */
#define GRD 256
static unsigned char* gr_alloc(size_t n) {
    unsigned char* p = (unsigned char*)calloc(1, n + 2 * GRD);
    memset(p, 0xA5, GRD);
    memset(p + GRD + n, 0xA5, GRD);
    return p + GRD;
}
static int gr_check(unsigned char* p, size_t n) {
    int v = 0;
    unsigned char* b = p - GRD;
    for (int i = 0; i < GRD; i++) if (b[i] != 0xA5) v++;
    unsigned char* a = p + n;
    for (int i = 0; i < GRD; i++) if (a[i] != 0xA5) v++;
    return v;
}
static size_t gr_size(size_t n) { return n; }
