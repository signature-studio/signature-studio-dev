/* probe7fa80.c — 0x180b7fa80 (係数オーケストレーション) を直接呼ぶ native プローブ。
 *   ./probe7fa80 <core> <iat> <pokes>
 * sig (= 呼出 site 180b6f1a3 の実引数配置, MS x64 positional):
 *   void f(void* block, int type, int order2, float A, float B, float C, float sr)
 *   A=P[0x9e0c] (xmm3), B=P[0x9e54] (stack+0x20), C=P[0x9e9c] (stack+0x28), sr=P[0x98] (stack+0x30) */
#include "pe_map.h"
#include "native_shim.h"
typedef void (__attribute__((ms_abi)) *fn_t)(void*, int, int, float, float, float, float);
int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]); guard_install();
    patch_iat(argc > 3 ? argv[3] : "iat_slots.txt");
    patch_pokes(argc > 4 ? argv[4] : "pokes.txt");
    fn_t fn = (fn_t)0x180b7fa80ULL;
    for (int type = 0; type <= 7; type++)
        for (int order = 0; order <= 5; order++) {
            static uint8_t blk[0x320];
            memset(blk, 0, sizeof blk);
            fn(blk, type, order * 2, 1000.0f, 0.70710678f, 0.5f, 48000.0f);
            printf("t%d o%d blk=", type, order); hexdump(blk, 0x320); printf("\n");
        }
    return 0;
}
