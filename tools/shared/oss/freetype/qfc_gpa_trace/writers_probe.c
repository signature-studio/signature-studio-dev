/* #3369 / T-SH-72: QuickFontCache の登録簿ポインタ [base+0x1d0c90] (VA 0x5d0c90) の書込み元を実行で記録する。
 * patch_writers.py が下の SITES の先頭バイトを int3 (0xCC) に置き換えた DLL を読み込み、本 VEH が
 * int3 で止まった命令を同じ意味でエミュレートしてから実行を続ける (素材の DllMain の流れは変えない)。
 *   W1  0x40f48b  mov [r13+0x10],rdx        (r13 = 0x5d0c80)    登録簿 = rdx を書く
 *   W2  0x40fcf5  rep movsq (rdi = 0x5d0c80, rcx = 0x25)        0x5d0c80 の 37 qword を復元 (第 3 qword が登録簿)
 *   他は到達の確認用 (call/push のエミュレーション)。
 * 注: Wine の ContextRecord->Rip は int3 の番地そのものを指す (+1 ではない)。
 */
#include <windows.h>
#include <stdio.h>
#include <stdint.h>

enum kind { K_W1, K_REPMOVS, K_PUSH_RDI, K_CALL_REL32, K_CALL_RBX, K_CALL_IND, K_MSGBOX_IDOK };
struct site {
    uint32_t rva;
    enum kind kind;
    const char *label;
};
static const struct site SITES[] = {
    {0xf48b, K_W1, "W1 mov [r13+0x10],rdx (0x40f48b)"},
    {0xfcf5, K_REPMOVS, "W2 rep movsq (0x40fcf5)"},
    {0xfb80, K_PUSH_RDI, "P1 0x40fb80 入口 push rdi"},
    {0xfb91, K_CALL_REL32, "P 0x40fb91 call 0x40f8b0"},
    {0xfb96, K_CALL_REL32, "P 0x40fb96 call 0x40faa0"},
    {0xfbb0, K_CALL_REL32, "P 0x40fbb0 call 0x406d90"},
    {0xfbcf, K_CALL_REL32, "P 0x40fbcf call 0x40fa40"},
    {0xfbf9, K_CALL_RBX, "P 0x40fbf9 call rbx"},
    {0xfc2b, K_CALL_REL32, "P 0x40fc2b call 0x409410"},
    {0xfc48, K_CALL_REL32, "P 0x40fc48 call 0x40f2f0"},
    {0xfad8, K_CALL_REL32, "P 0x40fad8 call 0x406d00"},
    {0xfafb, K_CALL_REL32, "P 0x40fafb call 0x406d10"},
    {0xfb14, K_CALL_REL32, "P 0x40fb14 call 0x410f20"},
    {0xfb33, K_CALL_REL32, "P 0x40fb33 call 0x406d10"},
    {0xfacd, K_CALL_IND, "P 0x40facd call [rip+..]"},
#ifdef SKIP_MSGBOX
    {0xfb56, K_MSGBOX_IDOK, "P 0x40fb56 call 0x406fb0 (user32!MessageBoxA): IDOK で即時に戻す (-DSKIP_MSGBOX)"},
#else
    {0xfb56, K_CALL_REL32, "P 0x40fb56 call 0x406fb0 (user32!MessageBoxA の jmp 経由)"},
#endif
};
#define NSITES (sizeof SITES / sizeof SITES[0])
#define REG_OFF 0x1d0c90u /* VA 0x5d0c90 - ImageBase 0x400000 */

