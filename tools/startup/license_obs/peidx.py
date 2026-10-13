"""FLEngine_x64.dll を .pdata の関数境界ごとに capstone で逆アセンブルする共通部品 (読取専用)。"""
import os, re, struct, sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import REPO_ROOT, FL_WIN64_DIR  # noqa: E402

DLL = os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
RIP = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')


class Image:
    def __init__(self, path=DLL):
        self.path = path
        self.pe = pefile.PE(path, fast_load=True)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.raw = open(path, 'rb').read()
        self.md = Cs(CS_ARCH_X86, CS_MODE_64)
        self.md.skipdata = True
        sec = {s.Name.rstrip(b'\0').decode(): s for s in self.pe.sections}
        self.sec = sec
        t = sec['.text']
        self.text_lo = self.base + t.VirtualAddress
        self.text_hi = self.text_lo + t.Misc_VirtualSize
        self.funcs = self._pdata()

    def _pdata(self):
        s = self.sec['.pdata']
        d = self.raw[s.PointerToRawData:s.PointerToRawData + s.Misc_VirtualSize]
        out = {}
        for i in range(0, len(d) - 11, 12):
            b, e, u = struct.unpack_from('<III', d, i)
            if b == 0 and e == 0:
                continue
            if u & 1:
                continue
            out[b] = max(out.get(b, 0), e)
        return sorted((self.base + b, self.base + e) for b, e in out.items())

    def off(self, va):
        return self.pe.get_offset_from_rva(va - self.base)

    def read(self, va, n):
        o = self.off(va)
        return self.raw[o:o + n]

    def func_of(self, va):
        import bisect
        if not hasattr(self, '_starts'):
            self._starts = [f[0] for f in self.funcs]
        i = bisect.bisect_right(self._starts, va) - 1
        if i >= 0 and self.funcs[i][0] <= va < self.funcs[i][1]:
            return self.funcs[i][0]
        return None

    def disasm_func(self, lo, hi):
        return list(self.md.disasm(self.read(lo, hi - lo), lo))

    def iter_insns(self):
        for lo, hi in self.funcs:
            if not (self.text_lo <= lo < self.text_hi):
                continue
            yield lo, hi, self.disasm_func(lo, hi)


def rip_target(insn):
    m = RIP.search(insn.op_str)
    if not m:
        return None
    d = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
    return insn.address + insn.size + d
