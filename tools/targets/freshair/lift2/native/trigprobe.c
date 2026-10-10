/* trigprobe.c — tan (0x18104ad90) / log? (0x18104f698) / bigmath (0x181046890) を直接呼ぶ native プローブ。
 *   ./trigprobe <core> <iat> <pokes> <fmaflag>
 * sig: double f(double x) (positional: xmm0 → 戻り xmm0)。0x1813070f8 の fma flag を設定してから呼ぶ。 */
#include "pe_map.h"
#include "native_shim.h"
typedef double (__attribute__((ms_abi)) *fn_t)(double);
static const double xs[] = {
    0.0, 1e-12, 1e-9, 1e-6, 0.0001220703125, 0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 0.7071067811865476,
    1.0, 1.5, 2.0, 3.141592653589793, 4.0, 6.283185307179586, 10.0, 100.0, 1000.0, 48000.0,
    3.9894979, 0.035543, 0.35355339059327373, 1.4426950408889634, -1.0, -0.5, -3.141592653589793,
    0.7853981633974483, 1e10, 1e300, 4.9406564584124654e-324, 2.2250738585072014e-308,
};
int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]); guard_install();
    patch_iat(argc > 3 ? argv[3] : "iat_slots.txt");
    patch_pokes(argc > 4 ? argv[4] : "pokes.txt");
    volatile int* fma = (int*)0x1813070f8ULL;
    *fma = argc > 5 ? atoi(argv[5]) : 0;
    struct { const char* nm; unsigned long long va; } fns[] = {
        {"tan", 0x18104ad90ULL}, {"log", 0x18104f698ULL}, {"dkl", 0x18105d170ULL}, {"p78", 0x18105cf80ULL},
    };
    int nf = 4;
    for (int k = 0; k < nf; k++) {
        fn_t fn = (fn_t)fns[k].va;
        printf("%s", fns[k].nm);
        for (unsigned i = 0; i < sizeof xs / sizeof *xs; i++) {
            double r;
            r = fn(xs[i]);
            unsigned long long b; memcpy(&b, &r, 8);
            printf(" %llx", b);
        }
        printf("\n");
        fflush(stdout);
    }
    return 0;
}
