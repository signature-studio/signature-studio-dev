#!/usr/bin/env python3
"""playlist の名前を含む PyMethodDef 配列を全て洗い、配列ごとの所属モジュールを出す (PY-44 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pymethoddef_scan.py

- 配列 = name/fn/flags/doc の 32 バイト記録の連続区間 (name が文字列として読める記録が続く間)。
- 配列の名前集合を flapi_table.json の各モジュールと突き合わせ、最も一致するモジュールを所属とみなす。
- 出力: 配列ごとに 開始 VA・件数・最良一致モジュール (一致数/件数)・playlist 名との重なり。
"""
import json
import os
import struct

import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = json.load(open(os.path.join(HERE, "flapi_table.json")))["modules"]
PL = set(TABLE["playlist"])


def main():
    pe_path = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
    raw = open(pe_path, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData) for s in pe.sections]

    def v2o(va):
        rva = va - base
        for v, vs, p, rs in secs:
            if v <= rva < v + max(vs, rs):
                return p + (rva - v)
        return None

    def cstr(va):
        fo = v2o(va) if va else None
        if fo is None:
            return None
        e = raw.find(b"\0", fo, fo + 200)
        s = raw[fo:e] if e != -1 else b""
        return s.decode() if s and len(s) <= 80 and all(32 <= c < 127 for c in s) else None

    def rec_name(off):
        return cstr(struct.unpack_from("<Q", raw, off)[0])

    # 名前 ptr の記録を走査し、playlist 名を含む連続区間を 1 配列とする (記録は 32 バイト間隔)。
    starts = []
    for off in range(0, len(raw) - 32, 8):
        if rec_name(off) in PL:
            starts.append(off)
    done = set()
    for s0 in starts:
        if s0 in done:
            continue
        names = []
        o = s0
        while True:
            n = rec_name(o)
            if n is None:
                break
            names.append(n)
            done.add(o)
            o += 32
        hits = sorted(set(names) & PL)
        best = max(((len(set(names) & set(v)), m) for m, v in TABLE.items()), key=lambda x: x[0])
        print(f"ARRAY start={s0:#x} rows={len(names)} best={best[1]}({best[0]}/{len(set(names))}) playlist_hits={len(hits)}")


if __name__ == "__main__":
    main()
