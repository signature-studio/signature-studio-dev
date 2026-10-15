#!/usr/bin/env python3
"""hs_callee_sem.py — Dispatcher (0x13173a0) の応答格納 0x2e・0x47 の call 先の意味論を機械語で検証する (#2945 受入 1)。

検証する事実 (block00031_PE.bin の VA・capstone 逆アセンブル):
  * 0x47: 0x1321bfd〜0x1321c07 で rcx = [[[rip+X]]+0x30]、0x1321c0b で call 0x75b3d0、0x1321c10 で [rbp+0x11a0] へ格納。
          0x75b3d0 は `mov rax,[rcx+0x28]; ret` (オブジェクトの qword フィールドを返す。副作用なし)。
  * 0x2e: 0x1320de3 で call 0x86c900、0x1320de8 で [rbp+0x11a0] へ格納 (戻り値 rax をそのまま格納)。
          0x86c900 (rbx = O1): [O1+0x1d0] が非 0 なら call [O1+0x1d0] (rdx=&out) で out に書かせる。
          out が 0 かつ O2 = [O1+0xa4] が非 0 なら 0x617920(O2) の戻り値を out に格納する。
          0x617920 は 0x6178e0(O2) を呼んだ後 `mov rax,[O2+0x45c]` を返す。
          0x6178e0(X) は副作用を持つ: [X+0x45c] が非 0 なら即 return (0x6178f0)。0 なら [X+0x78] が非 0 のとき
          その子に対して 0x6178e0 を再帰呼出し (0x6178fe)、最後に rcx = X・rbx = [X] (vtable) で
          call [vtable+0x1d0] を this = X で呼ぶ (0x617903〜0x617909)。
戻り値は全て qword (ポインタ幅) で、値はオブジェクトの状態 (フィールド・関数ポインタ・仮想メソッドの効果) に依存する。
値そのものは静的に定まらない。[O1+0x1d0] の target と vtable+0x1d0 の先 (受け手の型) は未解決 (REPORT_DISPATCHER_APPENDIX_2886.md §5)。

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<capstone,pefile の入った lib> python3 hs_callee_sem.py
終了コード: 0 = 全件一致 / 1 = 不一致 (素材の版が違う可能性)。
"""
import os
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

FL = os.environ['FL_WIN64_DIR']
data = open(os.path.join(FL, 'extracted', 'block00031_PE.bin'), 'rb').read()
pe = pefile.PE(data=data)
base = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_64)


def read_va(va, n):
    rva = va - base
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            off = rva - s.VirtualAddress
            return s.get_data()[off:off + n]
    return b''


def insns(lo, hi):
    """lo から線形に逆アセンブルし、アドレスが hi 未満の命令を {addr: (mnemonic, operands)} で返す。"""
    out = {}
    for i in md.disasm(read_va(lo, hi - lo + 16), lo):
        if i.address >= hi:
            break
        out[i.address] = (i.mnemonic, i.op_str)
    return out


fails = []


def expect(name, got, want):
    ok = got == want
    print('%s %s: %s' % ('OK ' if ok else 'NG ', name, got if ok else 'got %r want %r' % (got, want)))
    if not ok:
        fails.append(name)


FN_75B3D0 = insns(0x75b3d0, 0x75b3d5)
expect('0x75b3d0 body', [FN_75B3D0[a] for a in sorted(FN_75B3D0)],
       [('mov', 'rax, qword ptr [rcx + 0x28]'), ('ret', '')])

FN_86C900 = insns(0x86c900, 0x86c95b)
expect('0x86c900 callback call', FN_86C900.get(0x86c929), ('call', 'qword ptr [rbx + 0x1d0]'))
expect('0x86c900 fallback call', FN_86C900.get(0x86c947), ('call', '0x617920'))
expect('0x86c900 fallback store', FN_86C900.get(0x86c94c), ('mov', 'qword ptr [rbp + 0x28], rax'))
expect('0x86c900 return value', FN_86C900.get(0x86c950), ('mov', 'rax, qword ptr [rbp + 0x28]'))

FN_617920 = insns(0x617920, 0x61793d)
expect('0x617920 callee', FN_617920.get(0x61792b), ('call', '0x6178e0'))
expect('0x617920 return field', FN_617920.get(0x617930), ('mov', 'rax, qword ptr [rbx + 0x45c]'))

FN_6178E0 = insns(0x6178e0, 0x617915)
expect('0x6178e0 early return test', FN_6178E0.get(0x6178e8), ('cmp', 'qword ptr [rbx + 0x45c], 0'))
expect('0x6178e0 early return jump', FN_6178E0.get(0x6178f0), ('jne', '0x61790f'))
expect('0x6178e0 child recursion', FN_6178E0.get(0x6178fe), ('call', '0x6178e0'))
expect('0x6178e0 this = X', FN_6178E0.get(0x617903), ('mov', 'rcx, rbx'))
expect('0x6178e0 vtable load', FN_6178E0.get(0x617906), ('mov', 'rbx, qword ptr [rbx]'))
expect('0x6178e0 virtual call', FN_6178E0.get(0x617909), ('call', 'qword ptr [rbx + 0x1d0]'))

CS47 = insns(0x1321bfd, 0x1321c11)
expect('0x47 receiver chain', CS47.get(0x1321c07), ('mov', 'rcx, qword ptr [rax + 0x30]'))
expect('0x47 call', CS47.get(0x1321c0b), ('call', '0x75b3d0'))
expect('0x47 store', CS47.get(0x1321c10), ('mov', 'qword ptr [rbp + 0x11a0], rax'))

DISP = insns(0x13173a0, 0x1320df0)
expect('0x2e call', DISP.get(0x1320de3), ('call', '0x86c900'))
expect('0x2e store', DISP.get(0x1320de8), ('mov', 'qword ptr [rbp + 0x11a0], rax'))

print('結果: %s' % ('全件一致' if not fails else 'NG %d 件: %s' % (len(fails), ', '.join(fails))))
sys.exit(1 if fails else 0)
