.intel_syntax noprefix
.globl _start
_start:
  push rbp
  push rbx
  sub rsp, 0x68
  mov rbp, rsp
  mov rcx, qword ptr [rbp+0x80]
  mov ebx, dword ptr [rcx+0x14]
  sub ebx, 1
  xor eax, eax
  mov dword ptr [rbp+0x4c], eax
  cmp dword ptr [rbp+0x4c], ebx
  jg L2
  sub ebx, eax
  add ebx, 1
L1:
  mov edx, dword ptr [rbp+0x4c]
  add dword ptr [rcx+0x10], edx
  add dword ptr [rbp+0x4c], 1
  cmp dword ptr [rbp+0x4c], ebx
  jle L1
L2:
  mov eax, 7
  add rsp, 0x68
  pop rbx
  pop rbp
  ret
