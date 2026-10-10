/* shimx 実装を実際にリンクしたことで顕在化した lift 誤りの最小 override (CAB-166)。
 * M11 の m11_win.c は SysFreeString 等を no-op にしていたため、lift の誤り (引数が 1 段浅い) が隠れていた。
 * shimx は BSTR を実際に free するので誤ポインタで abort する。ここでは逆アセンブルと突合した該当関数のみを C に転記する。
 * (m11_ov.c と同じ流儀: IR 側は weak define、ここは強定義で上書き。shim 本体の実装ではない。) */
#include <stdint.h>

typedef unsigned long long u64;
#define Q(lva) (*(volatile u64*)(uintptr_t)(lva))

extern void SysFreeString(void*);

/* function_412e00  VA 0x412e00  (System._WStrClr(var S: WideString)) — rcx=&S
 *   mov rax,[rbx]; test rax,rax; je skip; mov [rbp+28],rax; mov qword [rbx],0; mov rcx,[rbp+28]; call SysFreeString(0x407290)
 * RetDec は `[rbx]` の 1 段目を落とし, `if (&S) { S = 0; SysFreeString(&S) }` と誤 lift した (CAB-129 と同根: スピル経由の deref 脱落)。 */
unsigned long long function_412e00(void* arg) {   /* IR 署名 (ptr)->i64 に合わせる (署名不一致 = trap thunk 回避) */
    u64 p = (u64)(uintptr_t)arg;
    if (p) {
        u64 old = Q(p);
        if (old) {
            Q(p) = 0;
            SysFreeString((void*)(uintptr_t)old);
        }
    }
    return p;
}
