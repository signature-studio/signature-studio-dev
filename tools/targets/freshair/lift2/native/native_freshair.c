/* native_freshair.c — FreshAirDsp 制御層 process (SlateCore 0x1803dfc10, vtable 0x1810cab70 slot[12]) を
 * 実機機械語で実行する参照ハーネス (FA-2c)。
 *   ./native_freshair <core> <scen.txt> [fma]
 * オブジェクトグラフ (native/wasm 同一規約, ctl_harness.mjs と鏡像):
 *   F    FreshAirDsp 本体 (ctor 0x180dee20 が設定するフィールドを同一値で初期化)
 *   PH   host state 0xa400: +0xa080 子 vector {begin,end,cap}, +0xa098 host vtable, +0xa0a0 host float,
 *        +0x9dc4 MidAir / +0x9e0c HighAir / +0x9e60 Trim (macro 生値), +0xa1a8 通知 obj (+0x28 に vector)
 *   CH[i] Snapin shell 0xc00: +0x2d0/+0x328 同一値 (equal → voice +0x360 のみ), +0x2e0/+0x338 → DspModel 配列,
 *        +0x318 → REG (param registry, +0xb0 に map header), +0x360 voice (+0x10 mgr=PH, +0x30 event 配列,
 *        +0x48 counter), +0x5d0 / +0x5e8 (latency cache)
 *   D[i] DspModel: S (+0x00 vtable, +0x68 inner=P_i, +0x90=P_i, slot5 経路用内部 L/R seg) + P_i 0xa400
 *        (FA-2b と同一: +0xa098 host vtable, +0xa0a0 host float, +0xa118 sidechain flag, +0xa128 Q)
 *   child[0] の REG のみ 0x157/0x158/0x15a → holder (scope: +0x2d0=+0x328, +0x318 → 空map) を登録。
 *   holder の map は空 → 0x180c9d700 の再帰は clean miss で終端 (マクロ→子パラメタ実書き込みは FA-4)。
 * scenario: 1 行 = sidx ncalls chain mid high trim nPoke (reg off val)* | per call: n (L R)* nPoke2 (reg off val)*
 *   reg: 0=F 1=PH 2+i=CH[i] 0xa+i=D[i]S 0x12+i=P[i], 0x20 bit = 1byte 書込
 * 比較: F / PH / 各 CH / 各 D 状態 + L/R 出力の全バイト (FA-2b と同一の canary 閉込)。 */
#include "pe_map.h"
#include "native_shim.h"
typedef long long (__attribute__((ms_abi)) *proc_t)(void*, void*);
#define PROC 0x1803dfc10ULL
#define VT_FRESHAIR 0x1810cab70ULL
#define VT_COMP 0x1810E1BE8ULL
#define VT_FILTER 0x1810FAAD0ULL
#define VT_GAIN 0x1810F8870ULL

static float __attribute__((ms_abi)) host_get(void* self) { float f; memcpy(&f, (char*)self + 8, 4); return f; }
static uint64_t VTPL[32];   /* host vtable (native: C 関数 / wasm: token 0x7F000001 at +0x60) */

enum { R_F = 0, R_PH = 1, R_CH = 2, R_DS = 0xa, R_DP = 0x12, R_MASK = 0x1f, R_BYTE = 0x20 };
#define NCH 8
#define SZ_F 0xd0
#define SZ_PH 0xa400
#define SZ_CH 0xc00
#define SZ_DS 0x200
#define SZ_DP 0xa400
#define EVN 128          /* voice event 配列エントリ数 */

/* .epf (Factory Bank 8 本) 由来の macro 既定: Mid Air / High Air / Trim の float bits (実測) */
static const unsigned EPF[8][3] = {
    {0x3e9c28f2u, 0x3e4f5c24u, 0xbf6e1540u},   /* Mixbus Polish */
    {0x3f2c28f6u, 0x3f400003u, 0x00000000u},   /* Shiny */
    {0x3e999995u, 0x3ece1474u, 0xbfb47ae0u},   /* Mixbus Sparkle */
    {0x3eccb0a5u, 0x3e9ac51du, 0x00000000u},   /* Vocal Bus Presence */
    {0x3f31eb85u, 0x3e4cccc7u, 0x00000000u},   /* Presence Pop */
    {0x3ecb8519u, 0x3f0d709au, 0x00000000u},   /* Hat Lifter */
    {0x3f0cccc6u, 0x3eb33326u, 0x00000000u},   /* Vocal Air */
    {0x3ee6666au, 0x3f3f5c21u, 0x00000000u},   /* Clap Lifter */
};

