#!/usr/bin/env python3
"""PY-68 (#2471): Delphi VMT (クラス参照 H) からクラス名・インスタンスサイズ・親チェーン・公開メソッドを読む (実機不要)。

  python3 analysis/py68_vmt.py vmt <PE.bin> <H VA hex> [...]      # クラス名・サイズ・親チェーン
  python3 analysis/py68_vmt.py methods <PE.bin> <H VA hex> [...]  # 親チェーン各段の公開メソッド (名前・コード VA)

Delphi 64-bit の VMT 負オフセット (REPORT_PY59 §9 で実測): [H-0xc8]=自己ポインタ (H)・[H-0x98]=公開メソッド表・
[H-0x88]=クラス名 (ShortString へのポインタ)・[H-0x80]=インスタンスサイズ・[H-0x78]=親 VMT の格納位置
(ポインタのポインタ)。[H-0x30] は NewInstance 相当 (`py59_handle.py` の F)。
自己ポインタが一致しない値は VMT と見なさない。
"""
import struct
import sys

import pefile


class Pe:
    def __init__(self, path):
        self.pe = pefile.PE(path, fast_load=True)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        with open(path, "rb") as fh:
            self.data = fh.read()

    def raw(self, va):
        rva = va - self.base
        for s in self.pe.sections:
            if s.PointerToRawData and s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
                return s.PointerToRawData + (rva - s.VirtualAddress)
        raise SystemExit(f"no raw data for {va:#x}")

    def q(self, va):
        return struct.unpack("<Q", self.data[self.raw(va):self.raw(va) + 8])[0]

    def w(self, va):
        return struct.unpack("<H", self.data[self.raw(va):self.raw(va) + 2])[0]

    def dword(self, va):
        return struct.unpack("<i", self.data[self.raw(va):self.raw(va) + 4])[0]

    def is_vmt(self, vmt):
        return vmt != 0 and self.q(vmt - 0xC8) == vmt

    def classname(self, vmt):
        p = self.raw(self.q(vmt - 0x88))
        n = self.data[p]
        return self.data[p + 1:p + 1 + n].decode("ascii", "replace")

    def chain(self, vmt):
        """vmt 自身から親へ辿った VMT の列。vmtParent は親 VMT を指すスロットへのポインタ。"""
        out, seen = [], set()
        while self.is_vmt(vmt) and vmt not in seen:
            seen.add(vmt)
            out.append(vmt)
            slot = self.q(vmt - 0x78)
            vmt = self.q(slot) if slot else 0
        return out

    def methods(self, vmt):
        """公開メソッド表 ([H-0x98]): 件数 (word)・各エントリ [size word][code qword][ShortString 名]。"""
        mt = self.q(vmt - 0x98)
        if not mt:
            return []
        out, p = [], mt + 2
        for _ in range(self.w(mt)):
            size, code = self.w(p), self.q(p + 2)
            n = self.data[self.raw(p + 10)]
            out.append((self.data[self.raw(p + 10) + 1:self.raw(p + 10) + 1 + n].decode("latin1"), code))
            p += size
        return out


def main():
    mode, path, args = sys.argv[1], sys.argv[2], sys.argv[3:]
    pe = Pe(path)
    for arg in args:
        h = int(arg, 16)
        if not pe.is_vmt(h):
            print(f"H {h:#x}: 自己ポインタ [H-0xc8] が一致しない (VMT ではない)")
            continue
        if mode == "vmt":
            size = pe.dword(h - 0x80)
            names = " <- ".join(pe.classname(v) for v in pe.chain(h))
            print(f"H {h:#x}: instsize={size:#x}({size}) chain={names}")
        elif mode == "methods":
            for v in pe.chain(h):
                size = pe.dword(v - 0x80)
                ms = ", ".join(f"{n}={c:#x}" for n, c in pe.methods(v))
                print(f"{pe.classname(v)} (instsize={size:#x}): {ms or '-'}")
        else:
            raise SystemExit("mode は vmt か methods")


if __name__ == "__main__":
    main()
