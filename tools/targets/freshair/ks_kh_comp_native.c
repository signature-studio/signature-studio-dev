/* ks_kh_comp_native.c — KH Compressor (HeartCore compressor::CompressorDsp の process 0x1802abc20) を
 * 実機 x86-64 機械語のまま実行する参照ハーネス (FA-38 / #3506)。
 *   ks_kh_comp_native <HeartCore.core_64> <ncases> <seed>  → stdout に 1 case 1 行
 * 入力の写像は HeartCore の機械語の読みで決めた (根拠は REPORT_APPENDIX_FA38.md §2):
 *   process(rcx=this, rdx=ctx, r8=aud)。ctx+0x3188 = P (param 16 B 系の小さい block)、
 *   ctx+0x3198 = Q (フラグ 0xfc/0xdc/0x11c・係数 0x68)、ctx+0x31a8 = 副 entry 配列 (entry+0x40 < 0 で副入力を
 *   使わない)、ctx+0x31b0 = 通知 vector (begin +0x60 / end +0x68 / cap +0x70)、ctx+0x3180 = 通知 id。
 *   aud+0 = L、aud+8 = R、aud+0x28 = n。this+0xc4 = 初回フラグ (1 で初期化経路)。
 * CHECK_NEG=1 のとき NEG_OFF (既定 0x10) の P フィールドを NEG_MUL (既定 0.5) 倍する (感度の負例)。
 * ERR は SIGSEGV/SIGILL/SIGTRAP を捕捉して数える。未束縛 import は戻り 0 の stub に置換 (件数と呼び出し元を SUMMARY/UNRES に出す)。
 */
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <setjmp.h>
#include <signal.h>
#include <ucontext.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

typedef long long (__attribute__((ms_abi)) *fn_t)(void*, void*, void*);

#define PROC_VA 0x1802abc20ULL
#define MAXN 128

static uint64_t unres_hits;
static uint64_t __attribute__((ms_abi)) stub_ret0(void) { return 0; }
static uint64_t unres_site[8], unres_cnt[8];
static uint64_t __attribute__((ms_abi)) stub_unres(void) {
    unres_hits++;
    uint64_t ra = (uint64_t)(uintptr_t)__builtin_return_address(0);
    int i = 0;
    while (i < 8 && unres_site[i] && unres_site[i] != ra) i++;
    if (i < 8) { unres_site[i] = ra; unres_cnt[i]++; }
    return 0;
}

/* FLS (FA-57 / #4622): index ごとの値の表と g_lasterr。index は 0x182989860 (HeartCore の .data) に入る。
 * FLS_IDX 未指定 (-1) のときは FlsSetValue が FALSE を返す (現行の stub の戻り 0 と同じ)。 */
#define FLS_N 64
static uint64_t fls_val[FLS_N];
static uint32_t g_lasterr;
static uint64_t fls_set_calls, fls_set_ok;
static uint64_t __attribute__((ms_abi)) fls_set(uint32_t idx, uint64_t val) {
    fls_set_calls++;
    if (idx >= FLS_N) return 0;
    fls_set_ok++;
    fls_val[idx] = val; return 1;
}
static uint64_t __attribute__((ms_abi)) fls_get(uint32_t idx) {
    if (idx >= FLS_N) return 0;
    return fls_val[idx];
}
static uint64_t __attribute__((ms_abi)) set_lasterr(uint32_t e) { g_lasterr = e; return 0; }

/* IAT の未束縛スロット (ファイル上は hint/name RVA のまま) を stub に差替える。
 * GetLastError は 0 を返す (fault 経路で呼ばれる)。他の import を呼んだら unres_hits を増やす。 */
static void patch_iat(uint8_t* m, uint32_t pe) {
    uint32_t imp_rva; memcpy(&imp_rva, m + pe + 144, 4);
    for (uint8_t* d = m + imp_rva; ; d += 20) {
        uint32_t oft, ft; memcpy(&oft, d, 4); memcpy(&ft, d + 16, 4);
        if (!oft && !ft) break;
        uint32_t int_rva = oft ? oft : ft;
        for (uint32_t k = 0;; k++) {
            uint64_t ent; memcpy(&ent, m + int_rva + 8 * k, 8);
            if (!ent) break;
            void* fp = (void*)stub_unres;
            if (!(ent >> 63) && !strcmp((const char*)m + (uint32_t)ent + 2, "GetLastError")) fp = (void*)stub_ret0;
            if (getenv("FLS_IDX") && !(ent >> 63)) {
                const char* nm = (const char*)m + (uint32_t)ent + 2;
                if (!strcmp(nm, "FlsSetValue")) fp = (void*)fls_set;
                else if (!strcmp(nm, "FlsGetValue")) fp = (void*)fls_get;
                else if (!strcmp(nm, "SetLastError")) fp = (void*)set_lasterr;
            }
            uint64_t v = (uint64_t)(uintptr_t)fp;
            memcpy(m + ft + 8 * k, &v, 8);
        }
    }
}

