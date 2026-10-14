/* native_ctrl.c — FA-2c: FreshAirDsp 制御層 (0x1803dfc10, vtable 17 slot) を実機機械語で実行する参照ハーネス。
 *   ./native_ctrl <core> <scen.txt> [fma]
 * オブジェクトグラフ (harness 契約 — ctrl_harness.mjs と同一の初期化を両側で行う):
 *   F  = FreshAirDsp wrapper (0x400)     — 実機 ctor 0x1803dee20(F, M) で構築 (vtable 0x1810cab70)
 *   M  = FreshAirDspModel (0xc000)       — harness 構築: macro 0x9dc4/0x9e0c/0x9e60, 子リスト 0xa080 (8 entry)
 *   C_k= Snapin インスタンス (0x2200)    — harness 構築: wrapper 配列 0x2e0/0x338, controller 0x318 (空 std::map),
 *                                          param block 0x360/0x470 (+0x10 = mgr, ゼロ初期化で全経路 inert)
 *   W_k= SnapinDsp<子DSP> wrapper (0x400)— 実機 ctor (0x180774cd0/0x180b6ed50/0x180afde00) で構築 (実 vtable VA)
 *   P_k= 子 DSP model (0xa400)           — comp 実績レイアウト: 0xa098=VT(host), 0xa128=Q, 0xa118=-1, 0x9f30=Q(gain)
 *   子の vtable は実 VA (0x1810e1be8/0x1810faad0/0x1810f8870) → 間接 call が実機機械語で dispatch される。
 *   shared_ptr 制御ブロックの解放先 [vtbl+8]/[vtbl+0x10] = 実 VA 0x1803b4070 (ret 0, 参照カウンタは余裕値で解放不発)。
 * シナリオ: sidx ncalls vcap { nW {rg off val}* n L[n] R[n] op [oparg] }*
 *   rg: bit0x100=1byte 書込 / region 0=F 1=M 2=ctx 0x10|k=W_k 0x20|k=P_k 0x30|k=C_k
 *   op: 0=process(F,ctx) 1=slot4(f32 sr) 2=slot3 3=slot13 4=slot7 5=slot9 6=slot8 7=slot16(ctx) 8=slot5(ctx) 9=slot10(ctx) */
#include "pe_map.h"
#include "native_shim.h"
typedef long long (__attribute__((ms_abi)) *proc4_t)(void*, void*, void*, void*); typedef long long (__attribute__((ms_abi)) *proc_t)(void*, void*);
#define F_CTOR 0x1803dee20ULL
#define PROCESS 0x1803dfc10ULL
static const unsigned short CHAIN[8] = {1, 0, 1, 0, 2, 0, 2, 2};  /* 0=comp 1=filter 2=gain (FRAR/DUMP 順) */
static const unsigned long long WRAP_CTOR[3] = {0x180774cd0ULL, 0x180b6ed50ULL, 0x180afde00ULL};
static const unsigned long long WRAP_VT[3] = {0x1810e1be8ULL, 0x1810faad0ULL, 0x1810f8870ULL};
static float __attribute__((ms_abi)) host_get(void* self) { float f; memcpy(&f, (char*)self + 8, 4); return f; }
static uint64_t VT[8][32];
static unsigned char *g_sc, *g_io, *g_sl, *g_sr2;
/* FA-4 観測フック (FA_MAP_TRACE=1): 0x180c9d700 (child param 設定 setter) を差替え、(child 種別/idx, id, value) を記録する。
 * harness の controller map (C+0x318) は空で本物の setter は param を解決できず no-op のため、差替えでも挙動は変わらない。 */
