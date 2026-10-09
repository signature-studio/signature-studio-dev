/* m8_rt.c (M8): missing 11 対応の hand C stub 群 (tools/m7/missing11.md 分類準拠).
 * 新規 10 種 (#1/2/3/4/5/7/8/9/10/11; #6 = caller broken-lift OOB 待ちは対象外) を
 * m6_rt.c / m6_stubs_hand.c 規模の延長で実装。closure IR declare がすべて
 * `declare i64 @function_...(…)` 形のため C 側返り値は long long (i64) 一致。
 * 実体忠実度の出典は各 stub 上部コメントの dsm (tools/m6/work/full_t1.drc.dsm)。
 * bit-exact 検証対象: #2 (1801c0ac8) / #4 (1801c17e0) / #5 (1801c17fc) /
 * #7 (1801c33e0) — tools/m8/rt_leaf_test.mjs で JS 期待値と突合。
 * probe (trap8_test.mjs) 直呼で引数が未整備の deref は対応表の分類に従い
 * fail-fast (DSP 数値経路外のため t1 には影響しない) を保持。 */
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>

#define M8BASE 0x30000000ul
/* linear memory 許容範囲 (m8 build: GLOBAL_BASE..MAXMEM) 内の妥当な生ポインタ */
static int m8_ptr_ok(unsigned long long a) {
    return a >= M8BASE && a < 0x36000000ull;
}
static void m8_fail(const char* nm) {
    fprintf(stderr, "[m8_rt] fail-fast: %s\n", nm);
    abort();
}

/* ---------- #1 function_1801bfab4(i64) — Win API (GetModuleHandleW) 参照値 stub
 * dsm: xor r8d,r8d; lea edx,[r8+2]; jmp 1801bf938 (UCRT app-policy 判定で
 * GetModuleHandleW + PE header parse 参照; wasm 単体では義理 shim 不可)。
 * 分類: Win API 参照値 0 返し stub (managed app 判定 false 相当)。
 * DSP 数値経路外。 */
long long function_1801bfab4(long long a) { (void)a; return 0; }

/* ---------- #2 function_1801c0ac8(i64 rcx=pa, ptr rdx=pb, i64 r8=n) — 純計算 leaf
 * (bit-exact 可能)。実体: wmemcmp/wcsncmp 相当 word 比較:
 *   test r8,r8;/jne → n==0 で 0;
 *   loop: movzx eax,u16[rcx]; test ax; je→end; cmp ax,u16[rdx]; jne→end;
 *         rcx+=2; rdx+=2; r8-=1; jne loop
 *   end: movzx eax,u16[rcx]; movzx ecx,u16[rdx]; sub eax,ecx; ret (i32 減算)。
 * NULL/garbage 引数は fail-fast (probe 直呼のみ到達し得る保守)。 */
long long function_1801c0ac8(long long a, void* b, long long n) {
    unsigned long long ua = (unsigned long long)a, ub = (unsigned long long)(uintptr_t)b;
    if (!m8_ptr_ok(ua) || !m8_ptr_ok(ub))
        m8_fail("function_1801c0ac8: bad pointer args");
    unsigned short* pa = (unsigned short*)ua;
    unsigned short* pb = (unsigned short*)ub;
    while (n > 0) {
        unsigned short x = *pa;
        if (x == 0 || x != *pb) break;
        pa++; pb++; n--;
    }
    /* sub eax, ecx → i32 / 符号拡張 ret */
    long long r = (long long)(int)((unsigned int)*pa - (unsigned int)*pb);
    return r;
}

/* ---------- #3 function_1801c1438(i64,i64) — UCRT _invalid_parameter 報告系 thunk
 * (dsm: r8d=0x20; lea rdx,[const 文字列 0x1801f278c]; jmp 1801c12f4)。
 * 報告先が DSP 経路外 → no-op stub (m6_stubs.c RaiseException no-op 同型)。OK 化。 */
long long function_1801c1438(long long a, long long b) { (void)a; (void)b; return 0; }

/* ---------- #4 function_1801c17e0(i64 rcx) — 純計算 leaf (bit-exact 可能)
 * dsm: movabs rax,0x0008000000000000; or rcx,rax; [rsp+8]=rcx;
 *      movsd xmm0,[rsp+8]; ret → double quiet bit 付与, bits をそのまま返す。
 * (IR declare は i64 返り値なので bits は i64 経路で一致)。 */
long long function_1801c17e0(long long a) {
    unsigned long long x = (unsigned long long)a | 0x0008000000000000ull;
    return (long long)x;
}

/* ---------- #5 function_1801c17fc(i64 arg1, i32 arg2) — 純計算 leaf (bit-exact 可能)
 * dsm: bts ecx,0x16; [rsp+8]=ecx; movss xmm0,[rsp+8]; ret。
 * 演算対象は ecx = arg1 下位 32bit (Win x64: arg1=rcx, arg2=rdx は未使用)。
 * f32 quiet bit22 (0x400000) 付与 → bits 返し。 */
