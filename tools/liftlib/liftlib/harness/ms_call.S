# ms_call.S — SysV x86-64 から MS x64 ABI 関数を呼ぶトランポリン
#   void ll_ms_call(struct ms_ctx* c);
#   struct ms_ctx { void* fn; u64 gpr[4]; u64 xmm[4]; u64 rax_out; u64 xmm0_out[2]; };
#   offsets: fn 0 / gpr 8..39 / xmm 40..71 / rax_out 72 / xmm0_out 80..95
    .text
    .globl ll_ms_call
    .type ll_ms_call,@function
ll_ms_call:
    pushq %rbp
    movq %rsp, %rbp
    pushq %rbx
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    movq %rdi, %rbx
    subq $40, %rsp              # shadow space 32 + alignment (entry rsp%16==8, 6 pushes -> 8, +40 -> 0)
    movq 8(%rbx), %rcx
    movq 16(%rbx), %rdx
    movq 24(%rbx), %r8
    movq 32(%rbx), %r9
    movq 40(%rbx), %xmm0
    movq 48(%rbx), %xmm1
    movq 56(%rbx), %xmm2
    movq 64(%rbx), %xmm3
    callq *(%rbx)
    movq %rax, 72(%rbx)
    movdqu %xmm0, 80(%rbx)
    addq $40, %rsp
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbx
    popq %rbp
    ret
    .size ll_ms_call, .-ll_ms_call
    .section .note.GNU-stack,"",@progbits
