#!/usr/bin/env python3
"""pedis.py — PE x64 annotated disassembler (capstone+pefile).
usage: pedis.py <pe> <start_va> [<end_va>|+len] [--strings]
Annotates RIP-relative refs: ASCII/UTF-16 strings, IAT imports, internal call targets.
"""
import sys, struct, pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

class PE64:
    def __init__(self, path):
        self.pe = pefile.PE(path)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.data = self.pe.__data__
        self.imports = {}
        if hasattr(self.pe, 'DIRECTORY_ENTRY_IMPORT'):
            for d in self.pe.DIRECTORY_ENTRY_IMPORT:
                for i in d.imports:
                    nm = i.name.decode() if i.name else 'ord%d' % i.ordinal
                    self.imports[i.address] = d.dll.decode().replace('.dll','').replace('.DLL','') + '!' + nm
        self.exports = {}
        if hasattr(self.pe, 'DIRECTORY_ENTRY_EXPORT'):
            for e in self.pe.DIRECTORY_ENTRY_EXPORT.symbols:
                self.exports[self.base + e.address] = e.name.decode() if e.name else 'ord%d' % e.ordinal
        self.md = Cs(CS_ARCH_X86, CS_MODE_64); self.md.detail = True
    def rva2off(self, rva):
        return self.pe.get_offset_from_rva(rva)
    def read(self, va, n):
        rva = va - self.base
        try:
            off = self.rva2off(rva)
        except Exception:
            return b''
        return self.data[off:off+n]
    def cstr(self, va, maxn=200):
        b = self.read(va, maxn)
        if not b: return None
        e = b.find(b'\0')
        if e < 3: 
            return None
        s = b[:e]
        if all(0x20 <= c < 0x7f or c in (9,10,13) for c in s): return 'A"' + s.decode() + '"'
        return None
    def wstr(self, va, maxn=400):
        b = self.read(va, maxn)
        if len(b) < 4: return None
        out = []
        for i in range(0, len(b)-1, 2):
            c = b[i] | (b[i+1] << 8)
            if c == 0: break
            if c < 0x20 and c not in (9,10,13) or c > 0x2ff: return None
            out.append(chr(c))
        if len(out) < 2 : return None
        return 'W"' + ''.join(out) + '"'
    def annotate(self, ins):
        notes = []
        for op in ins.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                tgt = ins.address + ins.size + op.mem.disp
                if tgt in self.imports: notes.append('IMP ' + self.imports[tgt]); continue
                if ins.mnemonic == 'lea':
                    s = self.cstr(tgt) or self.wstr(tgt)
                    if s: notes.append(s); continue
                    notes.append('&%#x' % tgt)
                else:
                    notes.append('[%#x]' % tgt)
        if ins.mnemonic in ('call','jmp') and ins.op_str.startswith('0x'):
            t = int(ins.op_str, 16)
            if t in self.exports: notes.append('EXP ' + self.exports[t])
        return notes
    def dis(self, start, length):
        code = self.read(start, length)
        for ins in self.md.disasm(code, start):
            n = self.annotate(ins)
            yield ins, n

if __name__ == '__main__':
    pe = PE64(sys.argv[1])
    start = int(sys.argv[2], 16)
    a3 = sys.argv[3] if len(sys.argv) > 3 else '+200'
    length = int(a3[1:], 0) if a3.startswith('+') else int(a3, 16) - start
    for ins, n in pe.dis(start, length):
        print('%x:\t%s\t%s%s' % (ins.address, ins.mnemonic, ins.op_str, ('\t; ' + ' | '.join(n)) if n else ''))
