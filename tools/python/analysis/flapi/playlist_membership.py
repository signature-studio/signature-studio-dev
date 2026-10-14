#!/usr/bin/env python3
"""playlist の PyMethodDef 配列を FLEngine PE から引き、flapi_table.json の playlist 42 関数との対応を出す (PY-44 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/playlist_membership.py [--start 0x1114a08]

- 配列の開始 VA は既定値 (fl-win64 26.1.7.5653 の block00031_PE.bin で確認した位置)。--start で上書き可。
- 配列は name/fn/flags/doc の 32 バイト記録の連続。name が文字列として読めない記録で止める。
- 出力: 配列内の名前ごとに fn VA・flags・表の引数/戻り型・doc。表に無い名前は末尾に "not in table" として出す。
"""
import argparse
import json
import os
import struct

import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = json.load(open(os.path.join(HERE, "flapi_table.json")))["modules"]["playlist"]
DEFAULT_START = 0x1114AC8  # trackCount。直前 6 記録 (0x1114a08〜0x1114aa8) は引数名文字列で配列ではない


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=lambda s: int(s, 0), default=DEFAULT_START)
    a = ap.parse_args()
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

    rows = []
    off = a.start
    while True:
        name = cstr(struct.unpack_from("<Q", raw, off)[0])
        if name is None:
            break
        fn = struct.unpack_from("<Q", raw, off + 8)[0]
        flags = struct.unpack_from("<i", raw, off + 16)[0]
        rows.append((off, name, fn, flags))
        off += 32

    print(f"array start={a.start:#x} rows={len(rows)} (playlist table={len(TABLE)})")
    for o, name, fn, flags in rows:
        if name not in TABLE:
            print(f"not in table: {name} @ {o:#x}")
            continue
        s = TABLE[name]["sig"] or {"params": [], "returns": "?"}
        ps = ",".join(f"{p['name']}:{p['type']}" + (f"={p['default']}" if p["default"] is not None else "") for p in s["params"])
        print(f"{o:#x} {name} fn={fn:#x} flags={flags} ({ps}) -> {s['returns']} | {TABLE[name]['doc']}")
    missing = sorted(set(TABLE) - {r[1] for r in rows})
    print(f"table not in array: {missing}")


if __name__ == "__main__":
    main()
