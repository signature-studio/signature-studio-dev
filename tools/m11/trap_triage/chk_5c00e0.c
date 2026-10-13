/* #474: function_5c00e0 (参照カウント付きキャッシュの find-or-insert) の転記 + リスト循環検査 (デバッグ専用; 本体には入れない).
 * 逆アセンブル 5c00e0..5c023c と突合した転記. 走査ループに Floyd 検出を足し, 循環したら node 列を stderr に出して abort() する.
 * 使い方: negctl_474.sh が work/obj/chk5c.o にコンパイルして link に混ぜる (weak な lifted 版を強シンボルで置換). */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef unsigned long long u64; typedef unsigned int u32; typedef unsigned short u16;
#define Q(a) (*(volatile u64*)(uintptr_t)(a))
#define D(a) (*(volatile u32*)(uintptr_t)(a))
#define W(a) (*(volatile u16*)(uintptr_t)(a))
extern u64 function_409c80(u64, u64, u64);
extern void function_4232e0(void*);
extern void function_423980(void*);
extern u64 function_439670(u64, u64, u64);
extern u64 function_525940(u64, u64);
extern u64 function_5bffa0(u64, unsigned int);
extern u64 function_409410(unsigned int);
static unsigned g_calls = 0, g_maxlen = 0, g_new = 0;
u64 function_5c00e0(u64 self, u64 key) {
    g_calls++;
    u16 h = (u16)function_5bffa0(key, W(self + 0x38));
    function_4232e0((void*)(uintptr_t)(self + 0x10));
    u32 tid = D(function_525940(0, 0) + 8);
    u64 node = Q(self + 8), slow = node;
    unsigned n = 0;
    while (node) {
        if (D(node + 0x18) == tid && W(node + 0x14) == h && (function_439670(node + 0x1c, key, W(self + 0x38)) & 0xff)) break;
        node = Q(node);
        n++;
        if ((n & 1) == 0) slow = Q(slow);
        if (node && node == slow) {
            fprintf(stderr, "[chk5c00e0] CYCLE call#%u self=%llx head=%llx key=%llx steps=%u at=%llx\n", g_calls, self, Q(self + 8), key, n, node);
            u64 p = Q(self + 8);
            for (unsigned i = 0; i < n + 2 && p; i++, p = Q(p))
                fprintf(stderr, "  node[%u]=%llx next=%llx rc=%u h=%x tid=%x\n", i, p, Q(p), D(p + 8), W(p + 0x14), D(p + 0x18));
            abort();
        }
    }
    if (n > g_maxlen) g_maxlen = n;
    fprintf(stderr, "[chk5c00e0] call#%u steps=%u %s maxlen=%u\n", g_calls, n, node ? "hit" : "new", g_maxlen);
    if (!node) {
        g_new++;
        node = function_409410(W(self + 0x38) + 0x1c);
        Q(node) = Q(self + 8);
        D(node + 8) = 0;
        Q(node + 0xc) = Q(key);
        W(node + 0x14) = h;
        D(node + 0x18) = tid;
        function_409c80(key, node + 0x1c, W(self + 0x38));
        Q(self + 8) = node;
    }
    D(node + 8) += 1;
    function_423980((void*)(uintptr_t)(self + 0x10));
    return node;
}
