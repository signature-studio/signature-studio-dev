#!/usr/bin/env python3
"""fa31_refs.py <SlateCore.core_64> — FA-31 (#2207): 挿入候補と UI 上流関数の参照元を静的に列挙する (診断のみ・判定は出さない)。
各 VA について (a) pdata 関数境界ごとに逆アセンブルした E8/E9 直接呼出元 (所属関数つき)、(b) 非 .text に現れる 8 バイト絶対ポインタ (vtable slot 候補) を表示する。
間接呼出 (レジスタ経由) と 32bit 相対の関数表は走査しない。vtable 所属の確定もしない。
exit 0 = 列挙完了。読めない場合のみ非 0。"""
import struct, sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1])
base = pe.OPTIONAL_HEADER.ImageBase
TARGETS = [
    (0x180caa820, "caa820 挿入候補"),
    (0x180e13590, "e13590 formatter slot2"),
    (0x180e12f20, "e12f20 formatter 構築"),
    (0x180e15030, "e15030"),
    (0x180d8ae60, "d8ae60"),
    (0x180d8c140, "d8c140"),
    (0x180d8d700, "d8d700"),
    (0x180d8c0b0, "d8c0b0 popup slot5"),
    (0x180d8c4f0, "d8c4f0"),
    (0x180d8c8b0, "d8c8b0 (d8d700 の呼出元)"),
    (0x180d8cc20, "d8cc20 (d8d700 の呼出元)"),
    (0x180d8cfe7, "d8cfe7 (d8d700 の呼出元)"),
    (0x180ca7db0, "ca7db0 map lower_bound"),
]
text = None
secs = []
for s in pe.sections:
    name = s.Name.rstrip(b"\0").decode(errors="replace")
    va0 = base + s.VirtualAddress
    raw = s.get_data()
    secs.append((name, va0, va0 + s.Misc_VirtualSize, raw))
    if name == ".text":
        text = (va0, raw)
assert text is not None
t_va, t_raw = text
md = Cs(CS_ARCH_X86, CS_MODE_64)
calls = {}
funcs = []
for rf in pe.DIRECTORY_ENTRY_EXCEPTION:
    b_va = base + rf.struct.BeginAddress
    e_va = base + rf.struct.EndAddress
    funcs.append((b_va, e_va))
    code = pe.get_data(rf.struct.BeginAddress, e_va - b_va)
    for ins in md.disasm(code, b_va):
        if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
            try:
                tgt = int(ins.op_str, 16)
            except ValueError:
                continue
            calls.setdefault(tgt, []).append(ins.address)
for va, label in TARGETS:
    direct = calls.get(va, [])
    own = [f for f in funcs if f[0] <= va < f[1]]
    print("%x %s (pdata 関数 %s) direct(call/jmp) callers=%s" % (va, label, ("%x" % own[0][0]) if own else "-", ",".join("%x(in %x)" % (a, min(f[0] for f in funcs if f[0] <= a < f[1])) if any(f[0] <= a < f[1] for f in funcs) else "%x" % a for a in direct) or "-"))
    ptr = struct.pack("<Q", va)
    hits = []
    for name, s_va, s_end, raw in secs:
        if name == ".text":
            continue
        off = 0
        while True:
            off = raw.find(ptr, off)
            if off < 0:
                break
            if off % 8 == 0:
                hits.append("%s:%x" % (name, s_va + off))
            off += 1
    print("   data-ptr hits (8-byte abs, non-.text)=%s" % (",".join(hits) or "-"))
