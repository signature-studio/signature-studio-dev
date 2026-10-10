/* native_comp.c — Compressor snapin process (SlateCore 0x180775220) を実機機械語で実行する参照ハーネス。
 *   ./native_comp <core> <scen.txt>
 * host オブジェクト (P+0xa098) の vtable slot 0x60 は ms_abi の C 関数 (this+8 の float を返す) に差替え。
 * 0x1803ded20 (std::vector grow) は MODE=real で機械語のまま (IAT は C 実装に差替え) / MODE=trap で int3。
 * ABI 検査: callee-saved (rbx,rbp,rsi,rdi,r12-r15,xmm6-15) 保存を全 call で確認。バッファは前後 64B canary 付き。 */
#include "pe_map.h"
#include "native_shim.h"
typedef long long (__attribute__((ms_abi)) *proc_t)(void*, void*);
#define PROC 0x180775220ULL
static float __attribute__((ms_abi)) host_get(void* self) { float f; memcpy(&f, (char*)self + 8, 4); return f; }
static uint64_t VT[32];
int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]); guard_install();
    /* fastfail / throw 系 (wasm 側 stub と同一集合) は int3 化: 到達 = ERR */
    static const unsigned long long stubs[] = {0x18103d37c, 0x18103d47c, 0x18102f728};
    for (unsigned k = 0; k < sizeof stubs / sizeof *stubs; k++) im[stubs[k] - 0x180000000ULL] = 0xCC;
    patch_iat(getenv("FA_IAT") ? getenv("FA_IAT") : "iat_slots.txt");
    patch_pokes(getenv("FA_POKES") ? getenv("FA_POKES") : "pokes.txt");
    VT[12] = (uint64_t)(uintptr_t)&host_get;
    volatile int* fma = (int*)0x1813070f8ULL;
    int fma_v = argc > 3 ? atoi(argv[3]) : 0;
    proc_t fn = (proc_t)PROC;
    FILE* fp = fopen(argv[2], "r"); if (!fp) { perror("scen"); return 2; }
    static char line[1 << 20];
    int guard_viol_total = 0;
    while (fgets(line, sizeof line, fp)) {
        static unsigned long tok[1 << 17]; int k = 0; char* p = strtok(line, " \n");
        while (p) { tok[k++] = strtoul(p, NULL, 16); p = strtok(NULL, " \n"); }
        int ti = 0; int sidx = (int)tok[ti++]; int ncalls = (int)tok[ti++]; int vcap = (int)tok[ti++];
        unsigned char* S = gr_alloc(0x200); unsigned char* P = gr_alloc(0xa400); unsigned char* Q = gr_alloc(0x80);
        unsigned char* vbuf = (unsigned char*)calloc(1, 64);   /* machine 側 HeapFree の対象ゆえ plain calloc (先頭) */
        unsigned char* ctx = gr_alloc(0x40); unsigned char* sc = gr_alloc(0x80);
        *(uint64_t*)(S + 0x90) = (uint64_t)P; *(uint64_t*)(P + 0xa098) = (uint64_t)VT;
        *(uint64_t*)(P + 0xa128) = (uint64_t)Q;
        *(uint64_t*)(Q + 0x28) = (uint64_t)vbuf; *(uint64_t*)(Q + 0x30) = (uint64_t)vbuf; *(uint64_t*)(Q + 0x38) = (uint64_t)(vbuf + vcap);
        *(int32_t*)(P + 0xa118) = -1; *fma = fma_v;
        printf("S%d", sidx);
        for (int c = 0; c < ncalls; c++) {
            int nW = (int)tok[ti++];
            for (int w = 0; w < nW; w++) {
                int rg = (int)tok[ti++]; unsigned off = (unsigned)tok[ti++]; uint32_t val = (uint32_t)tok[ti++];
                int bw = rg >= 0x10; rg &= 0xf;     /* 0x10 bit = 1 byte 書込 */
                uint8_t* base = rg == 0 ? S : rg == 1 ? P : rg == 2 ? ctx : Q;
                memcpy(base + off, &val, bw ? 1 : 4);
            }
            int n = (int)tok[ti++];
            float* L = (float*)gr_alloc((n + 1) * 4); float* R = (float*)gr_alloc((n + 1) * 4);
            float* SL = (float*)gr_alloc((n + 1) * 4); float* SR = (float*)gr_alloc((n + 1) * 4);
            for (int i = 0; i < n; i++) { uint32_t b = tok[ti + i]; memcpy(&L[i], &b, 4); b = tok[ti + n + i]; memcpy(&R[i], &b, 4); }
            ti += 2 * n;
            int hasSC = (int)tok[ti++];
            if (hasSC) { for (int i = 0; i < n; i++) { uint32_t b = tok[ti + i]; memcpy(&SL[i], &b, 4); b = tok[ti + n + i]; memcpy(&SR[i], &b, 4); } ti += 2 * n; }
            *(uint64_t*)(ctx + 0) = (uint64_t)L; *(uint64_t*)(ctx + 8) = (uint64_t)R; *(int32_t*)(ctx + 0x28) = n;
            *(uint64_t*)(ctx + 0x18) = (uint64_t)sc;
            /* sidechain 配列: entry 0 = {SL, SR, 0}; 通常は P+0xa118 = -1 (ctx 自身を使用) */
            memset(sc, 0, 0x80); *(uint64_t*)(sc + 0) = (uint64_t)SL; *(uint64_t*)(sc + 8) = (uint64_t)SR;
            *(uint64_t*)(sc + 24) = (uint64_t)SL; *(uint64_t*)(sc + 32) = (uint64_t)SR;
            *(int32_t*)(P + 0xa118) = hasSC ? 0 : -1;
            g_in_guard = 1; int s = sigsetjmp(g_jb, 1);
            if (s == 0) fn(S, ctx);
            g_in_guard = 0;
            int gv = gr_check(S, 0x200) + gr_check(P, 0xa400) + gr_check(Q, 0x80) + 0
                   + gr_check(ctx, 0x40) + gr_check(sc, 0x80) + gr_check((unsigned char*)L, (n + 1) * 4)
                   + gr_check((unsigned char*)R, (n + 1) * 4) + gr_check((unsigned char*)SL, (n + 1) * 4)
                   + gr_check((unsigned char*)SR, (n + 1) * 4);
            guard_viol_total += gv;
            if (s != 0) { printf(" |ERR"); if (getenv("FA_DBG")) fprintf(stderr, "ERR sig=%d rip=%llx addr=%llx\n", g_fault_sig, g_fault_rip, g_fault_addr); free((unsigned char*)L - GRD); free((unsigned char*)R - GRD); free((unsigned char*)SL - GRD); free((unsigned char*)SR - GRD); break; }
            if (gv) printf(" |GUARD");
            printf(" |"); hexdump(S + 0x98, 0x70); printf(" "); hexdump(P + 0x9f70, 0x10); hexdump(P + 0x9fb0, 0x10);
            hexdump(P + 0x9ff8, 0x8); hexdump(P + 0xa000, 0x8); hexdump(P + 0xa040, 4);
            uint64_t bp, endp, capp; memcpy(&bp, Q + 0x28, 8); memcpy(&endp, Q + 0x30, 8); memcpy(&capp, Q + 0x38, 8);
            printf(" %lu %lu ", (unsigned long)(endp - bp), (unsigned long)(capp - bp)); hexdump((void*)bp, endp - bp > 32 ? 32 : endp - bp);
            printf(" "); hexdump(L, n * 4); printf(" "); hexdump(R, n * 4);
        next:
            free((unsigned char*)L - GRD); free((unsigned char*)R - GRD); free((unsigned char*)SL - GRD); free((unsigned char*)SR - GRD);
        }
        printf("\n");
        free((unsigned char*)S - GRD); free((unsigned char*)P - GRD); free((unsigned char*)Q - GRD); free((unsigned char*)ctx - GRD); free((unsigned char*)sc - GRD); /* vbuf は machine の grow 経路で HeapFree 済みの可能性 (tcache 二重解放回避のため解放しない) */
    }
    if (abi_viol || guard_viol_total) fprintf(stderr, "ABI violations=%d guard violations=%d\n", abi_viol, guard_viol_total);
    return (abi_viol || guard_viol_total) ? 3 : 0;
}