static uint8_t* map_pe(const char* path) {
    int fd = open(path, O_RDONLY); if (fd < 0) { perror("open"); exit(2); }
    off_t sz = lseek(fd, 0, SEEK_END);
    uint8_t* f = mmap(NULL, sz, PROT_READ, MAP_PRIVATE, fd, 0);
    uint32_t pe; memcpy(&pe, f + 0x3c, 4);
    uint16_t ns, osz; memcpy(&ns, f + pe + 6, 2); memcpy(&osz, f + pe + 20, 2);
    uint64_t base; memcpy(&base, f + pe + 24 + 24, 8);
    uint32_t img; memcpy(&img, f + pe + 24 + 56, 4);
    uint8_t* m = mmap((void*)base, (img + 4095) & ~4095UL, PROT_READ | PROT_WRITE | PROT_EXEC,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (m != (void*)base) { fprintf(stderr, "map fail %p\n", m); exit(3); }
    uint32_t hdr; memcpy(&hdr, f + pe + 24 + 60, 4);
    memcpy(m, f, hdr);
    for (int i = 0; i < ns; i++) {
        uint8_t* s = f + pe + 24 + osz + i * 40;
        uint32_t vs, va, rs, rp; memcpy(&vs, s + 8, 4); memcpy(&va, s + 12, 4); memcpy(&rs, s + 16, 4); memcpy(&rp, s + 20, 4);
        memcpy(m + va, f + rp, rs < vs ? rs : vs);
    }
    patch_iat(m, pe);
    return m;
}

static uint32_t rng;
static uint32_t R32(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return rng; }
static float RF(float lo, float hi) { return lo + (hi - lo) * ((R32() >> 8) / 16777216.0f); }
static float RLG(float lo, float hi) { return powf(10.0f, RF(lo, hi)); }
static float RFS(float lo, float hi) {
    switch (R32() % 16) {
    case 0: return 0.0f;
    case 1: return lo;
    case 2: return hi;
    case 3: return 1e-20f;
    default: return RF(lo, hi);
    }
}

static sigjmp_buf jb;
static volatile int in_guard;
static volatile unsigned long long fault_rip, fault_addr;
static void on_fault(int sig, siginfo_t* si, void* uc) {
    if (in_guard) {
        fault_rip = (unsigned long long)((ucontext_t*)uc)->uc_mcontext.gregs[REG_RIP];
        fault_addr = (unsigned long long)si->si_addr;
        siglongjmp(jb, sig);
    }
    signal(sig, SIG_DFL); raise(sig);
}

static void hexdump(const void* p, size_t n) { const uint8_t* b = p; for (size_t i = 0; i < n; i++) printf("%02x", b[i]); }

int main(int argc, char** argv) {
    if (argc < 4) { fprintf(stderr, "usage: ks_kh_comp_native <HeartCore.core_64> <ncases> <seed>\n"); return 2; }
    int nc = atoi(argv[2]);
    rng = (uint32_t)strtoul(argv[3], 0, 0) * 2654435761u + 12345u; if (!rng) rng = 1;
    int neg = getenv("CHECK_NEG") && getenv("CHECK_NEG")[0] == '1';
    uint8_t* im = map_pe(argv[1]);
    (void)im;
    if (getenv("FLS_IDX")) {
        /* FLS index slot (HeartCore の RVA 0x189860 相当は .data 上の絶対 VA 0x182989860) */
        int32_t fi = (int32_t)strtol(getenv("FLS_IDX"), 0, 0);
        memcpy((void*)(uintptr_t)0x182989860ULL, &fi, 4);
    }
    fn_t proc = (fn_t)PROC_VA;
    struct sigaction sa; memset(&sa, 0, sizeof sa); sa.sa_sigaction = on_fault; sa.sa_flags = SA_SIGINFO | SA_NODEFER;
    sigaction(SIGSEGV, &sa, 0); sigaction(SIGILL, &sa, 0); sigaction(SIGTRAP, &sa, 0); sigaction(SIGBUS, &sa, 0);
    int err = 0, nvec_total = 0, nzero = 0, changed = 0;
    for (int ci = 0; ci < nc; ci++) {
        static const float srs[] = {44100.0f, 48000.0f, 96000.0f, 22050.0f};
        int n = (int)(R32() % (MAXN + 1));
        int mode = (int)(R32() % 3);
        int first = (int)(R32() & 1);
        uint8_t* self = calloc(1, 0x200);
        uint8_t* ctx = calloc(1, 0x3200);
        uint8_t* P = calloc(1, 0x40);
        uint8_t* Q = calloc(1, 0x140);
        uint8_t* V = calloc(1, 0x80);
        uint8_t* aud = calloc(1, 0x40);
        uint8_t* ent = calloc(1, 0x80);
        uint8_t** tab = calloc(3, 8);
        int* vec = calloc(16, 4);
        float *L = calloc(MAXN + 1, 4), *R = calloc(MAXN + 1, 4);
        for (int i = 0; i < n; i++) { L[i] = RFS(-1, 1); R[i] = RFS(-1, 1); }
        /* this (state): sr は +0x60。初回フラグ +0xc4 */
        *(float*)(self + 0x60) = srs[R32() & 3];
        *(float*)(self + 0x6c) = RF(0, 1);
        *(float*)(self + 0x70) = RLG(-4, 0);
        *(float*)(self + 0x74) = RF(0, 3);
        *(float*)(self + 0x78) = RF(0, 1);
        *(float*)(self + 0x80) = RF(0, 1); *(float*)(self + 0x84) = RF(0, 1);
        *(float*)(self + 0x88) = RF(0, 1); *(float*)(self + 0x8c) = RF(0, 1);
        *(float*)(self + 0x9c) = RF(0, 1); *(float*)(self + 0xa0) = RF(0, 1);
        *(float*)(self + 0xa4) = RF(0.5f, 1.0f);
        *(float*)(self + 0xa8) = RF(0, 1); *(float*)(self + 0xac) = RF(0, 1);
        *(float*)(self + 0xb0) = RF(0, 1); *(float*)(self + 0xb4) = RF(0, 1);
        *(float*)(self + 0xb8) = RF(0, 1); *(float*)(self + 0xbc) = RF(0, 1); *(float*)(self + 0xc0) = RF(0, 1);
        self[0xc4] = (uint8_t)first;
        *(float*)(self + 0xc8) = RF(0, 1);
        /* P (ctx+0x3188) */
        *(float*)(P + 0x00) = RLG(-4, 0);
        *(float*)(P + 0x04) = RLG(-3, 0.3f);
        *(int*)(P + 0x08) = mode;
        *(float*)(P + 0x10) = RFS(0, 2);
        *(float*)(P + 0x14) = RF(0.1f, 2.0f);
        *(float*)(P + 0x1c) = RF(0, 1);
        *(int*)(P + 0x24) = 0;
        *(int*)(P + 0x28) = 0;
        if (neg) *(float*)(P + (getenv("NEG_OFF") ? strtol(getenv("NEG_OFF"), 0, 0) : 0x10)) *= (getenv("NEG_MUL") ? atof(getenv("NEG_MUL")) : 0.5);
        /* Q (ctx+0x3198) */
        *(float*)(Q + 0x68) = RF(0, 1);
        Q[0xfc] = (uint8_t)(R32() & 1); Q[0xdc] = (uint8_t)(R32() & 1); Q[0x11c] = (uint8_t)(R32() & 1);
        /* 副入力 entry: +0x40 < 0 で副入力を使わない (aud の L/R を使う) */
        *(int*)(ent + 0x40) = -1;
        tab[0] = ent;
        /* 通知 vector (begin/end/cap) */
        *(int**)(V + 0x60) = vec; *(int**)(V + 0x68) = vec; *(int**)(V + 0x70) = vec + 16;
        *(void**)(ctx + 0x3188) = P; *(void**)(ctx + 0x3198) = Q; *(void**)(ctx + 0x31b0) = V;
        *(void**)(ctx + 0x31a8) = tab;
        *(int*)(ctx + 0x3180) = 2000;
        *(float**)(aud + 0) = L; *(float**)(aud + 8) = R; *(int*)(aud + 0x28) = n;
        printf("C%d n=%d mode=%d first=%d ", ci, n, mode, first);
        float *Lin = malloc((MAXN + 1) * 4), *Rin = malloc((MAXN + 1) * 4);
        memcpy(Lin, L, (MAXN + 1) * 4); memcpy(Rin, R, (MAXN + 1) * 4);
        in_guard = 1;
        int s = sigsetjmp(jb, 1);
        if (s == 0) proc(self, ctx, aud);
        in_guard = 0;
        if (s != 0) { err++; printf("ERR sig=%d rip=%llx addr=%llx\n", s, fault_rip, fault_addr); continue; }
        int np = (int)(*(int**)(V + 0x68) - vec);
        nvec_total += np;
        if (np == 0) nzero++;
        if (n && (memcmp(L, Lin, n * 4) || memcmp(R, Rin, n * 4))) changed++;
        printf("nv=%d ", np);
        for (int i = 0; i < np; i++) printf("%08x", (uint32_t)(vec[i] - 2000));
        printf(" ");
        hexdump(self + 0x60, 0x70); printf(" ");
        hexdump(P + 0x18, 0x0c); printf(" ");
        if (n) { hexdump(L, n * 4); printf(" "); hexdump(R, n * 4); } else printf("- -");
        printf("\n");
    }
    fprintf(stderr, "SUMMARY cases=%d err=%d audio_changed_cases=%d notify_total=%d no_notify_cases=%d unresolved_import_calls=%llu\n", nc, err, changed, nvec_total, nzero, (unsigned long long)unres_hits);
    if (getenv("FLS_IDX")) fprintf(stderr, "FLS fls_set_calls=%llu fls_set_ok=%llu\n", (unsigned long long)fls_set_calls, (unsigned long long)fls_set_ok);
    for (int i = 0; i < 8 && unres_site[i]; i++)
        fprintf(stderr, "UNRES site=%llx count=%llu\n", (unsigned long long)unres_site[i] - 5, (unsigned long long)unres_cnt[i]);
    return err ? 1 : 0;
}