static unsigned char* g_trCk[8]; static int g_trSidx;
static void __attribute__((ms_abi)) map_hook(void* child, int id, float v, void* key) {
    int k = -1; for (int i = 0; i < 8; i++) if ((void*)g_trCk[i] == child) k = i;
    uint32_t vb; memcpy(&vb, &v, 4); uint32_t kc = 0xffffffff, kidx = 0xffffffff;
    if (key) { memcpy(&kc, key, 4); memcpy(&kidx, (char*)key + 4, 4); }
    fprintf(stderr, "MAPTRACE S%d k=%d type=%s id=0x%x value=%08x keycnt=%u key0=%u\n", g_trSidx, k,
            k < 0 ? "?" : (CHAIN[k] == 0 ? "comp" : CHAIN[k] == 1 ? "filter" : "gain"), id, vb, kc, kidx);
}

/* FA-9 観測プローブ (FA_PROBE9=1): 0x180ca1480 (controller lookup) / 0x180da6c00 (param 書込) の入口で引数を記録し、
 * 元の機械語を一時復元して本物を呼び、再度 jmp を敷く (unpatch-call-repatch)。FA_ALT9=1 は C+0x328 を C+0x2d0 と不一致にし
 * 静的分岐 (map を引かず {C+0x308,C+0x470}) を強制する (ネガティブコントロール)。 */
