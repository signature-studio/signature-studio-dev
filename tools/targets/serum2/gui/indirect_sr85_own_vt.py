#!/usr/bin/env python3
"""SR-85 #5034: 閉包内のレジスタ経由の間接 call (`call qword ptr [reg+disp]`) を、XferOnOffButton 自身の vtable に限って候補化する。

範囲: COL は vtable_fn_addrs.py が出した 8 関数の COL (XferOnOffButton の 3 種) だけ。
  それ以外のクラスの vtable (例: this[3] の内部オブジェクト) は候補に入れず、件数として残す。
入力: PE・ghidra_xferonoff_indirect の SITE 行を含む log・出力先 TSV。
出力: 1 行 1 サイト (in_func, site, operand, candidates 関数 VA のカンマ区切り or 理由)。
usage: indirect_sr85_own_vt.py <pe> <site_log> <cols_hex,...>
"""
import re
import struct
import sys

import pefile

pe_path, site_log, cols = sys.argv[1], sys.argv[2], [int(c, 16) for c in sys.argv[3].split(",")]
pe = pefile.PE(pe_path)
data = open(pe_path, "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
t_lo = IMG + text.VirtualAddress
t_hi = t_lo + max(text.Misc_VirtualSize, text.SizeOfRawData)


def off_of(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return rva - s.VirtualAddress + s.PointerToRawData
    return None


def vtables_of(col_rva):
    """COL の絶対アドレスを指すポインタ (vtable[-1]) の直後から、.text を指す関数ポインタ列を読む。"""
    out = []
    needle = struct.pack("<Q", IMG + col_rva)
    p = data.find(needle)
    while p != -1:
        o = p + 8
        slots = []
        while o + 8 <= len(data):
            v = struct.unpack_from("<Q", data, o)[0]
            if not (t_lo <= v < t_hi):
                break
            slots.append(v)
            o += 8
        if slots:
            out.append(slots)
        p = data.find(needle, p + 1)
    return out


own = []
for c in cols:
    own.extend(vtables_of(c))
print(f"own_vtables={len(own)} cols={','.join(hex(c) for c in cols)}", file=sys.stderr)

pat = re.compile(r"SITE in=([0-9a-f]+) at=([0-9a-f]+) insn=CALL qword ptr \[(R[A-Z0-9]+)(?: \+ 0x([0-9a-f]+))?\]")
print("in_func\tsite\toperand\tresult")
for line in open(site_log):
    m = pat.search(line)
    if not m:
        continue
    fn, site, reg, disp = m.group(1), m.group(2), m.group(3), m.group(4)
    op = f"[{reg}{' + 0x' + disp if disp else ''}]"
    d = int(disp, 16) if disp else 0
    if d % 8:
        print(f"{fn}\t{site}\t{op}\tunresolved(disp 非 8 倍数)")
        continue
    slot = d // 8
    cands = sorted({vt[slot] for vt in own if slot < len(vt)})
    res = ",".join(hex(c) for c in cands) if cands else "unresolved(own vt に slot 無し)"
    print(f"{fn}\t{site}\t{op}\tslot={slot} n={len(cands)} {res}")
