/* probe_setval.c — FA-8: 実 ctor で構築した Filter model M に setter 0x1803debc0(M,id,v) を呼び、
 *   descriptor (M+desc_off, 0x48B) の setter 前後の全 dword と、DSP が読む M+0x9dc4/0x9e0c/0x9e54/0x9e9c/0x9ee4 の値を dump する。
 *   ./probe_setval <core> <id_dec> <desc_off_hex> <f32>...   → stdout: PRE/POST 行 */
#include "pe_map.h"
#include "native_shim.h"
typedef long long (__attribute__((ms_abi)) *ctor_t)(void*, void*);
typedef void (__attribute__((ms_abi)) *set_t)(void*, int, unsigned);
static void dump(const char* tag, unsigned char* M, unsigned off) {
    printf("%s desc@%x:", tag, off); for (int i = 0; i < 0x48; i += 4) printf(" %08x", *(uint32_t*)(M + off + i));
    printf(" | dsp:"); static const unsigned o[5] = {0x9dc4, 0x9e0c, 0x9e54, 0x9e9c, 0x9ee4};
    for (int i = 0; i < 5; i++) printf(" %x=%08x", o[i], *(uint32_t*)(M + o[i])); printf("\n");
}
int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]); guard_install();
    static const unsigned long long stubs[] = {0x18103d37c, 0x18103d47c, 0x18102f728};
    for (unsigned k = 0; k < sizeof stubs / sizeof *stubs; k++) im[stubs[k] - 0x180000000ULL] = 0xCC;
    { unsigned char* p = im + (0x18100c72cULL - 0x180000000ULL);
      if (p[0] == 0x65 && p[1] == 0x4c && p[2] == 0x8b && p[3] == 0x1c) { static const unsigned char G[9] = {0x4d,0x31,0xdb,0x90,0x90,0x90,0x90,0x90,0x90}; memcpy(p, G, 9); }
      unsigned char* q = im + (0x18100c738ULL - 0x180000000ULL); if (q[0] == 0x73) q[0] = 0xEB; }
    g_heap_zero = 1; patch_iat("iat_slots.txt"); patch_pokes("pokes.txt");
    static unsigned long long dummy[4]; unsigned char* M0 = gr_alloc(0xa400);
    g_in_guard = 1; int s = sigsetjmp(g_jb, 1);
    if (s == 0) ((ctor_t)0x180b4c040ULL)(M0, dummy);
    g_in_guard = 0; if (s) { fprintf(stderr, "ctor ERR\n"); return 3; }
    int id = atoi(argv[2]); unsigned off = (unsigned)strtoul(argv[3], 0, 16);
    for (int a = 4; a < argc; a++) {
        unsigned char* T = gr_alloc(0xa400); memcpy(T, M0, 0xa400); float f = strtof(argv[a], 0); unsigned v; memcpy(&v, &f, 4);
        printf("== id=%d v=%g\n", id, f); dump("PRE ", T, off);
        g_in_guard = 1; s = sigsetjmp(g_jb, 1);
        if (s == 0) ((set_t)0x1803debc0ULL)(T, id, v);
        g_in_guard = 0; dump("POST", T, off); printf("setErr=%d\n", s);
    }
    return 0;
}