static unsigned char g_sv_ca[12], g_sv_da[12]; static unsigned char *g_p_ca, *g_p_da; static unsigned char* g_nodeZ;
static void patch12(unsigned char* p, const void* t, unsigned char* sv) { memcpy(sv, p, 12); p[0] = 0x48; p[1] = 0xb8; memcpy(p + 2, &t, 8); p[10] = 0xff; p[11] = 0xe0; }
typedef void* (__attribute__((ms_abi)) *ca1480_t)(void*, void*, void*); typedef void (__attribute__((ms_abi)) *da6c00_t)(void*, int, int, int);
static void* __attribute__((ms_abi)) ca1480_probe(void* C, void* out, void* key) {
    /* FA-29 (#2145): FA_P9MIN=1 は call-through のみ (観測なし・前後の out[0] だけ記録)。full probe との差を切り分ける */
    if (getenv("FA_P9MIN")) { unsigned char tmp[12]; memcpy(tmp, g_sv_ca, 12); memcpy(g_p_ca, tmp, 12);
        if (getenv("FA_P9RD")) { uint64_t c2d0, c328, ctl, h[3]; memcpy(&c2d0, (char*)C + 0x2d0, 8); memcpy(&c328, (char*)C + 0x328, 8); memcpy(&ctl, (char*)C + 0x318, 8); memcpy(h, (char*)ctl + 0xa8, 24); fprintf(stderr, "P9RD S%d ctl=%llx\n", g_trSidx, (unsigned long long)ctl); }
        void* r0 = ((ca1480_t)(g_p_ca))(C, out, key); patch12(g_p_ca, (const void*)&ca1480_probe, g_sv_ca);
        uint64_t q0; memcpy(&q0, out, 8); fprintf(stderr, "P9MIN S%d out0=%llx C=%p\n", g_trSidx, (unsigned long long)q0, C); return r0; }
    uint64_t a2d0, a328, ctl, h[3]; memcpy(&a2d0, (char*)C + 0x2d0, 8); memcpy(&a328, (char*)C + 0x328, 8); memcpy(&ctl, (char*)C + 0x318, 8);
    uint32_t kc = 0xffffffffu, k0 = 0xffffffffu; if (key) { memcpy(&kc, key, 4); memcpy(&k0, (char*)key + 4, 4); }
    const char* pth = !key || kc == 0 ? "nokey" : a2d0 == a328 ? "map" : kc != 1 ? "zero" : k0 == 0 ? "static" : "map";
    memcpy(h, (char*)ctl + 0xa8, 24);
    { unsigned char tmp[12]; memcpy(tmp, g_sv_ca, 12); memcpy(g_p_ca, tmp, 12); }
    void* r = ((ca1480_t)(g_p_ca))(C, out, key);
    patch12(g_p_ca, (const void*)&ca1480_probe, g_sv_ca);
    uint64_t o0, o1, o2; memcpy(&o0, out, 8); memcpy(&o1, (char*)out + 8, 8); memcpy(&o2, (char*)out + 0x10, 8);
    fprintf(stderr, "FA9CA S%d eq=%d kc=%u k0=%u path=%s ret=%s out0=%llx out1=%llx found=%d hdr=%llx,%llx,%llx\n", g_trSidx, a2d0 == a328, kc, k0, pth,
            r == out ? "out" : "?", (unsigned long long)o0, (unsigned long long)o1, o0 != 0, (unsigned long long)h[0], (unsigned long long)h[1], (unsigned long long)h[2]);
    /* 観測のみ: out[0] が自前で確保した node Z の値オブジェクトを指すときだけ +0x10 を読む (想定外の値は deref しない) */
    if (o0) { int isZ = g_nodeZ && (unsigned char*)o0 == g_nodeZ; uint64_t o16 = 0; if (isZ) memcpy(&o16, (char*)o0 + 0x10, 8);
              fprintf(stderr, "FA9OBJ S%d out0_is_Z=%d obj=%llx obj+0x10=%llx\n", g_trSidx, isZ, (unsigned long long)o0, (unsigned long long)o16); }
    return r;
}
static void __attribute__((ms_abi)) da6c00_probe(void* T, int id, int idx, int r9) {
    fprintf(stderr, "FA9DA S%d this_id=0x%x idx=%d r9=%d\n", g_trSidx, (unsigned)id, idx, r9);
    unsigned char tmp[12]; memcpy(tmp, g_sv_da, 12); memcpy(g_p_da, tmp, 12);
    ((da6c00_t)(g_p_da))(T, id, idx, r9);
    patch12(g_p_da, (const void*)&da6c00_probe, g_sv_da);
}
#define W64(b, o, v) do { uint64_t _t = (uint64_t)(uintptr_t)(v); memcpy((b) + (o), &_t, 8); } while (0)
#define W32(b, o, v) do { uint32_t _t = (uint32_t)(v); memcpy((b) + (o), &_t, 4); } while (0)
static void build_tree(uint8_t* im, unsigned char** Fp, unsigned char** Mp, unsigned char** Ck, unsigned char** Wk,
                       unsigned char** Pk, unsigned char** Qk, unsigned char** blk, unsigned char** Rgk, unsigned char** Rbk, int vcap) {
    (void)im;
    unsigned char* F = *Fp = gr_alloc(0x400); unsigned char* M = *Mp = gr_alloc(0xc000);
    /* M は実機 FreshAirDspModel ctor (0x1803ba840) で構築 (macro cell 0x9dc0.. 群 / +0x19b8 / +0x9ba0 members)。
     * arg2 (rdx) は ctor が [arg2+4] (dword) を M+0xa088 (子リスト manager) に写すため **非 NULL が必要**
     * (0 を渡すと [0+4] 参照で SIGSEGV。fail は FA-2c で実測)。両側 (native/wasm) で同一の 0 初期化
     * 32B ダミーを渡す → M+0xa088 = 0 (hand-build 時のゼロと同値)。 */
    static unsigned long long m_dummy[4];
    memset(m_dummy, 0, sizeof m_dummy);
    ((proc4_t)0x1803ba840ULL)(M, m_dummy, 0, 0);
    for (int k = 0; k < 8; k++) {
        int t = CHAIN[k];
        unsigned char *C = Ck[k] = gr_alloc(0x2200), *W = Wk[k] = gr_alloc(0x1400), *P = Pk[k] = gr_alloc(0xa400);
        unsigned char *Q = Qk[k] = gr_alloc(0x80), *B = blk[k] = gr_alloc(0x30), *RG = Rgk[k] = gr_alloc(0x80010), *RB = Rbk[k] = gr_alloc(0x30);
        unsigned char* vbuf = (unsigned char*)calloc(1, 64);   /* machine HeapFree 対象ゆえ plain calloc (先頭) — FA-2b 規約 */
        /* W: 実機 ctor で構築 (0xa000×2 を operator new=HeapAlloc shim で確保) */
        ((proc4_t)WRAP_CTOR[t])(W, P, 0, 0);
        /* P: comp 実績の harness 契約 */
        W64(P, 0xa098, VT[k]); VT[k][12] = (uint64_t)(uintptr_t)&host_get;
        unsigned char* vb = Q; W64(P, 0xa128, Q); W64(P, 0x9f30, Q);
        W64(vb + 0x28, 0, vbuf); W64(vb + 0x30, 0, vbuf); W64(vb + 0x38, 0, vbuf + vcap);
        W32(P, 0xa118, 0xffffffff); W32(P, 0xa11c, 0xffffffff);
        /* filter model slot11 用 ring buffer (0x1806b22d0: {int,int,float[0x10000]}) + 解放 blk */
        W64(P, 0x9f98, RG); W64(P, 0x9fa0, RB);
        W64(RB, 0, RB + 0x10); W32(RB, 8, 0x40); W32(RB, 0xc, 0x40); W64(RB, 0x18, 0x1803b4070ULL); W64(RB, 0x20, 0x1803b4070ULL);
        /* C: Snapin インスタンス (単層: 0x2d0 == 0x328, 空パラメタ map) */
        W64(C, 0x2d0, C + 0x2d0); W64(C, 0x328, C + 0x2d0);
        if (getenv("FA_ALT9")) W64(C, 0x328, C + 0x2d8);   /* FA-9 ネガコン: 静的分岐を強制 (C+0x2d0 != C+0x328) */
        W64(C, 0x2e0, C + 0x600); W64(C + 0x600, 0, W);            /* arr1[0] = W */
        W64(C, 0x338, C + 0x610); W64(C + 0x610, 0, W);            /* arr2[0] = W */
        W64(C, 0x318, C + 0x2100);                                  /* controller */
        W64(C + 0x21a8, 8, C + 0x21b8);                             /* map._Myhead = H */
        for (int i = 0; i < 3; i++) W64(C + 0x21b8, i * 8, C + 0x21b8);  /* H.left/parent/right = H */
        C[0x21d0] = 1; C[0x21d1] = 1;                                     /* H._Isnil (H = C+0x21b8, +0x18/+0x19) */
        /* FA-16: 1 ノードを木に入れる (FA_NODE1=1 のときのみ。既定 OFF = 既存 baseline found=0 を維持)。
         * map 経路の探索 key は keycnt (0x180ca1499 の edx) なので node key = 1。
         * node: +0 left, +8 parent, +0x10 right, +0x19 isnil, +0x20 key(u16), +0x28 value, +0x30 blk */
        if (getenv("FA_NODE1")) { unsigned char* N = gr_alloc(0x40); unsigned char* Z = gr_alloc(0x40); unsigned char* NB = gr_alloc(0x30);
          memset(N, 0, 0x40); memset(Z, 0, 0x40); memset(NB, 0, 0x30);
          unsigned short k1 = 1; memcpy(N + 0x20, &k1, 2);
          W64(N, 0x00, C + 0x21b8); W64(N, 0x08, C + 0x21b8); W64(N, 0x10, C + 0x21b8);
          W64(N, 0x28, Z); W64(N, 0x30, NB);
          W64(NB, 0, NB + 0x10); W32(NB, 8, 0x40); W32(NB, 0xc, 0x40); W64(NB, 0x18, 0x1803b4070ULL); W64(NB, 0x20, 0x1803b4070ULL);
          W64(C + 0x21b8, 0x00, N); W64(C + 0x21b8, 0x08, N); W64(C + 0x21b8, 0x10, N); if (k == 0) { g_nodeZ = Z; if (getenv("FA_OUT0")) fprintf(stderr, "NODEZ Z=%p\n", (void*)Z); } }
        /* param block +0x10 = mgr。mgr は driver 0x180da68c0 が [mgr+0x19a8/0x19b0] (shared_ptr pair) を
         * 読むため、ダミー mgr を渡す (C+0x1900 = 0x1a00B, +0x19a8 = self, +0x19b0 = C+0x1c00 blk refcount=0x40)。 */
        W64(C, 0x370, C + 0x620); W64(C, 0x480, C + 0x620);
        W64(C + 0x620, 0x10, C + 0x1900);
        W64(C + 0x1900, 0x19a8, C + 0x1a00); W64(C + 0x1900, 0x19b0, C + 0x1c00);
        { unsigned char* DM = C + 0x1c00; W64(DM, 0, DM + 0x10); W32(DM, 8, 0x40); W32(DM, 0xc, 0x40); W64(DM, 0x18, 0x1803b4070ULL); W64(DM, 0x20, 0x1803b4070ULL); }
        /* blk: shared_ptr 制御ブロック (解放先 = 実 VA 0x1803b4070 ret 0, カウンタ余裕で dtor 不発) */
        W64(B, 0, B + 0x10); W32(B, 8, 0x40); W32(B, 0xc, 0x40);
        W64(B, 0x18, 0x1803b4070ULL); W64(B, 0x20, 0x1803b4070ULL);
        /* M+0xa080 子リスト entry k = {W, blk} */
        W64(M, 0xb000 + k * 16, C); W64(M, 0xb000 + k * 16 + 8, B);
        if (getenv("FA_FT") && k == 0) fprintf(stderr, "post-W-ctor k=0 [W+0x00]=%llx [W+0x90]=%llx [W+0x68]=%llx [W+0x30]=%llx [W+0x50]=%llx P=%p W=%p\n",
            *(unsigned long long*)(W + 0), *(unsigned long long*)(W + 0x90), *(unsigned long long*)(W + 0x68),
            *(unsigned long long*)(W + 0x30), *(unsigned long long*)(W + 0x50), (void*)P, (void*)W);
    }
    W64(M, 0xa090, M + 0xb000); W64(M, 0xa098, M + 0xb080); W64(M, 0xa0a0, M + 0xb080);
    ((proc4_t)F_CTOR)(F, M, 0, 0);   /* FreshAirDsp 実機 ctor (0xa000×2 確保 + [F+0x90]=M) */
}
int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]); guard_install();
    static const unsigned long long stubs[] = {0x18103d37c, 0x18103d47c, 0x18102f728};
    for (unsigned k = 0; k < sizeof stubs / sizeof *stubs; k++) im[stubs[k] - 0x180000000ULL] = 0xCC;
    /* __chkstk (0x18100c710) は gs:[0x10] = TEB StackLimit を読み probe loop を回す。この環境は gs_base=0 で
     * gs read 自身が SIGSEGV (実測) かつ Linux には TEB が存在しない。そこで (1) gs read (65 4c 8b 1d disp32) を
     * xor r11d,r11d + nop へ (2) probe loop 条件 jae -> jmp に差替え = chkstk を no-op 化。フレームは最大 0x5cc0
     * で 8MB stack / @fa_stack 1MB に収容済み (mlift 側も @fa_teb[2]=0 で同一挙動)。 */
    /* __chkstk (0x18100c710) の probe loop を停止 (Linux は gs_base=0 のため gs:[0x10] 読みが SIGSEGV)。
     * 実装は 65 4c 8b 1c 25 10 00 00 00 (mov r11, gs:[0x10]) → 4d 31 db (xor r11,r11) + nop。
     * wasm 側 (@fa_teb = 0) と同値 (StackLimit = 0 → probe は常時 skip)。 */
    { unsigned char* p = im + (0x18100c72cULL - 0x180000000ULL);
      if (p[0] == 0x65 && p[1] == 0x4c && p[2] == 0x8b && p[3] == 0x1c) {
          static const unsigned char GS_NEW[9] = {0x4d, 0x31, 0xdb, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90};
          memcpy(p, GS_NEW, 9);
      }
      unsigned char* q = im + (0x18100c738ULL - 0x180000000ULL); if (q[0] == 0x73) q[0] = 0xEB; }
    if (getenv("FA_HEAP_ZERO")) g_heap_zero = 1;   /* FA-2c: machine heap 0 初期化 (wasm 側と determinism 揃え) */
    patch_iat(getenv("FA_IAT") ? getenv("FA_IAT") : "iat_slots.txt");
    patch_pokes(getenv("FA_POKES") ? getenv("FA_POKES") : "pokes.txt");
    if (getenv("FA_MAP_TRACE")) {   /* mov rax, imm64 ; jmp rax */
        unsigned char* h = im + (0x180c9d700ULL - 0x180000000ULL); uint64_t t = (uint64_t)(uintptr_t)&map_hook;
        h[0] = 0x48; h[1] = 0xb8; memcpy(h + 2, &t, 8); h[10] = 0xff; h[11] = 0xe0;
    }
    if (getenv("FA_PROBE9")) {
        g_p_ca = im + (0x180ca1480ULL - 0x180000000ULL); g_p_da = im + (0x180da6c00ULL - 0x180000000ULL);
        patch12(g_p_ca, (const void*)&ca1480_probe, g_sv_ca); patch12(g_p_da, (const void*)&da6c00_probe, g_sv_da);
    }
    volatile int* fma = (int*)0x1813070f8ULL;
    int fma_v = argc > 3 ? atoi(argv[3]) : 0;
    proc_t fn = (proc_t)PROCESS;
    FILE* fp = fopen(argv[2], "r"); if (!fp) { perror("scen"); return 2; }
    static char line[1 << 22]; static unsigned long tok[1 << 21];
    int guard_viol_total = 0;
    while (fgets(line, sizeof line, fp)) {
        int k = 0; char* p = strtok(line, " \n"); while (p) { tok[k++] = strtoul(p, NULL, 16); p = strtok(NULL, " \n"); }
        int ti = 0; int sidx = (int)tok[ti++]; int ncalls = (int)tok[ti++]; int vcap = (int)tok[ti++];
        unsigned char *F, *M, *Ck[8], *Wk[8], *Pk[8], *Qk[8], *blk[8], *Rgk[8], *Rbk[8];
        build_tree(im, &F, &M, Ck, Wk, Pk, Qk, blk, Rgk, Rbk, vcap);
        unsigned char* ctx = gr_alloc(0x100);
        for (int i = 0; i < 8; i++) g_trCk[i] = Ck[i];
        g_trSidx = sidx;
        if (getenv("FA_FT")) fprintf(stderr, "post-ctor F=%p *(F+0x90)=%p M=%p\n", (void*)F, (void*)*(void**)(F + 0x90), (void*)M);
        *fma = fma_v;
        printf("S%d", sidx);
        for (int c = 0; c < ncalls; c++) {
            int nW = (int)tok[ti++];
            for (int w = 0; w < nW; w++) {
                int rg = (int)tok[ti++]; unsigned off = (unsigned)tok[ti++]; uint32_t val = (uint32_t)tok[ti++];
                int bw = rg >= 0x100; int reg = rg & 0xff;
                uint8_t* base = reg == 0 ? F : reg == 1 ? M : reg == 2 ? ctx :
                                (reg & 0xf0) == 0x10 ? Wk[reg & 15] : (reg & 0xf0) == 0x20 ? Pk[reg & 15] : Ck[reg & 15];
                memcpy(base + off, &val, bw ? 1 : 4);
            }
            int n = (int)tok[ti++];
            float* L = (float*)gr_alloc((n + 1) * 4); float* R = (float*)gr_alloc((n + 1) * 4);
            for (int i = 0; i < n; i++) { uint32_t b = tok[ti + i]; memcpy(&L[i], &b, 4); b = tok[ti + n + i]; memcpy(&R[i], &b, 4); }
            ti += 2 * n;
            int op = (int)tok[ti++];
            W64(ctx, 0, L); W64(ctx, 8, R); W32(ctx, 0x28, n); ctx[0x60] = 0;
            /* sidechain ctx 契約 (FA-2b comp 実績と同一): ctx+0x18 = sc {SL,SR,_,SL,SR} / ctx+0x70 = io block */
            if (!g_sc) { g_sc = gr_alloc(0x80); g_io = gr_alloc(0x100); g_sl = gr_alloc((2049) * 4); g_sr2 = gr_alloc((2049) * 4); }
            memset(g_sc, 0, 0x80);
            W64(g_sc, 0, g_sl); W64(g_sc, 8, g_sr2); W64(g_sc, 24, g_sl); W64(g_sc, 32, g_sr2);
            W64(ctx, 0x18, g_sc); W64(ctx, 0x70, g_io); W32(ctx, 0x78, 0);
            if (getenv("FA_FT")) fprintf(stderr, "pre-call c=%d op=%d F=%p *(F+0x90)=%p\n", c, op, (void*)F, (void*)*(void**)(F + 0x90));
            for (int t2 = 0; t2 < 8; t2++) W32(Pk[t2], 0xa118, 0xffffffff);  /* sidechain off (harness 契約, comp 実績と同一) */
            g_in_guard = 1; int s = sigsetjmp(g_jb, 1);
            unsigned long long ret = 0;
            if (s == 0) {
                /* 全 machine 呼出は ms_abi 必須 (MS x64: arg1=rcx / float arg2=xmm1)。素の関数ポインタ cast は
                 * SysV (rdi/xmm0) で呼んでしまい, this=garbage で即 SEGV になる (実測: this=&tok で rcx=[this+0x90]=0)。 */
                switch (op) {
                case 1: { float sr; uint32_t sb = (uint32_t)tok[ti++]; memcpy(&sr, &sb, 4); ((void (__attribute__((ms_abi))*)(void*, float))0x1803e0380ULL)(F, sr); break; }
                case 2: ((void (__attribute__((ms_abi))*)(void*))0x1803e01a0ULL)(F); break;
                case 3: ((void (__attribute__((ms_abi))*)(void*))0x1803e01d0ULL)(F); break;
                case 4: ret = (unsigned long long)((int (__attribute__((ms_abi))*)(void*))0x1803df050ULL)(F); break;
                case 5: ret = (unsigned long long)((int (__attribute__((ms_abi))*)(void*))0x1803df060ULL)(F); break;
                case 6: ret = (unsigned long long)((int (__attribute__((ms_abi))*)(void*))0x1803df030ULL)(F); break;
                case 7: ret = (unsigned long long)((int (__attribute__((ms_abi))*)(void*, void*))0x1803df040ULL)(F, ctx); break;
                case 8: ((void (__attribute__((ms_abi))*)(void*, void*))0x1803df580ULL)(F, ctx); break;
                case 9: ((void (__attribute__((ms_abi))*)(void*, void*))0x1803df810ULL)(F, ctx); break;
                default: fn(F, ctx); break;
                }
            }
            g_in_guard = 0;
            int gv = gr_check(F, 0x400) + gr_check(M, 0xc000) + gr_check(ctx, 0x100);
            for (int t = 0; t < 8; t++)
                gv += gr_check(Ck[t], 0x2200) + gr_check(Wk[t], 0x1400) + gr_check(Pk[t], 0xa400) + gr_check(Rgk[t], 0x80010) + gr_check(Rbk[t], 0x30)
                    + gr_check(Qk[t], 0x80) + gr_check(blk[t], 0x30)
                    + gr_check((unsigned char*)L, (n + 1) * 4) + gr_check((unsigned char*)R, (n + 1) * 4);
            guard_viol_total += gv;
            if (s != 0) { printf(" |ERR"); if (getenv("FA_DBG")) { fprintf(stderr, "ERR S%d sig=%d rip=%llx addr=%llx ret=%llx a118=%d ctx=%llx c18=%llx L=%llx R=%llx F58=%08x W0_58=%08x F90=%llx M90=%llx rcx=%llx rdx=%llx\n",
                    sidx, g_fault_sig, g_fault_rip, g_fault_addr, g_fault_ret, *(int32_t*)(Pk[0] + 0xa118), (unsigned long long)(uintptr_t)ctx,
                     *(unsigned long long*)(ctx + 0x18), *(unsigned long long*)(ctx + 0), *(unsigned long long*)(ctx + 8), *(uint32_t*)(F + 0x58), *(uint32_t*)(Wk[0] + 0x58), *(unsigned long long*)(F + 0x90), *(unsigned long long*)(M + 0xa090), g_rcx, g_rdx); } goto done; }
            if (gv) printf(" |GUARD");
            /* --- 状態ダンプ (ポインタ値は native/wasm で異なるため除外, 相対値と内容のみ) --- */
            printf(" |%llx", ret);
            printf(" "); hexdump(F + 0x10, 0x20); hexdump(F + 0x38, 0x18); hexdump(F + 0x58, 0x10); hexdump(F + 0x70, 0x20); hexdump(F + 0x98, 0x38);
            { uint64_t b1, b2; memcpy(&b1, F + 0x30, 8); memcpy(&b2, F + 0x50, 8); printf(" "); hexdump((void*)b1, 0x10); hexdump((void*)b2, 0x10); }
            printf(" "); printf("%02x%02x%02x ", M[0x9ba4], M[0x9bec], M[0x9cc4]);
            hexdump(M + 0x9dc4, 0x10); hexdump(M + 0x9e0c, 0x10); hexdump(M + 0x9e50, 0x20);
            printf(" "); hexdump(ctx + 0x10, 1); hexdump(ctx + 0x40, 1); hexdump(ctx + 0x58, 8); hexdump(ctx + 0x70, 0x10);
            for (int t = 0; t < 8; t++) {
                unsigned char* W = Wk[t]; uint64_t wb1, wb2;
                printf(" "); hexdump(W + 0x10, 0x20); hexdump(W + 0x38, 0x18); hexdump(W + 0x58, 0x10); hexdump(W + 0x70, 0x20); hexdump(W + 0x98, 0x78);
                memcpy(&wb1, W + 0x30, 8); memcpy(&wb2, W + 0x50, 8); printf(" "); hexdump((void*)wb1, 0x10); hexdump((void*)wb2, 0x10);
                unsigned char* P = Pk[t];
                printf(" "); hexdump(P + 0x9dc4, 0x80); hexdump(P + 0x9e50, 0x100); hexdump(P + 0x9f60, 0xe8);
                printf(" %02x", P[0xa11c] == 0xff && *(int32_t*)(P + 0xa118) == -1 ? 1 : 0); /* P+0xa118 遷移の要約 */
                uint64_t bp, ep, cp; memcpy(&bp, Qk[t] + 0x28, 8); memcpy(&ep, Qk[t] + 0x30, 8); memcpy(&cp, Qk[t] + 0x38, 8);
                printf(" %lu %lu ", (unsigned long)(ep - bp), (unsigned long)(cp - bp)); hexdump((void*)bp, ep - bp > 32 ? 32 : ep - bp);
                unsigned char* C = Ck[t];
                printf(" "); hexdump(C + 0x420, 4); hexdump(C + 0x428, 8); hexdump(C + 0x530, 4); hexdump(C + 0x538, 8);
                printf(" %02x", C[0x5d0]); hexdump(C + 0x5e8, 4);
                { uint64_t rp; memcpy(&rp, P + 0x9f98, 8); printf(" "); hexdump((void*)rp, 8); }
            }
            printf(" "); hexdump(L, n * 4); printf(" "); hexdump(R, n * 4);
        done:
            free((unsigned char*)L - GRD); free((unsigned char*)R - GRD);
            if (s != 0) break;
        }
        printf("\n");
        fflush(stdout);
    }
    if (abi_viol || guard_viol_total) fprintf(stderr, "ABI violations=%d guard violations=%d\n", abi_viol, guard_viol_total);
    return (abi_viol || guard_viol_total) ? 3 : 0;
}
