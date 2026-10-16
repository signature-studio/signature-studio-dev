#!/usr/bin/env python3
"""SR-85 #5934: 閉包内の間接 call `call qword ptr [reg+disp]` の候補を、PE 内の全クラス vtable から列挙し、型 (vptr 構築) で絞る (静的)。

入力: PE・ghidra_xferonoff_indirect の SITE 行を含む log。出力: 1 行 1 サイト の TSV。
手順:
  1. .rdata/.data の全 qword から COL を探し、x64 RTTI の COL (signature=1・pSelf=自分の RVA) を持つ vtable を全部集める (vtable[-1] = COL)。
  2. 候補 slot k = disp/8 について、全 vtable の slot k の関数を候補とする (別クラス含む)。
  3. 型の絞り込み: vtable V を持つオブジェクトが実行時に生成されるには、.text のどこかで V を rip 相対 lea で
     参照する (ctor が vptr を書く) 必要がある。参照が無い V は、その動的型を持つオブジェクトが .text 内で作られないので候補から外す。
     (vptr を別オブジェクトからコピーする経路・.text 外での書込みは見ていない。)
  4. 絞った後の候補のクラス名 (TypeDescriptor) と関数 VA を出す。
usage: indirect_sr85_all_vt.py <pe> <site_log> [--tsv out.tsv] [--classes]
"""
import re
import struct
import sys
from collections import defaultdict

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe_path, site_log = sys.argv[1], sys.argv[2]
want_classes = "--classes" in sys.argv

pe = pefile.PE(pe_path)
data = open(pe_path, "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase


def sec(name):
    return next(s for s in pe.sections if s.Name.rstrip(b"\0") == name)


text = sec(b".text")
t_lo = IMG + text.VirtualAddress
t_hi = t_lo + max(text.Misc_VirtualSize, text.SizeOfRawData)
code = text.get_data()[: t_hi - t_lo]
rdata_secs = [s for s in pe.sections if s.Name.rstrip(b"\0") in (b".rdata", b".data")]


def off_of(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return rva - s.VirtualAddress + s.PointerToRawData
    return None


def td_name(td_rva):
    o = off_of(td_rva + 0x10)
    if o is None:
        return "?"
    e = data.find(b"\x00", o, o + 512)
    return data[o:e].decode(errors="replace") if e > 0 else "?"


# 1. 全 vtable
vtables = []  # (vt_va, col_va, class_name, [slot VA...])
for s in rdata_secs:
    lo = s.PointerToRawData
    hi = lo + s.SizeOfRawData
    for o in range(lo, hi - 7, 8):
        v = struct.unpack_from("<Q", data, o)[0]
        col_rva = v - IMG
        co = off_of(col_rva) if 0 < col_rva < 0x10000000 else None
        if co is None or co + 0x18 > len(data):
            continue
        if struct.unpack_from("<I", data, co)[0] != 1:
            continue
        if struct.unpack_from("<I", data, co + 0x14)[0] != col_rva:
            continue
        td_rva = struct.unpack_from("<I", data, co + 0x0C)[0]
        name = td_name(td_rva)
        slots = []
        p = o + 8
        while p + 8 <= len(data):
            w = struct.unpack_from("<Q", data, p)[0]
            if not (t_lo <= w < t_hi):
                break
            slots.append(w)
            p += 8
        if slots:
            vtables.append((IMG + (o - lo + s.VirtualAddress) + 8, v, name, slots))
print(f"all_vtables={len(vtables)}", file=sys.stderr)

# 2. vptr 構築の参照 (.text 内の rip 相対 lea の宛先)
rip_re = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
md = Cs(CS_ARCH_X86, CS_MODE_64)
# vptr 書込み: `lea R, [rip+V]` の後 3 命令以内に `mov qword ptr [X], R` (R を格納) があるもの
store_re = re.compile(r"^qword ptr \[[^\]]+\], (r[a-z0-9]+)$")
lea_targets = defaultdict(int)
insns = list(md.disasm(code, t_lo))
for i, ins in enumerate(insns):
    if ins.mnemonic != "lea":
        continue
    m = rip_re.search(ins.op_str)
    if not m:
        continue
    reg = ins.op_str.split(",")[0].strip()
    ea = ins.address + ins.size + int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
    for nxt in insns[i + 1 : i + 4]:
        if nxt.mnemonic == "mov":
            sm = store_re.match(nxt.op_str)
            if sm and sm.group(1) == reg:
                lea_targets[ea] += 1
                break
        if nxt.mnemonic in ("call", "jmp", "ret"):
            break
print(f"vptr_store_targets={len(lea_targets)}", file=sys.stderr)

constructed = [v for v in vtables if lea_targets.get(v[0], 0) > 0]
print(f"constructed_vtables={len(constructed)}", file=sys.stderr)

# 3. サイトごとの候補
pat = re.compile(r"SITE in=([0-9a-f]+) at=([0-9a-f]+) insn=CALL qword ptr \[(R[A-Z0-9]+)(?: \+ 0x([0-9a-f]+))?\]")
rows = []
for line in open(site_log):
    m = pat.search(line)
    if not m:
        continue
    fn, site, reg, disp = m.group(1), m.group(2), m.group(3), m.group(4)
    d = int(disp, 16) if disp else 0
    if d % 8:
        rows.append((fn, site, f"[{reg}+{d:#x}]", "unresolved(disp 非 8 倍数)", "", ""))
        continue
    k = d // 8
    all_c = sorted({vt[3][k] for vt in vtables if k < len(vt[3])})
    con = [vt for vt in constructed if k < len(vt[3])]
    con_c = sorted({vt[3][k] for vt in con})
    names = sorted({vt[2] for vt in con})
    rows.append((
        fn, site, f"[{reg}+{d:#x}]",
        f"slot={k} all={len(all_c)} constructed={len(con_c)}",
        ",".join(f"{c - IMG:#x}" for c in con_c),
        ",".join(names) if want_classes else str(len(names)) + " classes",
    ))

print("in_func\tsite\toperand\tresult\tcand_rva\tclasses")
for r in rows:
    print("\t".join(r))
