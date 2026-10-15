/* qfc_ov.c — QuickFontCache の longjmp 相当 (VA 0x40f9c0) を C 実装に置換する override (T-SH-77 / #3410)。
 * x64c の --override 0x40f9c0=qfc_ov_longjmp で使う (qfc_boot.sh)。FLEngine の fle_ov_longjmp (tools/flelift/boot/fle_boot.c) と同型。
 * 0x40f9c0: rcx = jmp_buf (setjmp 0x40f950 が保存した領域), edx = retval。レジスタ・xmm6..15 を復元し rsp を戻して [buf] (戻り番地) へ dispatch。
 *
 * #4510: 復元した継続を longjmp 元の C フレームの上で dispatch すると、継続の ret が古い C フレーム
 * (f_40fa40 → f_40fb80) へ戻り、呼出し site の後行 (ExitProcess(0)) に届く偽の停止になる。実機の longjmp は戻らないので、
 * 継続は C の呼出し階層を捨てた状態で実行する。qfc_run が setjmp アンカーを張り、qfc_ov_longjmp はそこへ longjmp して
 * 戻り先を qfc_run の直下から dispatch する。 */
#include <setjmp.h>
#include "fle_cpu.h"

extern uint64_t fle_run(uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3,
                        uint64_t x0, uint64_t x1, uint64_t x2, uint64_t x3);

static jmp_buf qfc_anchor;
static uint64_t qfc_target;

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
    qfc_target = LD64(buf);
    longjmp(qfc_anchor, 1);
}

uint64_t qfc_run(uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3,
                 uint64_t x0, uint64_t x1, uint64_t x2, uint64_t x3) {
    if (setjmp(qfc_anchor) == 0)
        return fle_run(va, a0, a1, a2, a3, x0, x1, x2, x3);
    ott_dispatch(qfc_target);
    return R[RAX];
}