static void wr32(unsigned char* b, unsigned o, unsigned v) { memcpy(b + o, &v, 4); }
static void wr64(unsigned char* b, unsigned o, uint64_t v) { memcpy(b + o, &v, 8); }

typedef struct {
    unsigned char *F, *PH, *CH[NCH], *DS[NCH], *DP[NCH], *Q[NCH], *vbuf[NCH];
    unsigned char *holder[NCH][3], *hblk[NCH][3], *reg[NCH], *regh[NCH];
    unsigned char *hn[NCH], *node[NCH][3], *hn2[NCH], *hnH[NCH];
    unsigned char *arrA[NCH], *arrB[NCH], *ev[NCH];
    unsigned char *bufL[NCH], *bufR[NCH];
    unsigned char *sc, *io, *nobj, *vec;
    unsigned char *fbuf1, *fbuf2;
    int chain[NCH], nch;
} G;

static uint64_t vt_of(int type) { return type == 0 ? VT_COMP : type == 1 ? VT_FILTER : VT_GAIN; }

/* 空の std::map header: {_Parent(+0x08) = 自身 (=root), +0x19 = isnil}。reg+0xb0 = [REG+0xa8+8] に header */
static void map_empty(unsigned char* reg, unsigned char* hn) {
    memset(hn, 0, 0x28);
    wr64(hn, 0x08, (uint64_t)(uintptr_t)hn);   /* MSVC _Tree: root = _Myhead->_Parent */
    hn[0x19] = 1;
    wr64(reg, 0xb0, (uint64_t)(uintptr_t)hn);
}
/* 3 node BST (root=0x158, left=0x157, right=0x15a)。node: {+0 left, +8 parent, +0x10 right,
 *  +0x19 isnil, +0x20 key(word), +0x28 holder, +0x30 blk} */
static void map_macros(unsigned char* reg, unsigned char* hn, unsigned char* n157, unsigned char* n158,
                       unsigned char* n15a, unsigned char** holder, unsigned char** blk) {
    memset(hn, 0, 0x28);
    wr64(hn, 0x08, (uint64_t)(uintptr_t)n158);   /* root = _Myhead->_Parent */
    wr64(hn, 0x00, (uint64_t)(uintptr_t)n157);   /* _Left = leftmost */
    wr64(hn, 0x10, (uint64_t)(uintptr_t)n15a);   /* _Right = rightmost */
    hn[0x19] = 1;
    unsigned char* ns[3] = {n157, n158, n15a};
    unsigned keys[3] = {0x157, 0x158, 0x15a};
    for (int k = 0; k < 3; k++) {
        memset(ns[k], 0, 0x40);
        wr32(ns[k], 0x20, keys[k]);
        wr64(ns[k], 0x28, (uint64_t)(uintptr_t)holder[k]);
        wr64(ns[k], 0x30, (uint64_t)(uintptr_t)blk[k]);
        wr64(ns[k], 0x00, (uint64_t)(uintptr_t)hn);   /* leaf → children = nil */
        wr64(ns[k], 0x10, (uint64_t)(uintptr_t)hn);
    }
    wr64(n158, 0x00, (uint64_t)(uintptr_t)n157); wr64(n157, 0x08, (uint64_t)(uintptr_t)n158);
    wr64(n158, 0x10, (uint64_t)(uintptr_t)n15a); wr64(n15a, 0x08, (uint64_t)(uintptr_t)n158);
    wr64(n158, 0x08, (uint64_t)(uintptr_t)hn);
    wr64(reg, 0xb0, (uint64_t)(uintptr_t)hn);
}

