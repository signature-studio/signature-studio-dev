#!/usr/bin/env python3
"""PY-63 (#2030): py63_refs.py のネガティブコントロール (正例・負例で検出能力を確認)。

  cd tools/python && python3 analysis/py63_negctl.py <PE.bin>

C1: 既知の rel32 call 先は検出される (正例)。
C2: 参照の無い VA は rel32 も abs64 も 0 件 (負例)。
C3: .data 内で 1 回だけ出現する abs64 は、その格納位置が検出される (正例)。
C4: C1 の VA を +4 にずらすと、元の call 元は検出されない (改変例)。
"""
import os
import re
import struct
import subprocess
import sys

import pefile

PE = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(HERE, "py63_refs.py")
data = open(PE, "rb").read()
pe = pefile.PE(PE, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
sec = {s.Name.rstrip(b"\0").decode(): s for s in pe.sections}
text, dsec = sec[".text"], sec[".data"]
tva = base + text.VirtualAddress
tdata = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]


def refs(va):
    out = subprocess.run([sys.executable, REFS, PE, hex(va)], capture_output=True, text=True, check=True).stdout
    rel = re.search(r"rel32 call/jmp: (.*)", out).group(1)
    total = int(re.search(r"total=(\d+)", out).group(1))
    return rel, total, out


ok_all = True


def check(name, cond, detail):
    global ok_all
    ok_all &= bool(cond)
    print(f"{name}: {'PASS' if cond else 'FAIL'} | {detail}")


calls = []
for i in range(len(tdata) - 5):
    if tdata[i] == 0xE8:
        tgt = tva + i + 5 + struct.unpack_from("<i", tdata, i + 1)[0]
        if tva <= tgt < tva + text.SizeOfRawData:
            calls.append((tva + i, tgt))
ins, tgt = calls[1000]

rel, _, _ = refs(tgt)
check("C1 positive rel32", f"'{hex(ins)}'" in rel, f"call site {hex(ins)} -> target {hex(tgt)}; rel32 list size={rel.count(',') + 1}")

rel, total, _ = refs(0x12345678)
check("C2 negative", rel == "none" and total == 0, f"rel32={rel} abs64 total={total}")

rel, _, _ = refs(tgt + 4)
check("C4 shifted VA", f"'{hex(ins)}'" not in rel, f"VA {hex(tgt + 4)} must not list {hex(ins)}; rel32={rel}")

dlo, dhi = dsec.PointerToRawData, dsec.PointerToRawData + dsec.SizeOfRawData
found = None
for k in range(dlo, dhi - 8, 8):
    v = struct.unpack_from("<Q", data, k)[0]
    if tva <= v < tva + text.SizeOfRawData:
        ab = struct.pack("<Q", v)
        if data.find(ab) == k and data.find(ab, k + 1) < 0:
            found = (k, v)
            break
if found is None:
    check("C3 positive abs64", False, "no unique .data abs64 found")
else:
    k, v = found
    _, total, out = refs(v)
    check("C3 positive abs64", total == 1 and f"file_off={k:#x}" in out,
          f"slot file_off={k:#x} value={v:#x}; abs64 total={total}")

print("ALL PASS" if ok_all else "SOME FAIL")
sys.exit(0 if ok_all else 1)
