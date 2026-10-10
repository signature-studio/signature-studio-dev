# lp_call.S — landing pad 実行用 trampoline (CAB-227).
# SysV で呼ばれ、pad の実機械語を「rbp = 親フレーム、非 live-in レジスタ = 0」で実行する。
#   void lp_call(void* fn /*rdi*/, u64 rbp_val /*rsi*/, const u64* gpr_in /*rdx: [rax,rcx,r8,r9]*/, u64* out /*rcx*/)
# pad は r12-r15 を触らない (実測: 656 断片中 0)。fn/out は r10/r11 经由 (pad は r10/r11 を読まない)。
# pad は reraise call (noreturn, 検証では entry patch で即 return) で終端し、通常の ret で戻る。
    .text
    .globl lp_call
    .type lp_call,@function
lp_call:
    pushq %rbx
    movq %rdi, %r10        # fn
    movq %rcx, %r11        # out
    movq %rsi, %rbp        # rbp = 親フレーム
    movq 0(%rdx), %rax     # live-in: rax
    movq 8(%rdx), %rcx     # live-in: rcx
    movq 16(%rdx), %r8     # live-in: r8
    movq 24(%rdx), %r9     # live-in: r9
    xorl %edx, %edx        # 非 live-in レジスタは 0 初期化 (wasm 側 IR と対称)
    xorl %esi, %esi
    xorl %edi, %edi
    call *%r10
    movq %rax, 0(%r11)
    popq %rbx
    ret
    .size lp_call,.-lp_call
