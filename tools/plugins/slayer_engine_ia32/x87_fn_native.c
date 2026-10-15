/* x87_fn_native.c: x87 を含む Slayer_Engine.dll (block22434) の関数の参照ランナー (#2989)。
 * native_entry.c と同じ方式 (freestanding i386 ELF・int 0x80 のみ) だが、x87 を含む関数のために
 *  - 引数は 6 本 (スタック渡しの float 引数を含む)、 OBJ 窓は OBJ_WIN バイト (既定 0x540)、
 *  - 呼出し前に fninit、呼出し後に ST(0) を float32 として読み (fsts)・x87 の深さを FSW.TOP から求める。
 *  - #4924: ecx = WIDE_BASE の行は、image 内の広い範囲 (WIDE_BASE から WIDE_LEN) の書込みを数える (非自明性)。
 *    行の前に範囲を image の初期状態へ戻し、呼出し後の変化をハッシュにして出力する (wasm 側 x87_fn_entry_wasm.mjs と同じ式)。
 * 使い方: x87_fn_native <image.bin> <scen.txt> <out.txt>
 * 出力 1 行: 行番号 va eax st0(float32 bits) d(x87 深さ) mem(OBJ 窓の hex) stk(hex) wide(変化語数:ハッシュ / ecx が WIDE_BASE 以外は -)。 */
typedef unsigned int u32;
#define IMG_BASE 0x10000000u
#define IMG_SIZE 0x01000000u
#define OBJ_ADDR 0x10F80000u
#ifndef OBJ_WIN
#define OBJ_WIN 0x540u
#endif
#define GUEST_STACK_TOP 0x10F00000u
#define STK_LO (GUEST_STACK_TOP - 0x1100u)
#define STK_WIN 0x1E0u
#define IBUF_SZ (1u << 26)
#define OBUF_SZ (1u << 26)
/* #4924: 広い範囲 (image 内)。 呼出し規約のスタック (0x10EFE000..0x10F00100) は数えない (戻り番地・引数の位置は native と wasm で値が違うため)。 */
#define WIDE_BASE 0x10700000u
#define WIDE_LEN 0x900000u
#define WIDE_SKIP_LO 0x7FE000u
#define WIDE_SKIP_HI 0x800100u
/* 行ごとの復元用の写し (image の外・0x11000000 以降に mmap する。 bss は image と重なるため使わない) */
#define WIDE_SAVE 0x11000000u

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
    " mov $0x10F00000,%esp\n"
    " pushl 20(%esi)\n pushl 16(%esi)\n pushl 12(%esi)\n pushl 8(%esi)\n pushl 4(%esi)\n pushl (%esi)\n"
    " mov %edx,%ecx\n xor %eax,%eax\n xor %edx,%edx\n mov $0x10F00000-0x1000,%ebp\n"
    " call *%edi\n"
    " movl g_sp,%esp\n"
    " pop %edi\n pop %esi\n pop %ebx\n pop %ebp\n ret\n");
