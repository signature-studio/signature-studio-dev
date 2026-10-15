/* native_entry.c: Slayer_Engine.dll (block22434) の関数を実 ia32 機械語のまま実行する参照ランナー (#1223)。
 * 32bit libc が無い runner 向けに freestanding + int 0x80 (Linux i386 syscall) だけで作る。
 * 使い方: native_entry <image.bin> <scen.txt> <out.txt>
 * image.bin を VA 0x10000000 に敷設し、scen.txt の各行を cdecl/thiscall で呼ぶ (呼出し後の eax と OBJ 領域を出力)。 */
typedef unsigned int u32;
#define IMG_BASE 0x10000000u
#define IMG_SIZE 0x01000000u
#define OBJ_ADDR 0x10F80000u
#define OBJ_LEN 0x80u

static long sc3(long n, long a, long b, long c) {
    long r;
    __asm__ volatile("int $0x80" : "=a"(r) : "a"(n), "b"(a), "c"(b), "d"(c) : "memory");
    return r;
}
static long sys_mmap_fixed(u32 addr, u32 len) {
    u32 args[6] = {addr, len, 7u, 0x32u, (u32)-1, 0u};
    u32 *ap = args;
    long r;
    __asm__ volatile(
        "push %%ebx\n push %%ebp\n"
        "mov 0(%%esi),%%ebx\n mov 4(%%esi),%%ecx\n mov 8(%%esi),%%edx\n"
        "mov 16(%%esi),%%edi\n mov 20(%%esi),%%ebp\n mov 12(%%esi),%%esi\n"
        "mov $192,%%eax\n int $0x80\n"
        "pop %%ebp\n pop %%ebx\n"
        : "=a"(r), "+S"(ap)
        :
        : "ecx", "edx", "edi", "memory", "cc");
    return r;
}
u32 g_sp;
u32 call_guest(u32 fn, u32 thisp, const u32 *a);
__asm__(
    ".globl call_guest\n"
    "call_guest:\n"
    " push %ebp\n mov %esp,%ebp\n push %ebx\n push %esi\n push %edi\n"
    " mov 8(%ebp),%edi\n mov 12(%ebp),%edx\n mov 16(%ebp),%esi\n"
    " movl %esp,g_sp\n"
    " pushl 12(%esi)\n pushl 8(%esi)\n pushl 4(%esi)\n pushl (%esi)\n"
    " mov %edx,%ecx\n xor %eax,%eax\n xor %edx,%edx\n"
    " call *%edi\n"
    " movl g_sp,%esp\n"
    " pop %edi\n pop %esi\n pop %ebx\n pop %ebp\n ret\n");
