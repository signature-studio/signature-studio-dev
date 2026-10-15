/* x87_nan_downstream.c: NaN どうしのビット差 (符号・ペイロード) が後段の算術に出るかを見る (#5264 PLG-G2-73)。
 * native: -m32 freestanding。 四則・符号反転・絶対値・比較を x87 命令 (inline asm) で発行する。 基準は実 x87 命令。
 * wasm  : emcc。 同じ式を float 演算で行う。 どちらも各演算の結果を float32 に丸める (f80 の経由はしない)。
 * 入力: 値 12 種 (有限・±0・±inf・NaN 6 種) の全組 144 組。 各組に ((a*b)+1.5) と (1.0/(a+b)) の連鎖を加える。
 * 出力 1 行 = 1 組。 比較は ZF|PF<<1|CF<<2 (大小 a<b は 4、a==b は 1、a>b は 0、非順序は 7)。 */

#ifdef NATIVE
#define CLOB "st", "st(1)", "st(2)", "st(3)", "st(4)", "st(5)", "st(6)", "st(7)"
static void outs(const char *s, int n) {
    asm volatile("int $0x80" : : "a"(4), "b"(1), "c"(s), "d"(n) : "memory");
}
#else
#include <stdio.h>
static void outs(const char *s, int n) { fwrite(s, 1, n, stdout); }
#endif

static unsigned fbits(float f) { union { float f; unsigned u; } x; x.f = f; return x.u; }
static float fval(unsigned u) { union { float f; unsigned u; } x; x.u = u; return x.f; }

#ifdef NATIVE
/* op: 0 add, 1 sub, 2 mul, 3 div (st0 = a の後に m32 の b) */
static float op2(int op, float a, float b) {
    float r;
    switch (op) {
    case 0: asm volatile("flds %1\n\tfadds %2\n\tfstps %0" : "=m"(r) : "m"(a), "m"(b) : CLOB); break;
    case 1: asm volatile("flds %1\n\tfsubs %2\n\tfstps %0" : "=m"(r) : "m"(a), "m"(b) : CLOB); break;
    case 2: asm volatile("flds %1\n\tfmuls %2\n\tfstps %0" : "=m"(r) : "m"(a), "m"(b) : CLOB); break;
    default: asm volatile("flds %1\n\tfdivs %2\n\tfstps %0" : "=m"(r) : "m"(a), "m"(b) : CLOB); break;
    }
    return r;
}
static float neg1(float a) { float r; asm volatile("flds %1\n\tfchs\n\tfstps %0" : "=m"(r) : "m"(a) : CLOB); return r; }
static float abs1(float a) { float r; asm volatile("flds %1\n\tfabs\n\tfstps %0" : "=m"(r) : "m"(a) : CLOB); return r; }
static unsigned cmp2(float a, float b) {
    unsigned char z, p, c;
    /* b を先に積み、st0 = a・st1 = b で比較。 fucomip は st0 を 1 本降ろす。 残る b を捨てる。 */
    asm volatile("flds %4\n\tflds %3\n\tfucomip %%st(1), %%st\n\tfstp %%st(0)\n\tsete %0\n\tsetp %1\n\tsetb %2"
                 : "=q"(z), "=q"(p), "=q"(c) : "m"(a), "m"(b) : CLOB);
    return (unsigned)z | ((unsigned)p << 1) | ((unsigned)c << 2);
}
#else
static float op2(int op, float a, float b) {
    switch (op) {
    case 0: return a + b;
    case 1: return a - b;
    case 2: return a * b;
    default: return a / b;
    }
}
static float neg1(float a) { return -a; }
static float abs1(float a) { return fval(fbits(a) & 0x7fffffffu); }
static unsigned cmp2(float a, float b) {
    if (a != a || b != b) return 7;
    if (a == b) return 1;
    return a < b ? 4 : 0;
}
#endif

static const unsigned V[] = {
    0x3f800000u, 0xc0200000u, 0x00000000u, 0x80000000u, 0x7f800000u, 0xff800000u,
    0x7fc00000u, 0xffc00000u, 0x7fc00001u, 0x7f800001u, 0xff800001u, 0x7fc12345u,
};
#define NV ((int)(sizeof V / sizeof V[0]))
#define K15 0x3fc00000u
#define K10 0x3f800000u

static void hex8(char *p, unsigned u) {
    static const char h[] = "0123456789abcdef";
    for (int k = 7; k >= 0; k--) p[7 - k] = h[(u >> (4 * k)) & 15];
}

static void run(void) {
    char line[160];
    for (int i = 0; i < NV; i++) {
        for (int j = 0; j < NV; j++) {
            float a = fval(V[i]), b = fval(V[j]);
            unsigned r[7];
            r[0] = fbits(op2(0, a, b));
            r[1] = fbits(op2(1, a, b));
            r[2] = fbits(op2(2, a, b));
            r[3] = fbits(op2(3, a, b));
            r[4] = cmp2(a, b);
            r[5] = fbits(neg1(a));
            r[6] = fbits(abs1(a));
            unsigned c1 = fbits(op2(0, op2(2, a, b), fval(K15)));
            unsigned c2 = fbits(op2(3, fval(K10), op2(0, a, b)));
            int n = 0;
            line[n++] = (char)('0' + i / 10); line[n++] = (char)('0' + i % 10); line[n++] = ' ';
            line[n++] = (char)('0' + j / 10); line[n++] = (char)('0' + j % 10); line[n++] = ' ';
            const char *lab[] = {"add=", "sub=", "mul=", "div=", "cmp=", "neg=", "abs=", "c1=", "c2="};
            unsigned val[9] = {r[0], r[1], r[2], r[3], r[4], r[5], r[6], c1, c2};
            for (int k = 0; k < 9; k++) {
                for (const char *s = lab[k]; *s; s++) line[n++] = *s;
                if (k == 4) { line[n++] = (char)('0' + (val[k] % 10)); }
                else hex8(line + n, val[k]), n += 8;
                line[n++] = ' ';
            }
            line[n++] = '\n';
            outs(line, n);
        }
    }
}

#ifdef NATIVE
void _start(void) {
    run();
    asm volatile("movl $1, %%eax\n\txorl %%ebx, %%ebx\n\tint $0x80" : : : "eax", "ebx");
    for (;;) {}
}
#else
int main(void) {
    run();
    return 0;
}
#endif
