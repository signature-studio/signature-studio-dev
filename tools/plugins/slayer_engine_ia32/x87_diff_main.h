/* x87_diff_main.h — x87 差分試験の共通 driver (native / lowered の両方が include する)。
 * 入力 (stdin, 1 trial = 1 行): 8 個の slot (各 slot は 16 桁 hex の lo と hi の 2 語) + n + n 組の (op id, slot 番号 or -1) + d (終了時のスタック深さ)。
 *   slot は 16 byte。 80bit 値 (m80) は lo = 仮数 64bit、hi の下位 16bit = 符号・指数。 他の型は lo だけを使う (hi = 0)。
 * 出力 (stdout, 1 trial = 1 行): F (op ごとの FSW & 0x7f00 (C3/C2/C1/C0/TOP) の hex 4 桁) V (ST(0..d-1) の double bits) S (slot 8 個の lo hi)。
 * 呼び出し側は ops_init() / ops_exec(id, p) / ops_fsw() / ops_final(out, d) を定義する。 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

static uint64_t slots[8][2] __attribute__((aligned(16)));
uint8_t envbuf[128] __attribute__((aligned(16)));   /* 環境・fnsave 領域 (slot 番号 8 で指す。 lowered の inc が extern で参照) */

static uint64_t dbits(double v) { uint64_t u; memcpy(&u, &v, 8); return u; }

int main(void) {
    unsigned long long s[16];
    double out[8];
    for (;;) {
        int n, d, k;
        for (k = 0; k < 16; k++)
            if (scanf("%llx", &s[k]) != 1) return 0;
        if (scanf("%d", &n) != 1) return 1;
        for (k = 0; k < 8; k++) { slots[k][0] = s[2 * k]; slots[k][1] = s[2 * k + 1]; }
        int ids[16], sl[16];
        for (k = 0; k < n; k++)
            if (scanf("%d %d", &ids[k], &sl[k]) != 2) return 1;
        if (scanf("%d", &d) != 1) return 1;
        ops_init();
        memset(envbuf, 0, sizeof envbuf);
        unsigned rec[16][3];
        printf("F");
        for (k = 0; k < n; k++) {
            void* p = sl[k] == 8 ? (void*)envbuf : sl[k] >= 0 ? (void*)&slots[sl[k]][0] : NULL;
            ops_exec(ids[k], p);
            printf(" %04x", ops_fsw() & 0x7f00u);
            if (sl[k] == 8) {   /* 環境の格納値のうち比べる欄だけ (CW・SW の CMASK・TW)。 FIP/FOO 等は実アドレスなので除く */
                uint16_t cw, sw, tw;
                memcpy(&cw, envbuf, 2); memcpy(&sw, envbuf + 4, 2); memcpy(&tw, envbuf + 8, 2);
                rec[k][0] = cw; rec[k][1] = sw & 0x7d00u; rec[k][2] = tw;
            }
        }
        ops_final(out, d);
        printf(" V");
        for (k = 0; k < d; k++) printf(" %016llx", (unsigned long long)dbits(out[k]));
        printf(" S");
        for (k = 0; k < 8; k++) printf(" %016llx %016llx", (unsigned long long)slots[k][0], (unsigned long long)slots[k][1]);
        for (k = 0; k < n; k++)
            if (sl[k] == 8) printf(" E %04x %04x %04x", rec[k][0], rec[k][1], rec[k][2]);
        printf("\n");
    }
}
