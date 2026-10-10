/* native_runner.c — 実機 x86-64 機械語参照ランナー (汎用)。
 *   PE イメージを ImageBase に VA 通り敷設 (MAP_FIXED_NOREPLACE) し, MS x64 ABI で関数を直接実行する。
 *   usage: native_runner <image.pe> <func_va_hex> <scenarios.txt> <out.txt>
 *   シナリオ形式は harness/spec.py 参照。各 C (call) の後に全バッファを dump する:
 *     R <scen> <step> <crash:0|1> <rax> <xmm0 lo>
 *     D <name> <hexbytes(ポインタ欄は 0 埋め)> <ptr tokens>
 *   各バッファは size+64 の guard (ゼロ) 付きで確保し guard も dump する (範囲外書込み検出)。
 */
#define _GNU_SOURCE
#include <ctype.h>
#include <fcntl.h>
#include <setjmp.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

typedef uint8_t u8; typedef uint32_t u32; typedef uint64_t u64;

struct ms_ctx { void* fn; u64 gpr[4]; u64 xmm[4]; u64 rax_out; u64 xmm0_out[2]; };
extern void ll_ms_call(struct ms_ctx*);

static void map_pe(const char* path) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) { perror("open image"); exit(2); }
    off_t sz = lseek(fd, 0, SEEK_END);
    u8* f = mmap(NULL, sz, PROT_READ, MAP_PRIVATE, fd, 0);
    u32 pe; memcpy(&pe, f + 0x3c, 4);
    uint16_t ns, osz; memcpy(&ns, f + pe + 6, 2); memcpy(&osz, f + pe + 20, 2);
    u64 base; memcpy(&base, f + pe + 24 + 24, 8);
    u32 img; memcpy(&img, f + pe + 24 + 56, 4);
    void* m = mmap((void*)base, (img + 4095) & ~4095UL, PROT_READ | PROT_WRITE | PROT_EXEC,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE | MAP_NORESERVE, -1, 0);
    if (m != (void*)base) { fprintf(stderr, "cannot map image at %llx\n", (unsigned long long)base); exit(3); }
    u32 hdr; memcpy(&hdr, f + pe + 24 + 60, 4);
    memcpy(m, f, hdr);
    for (int i = 0; i < ns; i++) {
        u8* s = f + pe + 24 + osz + i * 40;
        u32 vs, va, rs, rp; memcpy(&vs, s + 8, 4); memcpy(&va, s + 12, 4); memcpy(&rs, s + 16, 4); memcpy(&rp, s + 20, 4);
        memcpy((u8*)m + va, f + rp, rs < vs ? rs : vs);
    }
}

#define MAXB 32
#define GUARD 64
static struct { char name[32]; u8* p; size_t n; } bufs[MAXB]; static int nb;
static struct { int sb; size_t so; int db; size_t doff; } pf[256]; static int npf;
static struct { int slot; char kind[8]; u64 v; int pb; size_t po; } args[8]; static int nargs;

static int find(const char* nm) { for (int i = 0; i < nb; i++) if (!strcmp(bufs[i].name, nm)) return i; fprintf(stderr, "no buffer %s\n", nm); exit(4); }
static sigjmp_buf jb; static volatile int crashed;
static void on_sig(int s) { crashed = 1; siglongjmp(jb, 1); }

static void unhex(const char* h, u8* o, size_t n) { for (size_t i = 0; i < n; i++) { unsigned v; sscanf(h + 2 * i, "%2x", &v); o[i] = v; } }

static void apply_ptr(int i) { u64 a = (u64)(uintptr_t)(bufs[pf[i].db].p + pf[i].doff); memcpy(bufs[pf[i].sb].p + pf[i].so, &a, 8); }

static void dump_all(FILE* o) {
    for (int b = 0; b < nb; b++) {
        size_t n = bufs[b].n + GUARD;
        u8* tmp = malloc(n); memcpy(tmp, bufs[b].p, n);
        char tok[4096]; tok[0] = 0;
        for (int i = 0; i < npf; i++) if (pf[i].sb == b) {
            u64 v; memcpy(&v, bufs[b].p + pf[i].so, 8);
            memset(tmp + pf[i].so, 0, 8);
            const char* r = "?";
            char t[128]; int hit = 0;
            for (int d = 0; d < nb && !hit; d++) {
                u64 base = (u64)(uintptr_t)bufs[d].p;
                if (v >= base && v < base + bufs[d].n + GUARD) { snprintf(t, sizeof t, "%s+%llu", bufs[d].name, (unsigned long long)(v - base)); hit = 1; }
            }
            if (!hit) snprintf(t, sizeof t, "raw:%llx", (unsigned long long)v);
            r = t;
            char piece[160]; snprintf(piece, sizeof piece, "%zu=%s;", pf[i].so, r); strncat(tok, piece, sizeof tok - strlen(tok) - 1);
        }
        fprintf(o, "D %s ", bufs[b].name);
        for (size_t i = 0; i < n; i++) fprintf(o, "%02x", tmp[i]);
        fprintf(o, " %s\n", tok[0] ? tok : "-");
        free(tmp);
    }
}

