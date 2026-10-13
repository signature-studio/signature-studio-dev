/* probe_setid.c — FA-7: 実 ctor (0x180b4c040) で構築した Filter モデル M に対し、実機 setter 0x1803debc0(M,id,value) を呼び
 *   (a) M (0xa400B) のどのバイトが変わるか (b) Filter process (0x180b6f050) の出力が変わるか を実測する。
 *   ./probe_setid <core> <id_hex>... [Pxxxx=f32] [Sid=f32]
 *     <id_hex>  : 3 水準 (f32 0.5 / 0.25 / 0.9) で setter を呼ぶ。
 *     Pxxxx=f32 : M+0xxxx へ直書き (陽性対照 POKE。setter 経由なし)。
 *     Sid=f32   : setter 1 水準の陽性対照 (PC 行。値は DSP 側の単位で与える)。
 *   測定単位は「ctor を毎回新規実行した独立モデル」。モデルは自己参照ポインタを持つため memcpy 複製は使わない
 *   (複製に setter を掛けると元モデル側が書き換わる。alias_check 行で実測)。
 *   (b) は sr=48000, 型 enum M+0x9dc4 = type (環境変数 FA_TYPE, 既定 ctor 値) で 64 sample の疑似ノイズを処理し L/R の FNV-1a を比較。 */