static void build_graph(G* g, int chain[NCH], int nch) {
    memset(g, 0, sizeof *g);
    g->nch = nch;
    for (int i = 0; i < NCH; i++) g->chain[i] = i < nch ? chain[i] : -1;
    g->F = gr_alloc(SZ_F);
    g->PH = gr_alloc(SZ_PH);
    g->fbuf1 = gr_alloc(0xa000); g->fbuf2 = gr_alloc(0xa000);
    g->sc = gr_alloc(0x80); g->io = gr_alloc(0x100); g->nobj = gr_alloc(0x180);
    g->vec = (unsigned char*)calloc(1, 0x200);
    /* F (ctor 0x1803dee20 相当のフィールド) */
    wr64(g->F, 0x00, VT_FRESHAIR);
    g->F[0x10] = 1;
    wr32(g->F, 0x18, 0x40); wr64(g->F, 0x1c, 0x2800);
    wr32(g->F, 0x28, 0); wr64(g->F, 0x30, (uint64_t)(uintptr_t)g->fbuf1);
    wr32(g->F, 0x38, 0x40); wr64(g->F, 0x3c, 0x2800);
    wr32(g->F, 0x48, 0); wr64(g->F, 0x50, (uint64_t)(uintptr_t)g->fbuf2);
    wr64(g->F, 0x70, 0);
    wr32(g->F, 0x78, 0); wr32(g->F, 0x7c, 0x3f800000); wr32(g->F, 0x80, 0x3f800000); wr32(g->F, 0x84, 0x3f800000);
    g->F[0x88] = 0;
    wr32(g->F, 0x58, 0);
    wr64(g->F, 0x68, (uint64_t)(uintptr_t)g->PH);
    wr64(g->F, 0x90, (uint64_t)(uintptr_t)g->PH);
    wr32(g->F, 0x9c, 0x3d23d70a);
    wr64(g->F, 0xa4, 0); wr32(g->F, 0xac, 0); wr32(g->F, 0xb0, 0x3df5c28f);
    wr32(g->F, 0xbc, 0x800000); wr32(g->F, 0xc0, 0x800000); wr32(g->F, 0xc4, 0x3f800000);
    /* PH: 子 vector (_Myfirst@+0xa090, _Mylast@+0xa098, _Myend@+0xa0a0 — 0x180c8b9c0 は +0x10/+0x18 を読む) */
    wr64(g->PH, 0xa090, (uint64_t)(uintptr_t)g->vec);
    wr64(g->PH, 0xa098, (uint64_t)(uintptr_t)(g->vec + 16 * NCH));
    wr64(g->PH, 0xa0a0, (uint64_t)(uintptr_t)(g->vec + 0x200));
    wr64(g->nobj, 0x28, (uint64_t)(uintptr_t)(g->nobj + 0x40));
    wr64(g->nobj, 0x30, (uint64_t)(uintptr_t)(g->nobj + 0x40));
    wr64(g->nobj, 0x38, (uint64_t)(uintptr_t)(g->nobj + 0x40 + 0x100));
    wr64(g->PH, 0xa1a8, (uint64_t)(uintptr_t)g->nobj);
    for (int i = 0; i < nch; i++) {
        int t = chain[i];
        g->CH[i] = gr_alloc(SZ_CH);
        g->DS[i] = gr_alloc(SZ_DS);
        g->DP[i] = gr_alloc(SZ_DP);
        g->Q[i] = gr_alloc(0x80);
        g->vbuf[i] = (unsigned char*)calloc(1, 64);
        g->arrA[i] = gr_alloc(16); g->arrB[i] = gr_alloc(16);
        g->ev[i] = gr_alloc(EVN * 16);
        g->bufL[i] = gr_alloc(0x8000); g->bufR[i] = gr_alloc(0x8000);
        g->hn[i] = gr_alloc(0x28); g->hn2[i] = gr_alloc(0x28); g->hnH[i] = gr_alloc(0x28);
        g->reg[i] = gr_alloc(0x100); g->regh[i] = gr_alloc(0x100);
        for (int k = 0; k < 3; k++) {
            g->holder[i][k] = gr_alloc(0x400);
            g->hblk[i][k] = gr_alloc(0x20);
            g->node[i][k] = gr_alloc(0x40);
        }
        /* DspModel D_i (FA-2b S+P 構成 + slot5 経路のフィールド) */
        wr64(g->DS[i], 0x00, vt_of(t));
        g->DS[i][0x10] = 0;
        wr32(g->DS[i], 0x58, 0); wr32(g->DS[i], 0x5c, 0x7fffffff); g->DS[i][0x60] = 0;
        wr64(g->DS[i], 0x68, (uint64_t)(uintptr_t)g->DP[i]);
        wr32(g->DS[i], 0x70, 0);
        wr32(g->DS[i], 0x78, 0); wr32(g->DS[i], 0x7c, 0x3f800000); wr32(g->DS[i], 0x80, 0x3f800000);
        wr32(g->DS[i], 0x84, 0x3f800000); g->DS[i][0x88] = 0;
        wr32(g->DS[i], 0x8c, 0);
        wr32(g->DS[i], 0x1c, 0); wr32(g->DS[i], 0x24, 0); wr64(g->DS[i], 0x30, (uint64_t)(uintptr_t)g->bufL[i]);
        wr32(g->DS[i], 0x28, 0);
        wr32(g->DS[i], 0x3c, 0); wr32(g->DS[i], 0x44, 0); wr64(g->DS[i], 0x50, (uint64_t)(uintptr_t)g->bufR[i]);
        wr32(g->DS[i], 0x48, 0);
        wr64(g->DS[i], 0x90, (uint64_t)(uintptr_t)g->DP[i]);
        wr32(g->DS[i], 0x98, 0x4650c000);   /* 44100.0f */
        /* P_i (FA-2b 規約) */
        wr64(g->DP[i], 0xa098, (uint64_t)(uintptr_t)VTPL);
        wr32(g->DP[i], 0xa118, 0xffffffff);
        wr64(g->DP[i], 0xa128, (uint64_t)(uintptr_t)g->Q[i]);
        wr64(g->Q[i], 0x28, (uint64_t)(uintptr_t)g->vbuf[i]);
        wr64(g->Q[i], 0x30, (uint64_t)(uintptr_t)g->vbuf[i]);
        wr64(g->Q[i], 0x38, (uint64_t)(uintptr_t)(g->vbuf[i] + 64));
        /* CH_i shell */
        wr64(g->CH[i], 0x2d0, (uint64_t)(uintptr_t)g->CH[i]);
        wr64(g->CH[i], 0x328, (uint64_t)(uintptr_t)g->CH[i]);
        wr64(g->arrA[i], 0, (uint64_t)(uintptr_t)g->DS[i]);
        wr64(g->arrB[i], 0, (uint64_t)(uintptr_t)g->DS[i]);
        wr64(g->CH[i], 0x2e0, (uint64_t)(uintptr_t)g->arrA[i]);
        wr64(g->CH[i], 0x338, (uint64_t)(uintptr_t)g->arrB[i]);
        wr64(g->CH[i], 0x360 + 0x10, (uint64_t)(uintptr_t)g->PH);
        wr64(g->CH[i], 0x360 + 0x30, (uint64_t)(uintptr_t)g->ev[i]);
        wr64(g->CH[i], 0x360 + 0x48, 0);
        wr32(g->CH[i], 0x5e8, 0);
        /* registry */
        if (i == 0) {
            map_macros(g->reg[0], g->hn[0], g->node[0][0], g->node[0][1], g->node[0][2],
                       g->holder[0], g->hblk[0]);
        } else {
            map_empty(g->reg[i], g->hn2[i]);
        }
        wr64(g->CH[i], 0x318, (uint64_t)(uintptr_t)g->reg[i]);
        /* holder = scope (再帰 1 段で clean miss): +0x2d0=+0x328 equal, +0x318 → 空map */
        for (int k = 0; k < 3; k++) {
            unsigned char* h = g->holder[i][k];
            wr64(h, 0x2d0, (uint64_t)(uintptr_t)h);
            wr64(h, 0x328, (uint64_t)(uintptr_t)h);
            map_empty(g->regh[i], g->hnH[i]);
            wr64(h, 0x318, (uint64_t)(uintptr_t)g->regh[i]);
            wr32(g->hblk[i][k], 8, 1);
        }
        /* children vector entry */
        wr64(g->vec + 16 * i, 0, (uint64_t)(uintptr_t)g->CH[i]);
        wr64(g->vec + 16 * i + 8, 0, (uint64_t)(uintptr_t)g->hblk[i][0]);
    }
}