int main(int argc, char** argv) {
    if (argc < 5) { fprintf(stderr, "usage: native_runner image func_va scen out\n"); return 2; }
    map_pe(argv[1]);
    u64 fva = strtoull(argv[2], NULL, 16);
    FILE* fi = fopen(argv[3], "r"); FILE* fo = fopen(argv[4], "w");
    if (!fi || !fo) { perror("io"); return 2; }
    struct sigaction sa; memset(&sa, 0, sizeof sa); sa.sa_handler = on_sig; sa.sa_flags = SA_NODEFER;
    sigaction(SIGSEGV, &sa, NULL); sigaction(SIGBUS, &sa, NULL); sigaction(SIGILL, &sa, NULL); sigaction(SIGFPE, &sa, NULL);
    static char line[1 << 22];
    int scen = -1, step = 0;
    while (fgets(line, sizeof line, fi)) {
        char* nl = strchr(line, '\n'); if (nl) *nl = 0;
        char c0[8], a[64], b[64], d[64]; unsigned long long x, y; int k;
        if (line[0] == 'S') { sscanf(line, "S %d", &scen); step = 0; for (int i = 0; i < nb; i++) free(bufs[i].p); nb = npf = nargs = 0; continue; }
        if (line[0] == 'B') {
            char nm[32]; size_t sz; sscanf(line, "B %31s %zu", nm, &sz);
            strcpy(bufs[nb].name, nm); bufs[nb].n = sz; bufs[nb].p = aligned_alloc(16, ((sz + GUARD) + 15) & ~15UL);
            memset(bufs[nb].p, 0, sz + GUARD);
            char* h = strrchr(line, ' ') + 1; unhex(h, bufs[nb].p, sz); nb++; continue;
        }
        if (!strncmp(line, "UP ", 3)) { char s[32], dn[32]; size_t so, doff; sscanf(line, "UP %31s %zu %31s %zu", s, &so, dn, &doff);
            int sb = find(s), db = find(dn); int i; for (i = 0; i < npf; i++) if (pf[i].sb == sb && pf[i].so == so) break;
            if (i == npf) npf++; pf[i].sb = sb; pf[i].so = so; pf[i].db = db; pf[i].doff = doff; apply_ptr(i); continue; }
        if (line[0] == 'P') { char s[32], dn[32]; size_t so, doff; sscanf(line, "P %31s %zu %31s %zu", s, &so, dn, &doff);
            pf[npf].sb = find(s); pf[npf].so = so; pf[npf].db = find(dn); pf[npf].doff = doff; apply_ptr(npf); npf++; continue; }
        if (line[0] == 'U') { char s[32]; size_t off; sscanf(line, "U %31s %zu", s, &off); char* h = strrchr(line, ' ') + 1; size_t hl = strlen(h) / 2; unhex(h, bufs[find(s)].p + off, hl); continue; }
        if (line[0] == 'A') {
            char kind[8], v[64]; int slot; sscanf(line, "A %d %7s %63s", &slot, kind, v);
            args[nargs].slot = slot; strcpy(args[nargs].kind, kind);
            if (!strcmp(kind, "ptr")) args[nargs].pb = find(v); else args[nargs].v = strtoull(v, NULL, 16);
            nargs++; continue;
        }
        if (line[0] == 'C') {
            struct ms_ctx c; memset(&c, 0, sizeof c); c.fn = (void*)(uintptr_t)fva;
            /* MS x64 ABI: float 引数は xmm を独立カウント, それ以外は gpr を独立カウント (A 行は宣言順) */
            int gp = 0, xp = 0;
            for (int i = 0; i < nargs; i++) {
                u64 val = !strcmp(args[i].kind, "ptr") ? (u64)(uintptr_t)bufs[args[i].pb].p : args[i].v;
                if (!strcmp(args[i].kind, "f32") || !strcmp(args[i].kind, "f64")) c.xmm[xp++] = val; else c.gpr[gp++] = val;
            }
            crashed = 0;
            if (sigsetjmp(jb, 1) == 0) ll_ms_call(&c);
            fprintf(fo, "R %d %d %d %016llx %016llx\n", scen, step, crashed, crashed ? 0ULL : (unsigned long long)c.rax_out, crashed ? 0ULL : (unsigned long long)c.xmm0_out[0]);
            dump_all(fo); step++; continue;
        }
        if (line[0] == 'E') { fprintf(fo, "E %d\n", scen); continue; }
    }
    return 0;
}
