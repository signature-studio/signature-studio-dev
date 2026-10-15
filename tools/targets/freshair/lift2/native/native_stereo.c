/* native_stereo.c — Stereo snapin (SlateCore 0x1805ee2a0) を実機機械語で実行する参照ハーネス (#4046・FA-48・#5011)。
 * 書込み元 0x1805cb150 は Stereo の構築関数 (this = P を取り、[P+0x9f88] = P を書く)。
 * 順序の確認: ctor を先に実行してから process を実行する (ctor=1)。ctor を飛ばす対照 (ctor=0) は
 * P+0x9f88 が 0 のまま読まれ、process が落ちることを確かめる。
 * FA_SELF_STORE=1 のときは構築関数を呼ばず、harness が P の確保直後に [P+0x9f88] = P を書く (#4046 の再現形)。
 *   ./native_stereo <core> <scen.txt> [fma] [ctor=1]
 * シナリオ形式とメモリ閉込は native_vocalfilter.c と同じ。 */
#include "pe_map.h"
#include "native_shim.h"
typedef long long (__attribute__((ms_abi)) *proc_t)(void*, void*);
int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]); guard_install();
    static const unsigned long long stubs[] = {0x18103d37c, 0x18103d47c, 0x18102f728};
    for (unsigned k = 0; k < sizeof stubs / sizeof *stubs; k++) im[stubs[k] - 0x180000000ULL] = 0xCC;
    /* __chkstk (0x18100c710) の gs:[0x10] (TEB StackLimit) 読みを停止。Linux は gs_base=0 で SIGSEGV するため
     * mov r11,gs:[0x10] → xor r11,r11 + nop に差替える (native_ctrl.c と同じ・wasm 側 @fa_teb=0 と同値)。 */
    { unsigned char* p = im + (0x18100c72cULL - 0x180000000ULL);
      if (p[0] == 0x65 && p[1] == 0x4c && p[2] == 0x8b && p[3] == 0x1c) {
          static const unsigned char GS_NEW[9] = {0x4d, 0x31, 0xdb, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90};
          memcpy(p, GS_NEW, 9);
      } }
    if (getenv("FA_IAT_ALL")) patch_iat_all(); else patch_iat(getenv("FA_IAT") ? getenv("FA_IAT") : "iat_slots.txt");
    patch_pokes(getenv("FA_POKES") ? getenv("FA_POKES") : "pokes.txt");
    volatile int* fma = (int*)0x1813070f8ULL; int fma_v = argc > 3 ? atoi(argv[3]) : 0;
    int use_ctor = argc > 4 ? atoi(argv[4]) : 1;
    int self_store = getenv("FA_SELF_STORE") != NULL;
    proc_t fn = (proc_t)0x1805ee2a0ULL;
    proc_t ctor = (proc_t)0x1805cb150ULL;
    FILE* fp = fopen(argv[2], "r"); if (!fp) { perror("scen"); return 2; }
    static char line[1 << 22]; static unsigned long tok[1 << 20];
    int guard_viol_total = 0; int ctor_ok = 0, ctor_bad = 0;
    while (fgets(line, sizeof line, fp)) {
        int k = 0; char* p = strtok(line, " \n"); while (p) { tok[k++] = strtoul(p, NULL, 16); p = strtok(NULL, " \n"); }
        int ti = 0; int sidx = (int)tok[ti++]; int ncalls = (int)tok[ti++];
        unsigned char* S = gr_alloc(0x1400); unsigned char* P = gr_alloc(0xa400); unsigned char* ctx = gr_alloc(0x80);
        unsigned char* A = gr_alloc(0x40);
        *(uint64_t*)(S + 0x90) = (uint64_t)P; *fma = fma_v;
        if (self_store) *(uint64_t*)(P + 0x9f88) = (uint64_t)P;
        printf("S%d", sidx);
        if (use_ctor && !self_store) {
            g_in_guard = 1; int s = sigsetjmp(g_jb, 1);
            if (s == 0) ctor(P, A);
            g_in_guard = 0;
            if (s != 0) { ctor_bad++; printf(" |CTOR_ERR"); if (getenv("FA_DBG")) fprintf(stderr, "CTOR_ERR sig=%d rip=%llx addr=%llx\n", g_fault_sig, g_fault_rip, g_fault_addr); }
            else if (*(uint64_t*)(P + 0x9f88) == (uint64_t)P) ctor_ok++;
            else { ctor_bad++; printf(" |CTOR_NOSELF"); }
        }
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
            hexdump(S + 0xca0, 0x12e0 + 0x30 - 0xca0);
            printf(" "); hexdump(L, n * 4); printf(" "); hexdump(R, n * 4);
            free((unsigned char*)L - GRD); free((unsigned char*)R - GRD);
        }
        printf("\n");
        free((unsigned char*)S - GRD); free((unsigned char*)P - GRD); free((unsigned char*)ctx - GRD); free((unsigned char*)A - GRD);
    }
    fprintf(stderr, "ctor=%d ctor_self_ok=%d ctor_bad=%d\n", use_ctor, ctor_ok, ctor_bad);
    if (abi_viol || guard_viol_total) fprintf(stderr, "ABI violations=%d guard violations=%d\n", abi_viol, guard_viol_total);
    return (abi_viol || guard_viol_total) ? 3 : 0;
}
