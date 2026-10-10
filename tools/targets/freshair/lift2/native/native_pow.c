/* native_pow.c — SlateCore UCRT powf (0x18103fd60) を実機機械語で実行。
 *   ./native_pow <core> <cases.txt>   各行: xbits ybits fma(0/1) → "R <resultbits>" or "ERR"
 * error handler (0x18105b4a4 以下 CRT _matherr 経路) は機械語のまま実行。fastfail/throw 系は int3=ERR (wasm stub と同一)。 */
#include "pe_map.h"
#include "native_shim.h"
typedef float (__attribute__((ms_abi)) *powf_t)(float, float);
int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]);
    guard_install();
    static const unsigned long long stubs[] = {0x18103d37c, 0x18103d47c, 0x18102f728};
    for (unsigned k = 0; k < sizeof stubs / sizeof *stubs; k++) im[stubs[k] - 0x180000000ULL] = 0xCC;
    patch_iat(getenv("FA_IAT") ? getenv("FA_IAT") : "iat_slots.txt");
    patch_pokes(getenv("FA_POKES") ? getenv("FA_POKES") : "pokes.txt");
    powf_t fn = (powf_t)0x18103fd60ULL; volatile int* flag = (int*)0x1813070f8ULL;
    FILE* fp = fopen(argv[2], "r"); char line[256];
    while (fgets(line, sizeof line, fp)) {
        unsigned x, y, f; sscanf(line, "%x %x %x", &x, &y, &f);
        float fx, fy; memcpy(&fx, &x, 4); memcpy(&fy, &y, 4); *flag = f;
        g_in_guard = 1; int s = sigsetjmp(g_jb, 1);
        if (s == 0) { float r = fn(fx, fy); unsigned rb; memcpy(&rb, &r, 4); printf("R %08x\n", rb); }
        else { printf("ERR\n"); if (getenv("FA_DBG")) fprintf(stderr, "ERR sig=%d rip=%llx ret=%llx\n", g_fault_sig, g_fault_rip, g_fault_ret); }
        g_in_guard = 0;
    }
    return 0;
}
