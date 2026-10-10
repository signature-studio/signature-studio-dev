/* scen_common.h — scenario 共通部品: AudioBuffer {float* ch[0]@0; float* ch[1]@8; ...; int n@0x28}。 */
#ifndef SCEN_COMMON_H
#define SCEN_COMMON_H
#include "ctxfuzz.h"

typedef struct { float* L; float* R; int n; u8* raw; } Buf;

#define BUFCAP 256
static Buf mkbuf(int n, float amp) {
    Buf b;
    b.raw = A(0x30);
    b.L = A((size_t)(BUFCAP + 4) * 4); b.R = A((size_t)(BUFCAP + 4) * 4);
    for (int i = 0; i < n; i++) { b.L[i] = RF(-amp, amp); b.R[i] = RF(-amp, amp); }
    *(float**)(b.raw + 0) = b.L; *(float**)(b.raw + 8) = b.R; *(int*)(b.raw + 0x28) = n;
    b.n = n;
    REGION("bufL", b.L, (BUFCAP + 4) * 4); REGION("bufR", b.R, (BUFCAP + 4) * 4);
    return b;
}
/* 同じ AudioBuffer へ新しい入力を書く (n は容量以下) */
static void refill(Buf* b, int n, float amp) {
    for (int i = 0; i < n; i++) { b->L[i] = RF(-amp, amp); b->R[i] = RF(-amp, amp); }
    *(int*)(b->raw + 0x28) = n;
}
static inline int pick_n(void) {
    static const int fixed[] = {0, 1, 2, 3, 4, 7, 16, 33, 64, 129};
    return (R32() & 3) ? fixed[R32() % 10] : RI(1, 200);
}
#endif
