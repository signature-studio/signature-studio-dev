.intel_syntax noprefix
.globl _start
_start:
  mov ebx, dword ptr [rcx+0x14]
  sub ebx, 1
  xor eax, eax
  cmp eax, ebx
  jg L2
  add dword ptr [rcx+0x10], 1
L2:
  mov eax, 7
  ret
