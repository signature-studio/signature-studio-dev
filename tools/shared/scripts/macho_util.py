#!/usr/bin/env python3
"""最小 Mach-O (thin x86_64) パーサ: セグメント/セクション、VA<->file offset 変換"""
import struct

class MachO:
    def __init__(self, path):
        self.path = path
        self.d = open(path, "rb").read()
        d = self.d
        magic, cpu, sub, ft, ncmds, sz, flags, _ = struct.unpack_from("<IiiIIIII", d, 0)
        assert magic == 0xFEEDFACF, hex(magic)
        self.segs = []; self.sects = []
        off = 32
        for _ in range(ncmds):
            cmd, cs = struct.unpack_from("<II", d, off)
            if cmd == 0x19:
                segname = d[off+8:off+24].rstrip(b"\0").decode()
                vmaddr, vmsize, fileoff, filesize, maxp, initp, nsects, fl = struct.unpack_from("<QQQQiiII", d, off+24)
                self.segs.append((segname, vmaddr, vmsize, fileoff, filesize))
                so = off + 72
                for i in range(nsects):
                    sname = d[so:so+16].rstrip(b"\0").decode()
                    sgn = d[so+16:so+32].rstrip(b"\0").decode()
                    addr, size, offset, align, reloff, nreloc, sflags = struct.unpack_from("<QQIIIII", d, so+32)
                    self.sects.append((sgn, sname, addr, size, offset, sflags))
                    so += 80
            off += cs
    def va2off(self, va):
        for n, vm, vs, fo, fs in self.segs:
            if vm <= va < vm + fs and fs:
                return fo + (va - vm)
        return None
    def off2va(self, off):
        for n, vm, vs, fo, fs in self.segs:
            if fo <= off < fo + fs and fs:
                return vm + (off - fo)
        return None
    def section(self, sg, sn):
        for s in self.sects:
            if s[0] == sg and s[1] == sn: return s
