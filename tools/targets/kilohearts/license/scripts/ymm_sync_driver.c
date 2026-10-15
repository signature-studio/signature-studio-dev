/* ymm_sync_check.py の実行器 (KH-51 #3306)。lowered IR の 3 関数 (A: VEX-128 で xmm2 を書く /
 * B: ymm2 を読んで vinsertf128 で書く / C: vzeroupper) を順に呼び、xmm2 と ymm2 の状態を検査する。
 * 終了コード 0 = 整合 (OK)、1 = 不一致 (MISMATCH)。 */
#include <stdio.h>
#include <string.h>

extern unsigned char xmm2[16];
extern unsigned char ymm2[32];
unsigned char kh_stack[65536] __attribute__((aligned(16)));

extern unsigned long long function_180f89cf0(unsigned long long, unsigned long long, unsigned long long, unsigned long long);
extern unsigned long long function_180fb6124(unsigned long long, unsigned long long, unsigned long long, unsigned long long);
extern unsigned long long function_180fb6130(unsigned long long, unsigned long long, unsigned long long, unsigned long long);

int main(void) {
    unsigned int got = 0, want = 0x12345678u + 257u;
    int bad = 0;
    function_180f89cf0(0, 0, 0, 0);
    function_180fb6124(0, 0, 0, 0);
    function_180fb6130(0, 0, 0, 0);
    memcpy(&got, xmm2, 4);
    if (got != want) bad |= 4;
    for (int k = 4; k < 16; k++) if (xmm2[k]) bad |= 4;
    if (memcmp(ymm2, xmm2, 16) != 0) bad |= 1;
    for (int k = 16; k < 32; k++) if (ymm2[k]) bad |= 2;
    if (bad) {
        printf("MISMATCH bits=%d xmm2=%08x ymm2_lo=%02x%02x%02x%02x ymm2_hi_nonzero=%d\n", bad, got,
               ymm2[3], ymm2[2], ymm2[1], ymm2[0], (int)(ymm2[16] | ymm2[17] | ymm2[18] | ymm2[19]));
        return 1;
    }
    printf("OK xmm2=%08x\n", got);
    return 0;
}
