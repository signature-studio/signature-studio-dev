/* native_limiter.c — Limiter snapin process (SlateCore 0x18094d9c0) を実機機械語で実行する参照ハーネス (#3739 / FA-43)。
 * P+0xa068 の sub-object (begin/end を空範囲) を harness で用意する (これが無いと 0x18094dd87 で SIGSEGV)。
 *   ./native_limiter <core> <scen.txt> [fma]
 * シナリオ形式は native_filter.c と同じ: sidx ncalls { nW {region off val}* n L[n] R[n] }*  region 0=S 1=P 2=ctx (+0x10 で 1 byte 書込)
 * ABI 検査・canary は native_shim.h / pe_map.h の共通方式。判定はしない (ERR 件数と行数だけを見る smoke 用)。 */
#include "pe_map.h"
#include "native_shim.h"
typedef long long (__attribute__((ms_abi)) *proc_t)(void*, void*);
#define PROC 0x18094d9c0ULL
int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]); guard_install();
    static const unsigned long long stubs[] = {0x18103d37c, 0x18103d47c, 0x18102f728};
    for (unsigned k = 0; k < sizeof stubs / sizeof *stubs; k++) im[stubs[k] - 0x180000000ULL] = 0xCC;
    if (getenv("FA_IAT_ALL")) patch_iat_all(); else patch_iat(getenv("FA_IAT") ? getenv("FA_IAT") : "iat_slots.txt");
    patch_pokes(getenv("FA_POKES") ? getenv("FA_POKES") : "pokes.txt");
    volatile int* fma = (int*)0x1813070f8ULL; int fma_v = argc > 3 ? atoi(argv[3]) : 0;
    proc_t fn = (proc_t)PROC;
    FILE* fp = fopen(argv[2], "r"); if (!fp) { perror("scen"); return 2; }
    static char line[1 << 22]; static unsigned long tok[1 << 20];
    int guard_viol_total = 0;
    while (fgets(line, sizeof line, fp)) {
        int k = 0; char* p = strtok(line, " \n"); while (p) { tok[k++] = strtoul(p, NULL, 16); p = strtok(NULL, " \n"); }
        int ti = 0; int sidx = (int)tok[ti++]; int ncalls = (int)tok[ti++];
        unsigned char* S = gr_alloc(0x1400); unsigned char* P = gr_alloc(0xa400); unsigned char* ctx = gr_alloc(0x80);
        *(uint64_t*)(S + 0x90) = (uint64_t)P; *fma = fma_v;
        /* P+0xa068 が指す sub-object (begin=+8, end=+0x10) を空の範囲で用意する */
        unsigned char* X = gr_alloc(0x40); *(uint64_t*)(X + 8) = (uint64_t)(X + 0x20); *(uint64_t*)(X + 0x10) = (uint64_t)(X + 0x20);
        *(uint64_t*)(P + 0xa068) = (uint64_t)X;
        printf("S%d", sidx);
        for (int c = 0; c < ncalls; c++) {
            int nW = (int)tok[ti++];
            for (int w = 0; w < nW; w++) {
                int rg = (int)tok[ti++]; unsigned off = (unsigned)tok[ti++]; uint32_t val = (uint32_t)tok[ti++];
                int bw = rg >= 0x10; rg &= 0xf; uint8_t* base = rg == 0 ? S : rg == 1 ? P : ctx;
                memcpy(base + off, &val, bw ? 1 : 4);
            }
            int n = (int)tok[ti++];
            float* L = (float*)gr_alloc((n + 1) * 4); float* R = (float*)gr_alloc((n + 1) * 4);
            for (int i = 0; i < n; i++) { uint32_t b = tok[ti + i]; memcpy(&L[i], &b, 4); b = tok[ti + n + i]; memcpy(&R[i], &b, 4); }
            ti += 2 * n;
            *(uint64_t*)(ctx + 0) = (uint64_t)L; *(uint64_t*)(ctx + 8) = (uint64_t)R; *(int32_t*)(ctx + 0x28) = n; ctx[0x60] = 0;
            g_in_guard = 1; int s = sigsetjmp(g_jb, 1);
            if (s == 0) fn(S, ctx);
            g_in_guard = 0;
            int gv = gr_check(S, 0x1400) + gr_check(P, 0xa400) + gr_check(ctx, 0x80)
                   + gr_check((unsigned char*)L, (n + 1) * 4) + gr_check((unsigned char*)R, (n + 1) * 4);
            guard_viol_total += gv;
            if (s != 0) { printf(" |ERR"); if (getenv("FA_DBG")) fprintf(stderr, "ERR sig=%d rip=%llx addr=%llx\n", g_fault_sig, g_fault_rip, g_fault_addr); free((unsigned char*)L - GRD); free((unsigned char*)R - GRD); break; }
            if (gv) printf(" |GUARD");
            printf(" |"); hexdump(S + 0x98, 8); hexdump(S + 0xa0, 0x20 * 16); hexdump(S + 0x4a0, 0x20 * 16);
            printf(" "); hexdump(L, n * 4); printf(" "); hexdump(R, n * 4);
            free((unsigned char*)L - GRD); free((unsigned char*)R - GRD);
        }
        printf("\n");
        free((unsigned char*)S - GRD); free((unsigned char*)P - GRD); free((unsigned char*)ctx - GRD);
    }
    if (abi_viol || guard_viol_total) fprintf(stderr, "ABI violations=%d guard violations=%d\n", abi_viol, guard_viol_total);
    return (abi_viol || guard_viol_total) ? 3 : 0;
}
