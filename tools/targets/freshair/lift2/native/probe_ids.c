/* probe_ids.c — FA-7: Filter model ctor (0x180b4c040) を実機機械語で構築し、param ID descriptor 表 (M+8 vector, rec = M+0x19b8+0x148*k) を dump する。
 *   ./probe_ids <core> [model_ctor_va=0x180b4c040]  → stdout: "ID desc_off cell_off(-1=dummy 0x9db8) ..." */
#include "pe_map.h"
#include "native_shim.h"
typedef long long (__attribute__((ms_abi)) *ctor_t)(void*, void*);
int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]); guard_install();
    static const unsigned long long stubs[] = {0x18103d37c, 0x18103d47c, 0x18102f728};
    for (unsigned k = 0; k < sizeof stubs / sizeof *stubs; k++) im[stubs[k] - 0x180000000ULL] = 0xCC;
    { unsigned char* p = im + (0x18100c72cULL - 0x180000000ULL);
      if (p[0] == 0x65 && p[1] == 0x4c && p[2] == 0x8b && p[3] == 0x1c) { static const unsigned char G[9] = {0x4d,0x31,0xdb,0x90,0x90,0x90,0x90,0x90,0x90}; memcpy(p, G, 9); }
      unsigned char* q = im + (0x18100c738ULL - 0x180000000ULL); if (q[0] == 0x73) q[0] = 0xEB; }
    g_heap_zero = 1;
    patch_iat("iat_slots.txt"); patch_pokes("pokes.txt");
    unsigned long long va = argc > 2 ? strtoull(argv[2], 0, 16) : 0x180b4c040ULL;
    unsigned char* P = gr_alloc(0xa400); static unsigned long long dummy[4];
    g_in_guard = 1; int s = sigsetjmp(g_jb, 1);
    if (s == 0) ((ctor_t)va)(P, dummy);
    g_in_guard = 0;
    if (s) { fprintf(stderr, "ctor ERR sig=%d rip=%llx addr=%llx\n", g_fault_sig, g_fault_rip, g_fault_addr); return 3; }
    uint64_t vb, ve; memcpy(&vb, P + 8, 8); memcpy(&ve, P + 0x10, 8);
    int n = (int)((ve - vb) / 8);
    printf("# ids=%d vecbase_off=%lld\n", n, (long long)(vb - (uint64_t)P));
    for (int id = 0; id < n; id++) {
        uint64_t d; memcpy(&d, (void*)(vb + id * 8), 8); if (!d) { printf("%d null\n", id); continue; }
        unsigned char* D = (unsigned char*)d; uint32_t did; memcpy(&did, D, 4);
        uint64_t cell, obj; memcpy(&cell, D + 0x28, 8); memcpy(&obj, D + 0x38, 8);
        printf("%d desc_id=%d desc_off=0x%llx cell_off=0x%llx obj=%s flags24=%02x41=%02x42=%02x def=%08x\n", id, did,
               (unsigned long long)(D - P), (unsigned long long)((unsigned char*)cell - P),
               obj ? "set" : "null", D[0x24], D[0x41], D[0x42], *(uint32_t*)(D + 4));
    }
    if (getenv("FA_OBJ")) for (int id = 0; id < n; id++) {   /* descriptor +0x38 obj の先頭 0x50B (vtable VA / 値域 float 候補) */
        uint64_t d; memcpy(&d, (void*)(vb + id * 8), 8); unsigned char* D = (unsigned char*)d; uint64_t obj; memcpy(&obj, D + 0x38, 8);
        if (!obj) continue; uint64_t vt; memcpy(&vt, (void*)obj, 8);
        printf("OBJ %d vt=%llx raw=", id, (unsigned long long)vt); hexdump((void*)(obj + 8), 0x38); printf(" D0x08=");
        hexdump(D + 8, 0x1c); printf("\n");
    }
    return 0;
}
