/* shimx の CP_ACP 変換を実測する probe (H14 / #549)。
 *   node probe.cjs <acp> <hex> ...  → 各 <hex> (ANSI バイト列) を MultiByteToWideChar(CP_ACP) で UTF-16 にした結果を
 *   "<acp> <入力hex> <UTF-16LE hex | ERR:<GetLastError>>" の 1 行で出力する。acp=0 は shimx 既定 (shimx_set_acp を呼ばない)。
 *   "GETACP" 行で GetACP() も出す。 */
#include "../../../shimx/src/shimx.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char** argv) {
    if (argc < 2) return 2;
    unsigned acp = (unsigned)strtoul(argv[1], NULL, 10);
    if (acp) shimx_set_acp(acp);
    printf("GETACP %u\n", GetACP());
    for (int i = 2; i < argc; i++) {
        size_t n = strlen(argv[i]) / 2;
        char in[512];
        for (size_t k = 0; k < n; k++) { unsigned v; sscanf(argv[i] + 2 * k, "%2x", &v); in[k] = (char)v; }
        WCHAR w[512];
        SetLastError(0);
        int r = MultiByteToWideChar(CP_ACP, MB_ERR_INVALID_CHARS, in, (int)n, w, 512);
        printf("%u %s ", GetACP(), argv[i]);
        if (r <= 0) { printf("ERR:%u\n", GetLastError()); continue; }
        for (int k = 0; k < r; k++) printf("%02x%02x", w[k] & 255, w[k] >> 8);
        printf("\n");
    }
    return 0;
}
