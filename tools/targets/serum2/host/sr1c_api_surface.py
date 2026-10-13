#!/usr/bin/env python3
# SR-1c (#256) 受入 #3: Serum2 が import する Win32 API と、実 host 実行 (WINEDEBUG=+relay) で実際に呼ばれた API の突合。
# usage: python3 sr1c_api_surface.py <Serum2_win64.vst3> <relay.log> <out.tsv>
# 出力: 1 行 1 API。列 = DLL, 名前, import 有無(PE), relay 呼出回数, 判定(called/imported-not-called)
# 注: relay ログには wine 内部 (ntdll 経由の呼出) も混ざるため、PE import テーブルの名前で絞る。
import re
import sys
from collections import Counter

import pefile

dll, log, out = sys.argv[1], sys.argv[2], sys.argv[3]
pe = pefile.PE(dll, fast_load=True)
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
imports = []
for ent in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
    d = ent.dll.decode().lower()
    for imp in ent.imports:
        if imp.name:
            imports.append((d, imp.name.decode()))
imp_set = set(imports)

calls = Counter()
pat = re.compile(r"Call ([A-Za-z0-9_.\-]+)\.([A-Za-z0-9_@?]+)")
with open(log, errors="replace") as f:
    for line in f:
        m = pat.search(line)
        if m:
            calls[(m.group(1).lower(), m.group(2))] += 1

rows = []
for d, n in sorted(imp_set):
    c = calls.get((d, n), 0) + calls.get((d.replace(".dll", ""), n), 0)
    rows.append((d, n, 1, c, "called" if c else "imported-not-called"))
with open(out, "w") as f:
    f.write("dll\tname\timported\trelay_calls\tstatus\n")
    for r in rows:
        f.write("\t".join(str(x) for x in r) + "\n")
called = sum(1 for r in rows if r[3])
print(f"import {len(rows)} 件 / relay で呼出確認 {called} 件 / 未呼出 {len(rows) - called} 件")
