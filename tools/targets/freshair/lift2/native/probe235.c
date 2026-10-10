/* probe235.c — 0x180d235b0 (多段係数設計) を直接呼ぶ native プローブ。
 *   ./probe235 <core> <iat_slots.txt>
 * sig: u64 f(u64 count, double gain, double sr, double freq, double Q, double gain2, u64 order2, void* out)
 *  (= 呼出 site 180b7fbe8 の実引数配置: rcx=count, xmm0=gain, xmm1=sr, xmm2=freq, xmm3=Q, [rsp+0x20]=gain, [rsp+0x28]=order2, [rsp+0x30]=out) */
#include "pe_map.h"
#include "native_shim.h"
typedef uint64_t (__attribute__((ms_abi)) *fn_t)(uint64_t, double, double, double, double, uint64_t, void*);
int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]); guard_install();
    patch_iat(argc > 3 ? argv[3] : "iat_slots.txt");
    patch_pokes(argc > 4 ? argv[4] : "pokes.txt");
    fn_t fn = (fn_t)0x180d235b0ULL;
    for (int count = 0; count <= 6; count++)
        for (int order2 = 0; order2 <= 10; order2 += 2) {
            uint8_t out[0x40]; memset(out, 0xCC, sizeof out);
            /* positional: rcx=count, xmm1=sr, xmm2=freq, xmm3=Q, +0x20=gain, +0x28=order2, +0x30=out */
            uint64_t r = fn((uint64_t)count, 48000.0, 1000.0, 0.7071067811865476, 0.5, (uint64_t)order2, out);
            printf("c%d o%d ret=%llx out=", count, order2, (unsigned long long)r);
            hexdump(out, 0x28); printf("\n");
        }
    return 0;
}
