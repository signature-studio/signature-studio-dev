=== disasm a9eff0 -> FUN_00a9eff0 @00a9eff0
  00a9eff0: PUSH RBP
  00a9eff1: PUSH RDI
  00a9eff2: PUSH RSI
  00a9eff3: SUB RSP,0x6f0
  00a9effa: MOV RBP,RSP
  00a9effd: MOV qword ptr [RBP + 0x20],RCX
  00a9f001: MOV RSI,RDX
  00a9f004: MOV byte ptr [RBP + 0x2e],R8B
  00a9f008: MOV byte ptr [RBP + 0x2f],R9B
  00a9f00c: MOV qword ptr [RBP + 0x30],0x0
  00a9f014: MOV qword ptr [RBP + 0x38],0x0
  00a9f01c: MOV qword ptr [RBP + 0x40],0x0
  00a9f024: MOV qword ptr [RBP + 0x48],0x0
  00a9f02c: LEA RDI,[RBP + 0xac]
  00a9f033: MOV ECX,0xc8
  00a9f038: MOVSQ.REP RDI,RSI
  00a9f03b: MOVSD RDI,RSI
  00a9f03c: NOP
  00a9f03d: MOV dword ptr [RBP + 0x68],0x8
  00a9f044: MOV RCX,qword ptr [RBP + 0x20]
  00a9f048: LEA RDX,[RBP + 0x68]
  00a9f04c: MOV R8D,0x4
  00a9f052: MOV RAX,qword ptr [RBP + 0x20]
  00a9f056: MOV RAX,qword ptr [RAX]
  00a9f059: CALL qword ptr [RAX + 0x38]
  00a9f05c: LEA RCX,[RBP + 0x5c]
  00a9f060: MOV RDX,qword ptr [RBP + 0x20]
  00a9f064: MOVZX R8,byte ptr [0x00a9f3bc]
  00a9f06c: CALL 0x008e8e10
  00a9f071: LEA RCX,[RBP + 0x93]
  00a9f078: MOV EDX,0x19
  00a9f07d: MOV RAX,qword ptr [0x015e0a48]
  00a9f084: CALL qword ptr [RAX]
  00a9f086: MOV dword ptr [RBP + 0x94],0xffffffff
  00a9f090: MOV dword ptr [RBP + 0x98],0xffffffff
  00a9f09a: MOV byte ptr [RBP + 0x93],0x0
  00a9f0a1: MOV dword ptr [RBP + 0x9c],0x407908
  00a9f0ab: MOVZX RAX,byte ptr [RBP + 0x2e]
  00a9f0b0: TEST AL,AL
  00a9f0b2: JZ 0x00a9f0be
  00a9f0b4: OR dword ptr [RBP + 0x9c],0x400
  00a9f0be: MOVZX RAX,byte ptr [RBP + 0x2f]
  00a9f0c3: TEST AL,AL
  00a9f0c5: JZ 0x00a9f0d1
  00a9f0c7: OR dword ptr [RBP + 0x9c],0x100000
  00a9f0d1: MOV byte ptr [RBP + 0xa4],0x1
  00a9f0d8: LEA RCX,[RBP + 0x5c]
  00a9f0dc: MOV EDX,0x2
  00a9f0e1: MOV R8D,0x19
  00a9f0e7: LEA R9,[RBP + 0x93]
  00a9f0ee: CALL 0x008e8ed0
  00a9f0f3: LEA RCX,[RBP + 0x6f]
  00a9f0f7: MOV EDX,0x10
  00a9f0fc: MOV RAX,qword ptr [0x015e0a48]
  00a9f103: CALL qword ptr [RAX]
  00a9f105: MOV EAX,dword ptr [RBP + 0xac]
  00a9f10b: MOV dword ptr [RBP + 0x6f],EAX
  00a9f10e: LEA RCX,[RBP + 0x5c]
  00a9f112: MOV EDX,0x32
  00a9f117: MOV R8D,0x10
  00a9f11d: LEA R9,[RBP + 0x6f]
  00a9f121: CALL 0x008e8ed0
  00a9f126: MOV EAX,dword ptr [RBP + 0xac]
  00a9f12c: SUB EAX,0x1
  00a9f12f: CMP EAX,-0x1
  00a9f132: JZ 0x00a9f154
  00a9f134: SUB EAX,0x3
  00a9f137: TEST EAX,EAX
  00a9f139: JZ 0x00a9f154
  00a9f13b: SUB EAX,0x3
  00a9f13e: CMP EAX,0x2
  00a9f141: JC 0x00a9f195
  00a9f143: SUB EAX,0x4
  00a9f146: CMP EAX,0x2
  00a9f149: JNC 0x00a9f1f4
  00a9f14f: JMP 0x00a9f1dd
  00a9f154: LEA RCX,[RBP + 0x8f]
  00a9f15b: MOV EDX,0x4
  00a9f160: MOV RAX,qword ptr [0x015e0a48]
  00a9f167: CALL qword ptr [RAX]
  00a9f169: MOV EAX,dword ptr [RBP + 0x4e0]
  00a9f16f: MOV dword ptr [RBP + 0x8f],EAX
  00a9f175: LEA RCX,[RBP + 0x5c]
  00a9f179: MOV EDX,0x33
  00a9f17e: MOV R8D,0x4
  00a9f184: LEA R9,[RBP + 0x8f]
  00a9f18b: CALL 0x008e8ed0
  00a9f190: JMP 0x00a9f273
  00a9f195: LEA RCX,[RBP + 0x7f]
  00a9f199: MOV EDX,0x10
  00a9f19e: MOV RAX,qword ptr [0x015e0a48]
  00a9f1a5: CALL qword ptr [RAX]
  00a9f1a7: LEA RAX,[RBP + 0x4c4]
  00a9f1ae: MOV RCX,RAX
  00a9f1b1: LEA RDX,[RBP + 0x7f]
  00a9f1b5: MOV R8D,0x10
  00a9f1bb: CALL 0x00409c80
  00a9f1c0: LEA RCX,[RBP + 0x5c]
  00a9f1c4: MOV EDX,0x34
  00a9f1c9: MOV R8D,0x10
  00a9f1cf: LEA R9,[RBP + 0x7f]
  00a9f1d3: CALL 0x008e8ed0
  00a9f1d8: JMP 0x00a9f273
  00a9f1dd: LEA RCX,[RBP + 0x5c]
  00a9f1e1: MOV EDX,0x3a
  00a9f1e6: MOV R8,qword ptr [RBP + 0x740]
  00a9f1ed: CALL 0x008e8fe0
  00a9f1f2: JMP 0x00a9f273
  00a9f1f4: LEA RCX,[RBP + 0x8f]
  00a9f1fb: MOV EDX,0x4
  00a9f200: MOV RAX,qword ptr [0x015e0a48]
  00a9f207: CALL qword ptr [RAX]
  00a9f209: MOV EAX,dword ptr [RBP + 0x4e0]
  00a9f20f: MOV dword ptr [RBP + 0x8f],EAX
  00a9f215: LEA RCX,[RBP + 0x5c]
  00a9f219: MOV EDX,0x33
  00a9f21e: MOV R8D,0x4
  00a9f224: LEA R9,[RBP + 0x8f]
  00a9f22b: CALL 0x008e8ed0
  00a9f230: LEA RCX,[RBP + 0x7f]
  00a9f234: MOV EDX,0x10
  00a9f239: MOV RAX,qword ptr [0x015e0a48]
  00a9f240: CALL qword ptr [RAX]
  00a9f242: LEA RAX,[RBP + 0x4c4]
  00a9f249: MOV RCX,RAX
  00a9f24c: LEA RDX,[RBP + 0x7f]
  00a9f250: MOV R8D,0x10
  00a9f256: CALL 0x00409c80
  00a9f25b: LEA RCX,[RBP + 0x5c]
  00a9f25f: MOV EDX,0x34
  00a9f264: MOV R8D,0x10
  00a9f26a: LEA R9,[RBP + 0x7f]
  00a9f26e: CALL 0x008e8ed0
  00a9f273: LEA RCX,[RBP + 0x48]
  00a9f277: LEA RDX,[RBP + 0xb0]
  00a9f27e: MOV R8D,0x105
  00a9f284: CALL 0x00414940
  00a9f289: CMP qword ptr [RBP + 0x48],0x0
  00a9f28e: JZ 0x00a9f2b8
  00a9f290: LEA RCX,[RBP + 0x40]
  00a9f294: LEA RDX,[RBP + 0xb0]
  00a9f29b: MOV R8D,0x105
  00a9f2a1: CALL 0x00414940
  00a9f2a6: LEA RCX,[RBP + 0x5c]
  00a9f2aa: MOV EDX,0x36
  00a9f2af: MOV R8,qword ptr [RBP + 0x40]
  00a9f2b3: CALL 0x008e8fe0
  00a9f2b8: LEA RCX,[RBP + 0x38]
  00a9f2bc: LEA RDX,[RBP + 0x2ba]
  00a9f2c3: MOV R8D,0x105
  00a9f2c9: CALL 0x00414940
  00a9f2ce: CMP qword ptr [RBP + 0x38],0x0
  00a9f2d3: JZ 0x00a9f2fd
  00a9f2d5: LEA RCX,[RBP + 0x30]
  00a9f2d9: LEA RDX,[RBP + 0x2ba]
  00a9f2e0: MOV R8D,0x105
  00a9f2e6: CALL 0x00414940
  00a9f2eb: LEA RCX,[RBP + 0x5c]
  00a9f2ef: MOV EDX,0x37
  00a9f2f4: MOV R8,qword ptr [RBP + 0x30]
  00a9f2f8: CALL 0x008e8fe0
  00a9f2fd: CMP qword ptr [RBP + 0x730],0x0
  00a9f305: JZ 0x00a9f31c
  00a9f307: LEA RCX,[RBP + 0x5c]
  00a9f30b: MOV EDX,0x38
  00a9f310: MOV R8,qword ptr [RBP + 0x730]
  00a9f317: CALL 0x008e8fe0
  00a9f31c: CMP qword ptr [RBP + 0x738],0x0
  00a9f324: JZ 0x00a9f37d
  00a9f326: MOV RCX,qword ptr [RBP + 0x738]
  00a9f32d: MOV RAX,qword ptr [RBP + 0x738]
  00a9f334: MOV RAX,qword ptr [RAX]
  00a9f337: CALL qword ptr [RAX + 0x18]
  00a9f33a: TEST RAX,RAX
  00a9f33d: JLE 0x00a9f37d
  00a9f33f: MOV RCX,qword ptr [RBP + 0x738]
  00a9f346: XOR EDX,EDX
  00a9f348: CALL 0x005123c0
  00a9f34d: MOV RCX,qword ptr [RBP + 0x738]
  00a9f354: MOV RAX,qword ptr [RBP + 0x738]
  00a9f35b: MOV RAX,qword ptr [RAX]
  00a9f35e: CALL qword ptr [RAX + 0x18]
  00a9f361: LEA RCX,[RBP + 0x5c]
  00a9f365: MOV EDX,0x35
  00a9f36a: MOV R8,RAX
  00a9f36d: MOV RAX,qword ptr [RBP + 0x738]
  00a9f374: MOV R9,qword ptr [RAX + 0x8]
  00a9f378: CALL 0x008e8ed0
  00a9f37d: NOP
  00a9f37e: LEA RCX,[RBP + 0x30]
  00a9f382: MOV EDX,0x4
  00a9f387: CALL 0x00412e40
  00a9f38c: LEA RSP,[RBP + 0x6f0]
  00a9f393: POP RSI
  00a9f394: POP RDI
  00a9f395: POP RBP
  00a9f396: RET
