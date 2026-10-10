#!/usr/bin/env python3
"""MSVC x64 RTTI から vtable を引き、各仮想関数の VA / サイズ(.pdata) を一覧する。
usage: rtti_vtables.py <pe> <regex-on-mangled-typename> [out.json]
例: rtti_vtables.py SlateCore.core_64 'FreshAir|SnapinDsp'
"""
import sys, re, struct, json, pefile


def main():
    path, rx = sys.argv[1], re.compile(sys.argv[2])
    outp = sys.argv[3] if len(sys.argv) > 3 else None
    pe = pefile.PE(path)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = pe.__data__
    pd = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    raw = pe.get_data(pd.VirtualAddress, pd.Size)
    funcs = {}
    for i in range(len(raw) // 12):
        b, e, _u = struct.unpack_from('<III', raw, i * 12)
        funcs[b] = e - b
    text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    t0, t1 = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize
    rd = [s for s in pe.sections if s.Name.rstrip(b'\0') in (b'.rdata', b'.data', b'_RDATA')]

    tds = {}
    for m in re.finditer(rb'\.\?A[VU][^\x00]{1,300}@@\x00', data):
        nm = m.group(0)[:-1].decode(errors='replace')
        if rx.search(nm):
            try:
                tds[pe.get_rva_from_offset(m.start() - 16)] = nm
            except Exception:
                pass

    out = []
    for td_rva, nm in tds.items():
        pat = struct.pack('<I', td_rva)
        cols = []
        for s in rd:
            blob = data[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
            j = blob.find(pat)
            while j >= 0:
                k = j - 12
                if k >= 0 and k % 4 == 0 and struct.unpack_from('<I', blob, k)[0] == 1:
                    cols.append(s.VirtualAddress + k)
                j = blob.find(pat, j + 1)
        for col_rva in cols:
            patq = struct.pack('<Q', base + col_rva)
            for s in rd:
                blob = data[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
                j = blob.find(patq)
                while j >= 0:
                    if j % 8 == 0:
                        ents, o = [], j + 8
                        while o + 8 <= len(blob):
                            v = struct.unpack_from('<Q', blob, o)[0] - base
                            if not (t0 <= v < t1):
                                break
                            ents.append((hex(base + v), funcs.get(v, -1)))
                            o += 8
                        out.append({"type": nm, "vtable_va": hex(base + s.VirtualAddress + j + 8),
                                    "n": len(ents), "entries": ents})
                    j = blob.find(patq, j + 1)
    out.sort(key=lambda d: d["type"])
    if outp:
        json.dump(out, open(outp, 'w'), indent=1)
    for d in out:
        print(d["type"], d["vtable_va"], "n=%d" % d["n"], "bytes=%d" % sum(max(0, s) for _, s in d["entries"]))


main()
