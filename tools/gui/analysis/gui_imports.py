#!/usr/bin/env python3
"""FL (win64 FLEngine_x64.dll) の import を全列挙し、静的 xref 件数を数える (GUI 系の優先度付けの入力)。

入力: PE32+ (既定 tools/m2/work/block00031_PE.bin = FLEngine_x64.dll)
出力: imports_all.json (同ディレクトリ)

xref 件数の数え方 (バイトパターン走査; Ghidra 非依存の *推定値*):
  - FF 15 disp32 (call [rip+d]) / FF 25 disp32 (jmp [rip+d]) / REX 8B modrm(rip) (mov r,[rip+d])
    が IAT スロットを直接参照 -> 直接参照
  - FF 25 thunk (.text 内で IAT へ jmp するだけのスタブ) を E8/E9 rel32 で呼ぶ -> thunk 経由
  Delphi は thunk 経由が主。誤検出は .text 内の偶然一致のみ (target が thunk 先頭と厳密一致するもののみ数える)。
"""
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PE = os.path.join(HERE, "..", "..", "m2", "work", "block00031_PE.bin")


def rd(data, off, fmt):
    return struct.unpack_from(fmt, data, off)


class PE:
    def __init__(self, path):
        self.data = open(path, "rb").read()
        d = self.data
        pe = rd(d, 0x3C, "<I")[0]
        assert d[pe:pe + 4] == b"PE\0\0"
        nsec = rd(d, pe + 6, "<H")[0]
        optsz = rd(d, pe + 20, "<H")[0]
        opt = pe + 24
        assert rd(d, opt, "<H")[0] == 0x20B, "PE32+ only"
        self.image_base = rd(d, opt + 24, "<Q")[0]
        self.dd = opt + 112
        so = opt + optsz
        self.secs = []
        for i in range(nsec):
            e = so + i * 40
            name = d[e:e + 8].split(b"\0")[0].decode("latin1")
            vsz, va, rsz, rptr = rd(d, e + 8, "<IIII")
            self.secs.append((name, va, vsz, rptr, rsz))

    def off(self, rva):
        for _, va, vsz, rptr, rsz in self.secs:
            if va <= rva < va + max(vsz, rsz):
                return rptr + rva - va
        raise ValueError(hex(rva))

    def cstr(self, rva):
        o = self.off(rva)
        e = self.data.index(b"\0", o)
        return self.data[o:e].decode("latin1")

    def imports(self):
        """returns {iat_slot_rva: (dll, name, kind)}"""
        d = self.data
        out = {}
        irva, isz = rd(d, self.dd + 8, "<II")
        if irva:
            p = self.off(irva)
            while True:
                oft, _, _, name_rva, ft = rd(d, p, "<IIIII")
                if name_rva == 0 and ft == 0:
                    break
                dll = self.cstr(name_rva).lower()
                self._thunks(out, dll, oft or ft, ft, "static")
                p += 20
        drva, dsz = rd(d, self.dd + 13 * 8, "<II")
        if drva:
            p = self.off(drva)
            while True:
                attrs, dllname, _, iat, int_, _, _, _ = rd(d, p, "<IIIIIIII")
                if dllname == 0:
                    break
                dll = self.cstr(dllname).lower()
                self._thunks(out, dll, int_, iat, "delay")
                p += 32
        return out

    def _thunks(self, out, dll, int_rva, iat_rva, kind):
        d = self.data
        po = self.off(int_rva)
        i = 0
        while True:
            v = rd(d, po + 8 * i, "<Q")[0]
            if v == 0:
                break
            if v >> 63:
                name = "#%d" % (v & 0xFFFF)
            else:
                name = self.cstr((v & 0x7FFFFFFF) + 2)
            out[iat_rva + 8 * i] = (dll, name, kind)
            i += 1

    def text(self):
        for name, va, vsz, rptr, rsz in self.secs:
            if name == ".text":
                return va, self.data[rptr:rptr + min(vsz, rsz)]
        raise RuntimeError("no .text")


def count_xrefs(pe, slots):
    tva, txt = pe.text()
    direct = {}
    thunks = {}  # thunk_rva -> slot
    for m in re.finditer(rb"\xff[\x15\x25]", txt):
        i = m.start()
        if i + 6 > len(txt):
            continue
        disp = struct.unpack_from("<i", txt, i + 2)[0]
        tgt = tva + i + 6 + disp
        if tgt in slots:
            if txt[i + 1] == 0x25:
                thunks[tva + i] = tgt
            direct[tgt] = direct.get(tgt, 0) + 1
    for m in re.finditer(rb"[\x48\x4c]\x8b[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]", txt):
        i = m.start()
        if i + 7 > len(txt):
            continue
        disp = struct.unpack_from("<i", txt, i + 3)[0]
        tgt = tva + i + 7 + disp
        if tgt in slots:
            direct[tgt] = direct.get(tgt, 0) + 1
    via = {}
    for m in re.finditer(rb"[\xe8\xe9]", txt):
        i = m.start()
        if i + 5 > len(txt):
            continue
        rel = struct.unpack_from("<i", txt, i + 1)[0]
        tgt = tva + i + 5 + rel
        s = thunks.get(tgt)
        if s is not None:
            via[s] = via.get(s, 0) + 1
    return direct, via, len(thunks)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PE
    pe = PE(path)
    slots = pe.imports()
    direct, via, nthunk = count_xrefs(pe, slots)
    rows = []
    for rva, (dll, name, kind) in slots.items():
        rows.append({
            "dll": dll, "name": name, "kind": kind, "iat_rva": hex(rva),
            "xref_direct": direct.get(rva, 0), "xref_via_thunk": via.get(rva, 0),
            "xref": direct.get(rva, 0) + via.get(rva, 0),
        })
    rows.sort(key=lambda r: (-r["xref"], r["dll"], r["name"]))
    out = {"pe": os.path.basename(path), "total_imports": len(rows), "text_iat_thunks": nthunk, "imports": rows}
    json.dump(out, open(os.path.join(HERE, "imports_all.json"), "w"), indent=1)
    per = {}
    for r in rows:
        e = per.setdefault(r["dll"], [0, 0])
        e[0] += 1
        e[1] += r["xref"]
    print("imports=%d thunks=%d" % (len(rows), nthunk))
    for k, v in sorted(per.items(), key=lambda kv: -kv[1][1]):
        print("%-22s n=%3d xref=%6d" % (k, v[0], v[1]))


if __name__ == "__main__":
    main()
