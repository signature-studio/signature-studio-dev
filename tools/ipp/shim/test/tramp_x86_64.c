/* 検証用 (native x86-64 Linux 専用): 「本物の MS x64 呼出」を IppBlk に落として ipp_shim_dispatch へ渡す手書き asm トランポリン。
   lift 後コードが icall ブロック (rcx/rdx/r8/r9/xmm0-3/スタック引数) を埋めて dispatch へ渡す動作の、独立実装による再現。
   ms_abi 関数ポインタとして呼べる: 420 本 (idx*16 バイト間隔)。thunk の生成コードとは無関係に書いてあるので、ABI 解釈の独立検査になる。 */
#include "../src/ipp_shim.h"
#include <stdint.h>
#include <string.h>
#define MS __attribute__((ms_abi))
__attribute__((weak)) void (*const ipp_probe_blk[1])(IppBlk *) = {0};   /* shim_selftest が強シンボルで上書き (test/gen/probe_thunks.c) */
/* idx 0..419 = shim 表の関数, 420.. = ABI プローブ (test/gen/probe_thunks.c) */
MS void ipp_tramp_dispatch(IppBlk *b, int idx) { if (idx >= 420) { ipp_probe_blk[idx - 420](b); return; } b->target = ipp_shim_cookie(idx); ipp_shim_dispatch(b); }
extern char ipp_tramp_base[];
void *ipp_tramp_for(int idx) { return ipp_tramp_base + 16 * idx; }
__asm__(
  ".text\n.intel_syntax noprefix\n"
  ".balign 16\nipp_tramp_common:\n"
  "  push rbp\n  mov rbp, rsp\n  sub rsp, 0xC0\n"
  "  mov [rsp+0x28], rcx\n  mov [rsp+0x30], rdx\n  mov [rsp+0x38], r8\n  mov [rsp+0x40], r9\n"
  "  movsd [rsp+0x48], xmm0\n  movsd [rsp+0x50], xmm1\n  movsd [rsp+0x58], xmm2\n  movsd [rsp+0x60], xmm3\n"
  "  lea rax, [rbp+0x30]\n  mov [rsp+0x68], rax\n"
  "  mov qword ptr [rsp+0xA0], 0\n  mov qword ptr [rsp+0xA8], 0\n"
  "  lea rcx, [rsp+0x20]\n  mov edx, r10d\n  call ipp_tramp_dispatch\n"
  "  mov rax, [rsp+0xA0]\n  movsd xmm0, [rsp+0xA8]\n  leave\n  ret\n"
  ".balign 16\n.globl ipp_tramp_base\nipp_tramp_base:\n"
  ".set i, 0\n.rept 440\n  .balign 16\n  mov r10d, i\n  jmp ipp_tramp_common\n  .set i, i+1\n.endr\n"
  ".att_syntax prefix\n");