#include "pe_map.h"
#include "native_shim.h"
#include <sys/wait.h>
typedef long long (__attribute__((ms_abi)) *ctor_t)(void*, void*);
typedef void (__attribute__((ms_abi)) *set_t)(void*, int, unsigned);
typedef void (__attribute__((ms_abi)) *proc_t)(void*, void*);
#define MS 0xa400
#define NOFF 32
typedef struct { uint64_t h; int serr, perr, nd, offs[NOFF]; } res_t;
static uint64_t fnv(const void* p, size_t n);
static uint64_t run_proc(unsigned char* M, unsigned type, int* err);
static int g_poff = -1; static unsigned g_pval;
/* ctor を新規実行して独立モデルを返す */
static unsigned char* fresh_model(void) {
    unsigned char* M = gr_alloc(MS); static unsigned long long dummy[4];
    g_in_guard = 1; int s = sigsetjmp(g_jb, 1);
    if (s == 0) ((ctor_t)0x180b4c040ULL)(M, dummy);
    g_in_guard = 0; if (s) { fprintf(stderr, "ctor ERR\n"); _exit(3); }
    return M;
}
static void do_setter(unsigned char* T, int id, unsigned val, int* serr) {
    g_in_guard = 1; int s = sigsetjmp(g_jb, 1);
    if (s == 0) ((set_t)0x1803debc0ULL)(T, id, val);
    g_in_guard = 0; *serr = s;
}
/* 測定は fork 子で隔離 (process が image 内グローバルを書き換えるため親状態を汚さない)。id<0 は setter 無し。 */
static res_t measure(int id, unsigned val, unsigned type) {
    res_t* sh = mmap(0, sizeof(res_t), PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    pid_t pid = fork();
    if (pid == 0) {
        unsigned char* T = fresh_model(); unsigned char* S0 = gr_alloc(MS); memcpy(S0, T, MS); res_t r; memset(&r, 0, sizeof r);
        if (g_poff >= 0) memcpy(T + g_poff, &g_pval, 4);
        if (id >= 0) do_setter(T, id, val, &r.serr);
        for (int i = 0; i < MS; i++) if (T[i] != S0[i]) { if (r.nd < NOFF) r.offs[r.nd] = i; r.nd++; }
        r.h = run_proc(T, type, &r.perr);
        *sh = r; _exit(0);
    }
    int st; waitpid(pid, &st, 0); res_t r = *sh; munmap(sh, sizeof(res_t)); return r;
}
/* 検査: memcpy で複製したモデル C に setter を掛けると、元モデル B が変わる (自己参照ポインタの aliasing)。戻り値 = B の変化バイト数 */
static int alias_check(float f) {
    res_t* sh = mmap(0, sizeof(res_t), PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    pid_t pid = fork();
    if (pid == 0) {
        unsigned bits; memcpy(&bits, &f, 4);
        unsigned char* B = fresh_model(); unsigned char* C = gr_alloc(MS); unsigned char* B0 = gr_alloc(MS);
        memcpy(C, B, MS); memcpy(B0, B, MS); int se; do_setter(C, 2, bits, &se);
        int n = 0; for (int i = 0; i < MS; i++) if (B[i] != B0[i]) n++;
        sh->nd = n; _exit(0);
    }
    int st; waitpid(pid, &st, 0); int n = sh->nd; munmap(sh, sizeof(res_t)); return n;
}
static uint64_t fnv(const void* p, size_t n) { uint64_t h = 1469598103934665603ULL; const uint8_t* b = p; for (size_t i = 0; i < n; i++) { h ^= b[i]; h *= 1099511628211ULL; } return h; }
static uint64_t run_proc(unsigned char* M, unsigned type, int* err) {
    unsigned char* S = gr_alloc(0x1400); unsigned char* ctx = gr_alloc(0x80); int n = 64;
    float* L = (float*)gr_alloc(n * 4 + 4); float* R = (float*)gr_alloc(n * 4 + 4);
    unsigned r = 12345; for (int i = 0; i < n; i++) { r = r * 1664525u + 1013904223u; L[i] = ((int)(r >> 8) - 8388608) / 8388608.0f * 0.5f; R[i] = -L[i] * 0.7f + 0.01f; }
    float sr = 48000.0f; memcpy(S + 0x98, &sr, 4); *(uint64_t*)(S + 0x90) = (uint64_t)M;
    if (type != 0xffffffffu) memcpy(M + 0x9dc4, &type, 4);
    *(uint64_t*)(ctx + 0) = (uint64_t)L; *(uint64_t*)(ctx + 8) = (uint64_t)R; *(int32_t*)(ctx + 0x28) = n;
    g_in_guard = 1; int s = sigsetjmp(g_jb, 1); *err = s;
    for (int rep = 0; rep < 3 && s == 0; rep++) ((proc_t)0x180b6f050ULL)(S, ctx);
    g_in_guard = 0;
    uint64_t h = fnv(L, n * 4) * 31 + fnv(R, n * 4);
    if (getenv("FA_SHOW")) { unsigned r2 = 12345; int diff = 0; float mx = 0; for (int i = 0; i < n; i++) { r2 = r2 * 1664525u + 1013904223u; float in = ((int)(r2 >> 8) - 8388608) / 8388608.0f * 0.5f; if (L[i] != in) diff++; float d = L[i] - in; if (d < 0) d = -d; if (d > mx) mx = d; } fprintf(stderr, "SHOW type=%u L!=in %d/%d maxabsdiff=%g\n", type, diff, n, mx); }
    return h;
}
int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]); guard_install();
    static const unsigned long long stubs[] = {0x18103d37c, 0x18103d47c, 0x18102f728};
    for (unsigned k = 0; k < sizeof stubs / sizeof *stubs; k++) im[stubs[k] - 0x180000000ULL] = 0xCC;
    { unsigned char* p = im + (0x18100c72cULL - 0x180000000ULL);
      if (p[0] == 0x65 && p[1] == 0x4c && p[2] == 0x8b && p[3] == 0x1c) { static const unsigned char G[9] = {0x4d,0x31,0xdb,0x90,0x90,0x90,0x90,0x90,0x90}; memcpy(p, G, 9); }
      unsigned char* q = im + (0x18100c738ULL - 0x180000000ULL); if (q[0] == 0x73) q[0] = 0xEB; }
    g_heap_zero = 1; patch_iat("iat_slots.txt"); patch_pokes("pokes.txt");
    fresh_model();
    unsigned type = getenv("FA_TYPE") ? (unsigned)atoi(getenv("FA_TYPE")) : 0xffffffffu;
    unsigned lv[3]; float fl[3] = {0.5f, 0.25f, 0.9f}; memcpy(lv, fl, 12);
    res_t b1 = measure(-1, 0, type), b2 = measure(-1, 0, type);
    printf("# type=%s base_out_hash=%016llx base_rerun_hash=%016llx deterministic=%d perr=%d\n", type == 0xffffffffu ? "ctor-default" : getenv("FA_TYPE"),
           (unsigned long long)b1.h, (unsigned long long)b2.h, b1.h == b2.h, b1.perr);
    printf("# alias_check: memcpy 複製モデルへの setter(ID 0x2, 1000) で元モデルが変わったバイト数 = %d (0 でなければ memcpy 複製は測定に使えない)\n", alias_check(1000.0f));
    for (int a = 2; a < argc; a++) {
        if (argv[a][0] == 'P') {   /* 陽性対照 POKE: M+off へ f32 を直書き (setter 経由なし) */
            char* eq = strchr(argv[a], '='); g_poff = (int)strtol(argv[a] + 1, 0, 16); float f = strtof(eq + 1, 0); memcpy(&g_pval, &f, 4);
            res_t r = measure(-1, 0, type); printf("POKE M+0x%x=%g: diffB=%d outChanged=%d perr=%d\n", g_poff, f, r.nd, r.h != b1.h, r.perr); g_poff = -1; continue; }
        if (argv[a][0] == 'S') {   /* 陽性対照 setter: 1 水準 (DSP 側の単位の値を与える) */
            char* eq = strchr(argv[a], '='); int id = (int)strtol(argv[a] + 1, 0, 16); float f = strtof(eq + 1, 0); unsigned bits; memcpy(&bits, &f, 4);
            res_t r = measure(id, bits, type); printf("PC ID 0x%x v=%g: setErr=%d diffB=%d outChanged=%d perr=%d\n", id, f, r.serr, r.nd, r.h != b1.h, r.perr); continue; }
        int id = (int)strtol(argv[a], 0, 16); printf("ID 0x%x:", id);
        for (int k = 0; k < 3; k++) {
            res_t r = measure(id, lv[k], type);
            printf(" [v=%.2f setErr=%d diffB=%d", fl[k], r.serr, r.nd);
            if (r.nd) { printf(" off="); for (int i = 0; i < r.nd && i < NOFF; i++) printf("%x,", r.offs[i]); }
            printf(" outChanged=%d perr=%d]", r.h != b1.h, r.perr);
        }
        printf("\n");
    }
    return 0;
}
