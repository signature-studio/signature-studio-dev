/* entry_native.c — FA-2c: VST2 エントリ群 (AEffect wrapper ctor + thunk: dispatcher/setParameter/
 *   getParameter/processReplacing/processDoubleReplacing/process) を実機機械語で実行する参照ハーネス。
 *   ./entry_native <core> <scen.txt>
 * グラフ (ctrl_harness.mjs / native_ctrl.c と同一契約):
 *   W  = AEffect wrapper (実機 ctor 0x180dace80, audioMaster=am_callback) — AEffect は W+0x30
 *   F  = FreshAirDsp wrapper 0x400 (実機 ctor 0x1803dee20)  — AEffect.object に F を設定 (VST host と同じ入口)
 *   M/C_k/W_k/P_k/... は native_ctrl.c の build_tree と同構成。
 * シナリオ: sidx vcap { nW {rg off val}* n L[n] R[n] op [args] }*   (rg は native_ctrl.c と同一)
 *   op 0=processReplacing(thunk) 1=setParameter(thunk) 2=getParameter(thunk) 3=dispatcher(thunk)
 *      4=processDoubleReplacing(thunk) 5=process(thunk) 6=何もしない (AEffect のみ) */
#include "pe_map.h"
#include "native_shim.h"
#include "am_host.h"
typedef long long (__attribute__((ms_abi)) *proc4_t)(void*, void*, void*, void*);
typedef long long (__attribute__((ms_abi)) *vswrap_t)(void*, void*, int, int);
typedef long long (__attribute__((ms_abi)) *proc_t)(void*, void*);
typedef long long (__attribute__((ms_abi)) *disp_t)(void*, int, int, long long, void*, float);
typedef void (__attribute__((ms_abi)) *setp_t)(void*, int, float);
typedef float (__attribute__((ms_abi)) *getp_t)(void*, int);
typedef void (__attribute__((ms_abi)) *vproc_t)(void*, float**, float**, int);
#define F_CTOR 0x1803dee20ULL
#define PROCESS 0x1803dfc10ULL
#define VST_WRAP_CTOR 0x180dace80ULL     /* VST2 AEffect wrapper 派生 ctor (this, audioMaster, numPrograms, numParams) */
static const unsigned short CHAIN[8] = {1, 0, 1, 0, 2, 0, 2, 2};  /* 0=comp 1=filter 2=gain */
static const unsigned long long CHILD_CTOR[3] = {0x180774cd0ULL, 0x180b6ed50ULL, 0x180afde00ULL};
static float __attribute__((ms_abi)) host_get(void* self) { float f; memcpy(&f, (char*)self + 8, 4); return f; }
static uint64_t VT[8][32];
static unsigned char *g_sc, *g_io, *g_sl, *g_sr2;
#define W64(b, o, v) do { uint64_t _t = (uint64_t)(uintptr_t)(v); memcpy((b) + (o), &_t, 8); } while (0)
#define W32(b, o, v) do { uint32_t _t = (uint32_t)(v); memcpy((b) + (o), &_t, 4); } while (0)
static void build_tree(unsigned char** Fp, unsigned char** Mp, unsigned char** Ck, unsigned char** Wk,
                       unsigned char** Pk, unsigned char** Qk, unsigned char** blk, unsigned char** Rgk, unsigned char** Rbk, int vcap) {
    unsigned char* F = *Fp = gr_alloc(0x400); unsigned char* M = *Mp = gr_alloc(0xc000);
    ((proc4_t)0x1803ba840ULL)(M, 0, 0, 0);
    for (int k = 0; k < 8; k++) {
        int t = CHAIN[k];
        unsigned char *C = Ck[k] = gr_alloc(0x2200), *W = Wk[k] = gr_alloc(0x1400), *P = Pk[k] = gr_alloc(0xa400);
        unsigned char *Q = Qk[k] = gr_alloc(0x80), *B = blk[k] = gr_alloc(0x30), *RG = Rgk[k] = gr_alloc(0x80010), *RB = Rbk[k] = gr_alloc(0x30);
        unsigned char* vbuf = (unsigned char*)calloc(1, 64);
        ((proc4_t)CHILD_CTOR[t])(W, P, 0, 0);
        W64(P, 0xa098, VT[k]); VT[k][12] = (uint64_t)(uintptr_t)&host_get;
        unsigned char* vb = Q; W64(P, 0xa128, Q); W64(P, 0x9f30, Q);
        W64(vb + 0x28, 0, vbuf); W64(vb + 0x30, 0, vbuf); W64(vb + 0x38, 0, vbuf + vcap);
        W32(P, 0xa118, 0xffffffff); W32(P, 0xa11c, 0xffffffff);
        W64(P, 0x9f98, RG); W64(P, 0x9fa0, RB);
        W64(RB, 0, RB + 0x10); W32(RB, 8, 0x40); W32(RB, 0xc, 0x40); W64(RB, 0x18, 0x1803b4070ULL); W64(RB, 0x20, 0x1803b4070ULL);
        W64(C, 0x2d0, C + 0x2d0); W64(C, 0x328, C + 0x2d0);
        W64(C, 0x2e0, C + 0x600); W64(C + 0x600, 0, W);
        W64(C, 0x338, C + 0x610); W64(C + 0x610, 0, W);
        W64(C, 0x318, C + 0x2100);
        W64(C + 0x21a8, 8, C + 0x21b8);
        for (int i = 0; i < 3; i++) W64(C + 0x21b8, i * 8, C + 0x21b8);
        C[0x21d0] = 1; C[0x21d1] = 1;
        W64(C, 0x370, C + 0x620); W64(C, 0x480, C + 0x620);
        W64(C + 0x620, 0x10, C + 0x1900);
        W64(C + 0x1900, 0x19a8, C + 0x1a00); W64(C + 0x1900, 0x19b0, C + 0x1c00);
        { unsigned char* DM = C + 0x1c00; W64(DM, 0, DM + 0x10); W32(DM, 8, 0x40); W32(DM, 0xc, 0x40); W64(DM, 0x18, 0x1803b4070ULL); W64(DM, 0x20, 0x1803b4070ULL); }
        W64(B, 0, B + 0x10); W32(B, 8, 0x40); W32(B, 0xc, 0x40);
        W64(B, 0x18, 0x1803b4070ULL); W64(B, 0x20, 0x1803b4070ULL);
        W64(M, 0xb000 + k * 16, C); W64(M, 0xb000 + k * 16 + 8, B);
    }
    W64(M, 0xa090, M + 0xb000); W64(M, 0xa098, M + 0xb080); W64(M, 0xa0a0, M + 0xb080);
    ((proc4_t)F_CTOR)(F, M, 0, 0);
}
int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]); guard_install();
    static const unsigned long long stubs[] = {0x18103d37c, 0x18103d47c, 0x18102f728};
    for (unsigned k = 0; k < sizeof stubs / sizeof *stubs; k++) im[stubs[k] - 0x180000000ULL] = 0xCC;
    /* __chkstk (0x18100c710) の probe loop を停止: Linux は gs_base=0 のため gs:[0x10] 読みが SIGSEGV。
     * 実装は 65 4c 8b 1c 25 10 00 00 00 (mov r11, gs:[0x10]) → 4d 31 db (xor r11,r11) + nop 相当へ。
     * wasm 側 (@fa_teb = 0) と同値 (StackLimit = 0 → probe は常時 skip)。 */
    { unsigned char* p = im + (0x18100c72cULL - 0x180000000ULL);
      if (p[0] == 0x65 && p[1] == 0x4c && p[2] == 0x8b && p[3] == 0x1c) {
          static const unsigned char GS_NEW[9] = {0x4d, 0x31, 0xdb, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90};
          memcpy(p, GS_NEW, 9);
      }
      unsigned char* q = im + (0x18100c738ULL - 0x180000000ULL); if (q[0] == 0x73) q[0] = 0xEB; }
    if (getenv("FA_HEAP_ZERO")) g_heap_zero = 1;   /* FA-2c: machine heap 0 初期化 (wasm 側と determinism 揃え) */
    patch_iat(getenv("FA_IAT") ? getenv("FA_IAT") : "iat_slots.txt");
    if (getenv("FA_IAT_ALL")) patch_iat_all();
    patch_pokes(getenv("FA_POKES") ? getenv("FA_POKES") : "pokes.txt");
    volatile int* fma = (int*)0x1813070f8ULL;
    FILE* fp = fopen(argv[2], "r"); if (!fp) { perror("scen"); return 2; }
    static char line[1 << 22]; static unsigned long tok[1 << 21];
    int guard_viol_total = 0;
    while (fgets(line, sizeof line, fp)) {
        int k = 0; char* p = strtok(line, " \n"); while (p) { tok[k++] = strtoul(p, NULL, 16); p = strtok(NULL, " \n"); }
        int ti = 0; int sidx = (int)tok[ti++]; int vcap = (int)tok[ti++];
        unsigned char *F, *M, *Ck[8], *Wk[8], *Pk[8], *Qk[8], *blk[8], *Rgk[8], *Rbk[8];
        build_tree(&F, &M, Ck, Wk, Pk, Qk, blk, Rgk, Rbk, vcap);
        /* AEffect wrapper: 実機 ctor (audioMaster = am_callback) → AEffect = W+0x30, object = F (VST host と同じ入口) */
        unsigned char* V = gr_alloc(0x200); memset(V, 0, 0x200);
        unsigned char* e = NULL;
        am_reset();
        g_in_guard = 1;
        int cs = sigsetjmp(g_jb, 1);
        if (cs == 0) e = (unsigned char*)((vswrap_t)VST_WRAP_CTOR)(V, (void*)(uintptr_t)&am_callback, 1, 3);
        g_in_guard = 0;
        if (cs != 0) { printf("S%d |ERR wrapper-ctor sig=%d rip=%llx\n", sidx, g_fault_sig, g_fault_rip); continue; }
        e = V + 0x30;
        W64(e, 0x60, F);                                  /* AEffect.object = F (FreshAirDsp) */
        unsigned char* ctx = gr_alloc(0x100);
        printf("S%d", sidx);
        for (int c = 0; ; c++) {
            int nW = (int)tok[ti++];
            if (nW < 0) break;
            for (int w = 0; w < nW; w++) {
                int rg = (int)tok[ti++]; unsigned off = (unsigned)tok[ti++]; uint32_t val = (uint32_t)tok[ti++];
                int bw = rg >= 0x100; int reg = rg & 0xff;
                uint8_t* base = reg == 0 ? F : reg == 1 ? M : reg == 2 ? V : reg == 3 ? e :
                                (reg & 0xf0) == 0x10 ? Wk[reg & 15] : (reg & 0xf0) == 0x20 ? Pk[reg & 15] : Ck[reg & 15];
                memcpy(base + off, &val, bw ? 1 : 4);
            }
            int n = (int)tok[ti++];
            float* L = (float*)gr_alloc((n + 1) * 4); float* R = (float*)gr_alloc((n + 1) * 4);
            float* oL = (float*)gr_alloc((n + 1) * 4); float* oR = (float*)gr_alloc((n + 1) * 4);
            for (int i = 0; i < n; i++) { uint32_t b = tok[ti + i]; memcpy(&L[i], &b, 4); b = tok[ti + n + i]; memcpy(&R[i], &b, 4); }
            ti += 2 * n;
            int op = (int)tok[ti++];
            unsigned long long ret = 0; float fx = 0.0f;
            float* ins[2] = {L, R}; float* outs[2] = {oL, oR};
            if (op != 1 && op != 2 && op != 3) {
                if (!g_sc) { g_sc = gr_alloc(0x80); g_io = gr_alloc(0x100); g_sl = gr_alloc(2049 * 4); g_sr2 = gr_alloc(2049 * 4); }
                memset(g_sc, 0, 0x80);
                W64(g_sc, 0, g_sl); W64(g_sc, 8, g_sr2); W64(g_sc, 24, g_sl); W64(g_sc, 32, g_sr2);
                W64(ctx, 0x18, g_sc); W64(ctx, 0x70, g_io); W32(ctx, 0x78, 0);
                for (int t2 = 0; t2 < 8; t2++) W32(Pk[t2], 0xa118, 0xffffffff);
            }
            int s; g_in_guard = 1; s = sigsetjmp(g_jb, 1);
            if (s == 0) {
                switch (op) {
                case 0: ((vproc_t)*(void**)(e + 0x78))(e, ins, outs, n); break;                     /* processReplacing */
                case 1: { unsigned idx = (unsigned)tok[ti++]; uint32_t vb = (uint32_t)tok[ti++]; float f; memcpy(&f, &vb, 4);
                          ((setp_t)*(void**)(e + 0x18))(e, (int)idx, f); break; }                     /* setParameter */
                case 2: { unsigned idx = (unsigned)tok[ti++]; fx = ((getp_t)*(void**)(e + 0x20))(e, (int)idx); break; }  /* getParameter */
                case 3: { int dop = (int)tok[ti++]; int didx = (int)tok[ti++]; uint64_t dval = (uint64_t)tok[ti++];
                          void* dptr = (void*)(uintptr_t)tok[ti++]; float dopt; uint32_t ob = (uint32_t)tok[ti++]; memcpy(&dopt, &ob, 4);
                          ret = ((disp_t)*(void**)(e + 8))(e, dop, didx, (long long)dval, dptr, dopt); break; }  /* dispatcher */
                case 4: ((vproc_t)*(void**)(e + 0x80))(e, ins, outs, n); break;                      /* processDoubleReplacing */
                case 5: ((vproc_t)*(void**)(e + 0x10))(e, ins, outs, n); break;                      /* process (legacy) */
                default: break;
                }
            }
            g_in_guard = 0;
            int gv = gr_check(F, 0x400) + gr_check(M, 0xc000) + gr_check(V, 0x200) + gr_check(e, 0xa8) + gr_check(ctx, 0x100);
            for (int t = 0; t < 8; t++)
                gv += gr_check(Ck[t], 0x2200) + gr_check(Wk[t], 0x1400) + gr_check(Pk[t], 0xa400) + gr_check(Rgk[t], 0x80010) + gr_check(Rbk[t], 0x30)
                    + gr_check(Qk[t], 0x80) + gr_check(blk[t], 0x30)
                    + gr_check((unsigned char*)L, (n + 1) * 4) + gr_check((unsigned char*)R, (n + 1) * 4)
                    + gr_check((unsigned char*)oL, (n + 1) * 4) + gr_check((unsigned char*)oR, (n + 1) * 4);
            guard_viol_total += gv;
            if (s != 0) { printf(" |ERR sig=%d rip=%llx addr=%llx\n", g_fault_sig, g_fault_rip, g_fault_addr); break; }
            if (gv) printf(" |GUARD");
            printf(" |%llx", ret);
            if (op == 2) printf(" %08x", *(unsigned*)&fx);
            printf(" am=%llu", (unsigned long long)am_count());
            printf(" ae=%08x", *(unsigned*)(e));
            printf(" objset=%d", *(unsigned long long*)(e + 0x60) == (unsigned long long)(uintptr_t)F ? 1 : 0);
            /* AEffect 全 0xa8 byte (ポインタ値は native/wasm で異なる → obj は差分として許容) */
            printf(" ae2="); for (int i = 0x10; i < 0x28; i += 4) printf("%08x", *(unsigned*)(e + i));
            printf(" "); hexdump(F + 0x10, 0x20); hexdump(F + 0x38, 0x18); hexdump(F + 0x58, 0x10); hexdump(F + 0x70, 0x20); hexdump(F + 0x98, 0x38);
            { uint64_t b1, b2; memcpy(&b1, F + 0x30, 8); memcpy(&b2, F + 0x50, 8); printf(" "); hexdump((void*)b1, 0x10); hexdump((void*)b2, 0x10); }
            printf(" "); printf("%02x%02x%02x ", M[0x9ba4], M[0x9bec], M[0x9cc4]);
            hexdump(M + 0x9dc4, 0x10); hexdump(M + 0x9e0c, 0x10); hexdump(M + 0x9e50, 0x20);
            for (int t = 0; t < 8; t++) {
                unsigned char* W = Wk[t]; uint64_t wb1, wb2;
                printf(" "); hexdump(W + 0x10, 0x20); hexdump(W + 0x38, 0x18); hexdump(W + 0x58, 0x10); hexdump(W + 0x70, 0x20); hexdump(W + 0x98, 0x78);
                memcpy(&wb1, W + 0x30, 8); memcpy(&wb2, W + 0x50, 8); printf(" "); hexdump((void*)wb1, 0x10); hexdump((void*)wb2, 0x10);
                unsigned char* P = Pk[t];
                printf(" "); hexdump(P + 0x9dc4, 0x80); hexdump(P + 0x9e50, 0x100); hexdump(P + 0x9f60, 0xe8);
                printf(" %02x", P[0xa11c] == 0xff && *(int32_t*)(P + 0xa118) == -1 ? 1 : 0);
                uint64_t bp, ep, cp; memcpy(&bp, Qk[t] + 0x28, 8); memcpy(&ep, Qk[t] + 0x30, 8); memcpy(&cp, Qk[t] + 0x38, 8);
                printf(" %lu %lu ", (unsigned long)(ep - bp), (unsigned long)(cp - bp)); hexdump((void*)bp, ep - bp > 32 ? 32 : ep - bp);
                unsigned char* C = Ck[t];
                printf(" "); hexdump(C + 0x420, 4); hexdump(C + 0x428, 8); hexdump(C + 0x530, 4); hexdump(C + 0x538, 8);
                printf(" %02x", C[0x5d0]); hexdump(C + 0x5e8, 4);
                { uint64_t rp; memcpy(&rp, P + 0x9f98, 8); printf(" "); hexdump((void*)rp, 8); }
            }
            printf(" "); hexdump(L, n * 4); printf(" "); hexdump(R, n * 4);
            printf(" "); hexdump(oL, n * 4); printf(" "); hexdump(oR, n * 4);
        }
        printf("\n");
        fflush(stdout);
    }
    if (abi_viol || guard_viol_total) fprintf(stderr, "ABI violations=%d guard violations=%d\n", abi_viol, guard_viol_total);
    return (abi_viol || guard_viol_total) ? 3 : 0;
}
