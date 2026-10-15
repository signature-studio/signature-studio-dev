#!/usr/bin/env python3
"""cpi_entry_refs.py: CreatePlugInstance の名前文字列と export を、lift 済み C から参照しているかを実測する (#5253 受入 2)。

Wrapper の起動経路 (LoadLibrary → GetProcAddress("CreatePlugInstance")) は、Wrapper の中の code が名前を参照する場合だけ
block 内から到達できる。本スクリプトは PE の export 表から名前文字列の VA を求め、x64c 生成 C にその VA が出る箇所を数える。
usage: cpi_entry_refs.py <block.bin> <ott_lifted.c> [export 名 (既定 CreatePlugInstance)]
出力は JSON 1 個 (name_va・export_va・name_refs・export_refs・getprocaddress_calls・name_ref_lines)。
"""
import json
import sys

import pefile

block, lifted = sys.argv[1], sys.argv[2]
export = sys.argv[3] if len(sys.argv) > 3 else "CreatePlugInstance"

pe = pefile.PE(block)
ib = pe.OPTIONAL_HEADER.ImageBase
sym = next(s for s in pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name == export.encode())
export_va = ib + sym.address
data = open(block, "rb").read()
name_off = data.find(export.encode() + b"\x00")
name_va = ib + pe.get_rva_from_offset(name_off)

name_hex = "0x%x" % name_va
export_hex = "0x%x" % export_va
name_lines = []
name_refs = export_refs = gpa = 0
with open(lifted, encoding="utf-8", errors="replace") as fh:
    for n, line in enumerate(fh, 1):
        if name_hex + "ULL" in line or name_hex + ")" in line or name_hex + "," in line or name_hex + ";" in line:
            name_refs += 1
            if len(name_lines) < 20:
                name_lines.append(n)
        if export_hex + "ULL" in line or export_hex + ")" in line:
            export_refs += 1
        if "imp_GetProcAddress();" in line:
            gpa += 1

print(json.dumps({
    "export": export,
    "name_va": name_hex,
    "export_va": export_hex,
    "name_refs": name_refs,
    "export_refs": export_refs,
    "getprocaddress_calls": gpa,
    "name_ref_lines": name_lines,
}, indent=1))