long long function_1801c17fc(long long a, int b) {
    (void)b;
    unsigned int x = (unsigned int)a | 0x400000u;
    return (long long)x;   /* bits 値 (0 拡張; 低 32bit = f32 bits) */
}

/* ---------- #7 function_1801c33e0() — 純計算 leaf (bit-exact 可能)
 * dsm: rcx=[rip+0x9d8f9] (VA 0x180260ce0 → linear 0x30260ce0); eax=0; rcx|=1;
 *      cmp [rip+0xa912c] (VA 0x18026c520 → linear 0x3026c520),rcx; sete al; ret。
 * linear memory 直読み (m6_data install 値) で実機と同一条件分岐。 */
long long function_1801c33e0(void) {
    unsigned long long a = *(volatile unsigned long long*)(uintptr_t)(M8BASE + 0x260ce0);
    unsigned long long b = *(volatile unsigned long long*)(uintptr_t)(M8BASE + 0x26c520);
    a |= 1;
    return (long long)(b == a);
}

/* ---------- #8 function_1801c6744(i64 cp, i32 flags, i64 src, i64 dst)
 * MultiByteToWideChar 分類 filter → Win API import 直 thunk (dsm 25 insns の
 * CP 範囲 filter 後 jmp qword [MultiByteToWideChar])。変換自体は shim 外の
 * Win API 参照 → 変換層の M4 file API 外挿後追いまで fail-fast 保持
 * (missing11.md: FLEEngine .flp 読込時に JS 側 UTF-16 変換層を接続)。 */
long long function_1801c6744(long long cp, int flags, long long src, long long dst) {
    (void)cp; (void)flags; (void)src; (void)dst;
    m8_fail("function_1801c6744 (MultiByteToWideChar thunk): Win API import 先 (M4 外挿待ち)");
    return 0;
}

/* ---------- function_1801c69a4(i64 rcx) — #9 の tail 先 (closure 外, IR 定義なし)
 * dsm: test rcx/je→0x7fffffff; lea rax,[rip+0x57500] (VA 0x18021deb5);
 *      cmp rcx,rax/je→0x7fffffff; mov eax,1; lock xadd [rcx+0x15c],eax;
 *      inc eax; ret / else eax=0x7fffffff。単 thread のため通常 inc で意味等価。 */
static long long m8_c69a4_port(long long rcx) {
    if (rcx == 0) return 0x7fffffffLL;
    unsigned long long rr = (unsigned long long)rcx;
    if (rr == (unsigned long long)(uintptr_t)(M8BASE + 0x21deb5)) return 0x7fffffffLL;
    if (!m8_ptr_ok(rr)) m8_fail("m8_c69a4_port: bad rcx");
    unsigned int old = *(volatile unsigned int*)(uintptr_t)(rr + 0x15c);
    *(volatile unsigned int*)(uintptr_t)(rr + 0x15c) = old + 1;   /* xadd +1 */
    return (long long)(int)(old + 1);
}

/* ---------- #9 function_1801c67a0(i64 rcx) — module record refcount addref 群
 * dsm 忠実 port:
 *   lock inc [rcx+0x10];
 *   for p in [rcx+0xe0],[rcx+0xf0],[rcx+0xe8],[rcx+0x100]: if p: lock inc [p];
 *   6 iteration (rax = rcx+0x38 + i*0x20):
 *     if [rax-0x10] != tag(0x180261258 → 0x30261258): rdx=[rax]; if rdx: inc [rdx];
 *     if [rax-0x18] != 0: rdx=[rax-8]; if rdx: inc [rdx]
 *   rcx=[rcx+0x120] → jmp c69a4(rcx)。
 * lock は単 thread 用途 (m6_stubs_hand.c の be668/be6bc no-op 運用踏襲)。 */
long long function_1801c67a0(long long rcx) {
    if (!m8_ptr_ok((unsigned long long)rcx))
        m8_fail("function_1801c67a0(rcx 不正): module record 未解決 (probe 直呼)");
#define M8INC32(a) do { \
    unsigned long long _a = (a); \
    if (_a && m8_ptr_ok(_a)) ++*(volatile unsigned int*)(uintptr_t)_a; \
} while (0)
    M8INC32((unsigned long long)rcx + 0x10);
    M8INC32(*(volatile unsigned long long*)(uintptr_t)((unsigned long long)rcx + 0xe0));
    M8INC32(*(volatile unsigned long long*)(uintptr_t)((unsigned long long)rcx + 0xf0));
    M8INC32(*(volatile unsigned long long*)(uintptr_t)((unsigned long long)rcx + 0xe8));
    M8INC32(*(volatile unsigned long long*)(uintptr_t)((unsigned long long)rcx + 0x100));
    unsigned long long base = (unsigned long long)rcx;
    unsigned long long tag = (unsigned long long)(uintptr_t)(M8BASE + 0x261258);
    for (int i = 0; i < 6; i++) {
        unsigned long long rax = base + 0x38 + (unsigned long long)i * 0x20;
        if (*(volatile unsigned long long*)(uintptr_t)(rax - 0x10) != tag)
            M8INC32(*(volatile unsigned long long*)(uintptr_t)rax);
        if (*(volatile unsigned long long*)(uintptr_t)(rax - 0x18) != 0)
            M8INC32(*(volatile unsigned long long*)(uintptr_t)(rax - 8));
    }
