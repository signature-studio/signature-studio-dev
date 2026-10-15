/* qfc_ov.c — QuickFontCache の longjmp 相当 (VA 0x40f9c0) を C 実装に置換する override (T-SH-77 / #3410)。
 * x64c の --override 0x40f9c0=qfc_ov_longjmp で使う (qfc_boot.sh)。FLEngine の fle_ov_longjmp (tools/flelift/boot/fle_boot.c) と同型。
 * 0x40f9c0: rcx = jmp_buf (setjmp 0x40f950 が保存した領域), edx = retval。レジスタ・xmm6..15 を復元し rsp を戻して [buf] (戻り番地) へ dispatch。 */
#include "fle_cpu.h"

void qfc_ov_longjmp(void) {
    uint64_t buf = R[1];
    uint32_t retval = R[2] & 0xffffffff;
    R[0] = retval;
    R[3] = LD64(buf + 0x10);
    R[5] = LD64(buf + 0x18);
    R[6] = LD64(buf + 0x20);
    R[7] = LD64(buf + 0x28);
    R[12] = LD64(buf + 0x30); R[13] = LD64(buf + 0x38); R[14] = LD64(buf + 0x40); R[15] = LD64(buf + 0x48);
    for (int k = 0; k < 10; k++) X[6 + k] = LDX(buf + 0x50 + 16 * k);
    R[4] = LD64(buf + 8);
    ott_dispatch(LD64(buf));
}