static char ibuf[IBUF_SZ];
static char obuf[OBUF_SZ];
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
static void wcopy(volatile u32 *dst, const volatile u32 *src) {
    for (u32 i = 0; i < WIDE_LEN / 4; i++) dst[i] = src[i];
}
static u32 wdiff(const volatile u32 *pre, const volatile u32 *post, u32 *cnt) {
    u32 h = 0x811c9dc5u, c = 0;
    for (u32 i = 0; i < WIDE_LEN / 4; i++) {
        u32 o = i * 4;
        if (o >= WIDE_SKIP_LO && o < WIDE_SKIP_HI) continue;
        if (pre[i] != post[i]) {
            h = (h ^ o) * 0x01000193u;
            h = (h ^ post[i]) * 0x01000193u;
            c++;
        }
    }
    *cnt = c;
    return h;
}
void entry_main(u32 *sp) {
    int argc = (int)sp[0];
    const char **argv = (const char **)(sp + 1);
    if (argc < 4) { sc3(1, 2, 0, 0); }
    long n;
    if (sys_mmap_fixed(IMG_BASE, IMG_SIZE) != (long)IMG_BASE) { sc3(1, 3, 0, 0); }
    long img = rd_all(argv[1], (char *)IMG_BASE, IMG_SIZE);
    if (img <= 0) { sc3(1, 4, 0, 0); }
    if (sys_mmap_fixed(WIDE_SAVE, 2 * WIDE_LEN) != (long)WIDE_SAVE) { sc3(1, 9, 0, 0); }
    wcopy((volatile u32 *)WIDE_SAVE, (volatile u32 *)WIDE_BASE);
    n = rd_all(argv[2], ibuf, sizeof ibuf);
    if (n <= 0 || n >= (long)sizeof ibuf) { sc3(1, 5, 0, 0); }
    long fd_out = sc3(5, (long)argv[3], 0x241, 0644);
    if (fd_out < 0) { sc3(1, 6, 0, 0); }
    int i = 0, line = 0;
    while (i < n) {
        int s = i;
        while (i < n && ibuf[i] != '\n') i++;
        int e = i; i++;
        if (e == s) continue;
        if (e - s < 10) { sc3(1, 7, 0, 0); }
        if (ofs > (int)OBUF_SZ - 8192) { sc3(4, fd_out, (long)obuf, ofs); ofs = 0; }
        /* 行: va ecx a0 a1 a2 a3 a4 a5 init(hex, OBJ_WIN バイト) */
        u32 f[8]; int k = 0, p = s;
        while (k < 8) {
            while (ibuf[p] == ' ') p++;
            int q = p;
            while (ibuf[q] != ' ') q++;
            f[k++] = hexval(ibuf + p, q - p);
            p = q;
        }
        while (ibuf[p] == ' ') p++;
        /* #4147: 窓は行の ecx (f[1]) に置く。 ecx 相対の読みが大きい関数は ecx を image 内の番地にずらす */
        u32 win = f[1];
        int wide = win == WIDE_BASE;
        if (wide) wcopy((volatile u32 *)WIDE_BASE, (volatile u32 *)WIDE_SAVE);
        for (int b = 0; b < (int)OBJ_WIN; b++) {
            ((unsigned char *)win)[b] = (unsigned char)hexval(ibuf + p + 2 * b, 2);
        }
        u32 a[6] = {f[2], f[3], f[4], f[5], f[6], f[7]};
        for (u32 b = 0; b < STK_WIN; b++) ((volatile unsigned char *)STK_LO)[b] = 0;
        if (wide) wcopy((volatile u32 *)(WIDE_SAVE + WIDE_LEN), (volatile u32 *)WIDE_BASE);
        __asm__ volatile("fninit" ::: "memory");
#ifdef X87_PUSH64
        {
            /* #4840: 呼出し前に double (a[0] = 下位 dword・a[1] = 上位 dword) を ST(0) に積む */
            volatile u32 dw[2] = {a[0], a[1]};
            __asm__ volatile("fldl %0" :: "m"(*(volatile double *)dw) : "memory");
        }
#endif
        u32 r = call_guest(f[0], f[1], a);
        u32 wc = 0, wh = 0;
        if (wide) wh = wdiff((volatile u32 *)(WIDE_SAVE + WIDE_LEN), (volatile u32 *)WIDE_BASE, &wc);
        unsigned short sw;
        __asm__ volatile("fnstsw %0" : "=m"(sw) :: "memory");
        u32 depth = (8u - (((u32)sw >> 11) & 7u)) & 7u;
        float st0 = 0.0f;
        double st0d = 0.0;
        if (depth) {
            __asm__ volatile("fsts %0" : "=m"(st0) :: "memory");
            __asm__ volatile("fstl %0" : "=m"(st0d) :: "memory");
        }
        __asm__ volatile("fninit" ::: "memory");
        union { float f; u32 u; } st0u;
        union { double d; unsigned long long u; } st0du;
        st0u.f = st0;
        st0du.d = st0d;
        ohex(line, 4); oput(" va=", 4); ohex(f[0], 8); oput(" eax=", 5); ohex(r, 8);
        oput(" st0=", 5); ohex(st0u.u, 8); oput(" st0d=", 6);
        ohex((u32)(st0du.u >> 32), 8); ohex((u32)st0du.u, 8);
        oput(" d=", 3); ohex(depth, 1); oput(" mem=", 5);
        for (int b = 0; b < (int)OBJ_WIN; b++) ohex(((unsigned char *)win)[b], 2);
        oput(" stk=", 5);
        for (u32 b = 0; b < STK_WIN; b++) ohex(((unsigned char *)STK_LO)[b], 2);
        oput(" wide=", 6);
        if (wide) { ohex(wc, 4); oput(":", 1); ohex(wh, 8); } else oput("-", 1);
        obuf[ofs++] = '\n';
        line++;
    }
    long off = 0;
    while (off < ofs) {
        long w = sc3(4, fd_out, (long)(obuf + off), ofs - off);
        if (w <= 0) { sc3(1, 8, 0, 0); }
        off += w;
    }
    sc3(6, fd_out, 0, 0);
    sc3(1, 0, 0, 0);
}
__asm__(".globl _start\n_start:\n movl %esp, %eax\n pushl %eax\n call entry_main\n");