#undef M8INC32
    unsigned long long nxt = *(volatile unsigned long long*)(uintptr_t)(base + 0x120);
    return m8_c69a4_port(nxt);
}

/* ---------- #10 function_1801c6a04(i64 rcx, i64, i64) — lock xadd [rcx+0x15c] dec
 * dsm 忠実 port:
 *   test rcx/je→0x7fffffff; lea rax,[rip+0x574a0] (VA 0x18021deb0);
 *   cmp rcx,rax/ je→0x7fffffff; or eax,-1; lock xadd [rcx+0x15c],eax;
 *   dec eax; ret (xadd 後 eax = old 値 → dec で old-1)。 */
long long function_1801c6a04(long long rcx, long long a2, long long a3) {
    (void)a2; (void)a3;
    if (rcx == 0) return 0x7fffffffLL;
    unsigned long long rr = (unsigned long long)rcx;
    if (rr == (unsigned long long)(uintptr_t)(M8BASE + 0x21deb0)) return 0x7fffffffLL;
    if (!m8_ptr_ok(rr)) m8_fail("function_1801c6a04: bad rcx");
    unsigned int old = *(volatile unsigned int*)(uintptr_t)(rr + 0x15c);
    *(volatile unsigned int*)(uintptr_t)(rr + 0x15c) = old - 1;   /* xadd -1 */
    return (long long)(int)(old - 1);
}

/* ---------- #11 function_1801c721c(i64 rcx, ptr rdx) — CRT lock 同族
 * dsm 忠実 port (0x1801c721c..0x1801c72d4)。be668/be6bc は m6_stubs_hand.c の
 * lock no-op hand stub を C から直接呼び出し、c0b6c は closure IR define
 * (実体 lift) を wasm 内部呼出。
 *   flag = *(u32*)(0x302617f0) (dsm rip+0x9a5b9: VA 0x1802617f0)
 *   if ((p[0x3a8] & flag) != 0 && p[0x90] != 0):  rbx=p[0x88]; goto END
 *   else                                         goto LOCKPATH
 *   LOCKPATH:
 *     be668(5); rbx=p[0x88];
 *     if (rbx != *q):
 *       if (rbx != 0):
 *         old = xadd([rbx], -1) → eax=old
 *         if (old == 1 && p[0x88] != *(u64*)(0x302612b0)):    [dsm rip+0x9a02a]
 *           c0b6c(rbx, q)                                     [rcx=rbx, rdx=q]
 *       rax=q[0]; p[0x88]=rax; if (rax) inc dword [rax]
 *   be6bc(5)
 *   END: if (rbx == 0) call be5a8()  (dsm je to 1801c72ce)
 *        return rbx
 */
long long function_1801be668(int i);
long long function_1801be6bc(int i);
long long function_1801be5a8(void);
long long function_1801c0b6c(long long a, long long b);
long long function_1801c721c(long long arg1, void* arg2) {
    unsigned long long p = (unsigned long long)arg1;
    unsigned long long q = (unsigned long long)(uintptr_t)arg2;
    if (!m8_ptr_ok(p) || !m8_ptr_ok(q))
        m8_fail("function_1801c721c: bad args (probe 直呼)");
    unsigned int flag = *(volatile unsigned int*)(uintptr_t)(M8BASE + 0x2617f0);
    unsigned long long rbx = 0;
    if ((*(volatile unsigned int*)(uintptr_t)(p + 0x3a8) & flag) != 0
        && *(volatile unsigned long long*)(uintptr_t)(p + 0x90) != 0) {
        rbx = *(volatile unsigned long long*)(uintptr_t)(p + 0x88);
        goto END;   /* fast path: dsm jmp 0x1801c72b6 (lock path / be6bc 双方 skip) */
    }
    function_1801be668(5);
    rbx = *(volatile unsigned long long*)(uintptr_t)(p + 0x88);
    if (rbx != *(volatile unsigned long long*)(uintptr_t)q) {
        if (rbx != 0) {
            unsigned int old;
            if (!m8_ptr_ok(rbx)) m8_fail("function_1801c721c: rbx 不正");
            old = *(volatile unsigned int*)(uintptr_t)rbx;
            *(volatile unsigned int*)(uintptr_t)rbx = old - 1;   /* xadd -1 */
            unsigned long long e = (unsigned long long)(uintptr_t)(M8BASE + 0x2612b0);
            if (old == 1 && rbx != e)
                function_1801c0b6c((long long)rbx, (long long)q);
        }
        unsigned long long rax = *(volatile unsigned long long*)(uintptr_t)q;
        *(volatile unsigned long long*)(uintptr_t)(p + 0x88) = rax;
        if (rax) ++*(volatile unsigned int*)(uintptr_t)rax;
    }
    function_1801be6bc(5);
END:
    if (rbx == 0) function_1801be5a8();
    return (long long)rbx;
}