static char ibuf[1 << 20];
static char obuf[1 << 22];
static int ofs;
static void oput(const char *s, int n) { for (int i = 0; i < n; i++) obuf[ofs++] = s[i]; }
static void ohex(u32 v, int digits) {
    static const char h[] = "0123456789abcdef";
    for (int i = digits - 1; i >= 0; i--) obuf[ofs++] = h[(v >> (4 * i)) & 15];
}
static u32 hexval(const char *p, int n) {
    u32 v = 0;
    for (int i = 0; i < n; i++) {
        char c = p[i];
        v = v * 16 + (u32)(c <= '9' ? c - '0' : (c | 32) - 'a' + 10);
    }
    return v;
}
static long rd_all(const char *path, char *buf, long cap) {
    long fd = sc3(5, (long)path, 0, 0);
    if (fd < 0) return -1;
    long n = 0, k;
    while ((k = sc3(3, fd, (long)(buf + n), cap - n)) > 0) n += k;
    sc3(6, fd, 0, 0);
    return n;
}
/* KERNEL32 import の ia32 モデル。 rt32_glue.c と同じ規約・同じ値 (stdcall: callee が引数を pop、 void 相当は eax=0)。 */
#define STD __attribute__((stdcall))
#define H32_BASE 0x10800000u
#define HOST_BASE 0x00828000u
#define HOST_LEN 0x10000u
static u32 g_top, g_lasterr, g_tls[64];
static void zero(u32 p, u32 n) { volatile unsigned char *q = (unsigned char *)p; for (u32 i = 0; i < n; i++) q[i] = 0; }
static void copy(u32 d, u32 s, u32 n) {
    volatile unsigned char *q = (unsigned char *)d;
    const volatile unsigned char *r = (const unsigned char *)s;
    for (u32 i = 0; i < n; i++) q[i] = r[i];
}
static void h32_reset(void) {
    g_top = H32_BASE; g_lasterr = 0;
    for (u32 i = 0; i < 64; i++) g_tls[i] = 0;
    zero(HOST_BASE, HOST_LEN);
}
static u32 h32_alloc(u32 sz) {
    u32 p = (g_top + 8 + 7) & ~7u;
    g_top = p + (((sz ? sz : 1) + 7) & ~7u);
    *(u32 *)(p - 8) = sz;
    zero(p, sz);
    return p;
}
static u32 h32_realloc(u32 p, u32 sz) {
    if (!p) return h32_alloc(sz);
    u32 old = *(u32 *)(p - 8), n = h32_alloc(sz);
    copy(n, p, old < sz ? old : sz);
    return n;
}
static u32 h32_valloc(u32 sz) {
    g_top = (g_top + 4095) & ~4095u;
    u32 p = g_top;
    g_top += (sz + 4095) & ~4095u;
    zero(p, sz);
    return p;
}
static STD u32 n_EnterCriticalSection(u32 a) { return 0; }
static STD u32 n_LeaveCriticalSection(u32 a) { return 0; }
static STD u32 n_InitializeCriticalSection(u32 a) { return 0; }
static STD u32 n_GetCurrentThreadId(void) { return 0x1000; }
static STD u32 n_GetLastError(void) { return g_lasterr; }
static STD u32 n_SetLastError(u32 e) { g_lasterr = e; return 0; }
static STD u32 n_TlsGetValue(u32 i) { return g_tls[i & 63]; }
static STD u32 n_TlsSetValue(u32 i, u32 v) { g_tls[i & 63] = v; return 1; }
static STD u32 n_GetModuleFileNameA(u32 h, u32 b, u32 n) { return 0; }
static STD u32 n_GetStdHandle(u32 n) { return 0x00020000u | (n & 0xffff); }
static STD u32 n_HeapAlloc(u32 h, u32 f, u32 sz) { return h32_alloc(sz); }
static STD u32 n_HeapFree(u32 h, u32 f, u32 p) { return 1; }
static STD u32 n_HeapReAlloc(u32 h, u32 f, u32 p, u32 sz) { return h32_realloc(p, sz); }
static STD u32 n_LoadLibraryA(u32 name) { return 0; }
static STD u32 n_WriteFile(u32 h, u32 buf, u32 n, u32 written, u32 ov) {
    if (written) *(u32 *)written = n;
    return 1;
}
static STD u32 n_VirtualAlloc(u32 a, u32 sz, u32 t, u32 p) { return h32_valloc(sz); }
static STD u32 n_VirtualFree(u32 a, u32 sz, u32 t) { return 1; }
static STD u32 n_missing(void) { sc3(1, 9, 0, 0); return 0; }
static const struct { const char *nm; void *fn; } g_imp[] = {
    {"EnterCriticalSection", (void *)n_EnterCriticalSection},
    {"LeaveCriticalSection", (void *)n_LeaveCriticalSection},
    {"InitializeCriticalSection", (void *)n_InitializeCriticalSection},
    {"GetCurrentThreadId", (void *)n_GetCurrentThreadId},
    {"GetLastError", (void *)n_GetLastError},
    {"SetLastError", (void *)n_SetLastError},
    {"TlsGetValue", (void *)n_TlsGetValue},
    {"TlsSetValue", (void *)n_TlsSetValue},
    {"GetModuleFileNameA", (void *)n_GetModuleFileNameA},
    {"GetStdHandle", (void *)n_GetStdHandle},
    {"HeapAlloc", (void *)n_HeapAlloc},
    {"HeapFree", (void *)n_HeapFree},
    {"HeapReAlloc", (void *)n_HeapReAlloc},
    {"LoadLibraryA", (void *)n_LoadLibraryA},
    {"WriteFile", (void *)n_WriteFile},
    {"VirtualAlloc", (void *)n_VirtualAlloc},
    {"VirtualFree", (void *)n_VirtualFree},
};
static u32 str_eq(const char *a, const char *b) {
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}
static u32 imp_addr(const char *nm) {
    for (u32 i = 0; i < sizeof g_imp / sizeof g_imp[0]; i++)
        if (str_eq(nm, g_imp[i].nm)) return (u32)g_imp[i].fn;
    return (u32)n_missing;
}
/* PE の import directory を読み、 IAT の各 slot を上の表の stub で置き換える (未実装は n_missing = fail-fast) */
static void patch_iat(void) {
    u32 opt = IMG_BASE + *(u32 *)(IMG_BASE + 0x3c) + 24;
    u32 d = IMG_BASE + *(u32 *)(opt + 96 + 8);
    for (;; d += 20) {
        u32 oft = *(u32 *)d, nm = *(u32 *)(d + 12), ft = *(u32 *)(d + 16);
        if (!oft && !nm && !ft) break;
        u32 lt = oft ? oft : ft;
        for (u32 k = 0; *(u32 *)(IMG_BASE + lt + 4 * k); k++) {
            u32 ent = *(u32 *)(IMG_BASE + lt + 4 * k);
            *(u32 *)(IMG_BASE + ft + 4 * k) = (ent & 0x80000000u) ? (u32)n_missing : imp_addr((const char *)(IMG_BASE + ent + 2));
        }
    }
}

