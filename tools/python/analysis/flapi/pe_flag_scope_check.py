#!/usr/bin/env python3
"""FLEngine PE の 3 フラグ (flagA `0x16baff0`・flagB `0x16baff1`・flagC `0x13e7628`) の書込み 18 件 (PY-110 付録 #2926 §1-2)
について、所属関数・直接 call の呼出し元と、midiNoteOn ハンドラ `0xd5c800` への直接 call 閉包を出す (#3649 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_flag_scope_check.py

- 所属関数: pe_callgraph.function_starts (int3 パディング直後の命令を関数先頭とみなす)。
- 呼出し元: 所属関数の先頭 VA への直接 call (E8)。直接 jmp (末尾呼出し) の箇所も数える。
- 閉包: 書込み関数の集合から直接 call のみで前進し、ハンドラ 0xd5c800 へ至るかを深さ 60 まで見る (pe_callgraph.walk)。
  間接 call (call reg・call [mem]) は辿らない。
- ゲート: ハンドラ 0xd5c800 の直接 call を、ゲート呼出し 0xd5c858 (→ 0x11d1430 → vt+0x88) の前後で分ける。
- vtable: V = 0x125b1c0 の +0x48・+0x60・+0x88・+0x90 の格納値 (ファイル上)。
- 間接呼出しの数: `call qword ptr [reg+0x60]` と `[reg+0x88]` の箇所数 (far call `call ptr [..]` = FF /3 は数えない)。
- 格納箇所: 書込み関数の先頭 VA を 8 byte 境界で格納する箇所 (関数ポインタ表・vtable の探索の入口)。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import bisect
import collections
import os
import re
import struct
import sys

import pefile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe_callgraph as pc  # noqa: E402

WRITES = [
    ("A", 0xC4DEA0, 1), ("A", 0xC4EA3B, 0), ("A", 0xD1A2AC, 1), ("A", 0xD1CB19, 0),
    ("B", 0xF46338, 0), ("B", 0xF520EB, 1), ("B", 0xF53F20, 0), ("B", 0xFEFBD3, 1),
    ("B", 0xFEFCD7, 0), ("B", 0xFFF311, 1), ("B", 0xFFF3C3, "bl"), ("B", 0x1042E47, 1),
    ("B", 0x10440AF, "cl"), ("B", 0x11D6145, 1), ("B", 0x11D6310, 0), ("B", 0x11D631F, 0),
    ("C", 0x11C761C, 1), ("C", 0x1262977, 1),
]
HANDLER = 0xD5C800
GATE_CALL = 0xD5C858
GATE_FN = 0x11D1430
VT = 0x125B1C0


def main():
    pe = pefile.PE(pc.PE, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    raw = open(pc.PE, "rb").read()

    def va_to_fo(va):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                return s.PointerToRawData + (rva - s.VirtualAddress)
        raise ValueError(hex(va))

    def fo_to_va(fo):
        for s in pe.sections:
            if s.PointerToRawData <= fo < s.PointerToRawData + s.SizeOfRawData:
                return base + s.VirtualAddress + (fo - s.PointerToRawData)
        return None

    insns = pc.load()
    starts = pc.function_starts(insns)

    def func_of(va):
        i = bisect.bisect_right(starts, va) - 1
        return starts[i] if i >= 0 else None

    calls_of = collections.defaultdict(set)
    sites = collections.defaultdict(list)
    call_tgt = {}
    jumps = collections.defaultdict(list)
    indirect = collections.Counter()
    for a, m, o in insns:
        if m == "call" and o.startswith("0x"):
            t = int(o, 16)
            sites[t].append(a)
            call_tgt[a] = t
            calls_of[func_of(a)].add(t)
        elif m == "call":
            if re.search(r"qword ptr \[[^\]]*\+ 0x60\]", o):
                indirect["+0x60"] += 1
            if re.search(r"qword ptr \[[^\]]*\+ 0x88\]", o):
                indirect["+0x88"] += 1
        elif m == "jmp" and o.startswith("0x"):
            jumps[int(o, 16)].append(a)

    funcs = sorted({func_of(w[1]) for w in WRITES})
    print(f"writes {len(WRITES)} (A {sum(w[0] == 'A' for w in WRITES)} / B {sum(w[0] == 'B' for w in WRITES)} / C {sum(w[0] == 'C' for w in WRITES)})")
    print(f"writer functions {len(funcs)}")
    for flag, va, val in WRITES:
        f = func_of(va)
        cs = sites.get(f, [])
        cs_txt = ", ".join(f"{hex(c)} (in {hex(func_of(c))})" for c in cs[:4])
        more = f" +{len(cs) - 4} more" if len(cs) > 4 else ""
        print(f"  flag {flag} write {hex(va)} val {val} -> func {hex(f)} direct callers {len(cs)}: {cs_txt}{more}")
    for f in funcs:
        if jumps.get(f):
            print(f"  tail-jmp to writer function {hex(f)}: {[hex(j) for j in jumps[f]]}")

    print(f"gate: handler {hex(HANDLER)} calls {hex(GATE_FN)} at {hex(GATE_CALL)}: {GATE_CALL in sites.get(GATE_FN, [])}")
    for s in sorted(a for a in call_tgt if func_of(a) == HANDLER):
        tag = "pre-gate" if s < GATE_CALL else ("gate" if s == GATE_CALL else "post-gate")
        print(f"  handler call {hex(s)} ({tag}) -> {hex(call_tgt[s])}")

    reached = 0
    for f in funcs:
        _, hits = pc.walk([f], calls_of, {HANDLER}, 60)
        if hits:
            reached += 1
            print(f"  reach {hex(f)} -> handler: " + " -> ".join(hex(x) for x in hits[0][::-1]))
    print(f"writer functions reaching handler by direct calls (depth <= 60): {reached} of {len(funcs)}")

    for name, off in (("+0x48", 0x48), ("+0x60", 0x60), ("+0x88", 0x88), ("+0x90", 0x90)):
        print(f"vt V{name} = {hex(struct.unpack_from('<Q', raw, va_to_fo(VT + off))[0])}")
    print(f"indirect call sites [reg+0x60] {indirect['+0x60']}, [reg+0x88] {indirect['+0x88']}")

    for f in funcs:
        at = []
        p = raw.find(struct.pack("<Q", f))
        while p != -1 and len(at) < 4:
            va = fo_to_va(p)
            if va is not None and va % 8 == 0:
                at.append(hex(va))
            p = raw.find(struct.pack("<Q", f), p + 1)
        print(f"  qword {hex(f)} stored at {at if at else 'nowhere'}")


if __name__ == "__main__":
    main()
