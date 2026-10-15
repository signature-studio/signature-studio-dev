/* x87_diff_main.h — x87 差分試験の共通 driver (native / lowered の両方が include する)。
 * 入力 (stdin, 1 trial = 1 行): 8 個の slot 値 (16 桁 hex u64) + n + n 組の (op id, slot 番号 or -1) + d (終了時のスタック深さ)。
 * 出力 (stdout, 1 trial = 1 行): F (op ごとの FSW & 0x7d00 の hex 4 桁) V (ST(0..d-1) の double bits) S (slot 8 個の u64)。
 * 呼び出し側は ops_init() / ops_exec(id, p) / ops_fsw() / ops_final(out, d) を定義する。 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

static uint64_t slots[8] __attribute__((aligned(16)));

static uint64_t dbits(double v) { uint64_t u; memcpy(&u, &v, 8); return u; }

int main(void) {
    unsigned long long s[8];
    double out[8];
    for (;;) {
        int n, d, k;
        for (k = 0; k < 8; k++)
            if (scanf("%llx", &s[k]) != 1) return 0;
        if (scanf("%d", &n) != 1) return 1;
        for (k = 0; k < 8; k++) slots[k] = s[k];
        int ids[16], sl[16];
        for (k = 0; k < n; k++)
            if (scanf("%d %d", &ids[k], &sl[k]) != 2) return 1;
        if (scanf("%d", &d) != 1) return 1;
        ops_init();
        printf("F");
        for (k = 0; k < n; k++) {
            ops_exec(ids[k], sl[k] >= 0 ? (void*)&slots[sl[k]] : NULL);
            printf(" %04x", ops_fsw() & 0x7d00u);
        }
        ops_final(out, d);
        printf(" V");
        for (k = 0; k < d; k++) printf(" %016llx", (unsigned long long)dbits(out[k]));
        printf(" S");
        for (k = 0; k < 8; k++) printf(" %016llx", (unsigned long long)slots[k]);
        printf("\n");
    }
}