void entry_main(u32 *sp) {
    int argc = (int)sp[0];
    const char **argv = (const char **)(sp + 1);
    if (argc < 4) { sc3(1, 2, 0, 0); }
    long n;
    if (sys_mmap_fixed(IMG_BASE, IMG_SIZE) != (long)IMG_BASE) { sc3(1, 3, 0, 0); }
    long img = rd_all(argv[1], (char *)IMG_BASE, IMG_SIZE);
    if (img <= 0) { sc3(1, 4, 0, 0); }
    if (sys_mmap_fixed(HOST_BASE, HOST_LEN) != (long)HOST_BASE) { sc3(1, 7, 0, 0); }
    patch_iat();
    n = rd_all(argv[2], ibuf, sizeof ibuf);
    if (n <= 0) { sc3(1, 5, 0, 0); }
    long fd_out = sc3(5, (long)argv[3], 0x241, 0644);
    if (fd_out < 0) { sc3(1, 6, 0, 0); }
    int i = 0, line = 0;
    while (i < n) {
        int s = i;
        while (i < n && ibuf[i] != '\n') i++;
        int e = i; i++;
        if (e - s < 10) continue;
        /* 行: va ecx a0 a1 a2 a3 init(hex) */
        u32 f[6]; int k = 0, p = s;
        while (k < 6) {
            while (ibuf[p] == ' ') p++;
            int q = p;
            while (ibuf[q] != ' ') q++;
            f[k++] = hexval(ibuf + p, q - p);
            p = q;
        }
        while (ibuf[p] == ' ') p++;
        for (int b = 0; b < (int)OBJ_LEN; b++) {
            ((unsigned char *)OBJ_ADDR)[b] = (unsigned char)hexval(ibuf + p + 2 * b, 2);
        }
        u32 a[4] = {f[2], f[3], f[4], f[5]};
        h32_reset();
        u32 r = call_guest(f[0], f[1], a);
        ohex(line, 4); oput(" va=", 4); ohex(f[0], 8); oput(" eax=", 5); ohex(r, 8); oput(" mem=", 5);
        for (int b = 0; b < (int)OBJ_LEN; b++) ohex(((unsigned char *)OBJ_ADDR)[b], 2);
        oput(" heap=", 6);
        for (int b = 0; b < 64; b++) ohex(((unsigned char *)H32_BASE)[b], 2);
        obuf[ofs++] = '\n';
        line++;
    }
    sc3(4, fd_out, (long)obuf, ofs);
    sc3(6, fd_out, 0, 0);
    sc3(1, 0, 0, 0);
}
__asm__(".globl _start\n_start:\n movl %esp, %eax\n pushl %eax\n call entry_main\n");
