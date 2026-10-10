"""pe_image.py — PE32+ 読取補助 (セクション/pdata 関数境界/IAT 名/データ領域)。mlift.py から使う。"""
import struct, bisect
import pefile


class Image:
    def __init__(self, path):
        self.path = path
        self.pe = pefile.PE(path)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.size_of_image = self.pe.OPTIONAL_HEADER.SizeOfImage
        self.sections = []
        for s in self.pe.sections:
            nm = s.Name.rstrip(b'\0').decode()
            self.sections.append((nm, self.base + s.VirtualAddress, s.Misc_VirtualSize, s.SizeOfRawData,
                                  s.PointerToRawData, s.Characteristics))
        text = [s for s in self.sections if s[0] == '.text'][0]
        self.text_lo, self.text_hi = text[1], text[1] + text[2]
        self.data = self.pe.__data__
        # pdata (CHAININFO 併合 = closure.py と同一規則)
        pd = self.pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
        raw = self.pe.get_data(pd.VirtualAddress, pd.Size)
        ents = []
        for i in range(len(raw) // 12):
            b, e, u = struct.unpack_from('<III', raw, i * 12)
            ents.append((b, e, (self.pe.get_data(u & ~1, 1)[0] >> 3) & 4))
        ents.sort()
        funcs = []
        for b, e, ch in ents:
            if ch and funcs and funcs[-1][1] == b:
                funcs[-1] = (funcs[-1][0], e)
            else:
                funcs.append((b, e))
        self.funcs = [(self.base + b, self.base + e) for b, e in funcs]
        self._starts = [b for b, e in self.funcs]
        # IAT: VA -> 'dll!name'
        self.iat = {}
        if hasattr(self.pe, 'DIRECTORY_ENTRY_IMPORT'):
            for imp in self.pe.DIRECTORY_ENTRY_IMPORT:
                for i in imp.imports:
                    self.iat[i.address] = (imp.dll.decode().lower().replace('.dll', ''),
                                           i.name.decode() if i.name else 'ord%d' % i.ordinal)

    def func_of(self, va):
        i = bisect.bisect_right(self._starts, va) - 1
        if i >= 0 and self.funcs[i][0] <= va < self.funcs[i][1]:
            return self.funcs[i]
        return None

    def read(self, va, n):
        """VA からバイト列 (セクション未初期化部は 0 埋め, イメージ外は ValueError)。"""
        out = bytearray()
        while n > 0:
            for nm, lo, vs, rs, rp, ch in self.sections:
                if lo <= va < lo + max(vs, rs):
                    take = min(n, lo + max(vs, rs) - va)
                    off = va - lo
                    chunk = bytearray(take)
                    if off < rs:
                        k = min(take, rs - off)
                        chunk[:k] = self.data[rp + off:rp + off + k]
                    out += chunk; va += take; n -= take
                    break
            else:
                hdr_end = self.base + self.pe.OPTIONAL_HEADER.SizeOfHeaders
                if self.base <= va < hdr_end:
                    take = min(n, hdr_end - va)
                    out += self.data[va - self.base:va - self.base + take]; va += take; n -= take
                elif self.in_image(va):
                    nxt = min([x[1] for x in self.sections if x[1] > va] + [self.base + self.size_of_image])
                    take = min(n, nxt - va)
                    out += bytes(take); va += take; n -= take
                else:
                    raise ValueError('VA %x outside image' % va)
        return bytes(out)

    def section_of(self, va):
        for s in self.sections:
            if s[1] <= va < s[1] + max(s[2], s[3]):
                return s[0]
        return None

    def in_image(self, va):
        return self.base <= va < self.base + self.size_of_image

    def is_text(self, va):
        return self.text_lo <= va < self.text_hi

    def func_extent(self, va, md):
        """call 先 VA の関数範囲 (pdata 優先。pdata 無し leaf/thunk は ret/jmp まで線形走査, 最大 512B)。"""
        f = self.func_of(va)
        if f and f[0] == va:
            return f
        if f:      # 関数途中への call は未対応 (呼出側で拒否)
            return None
        if not self.is_text(va):
            return None
        code = self.read(va, 512)
        end = va; maxfwd = va
        for i in md.disasm(code, va):
            end = i.address + i.size
            m = i.mnemonic
            if (m == 'jmp' or m.startswith('j')) and i.operands and i.operands[0].type == 2:
                t = i.operands[0].imm
                if va <= t < va + 512 and t > maxfwd:
                    maxfwd = t
            if m in ('ret', 'int3', 'ud2') or (m == 'jmp' and True):
                if end > maxfwd:
                    break
        return (va, end)
