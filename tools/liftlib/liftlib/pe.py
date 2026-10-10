"""pe.py — PE イメージの VA 読取 (x64)。pefile ベース。

Image(path).read(va, n)         : ImageBase 基準の VA からバイト列 (セクション外/raw 外は 0 埋め)
Image(path).func_at(va)         : .pdata の RUNTIME_FUNCTION (begin, end) を返す
Image(path).map_into(buf, base) : ネイティブ参照用に全セクションを仮想配置したバイト列を返す
"""
import bisect
import struct

import pefile


class Image:
    def __init__(self, path):
        self.path = path
        self.pe = pefile.PE(path, fast_load=True)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.size = self.pe.OPTIONAL_HEADER.SizeOfImage
        self.sections = []
        for s in self.pe.sections:
            self.sections.append((s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData),
                                  s.PointerToRawData, s.SizeOfRawData,
                                  s.Name.rstrip(b"\0").decode("latin1")))
        with open(path, "rb") as fh:
            self.raw = fh.read()
        self._pdata = None
        self._pd_begin = None

    # ---- memory image ----------------------------------------------------
    def read(self, va, n):
        rva = va - self.base
        out = bytearray(n)
        hdr = self.pe.OPTIONAL_HEADER.SizeOfHeaders
        if 0 <= rva < hdr:
            k = min(n, hdr - rva)
            out[:k] = self.raw[rva:rva + k]
        for (sva, vsz, roff, rsz, _nm) in self.sections:
            lo, hi = max(rva, sva), min(rva + n, sva + vsz)
            if lo >= hi:
                continue
            flo, fhi = max(lo, sva), min(hi, sva + rsz)
            if flo < fhi:
                out[flo - rva:fhi - rva] = self.raw[roff + (flo - sva):roff + (fhi - sva)]
        return bytes(out)

    def virtual_image(self):
        """SizeOfImage 長の仮想配置イメージ (RVA 添字)。"""
        img = bytearray(self.size)
        hdr = self.pe.OPTIONAL_HEADER.SizeOfHeaders
        img[:hdr] = self.raw[:hdr]
        for (sva, vsz, roff, rsz, _nm) in self.sections:
            n = min(rsz, vsz)
            img[sva:sva + n] = self.raw[roff:roff + n]
        return bytes(img)

    def section_of(self, va):
        rva = va - self.base
        for (sva, vsz, _ro, _rs, nm) in self.sections:
            if sva <= rva < sva + vsz:
                return nm
        return None

    # ---- .pdata -----------------------------------------------------------
    def _load_pdata(self):
        if self._pdata is not None:
            return
        pdata = None
        for (sva, vsz, roff, rsz, nm) in self.sections:
            if nm == ".pdata":
                pdata = (roff, rsz)
        ents = []
        if pdata:
            roff, rsz = pdata
            for i in range(rsz // 12):
                b, e, u = struct.unpack_from("<III", self.raw, roff + i * 12)
                if b == 0 and e == 0:
                    continue
                ents.append((self.base + b, self.base + e, u))
        ents.sort()
        self._pdata = ents
        self._pd_begin = [e[0] for e in ents]

    def func_at(self, va):
        self._load_pdata()
        i = bisect.bisect_right(self._pd_begin, va) - 1
        if i >= 0:
            b, e, _u = self._pdata[i]
            if b <= va < e:
                return (b, e)
        return None

    def pdata_functions(self):
        self._load_pdata()
        return [(b, e) for (b, e, _u) in self._pdata]

    def relocs_dir64(self):
        """IMAGE_REL_BASED_DIR64 の RVA 一覧。"""
        d = self.pe.OPTIONAL_HEADER.DATA_DIRECTORY[5]
        if d.VirtualAddress == 0:
            return []
        out = []
        rva, end = d.VirtualAddress, d.VirtualAddress + d.Size
        base = self.read(self.base + rva, d.Size)
        i = 0
        while i + 8 <= len(base):
            page, blk = struct.unpack_from("<II", base, i)
            if blk < 8:
                break
            for k in range((blk - 8) // 2):
                e = struct.unpack_from("<H", base, i + 8 + k * 2)[0]
                if (e >> 12) == 10:
                    out.append(page + (e & 0xFFF))
            i += blk
        return out
