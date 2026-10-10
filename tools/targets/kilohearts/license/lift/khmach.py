#!/usr/bin/env python3
"""khmach.py — 機械語側の事実 (capstone) を IR pass に供給する小ライブラリ。

  M = Mach(core_path)            HeartCore.core_64 (PE) を読む
  fn = M.function(va)            extent は pdata 優先、無ければ BB 走査 (scripts/fnscan と同じ)
  fn.insns                       [Insn(addr,size,mn,ops,regs_read,regs_write,flags_write,mem)] アドレス昇順
  fn.at(addr)                    addr の命令
  fn.targets                     関数内 jmp/jcc の分岐先集合 (join point)
  fn.written_regs                関数内で書かれる GPR(64bit 正規化) の集合
"""
import struct
import sys
import pefile
import capstone
from capstone import x86 as cx

GPR64 = ['rax', 'rcx', 'rdx', 'rbx', 'rsp', 'rbp', 'rsi', 'rdi', 'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15']
_SUB = {}
for i, r in enumerate(GPR64):
    n = r[1:] if r[0] == 'r' and not r[1].isdigit() else None
    if n:
        _SUB[r] = r; _SUB['e' + n] = r; _SUB[n] = r
        _SUB[n[0] + 'l' if n[1] == 'x' else n + 'l'] = r
    else:
        _SUB[r] = r; _SUB[r + 'd'] = r; _SUB[r + 'w'] = r; _SUB[r + 'b'] = r
for n in ('si', 'di', 'bp', 'sp'):
    _SUB['r' + n] = 'r' + n; _SUB['e' + n] = 'r' + n; _SUB[n] = 'r' + n; _SUB[n + 'l'] = 'r' + n
_SUB['ah'] = 'rax'; _SUB['ch'] = 'rcx'; _SUB['dh'] = 'rdx'; _SUB['bh'] = 'rbx'


def canon(name):
    """レジスタ名 → 64bit GPR 名 / xmmN / None"""
    if name.startswith(('xmm', 'ymm', 'zmm')):
        return 'xmm' + name[3:]
    return _SUB.get(name)


class Insn:
    __slots__ = ('addr', 'size', 'mn', 'ops', 'reads', 'writes', 'flagw', 'flagr', 'mem', 'raw')

    def __repr__(self):
        return '%x %s %s' % (self.addr, self.mn, self.ops)


class Function:
    def __init__(self, va, end, insns):
        self.va, self.end, self.insns = va, end, insns
        self._by = {i.addr: i for i in insns}
        self.targets = set()
        self.written_regs = set()
        for i in insns:
            self.written_regs |= {r for r in i.writes if r in GPR64}
            if (i.mn == 'jmp' or i.mn.startswith('j')) and i.ops.startswith('0x'):
                self.targets.add(int(i.ops, 16))

    def at(self, a):
        return self._by.get(a)

    def index(self, a):
        for k, i in enumerate(self.insns):
            if i.addr == a:
                return k
        return -1


class Mach:
    def __init__(self, path):
        self.pe = pefile.PE(path, fast_load=True)
        self.data = open(path, 'rb').read()
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True
        sec = {s.Name.rstrip(b'\0').decode(): s for s in self.pe.sections}
        pd = sec['.pdata']
        b = self.data[pd.PointerToRawData:pd.PointerToRawData + pd.Misc_VirtualSize]
        self.pdata = {}
        for k in range(0, len(b) // 12 * 12, 12):
            s, e, _ = struct.unpack_from('<III', b, k)
            if s:
                self.pdata[self.base + s] = self.base + e
        t = sec['.text']
        self.t_lo, self.t_hi = self.base + t.VirtualAddress, self.base + t.VirtualAddress + t.Misc_VirtualSize
        self._cache = {}

    def rd(self, va, n):
        rva = va - self.base
        for s in self.pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                o = s.PointerToRawData + rva - s.VirtualAddress
                return self.data[o:o + n]
        raise ValueError(hex(va))

    def _mk(self, ins):
        x = Insn()
        x.addr, x.size, x.mn, x.ops = ins.address, ins.size, ins.mnemonic, ins.op_str
        rr, ww = ins.regs_access()
        x.reads = {canon(ins.reg_name(r)) for r in rr} - {None}
        x.writes = {canon(ins.reg_name(r)) for r in ww} - {None}
        x.flagw = bool(ins.eflags & (cx.X86_EFLAGS_MODIFY_AF | cx.X86_EFLAGS_MODIFY_CF | cx.X86_EFLAGS_MODIFY_SF |
                                     cx.X86_EFLAGS_MODIFY_ZF | cx.X86_EFLAGS_MODIFY_PF | cx.X86_EFLAGS_MODIFY_OF |
                                     cx.X86_EFLAGS_RESET_CF | cx.X86_EFLAGS_RESET_ZF | cx.X86_EFLAGS_SET_CF | cx.X86_EFLAGS_SET_ZF))
        x.flagr = bool(ins.eflags & (cx.X86_EFLAGS_TEST_CF | cx.X86_EFLAGS_TEST_ZF | cx.X86_EFLAGS_TEST_SF |
                                     cx.X86_EFLAGS_TEST_OF | cx.X86_EFLAGS_TEST_PF))
        x.mem = None
        for o in ins.operands:
            if o.type == cx.X86_OP_MEM:
                m = o.mem
                x.mem = dict(base=canon(ins.reg_name(m.base)) if m.base else None,
                             index=canon(ins.reg_name(m.index)) if m.index else None,
                             scale=m.scale, disp=m.disp, size=o.size, access=o.access)
        x.raw = None
        return x

    def function(self, va):
        if va in self._cache:
            return self._cache[va]
        fixed = va in self.pdata
        end = self.pdata.get(va)
        todo, seen, hi = [va], {}, va
        while todo:
            a = todo.pop()
            while True:
                if a in seen or (fixed and not (va <= a < end)):
                    break
                ins = next(self.md.disasm(self.rd(a, 16), a, 1), None)
                if ins is None:
                    break
                seen[a] = self._mk(ins)
                nxt = a + ins.size
                hi = max(hi, nxt)
                mn = ins.mnemonic
                if mn == 'int3' or mn == 'ret':
                    break
                if (mn == 'jmp' or mn.startswith('j')) and ins.op_str.startswith('0x'):
                    tg = int(ins.op_str, 16)
                    inside = (va <= tg < end) if fixed else (va <= tg < hi + 0x2000 and tg < self.t_hi)
                    if inside:
                        todo.append(tg)
                if mn == 'jmp':
                    break
                a = nxt
        f = Function(va, end if fixed else hi, [seen[k] for k in sorted(seen)])
        self._cache[va] = f
        return f


if __name__ == '__main__':
    M = Mach(sys.argv[1])
    f = M.function(int(sys.argv[2], 16))
    for i in f.insns:
        print(i, 'R', sorted(i.reads), 'W', sorted(i.writes), 'F' if i.flagw else '', i.mem or '')
