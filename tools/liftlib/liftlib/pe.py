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

    def _chain_parent(self, u):
        """UNWIND_INFO (RVA u) が CHAININFO なら親 RUNTIME_FUNCTION (begin,end) を返す。"""
        try:
            d = self.read(self.base + u, 4)
            flags = d[0] >> 3
            if not (flags & 4):
                return None
            ncodes = d[2]
            off = 4 + ((ncodes + 1) & ~1) * 2
            b, e, _u2 = struct.unpack("<III", self.read(self.base + u + off, 12))
            return (self.base + b, self.base + e)
        except Exception:
            return None

    def _merged(self):
        """chain 併合した関数範囲 {root_begin: [(b,e), ...]}"""
        if hasattr(self, "_mg"):
            return self._mg
        self._load_pdata()
        root = {}
        for (b, e, u) in self._pdata:
            p = self._chain_parent(u)
            root[b] = p[0] if p else b
        groups = {}
        for (b, e, u) in self._pdata:
            r = root[b]
            for _ in range(8):
                r2 = root.get(r, r)
                if r2 == r:
                    break
                r = r2
            groups.setdefault(r, []).append((b, e))
        self._mg = groups
        self._mg_begin = sorted(groups)
        self._mg_of = {}
        for r, lst in groups.items():
            for (b, e) in lst:
                self._mg_of[b] = r
        return groups

    def func_at(self, va, merge=True):
        """va を含む関数の範囲 (b, e)。merge=True なら chain された pdata を併合 (連続部分のみ)。"""
        self._load_pdata()
        i = bisect.bisect_right(self._pd_begin, va) - 1
        if i < 0:
            return None
        b, e, _u = self._pdata[i]
        if not (b <= va < e):
            return None
        if not merge:
            return (b, e)
        self._merged()
        r = self._mg_of.get(b, b)
        lst = sorted(self._mg[r])
        # r から連続して接する範囲を結合
        cur_b, cur_e = lst[0]
        for (bb, ee) in lst[1:]:
            if bb <= cur_e:
                cur_e = max(cur_e, ee)
            else:
                break
        return (cur_b, cur_e) if cur_b <= va or True else (b, e)

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
