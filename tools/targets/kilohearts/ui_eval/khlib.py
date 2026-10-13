"""HeartCore.core_64 共有ヘルパ (ui_eval 用): PE 読込・IAT xref・関数境界・逆アセンブル。"""
import re, struct
import numpy as np
import pefile


class Core:
    def __init__(self, path, data=None):
        self.path = path
        self.data = bytearray(data if data is not None else open(path, 'rb').read())
        self.pe = pefile.PE(data=bytes(self.data), fast_load=True)
        self.pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT'],
                                                    pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT']])
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.sec = {s.Name.rstrip(b'\0').decode(): s for s in self.pe.sections}
        t = self.sec['.text']
        self.t0, self.tsz = t.VirtualAddress, t.Misc_VirtualSize
        self.text = bytes(self.data[t.PointerToRawData:t.PointerToRawData + t.SizeOfRawData])
        pd = self.sec['.pdata']
        arr = np.frombuffer(bytes(self.data[pd.PointerToRawData:pd.PointerToRawData + pd.Misc_VirtualSize // 12 * 12]),
                            dtype='<u4').reshape(-1, 3)
        o = np.argsort(arr[:, 0])
        self.fbeg, self.fend = arr[o, 0].copy(), arr[o, 1].copy()
        self.iat = {}      # iat slot rva -> (dll, name)
        self.imports = []  # (dll, name, delay)
        for d in getattr(self.pe, 'DIRECTORY_ENTRY_IMPORT', []):
            for i in d.imports:
                nm = i.name.decode() if i.name else '#%d' % i.ordinal
                self.iat[i.address - self.base] = (d.dll.decode().lower(), nm)
                self.imports.append((d.dll.decode().lower(), nm, False))
        for d in getattr(self.pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', []):
            for i in d.imports:
                nm = i.name.decode() if i.name else '#%d' % i.ordinal
                self.imports.append((d.dll.decode().lower(), nm, True))
        self._xrefs = None

    def func_of(self, rva):
        i = int(np.searchsorted(self.fbeg, rva, side='right')) - 1
        if i >= 0 and self.fbeg[i] <= rva < self.fend[i]:
            return int(self.fbeg[i]), int(self.fend[i])
        return None

    def xrefs(self):
        """IAT 名 -> [(call-site rva, kind)] (FF15 call / FF25 jmp / mov r64,[rip+iat])"""
        if self._xrefs is not None:
            return self._xrefs
        tb, t0 = self.text, self.t0
        out = {}
        for m in re.finditer(rb'\xff[\x15\x25]', tb, flags=re.S):
            p = m.start()
            if p + 6 > len(tb):
                continue
            tgt = t0 + p + 6 + struct.unpack_from('<i', tb, p + 2)[0]
            if tgt in self.iat:
                out.setdefault(self.iat[tgt], []).append((t0 + p, 'call' if tb[p + 1] == 0x15 else 'jmp'))
        for m in re.finditer(rb'[\x48\x4c]\x8b[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]', tb, flags=re.S):
            p = m.start()
            if p + 7 > len(tb):
                continue
            tgt = t0 + p + 7 + struct.unpack_from('<i', tb, p + 3)[0]
            if tgt in self.iat:
                out.setdefault(self.iat[tgt], []).append((t0 + p, 'mov'))
        self._xrefs = out
        return out

    def read_va(self, va, n):
        rva = va - self.base
        s = self.pe.get_section_by_rva(rva)
        off = s.PointerToRawData + rva - s.VirtualAddress
        return bytes(self.data[off:off + n])

    def disasm(self, va_from, va_to):
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        return [(i.address, i.size, i.mnemonic, i.op_str) for i in md.disasm(self.read_va(va_from, va_to - va_from), va_from)]

    def lea_refs(self, target_rva):
        """`lea r64, [rip+d]` が target_rva を指す命令の rva 一覧 (関数ポインタ取得の検出)"""
        out = []
        for m in re.finditer(rb'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]', self.text, flags=re.S):
            p = m.start()
            if p + 7 > len(self.text):
                continue
            if self.t0 + p + 7 + struct.unpack_from('<i', self.text, p + 3)[0] == target_rva:
                out.append(self.t0 + p)
        return out
