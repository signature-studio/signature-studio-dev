# uint64_t ott_ms_call(void* fn, const uint64_t* gpr4, const uint64_t* xmm4, const uint64_t* stk, long nstk, uint64_t* out2)
# SysV 呼出 → MS x64 ABI の関数 fn を (rcx,rdx,r8,r9 / xmm0-3 / stack) 位置引数で実行する汎用 trampoline。
    .text
    .globl ott_ms_call
    .type ott_ms_call,@function
ott_ms_call:
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
    call *%r12
    .globl ott_ms_ret
ott_ms_ret:
    movq %rax,0(%r15)
    movq %xmm0,8(%r15)
    leaq -40(%rbp),%rsp
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbx
    popq %rbp
    ret
    .size ott_ms_call,.-ott_ms_call
    .section .note.GNU-stack,"",@progbits
