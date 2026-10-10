=== disasm 5bfc30 -> FUN_005bfc30 @005bfc30
  005bfc30: PUSH RBP
  005bfc31: PUSH RDI
  005bfc32: PUSH RSI
  005bfc33: PUSH RBX
  005bfc34: SUB RSP,0x88
  005bfc3b: MOV RBP,RSP
  005bfc3e: MOV RBX,RCX
  005bfc41: XOR ESI,ESI
  005bfc44: MOV RCX,RBX
  005bfc47: MOV RAX,qword ptr [RBX]
  005bfc4a: CALL qword ptr [RAX + 0x18]
  005bfc4d: CMP RAX,0x40
  005bfc51: JL 0x005bfe39
  005bfc57: MOV RCX,RBX
  005bfc5a: LEA RDX,[RBP + 0x28]
  005bfc5e: MOV R8D,0x40
  005bfc64: CALL 0x00501ab0
  005bfc69: CMP word ptr [RBP + 0x28],0x5a4d
  005bfc6f: JNZ 0x005bfe39
  005bfc75: MOVZX RCX,word ptr [RBP + 0x2a]
  005bfc7a: TEST CX,CX
  005bfc7d: JNZ 0x005bfc88
  005bfc7f: MOVZX EDI,word ptr [RBP + 0x2c]
  005bfc83: SHL EDI,0x9
  005bfc86: JMP 0x005bfca5
  005bfc88: MOVZX RAX,word ptr [RBP + 0x2c]
  005bfc8d: TEST AX,AX
  005bfc90: JBE 0x005bfca2
  005bfc92: MOVZX EDI,AX
  005bfc95: SUB EDI,0x1
  005bfc98: SHL EDI,0x9
  005bfc9b: MOVZX ECX,CX
  005bfc9e: ADD EDI,ECX
  005bfca0: JMP 0x005bfca5
  005bfca2: MOVZX EDI,CX
  005bfca5: MOV RCX,RBX
  005bfca8: MOV RAX,qword ptr [RBX]
  005bfcab: CALL qword ptr [RAX + 0x18]
  005bfcae: MOVSXD RCX,EDI
  005bfcb1: CMP RAX,RCX
  005bfcb4: JL 0x005bfe39
  005bfcba: MOVZX EAX,word ptr [RBP + 0x40]
  005bfcbe: CMP EAX,EDI
  005bfcc0: JG 0x005bfe39
  005bfcc6: MOV SIL,0x2
  005bfcc9: MOV RCX,RBX
  005bfccc: MOV RAX,qword ptr [RBX]
  005bfccf: CALL qword ptr [RAX + 0x18]
  005bfcd2: CMP RAX,0x40
  005bfcd6: JLE 0x005bfe39
  005bfcdc: MOV EDI,dword ptr [RBP + 0x64]
  005bfcdf: MOV RCX,RBX
  005bfce2: MOVSXD RDX,EDI
  005bfce5: CALL 0x00501370
  005bfcea: MOV RCX,RBX
  005bfced: LEA RDX,[RBP + 0x7e]
  005bfcf1: MOV R8D,0x2
  005bfcf7: CALL 0x00501ab0
  005bfcfc: MOVZX RAX,word ptr [RBP + 0x7e]
  005bfd01: SUB AX,0x454c
  005bfd05: TEST AX,AX
  005bfd08: JZ 0x005bfe36
  005bfd0e: SUB AX,0x2
  005bfd12: TEST AX,AX
  005bfd15: JZ 0x005bfde6
  005bfd1b: SUB AX,0x2
  005bfd1f: TEST AX,AX
  005bfd22: JNZ 0x005bfe39
  005bfd28: MOV RCX,RBX
  005bfd2b: MOV RAX,qword ptr [RBX]
  005bfd2e: CALL qword ptr [RAX + 0x18]
  005bfd31: ADD EDI,0x18
  005bfd34: MOVSXD RDI,EDI
  005bfd37: CMP RAX,RDI
  005bfd3a: JL 0x005bfe39
  005bfd40: MOV RCX,RBX
  005bfd43: CALL 0x00501350
  005bfd48: MOV RCX,RBX
  005bfd4b: LEA RDX,[RAX + 0x2]
  005bfd4f: CALL 0x00501370
  005bfd54: MOV RCX,RBX
  005bfd57: LEA RDX,[RBP + 0x68]
  005bfd5b: MOV R8D,0x14
  005bfd61: MOV RAX,qword ptr [RBX]
  005bfd64: CALL qword ptr [RAX + 0x30]
  005bfd67: XOR EAX,EAX
  005bfd69: MOVZX RCX,word ptr [RBP + 0x68]
  005bfd6e: SUB CX,0x14c
  005bfd73: TEST CX,CX
  005bfd76: JZ 0x005bfd8e
  005bfd78: SUB CX,0xb4
  005bfd7d: TEST CX,CX
  005bfd80: JZ 0x005bfd95
  005bfd82: SUB CX,0x8464
  005bfd87: TEST CX,CX
  005bfd8a: JNZ 0x005bfda1
  005bfd8c: JMP 0x005bfd9c
  005bfd8e: MOV EAX,0x20
  005bfd93: JMP 0x005bfda1
  005bfd95: MOV EAX,0x40
  005bfd9a: JMP 0x005bfda1
  005bfd9c: MOV EAX,0x40
  005bfda1: MOVZX RCX,word ptr [RBP + 0x7a]
  005bfda6: AND CX,0x2000
  005bfdab: CMP CX,0x2000
  005bfdb0: JNZ 0x005bfdcc
  005bfdb2: SUB EAX,0x20
  005bfdb5: TEST EAX,EAX
  005bfdb7: JZ 0x005bfdc2
  005bfdb9: SUB EAX,0x20
  005bfdbc: TEST EAX,EAX
  005bfdbe: JNZ 0x005bfe39
  005bfdc0: JMP 0x005bfdc7
  005bfdc2: MOV SIL,0x7
  005bfdc5: JMP 0x005bfe39
  005bfdc7: MOV SIL,0x6
  005bfdca: JMP 0x005bfe39
  005bfdcc: SUB EAX,0x20
  005bfdcf: TEST EAX,EAX
  005bfdd1: JZ 0x005bfddc
  005bfdd3: SUB EAX,0x20
  005bfdd6: TEST EAX,EAX
  005bfdd8: JNZ 0x005bfe39
  005bfdda: JMP 0x005bfde1
  005bfddc: MOV SIL,0x4
  005bfddf: JMP 0x005bfe39
  005bfde1: MOV SIL,0x3
  005bfde4: JMP 0x005bfe39
  005bfde6: MOV RCX,RBX
  005bfde9: MOV RAX,qword ptr [RBX]
  005bfdec: CALL qword ptr [RAX + 0x18]
  005bfdef: MOV RCX,RAX
  005bfdf2: MOV EAX,EDI
  005bfdf4: ADD EAX,0xd
  005bfdf7: MOV EDX,EAX
  005bfdf9: ADD EDX,0x1
  005bfdfc: MOVSXD RDX,EDX
  005bfdff: CMP RCX,RDX
  005bfe02: JLE 0x005bfe39
  005bfe04: MOV RCX,RBX
  005bfe07: MOVSXD RDX,EAX
  005bfe0a: CALL 0x00501370
  005bfe0f: MOV RCX,RBX
  005bfe12: LEA RDX,[RBP + 0x27]
  005bfe16: MOV R8D,0x1
  005bfe1c: CALL 0x00501ab0
  005bfe21: MOVZX RAX,byte ptr [RBP + 0x27]
  005bfe26: AND AL,0x80
  005bfe28: CMP AL,0x80
  005bfe2a: JNZ 0x005bfe31
  005bfe2c: MOV SIL,0x8
  005bfe2f: JMP 0x005bfe39
  005bfe31: MOV SIL,0x5
  005bfe34: JMP 0x005bfe39
  005bfe36: MOV SIL,0x9
  005bfe39: MOV EAX,ESI
  005bfe3c: LEA RSP,[RBP + 0x88]
  005bfe43: POP RBX
  005bfe44: POP RSI
  005bfe45: POP RDI
  005bfe46: POP RBP
  005bfe47: RET
