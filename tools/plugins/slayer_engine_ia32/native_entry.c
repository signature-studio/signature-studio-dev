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
void entry_main(u32 *sp) {
    int argc = (int)sp[0];
    const char **argv = (const char **)(sp + 1);
    if (argc < 4) { sc3(1, 2, 0, 0); }
    long n;
    if (sys_mmap_fixed(IMG_BASE, IMG_SIZE) != (long)IMG_BASE) { sc3(1, 3, 0, 0); }
    long img = rd_all(argv[1], (char *)IMG_BASE, IMG_SIZE);
    if (img <= 0) { sc3(1, 4, 0, 0); }
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
        u32 r = call_guest(f[0], f[1], a);
        ohex(line, 4); oput(" va=", 4); ohex(f[0], 8); oput(" eax=", 5); ohex(r, 8); oput(" mem=", 5);
        for (int b = 0; b < (int)OBJ_LEN; b++) ohex(((unsigned char *)OBJ_ADDR)[b], 2);
        obuf[ofs++] = '\n';
        line++;
    }
    sc3(4, fd_out, (long)obuf, ofs);
    sc3(6, fd_out, 0, 0);
    sc3(1, 0, 0, 0);
}
__asm__(".globl _start\n_start:\n movl %esp, %eax\n pushl %eax\n call entry_main\n");