static LONG WINAPI veh(PEXCEPTION_POINTERS ep) {
    CONTEXT *c = ep->ContextRecord;
    MEMORY_BASIC_INFORMATION mbi;
    uint8_t *addr, *base, *ip;
    uint64_t *reg;
    size_t i;
    if (ep->ExceptionRecord->ExceptionCode != EXCEPTION_BREAKPOINT) return EXCEPTION_CONTINUE_SEARCH;
    addr = (uint8_t *)(uintptr_t)c->Rip;
    if (!VirtualQuery(addr, &mbi, sizeof mbi)) return EXCEPTION_CONTINUE_SEARCH;
    if (*addr != 0xCC) addr -= 1;
    base = (uint8_t *)mbi.AllocationBase;
    ip = addr;
    for (i = 0; i < NSITES; i++) {
        const struct site *s = &SITES[i];
        if (ip != base + s->rva) continue;
        reg = (uint64_t *)(base + REG_OFF);
        switch (s->kind) {
        case K_W1: {
            uint64_t before = *reg;
            *(uint64_t *)(uintptr_t)(c->R13 + 0x10) = c->Rdx;
            c->Rip = (DWORD64)(uintptr_t)(ip + 4);
            /* 0x40f430 の戻り番地 = rbp+0x138、その呼出元 0x419dc0 の戻り番地 = rbp+0x1a8 */
            fprintf(stderr, "%s: r13=%llx rdx=%llx [0x5d0c90] before=%llx after=%llx caller(0x419dc0 ret)=%llx\n",
                    s->label, (unsigned long long)c->R13, (unsigned long long)c->Rdx,
                    (unsigned long long)before, (unsigned long long)*reg,
                    (unsigned long long)*(uint64_t *)(uintptr_t)(c->Rbp + 0x1a8));
            break;
        }
        case K_REPMOVS: {
            uint64_t n = c->Rcx, k, before = *reg;
            uint64_t *d = (uint64_t *)(uintptr_t)c->Rdi, *sp = (uint64_t *)(uintptr_t)c->Rsi;
            for (k = 0; k < n; k++) d[k] = sp[k];
            c->Rsi += 8 * n;
            c->Rdi += 8 * n;
            c->Rcx = 0;
            c->Rip = (DWORD64)(uintptr_t)(ip + 3);
            fprintf(stderr, "%s: n=%llu dst=%llx src=%llx [0x5d0c90] before=%llx after=%llx\n", s->label,
                    (unsigned long long)n, (unsigned long long)(c->Rdi - 8 * n),
                    (unsigned long long)(c->Rsi - 8 * n), (unsigned long long)before, (unsigned long long)*reg);
            break;
        }
        case K_PUSH_RDI:
            c->Rsp -= 8;
            *(uint64_t *)(uintptr_t)c->Rsp = c->Rdi;
            c->Rip = (DWORD64)(uintptr_t)(ip + 1);
            fprintf(stderr, "%s\n", s->label);
            break;
        case K_CALL_REL32: {
            int32_t rel = *(int32_t *)(ip + 1);
            c->Rsp -= 8;
            *(uint64_t *)(uintptr_t)c->Rsp = (uint64_t)(uintptr_t)(ip + 5);
            c->Rip = (DWORD64)(uintptr_t)(ip + 5 + rel);
            fprintf(stderr, "%s\n", s->label);
            break;
        }
        case K_CALL_IND: {
            int32_t disp = *(int32_t *)(ip + 2);
            uint64_t *slot = (uint64_t *)(uintptr_t)(ip + 6 + disp);
            c->Rsp -= 8;
            *(uint64_t *)(uintptr_t)c->Rsp = (uint64_t)(uintptr_t)(ip + 6);
            c->Rip = (DWORD64)*slot;
            fprintf(stderr, "%s -> %llx\n", s->label, (unsigned long long)*slot);
            break;
        }
        case K_MSGBOX_IDOK:
            c->Rax = 1;
            c->Rip = (DWORD64)(uintptr_t)(ip + 5);
            fprintf(stderr, "%s\n", s->label);
            break;
        case K_CALL_RBX:
            c->Rsp -= 8;
            *(uint64_t *)(uintptr_t)c->Rsp = (uint64_t)(uintptr_t)(ip + 2);
            c->Rip = c->Rbx;
            fprintf(stderr, "%s -> %llx\n", s->label, (unsigned long long)c->Rbx);
            break;
        }
        fflush(stderr);
        return EXCEPTION_CONTINUE_EXECUTION;
    }
    return EXCEPTION_CONTINUE_SEARCH;
}

int main(void) {
    HMODULE h;
    AddVectoredExceptionHandler(1, veh);
    printf("start\n");
    fflush(stdout);
    h = LoadLibraryW(L"QuickFontCache_x64.dll");
    printf("LoadLibrary=%p err=%lu\n", (void *)h, GetLastError());
    if (h) printf("final [base+0x1d0c90]=%p\n", *(void **)((char *)h + REG_OFF));
    fflush(stdout);
    return 0;
}