static unsigned char* reg_base(G* g, int rg) {
    if (rg == R_F) return g->F;
    if (rg == R_PH) return g->PH;
    if (rg >= R_CH && rg < R_DS) return g->CH[rg - R_CH];
    if (rg >= R_DS && rg < R_DP) return g->DS[rg - R_DS];
    if (rg >= R_DP && rg < R_DP + NCH) return g->DP[rg - R_DP];
    return 0;
}

static void apply_write(G* g, int rg, unsigned off, unsigned val) {
    int bw = rg >= R_BYTE; rg &= R_MASK;
    unsigned char* b = reg_base(g, rg);
    if (!b) return;
    if (bw) b[off] = (unsigned char)val; else memcpy(b + off, &val, 4);
}

int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]); guard_install();
    static const unsigned long long stubs[] = {0x18103d37c, 0x18103d47c, 0x18102f728};
    for (unsigned k = 0; k < sizeof stubs / sizeof *stubs; k++) im[stubs[k] - 0x180000000ULL] = 0xCC;
    patch_iat(getenv("FA_IAT") ? getenv("FA_IAT") : "iat_slots.txt");
    patch_pokes(getenv("FA_POKES") ? getenv("FA_POKES") : "pokes.txt");
    for (int k = 0; k < 32; k++) VTPL[k] = (uint64_t)(uintptr_t)&host_get;
    volatile int* fma = (int*)0x1813070f8ULL;
    int fma_v = argc > 3 ? atoi(argv[3]) : 0;
    proc_t fn = (proc_t)PROC;
    FILE* fp = fopen(argv[2], "r"); if (!fp) { perror("scen"); return 2; }
    static char line[1 << 21];
    static unsigned long tok[1 << 19];
    int guard_viol_total = 0;
    while (fgets(line, sizeof line, fp)) {
        int k = 0; char* p = strtok(line, " \n");
        while (p) { tok[k++] = strtoul(p, NULL, 16); p = strtok(NULL, " \n"); }
        int ti = 0;
        int sidx = (int)tok[ti++]; int ncalls = (int)tok[ti++]; int chain = (int)tok[ti++];
        unsigned mid = (unsigned)tok[ti++], high = (unsigned)tok[ti++], trim = (unsigned)tok[ti++];
        int nP = (int)tok[ti++];
        int ctype[8];
        for (int i = 0; i < 8; i++) { int v = (chain >> (2 * i)) & 3; ctype[i] = v == 3 ? 2 : v; }
        G g; build_graph(&g, ctype, 8);
        wr32(g.PH, 0x9dc4, mid); wr32(g.PH, 0x9e0c, high); wr32(g.PH, 0x9e60, trim);
        for (int w = 0; w < nP; w++) {
            int rg = (int)tok[ti++]; unsigned off = (unsigned)tok[ti++]; unsigned val = (unsigned)tok[ti++];
            apply_write(&g, rg, off, val);
        }
        printf("S%d", sidx);
        for (int c = 0; c < ncalls; c++) {
            int n = (int)tok[ti++];
            float* L = (float*)gr_alloc((n + 1) * 4); float* R = (float*)gr_alloc((n + 1) * 4);
            float* SL = (float*)gr_alloc((n + 1) * 4); float* SR = (float*)gr_alloc((n + 1) * 4);
            for (int i = 0; i < n; i++) { uint32_t b = (uint32_t)tok[ti + i]; memcpy(&L[i], &b, 4); b = (uint32_t)tok[ti + n + i]; memcpy(&R[i], &b, 4); }
            ti += 2 * n;
            int nP2 = (int)tok[ti++];
            for (int w = 0; w < nP2; w++) {
                int rg = (int)tok[ti++]; unsigned off = (unsigned)tok[ti++]; unsigned val = (unsigned)tok[ti++];
                apply_write(&g, rg, off, val);
            }
            unsigned char* ctx = gr_alloc(0x80);
            uint64_t t64;
            uint32_t t32;
            t64 = (uint64_t)(uintptr_t)L; memcpy(ctx + 0x00, &t64, 8);
            t64 = (uint64_t)(uintptr_t)R; memcpy(ctx + 0x08, &t64, 8);
            t64 = (uint64_t)(uintptr_t)g.sc; memcpy(ctx + 0x18, &t64, 8);
            t32 = (uint32_t)n; memcpy(ctx + 0x28, &t32, 4);
            t64 = (uint64_t)(uintptr_t)g.io; memcpy(ctx + 0x70, &t64, 8);
            t32 = 0; memcpy(ctx + 0x78, &t32, 4);
            memset(g.sc, 0, 0x80);
            t64 = (uint64_t)(uintptr_t)SL; memcpy(g.sc + 0, &t64, 8);
            t64 = (uint64_t)(uintptr_t)SR; memcpy(g.sc + 8, &t64, 8);
            t64 = (uint64_t)(uintptr_t)SL; memcpy(g.sc + 24, &t64, 8);
            t64 = (uint64_t)(uintptr_t)SR; memcpy(g.sc + 32, &t64, 8);
            *fma = fma_v;
            g_in_guard = 1; int s = sigsetjmp(g_jb, 1);
            if (s == 0) fn(g.F, ctx);
            g_in_guard = 0;
            int gv = gr_check(g.F, SZ_F) + gr_check(g.PH, SZ_PH);
            for (int i = 0; i < 8; i++) gv += gr_check(g.CH[i], SZ_CH) + gr_check(g.DS[i], SZ_DS) + gr_check(g.DP[i], SZ_DP) + gr_check(g.Q[i], 0x80);
            gv += gr_check(ctx, 0x80) + gr_check(g.sc, 0x80) + gr_check((unsigned char*)L, (n + 1) * 4) + gr_check((unsigned char*)R, (n + 1) * 4);
            guard_viol_total += gv;
            if (s != 0) {
                printf(" |ERR");
                if (getenv("FA_DBG")) fprintf(stderr, "ERR sig=%d rip=%llx addr=%llx\n", g_fault_sig, g_fault_rip, g_fault_addr);
                free((unsigned char*)L - GRD); free((unsigned char*)R - GRD); free((unsigned char*)SL - GRD); free((unsigned char*)SR - GRD);
                free(ctx - GRD);
                break;
            }
            if (gv) printf(" |GUARD");
            /* F: ポインタ field (+0x30 fbuf1, +0x50 fbuf2) を除いて dump (native/wasm でアドレスが異なるため) */
            printf(" |"); hexdump(g.F + 0x10, 0x20); hexdump(g.F + 0x38, 0x18); hexdump(g.F + 0x58, 0x78);
            printf(" "); hexdump(g.PH + 0x9e98, 0x50); hexdump(g.PH + 0x9f70, 0x60);
            uint64_t vb, ve; memcpy(&vb, g.PH + 0xa090, 8); memcpy(&ve, g.PH + 0xa098, 8);
            printf(" %lu", (unsigned long)(ve - vb));
            unsigned char* nb; memcpy(&nb, g.PH + 0xa1a8, 8);
            uint64_t nbgn, nend; memcpy(&nbgn, nb + 0x28, 8); memcpy(&nend, nb + 0x30, 8);
            printf(" %lu", (unsigned long)(nend - nbgn));
            hexdump(nb + 0x40, nend - nbgn > 32 ? 32 : (int)(nend - nbgn));
            for (int i = 0; i < 8; i++) {
                printf(" %02x|%d|%d|%d", g.CH[i][0x5d0], *(int*)(g.CH[i] + 0x5e8),
                    (int)(*(uint64_t*)(g.CH[i] + 0x360 + 0x48)), *(int*)(g.DS[i] + 0x58));
                printf("|%02x|%d|%d", g.DS[i][0x60], *(int*)(g.DS[i] + 0x5c), (int)(*(uint32_t*)(g.DS[i] + 0x28)));
                printf("|%02x", g.DS[i][0x8c]);
                printf("|"); hexdump(g.DS[i] + 0x1c, 8);
                printf("|"); hexdump(g.DP[i] + 0x9f70, 0x10); hexdump(g.DP[i] + 0x9fb0, 0x10);
                hexdump(g.DP[i] + 0x9ff8, 8); hexdump(g.DP[i] + 0xa000, 8);
            }
            printf(" "); hexdump((unsigned char*)L, n * 4); printf(" "); hexdump((unsigned char*)R, n * 4);
            free((unsigned char*)L - GRD); free((unsigned char*)R - GRD); free((unsigned char*)SL - GRD); free((unsigned char*)SR - GRD);
            free(ctx - GRD);
        }
        printf("\n");
        fflush(stdout);
    }
    if (abi_viol || guard_viol_total) fprintf(stderr, "ABI violations=%d guard violations=%d\n", abi_viol, guard_viol_total);
    return (abi_viol || guard_viol_total) ? 3 : 0;
}
