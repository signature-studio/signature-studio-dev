# void ld_ms_call(void* fn, const u64* gpr4, const u64* xmm4, const u64* stk, long nstk, u64* out4, u64 rax_init)
# SysV で呼ばれ、MS x64 ABI の fn を (rcx,rdx,r8,r9 / xmm0-3 / stack) で実行する汎用 trampoline.
# out4 = {rax, rdx, xmm0.lo64, xmm1.lo64}
    .text
    .globl ld_ms_call
    .type ld_ms_call,@function
ld_ms_call:
    pushq %rbp
    movq %rsp,%rbp
    pushq %rbx
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    subq $8,%rsp
    movq %rdi,%r12
    movq %rsi,%r13
    movq %rdx,%r14
    movq %r9,%r15
    movq %rcx,%rbx
    movq 16(%rbp),%r10          # rax_init
    leaq 32(,%r8,8),%rax
    addq $15,%rax
    andq $-16,%rax
    subq %rax,%rsp
    xorq %rcx,%rcx
1:  cmpq %r8,%rcx
    jge 2f
    movq (%rbx,%rcx,8),%rax
    movq %rax,32(%rsp,%rcx,8)
    incq %rcx
    jmp 1b
2:  movq 0(%r14),%xmm0
    movq 8(%r14),%xmm1
    movq 16(%r14),%xmm2
    movq 24(%r14),%xmm3
    movq 0(%r13),%rcx
    movq 8(%r13),%rdx
    movq 16(%r13),%r8
    movq 24(%r13),%r9
    movq %r10,%rax
    call *%r12
    movq %rax,0(%r15)
    movq %rdx,8(%r15)
    movq %xmm0,16(%r15)
    movq %xmm1,24(%r15)
    leaq -40(%rbp),%rsp
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbx
    popq %rbp
    ret
    .size ld_ms_call,.-ld_ms_call

# IAT thunk 共通部: r10 = import index, rcx/rdx/r8/r9 = MS ABI 引数。MS callee-saved (rdi,rsi,xmm6-15) を保存して C を呼ぶ。
    .globl ld_stub_common
    .type ld_stub_common,@function
ld_stub_common:
    pushq %rdi
    pushq %rsi
    subq $168,%rsp
    movups %xmm6,0(%rsp)
    movups %xmm7,16(%rsp)
    movups %xmm8,32(%rsp)
    movups %xmm9,48(%rsp)
    movups %xmm10,64(%rsp)
    movups %xmm11,80(%rsp)
    movups %xmm12,96(%rsp)
    movups %xmm13,112(%rsp)
    movups %xmm14,128(%rsp)
    movups %xmm15,144(%rsp)
    movq %r10,%rdi
    movq %rcx,%rsi
    movq %r8,%rcx
    movq %r9,%r8
    leaq 212(%rsp),%r9           # &MS 第5引数 ([entry_rsp+0x28]; 第6引数は +8) — ゲスト stack への書込はしない
    leaq 184(%rsp),%rax          # entry rsp (= [rsp] が呼出元の戻り番地)。既定の経路でも毎回保存するが、読むのは wintrace の wt_rec だけ (戻り値は変えない)
    movq %rax,ld_stub_ent(%rip)
    call ld_stub_c
    movups 0(%rsp),%xmm6
    movups 16(%rsp),%xmm7
    movups 32(%rsp),%xmm8
    movups 48(%rsp),%xmm9
    movups 64(%rsp),%xmm10
    movups 80(%rsp),%xmm11
    movups 96(%rsp),%xmm12
    movups 112(%rsp),%xmm13
    movups 128(%rsp),%xmm14
    movups 144(%rsp),%xmm15
    addq $168,%rsp
    popq %rsi
    popq %rdi
    ret
    .size ld_stub_common,.-ld_stub_common
    .section .note.GNU-stack,"",@progbits
