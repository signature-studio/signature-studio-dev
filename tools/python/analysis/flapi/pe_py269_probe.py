#!/usr/bin/env python3
"""PY-269 (#3902): TUndoEvent_MovedFXTracks の VMT スロット 1 (0x1021670) の呼出し元の集計と、
0x1021670 の [rbp+0x30] (0x45c290 の引数) の所属の確認 (解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py269_probe.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import bisect
import os
import re
import struct
import sys

import pefile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe_callgraph as pc  # noqa: E402

VMT = 0x1012F40
SLOT1 = 0x1021670
CLASSREF = 0x1012E78
FN_REF = 0x101CA60
CALLER_DYN = re.compile(r"qword ptr \[(r\w+) \+ (0x[0-9a-f]+|\d+)\]")
FN_END = 0x1021A40
RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" :: {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def main():
    raw = open(pc.PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase

    def fo(va):
        for s in pe.sections:
            lo = base + s.VirtualAddress
            if lo <= va < lo + s.SizeOfRawData:
                return va - lo + s.PointerToRawData
        raise ValueError(f"{va:#x}")

    insns = pc.load()
    addr_idx = {a: k for k, (a, _, _) in enumerate(insns)}
    starts = pc.function_starts(insns)

    def fstart(a):
        i = bisect.bisect_right(starts, a) - 1
        return starts[i] if i >= 0 else None

    def body(lo, n):
        k = addr_idx[lo]
        return insns[k:k + n]

    name_ptr = struct.unpack_from("<Q", raw, fo(VMT - 0x88))[0]
    name = raw[fo(name_ptr) + 1:fo(name_ptr) + 1 + raw[fo(name_ptr)]].decode("latin1")
    slot1 = struct.unpack_from("<Q", raw, fo(VMT + 8))[0]
    check("C1 VMT 0x1012f40 は TUndoEvent_MovedFXTracks、slot 1 = 0x1021670",
          name == "TUndoEvent_MovedFXTracks" and slot1 == SLOT1, f"{name} {slot1:#x}")

    direct_e8 = [hex(a) for a, m, o in insns if m == "call" and o == hex(SLOT1)]
    check("C2 0x1021670 への直接 call (E8) は 0 件", not direct_e8, str(direct_e8[:3]))

    dyn = []
    for a, m, o in insns:
        if m == "call":
            mm = CALLER_DYN.search(o)
            if mm and int(mm.group(2), 0) == 8:
                dyn.append(a)
    check("C3 call qword ptr [reg+8] (スロット 1 の仮想呼出し) は 1638 件 (10 進 8 も数える)",
          len(dyn) == 1638, f"{len(dyn)} 件")
    table = [a for a in dyn if b"\x42\x00\xf1\xff" in raw[fo(a) - 24:fo(a) + 24]]
    check("C3b 1638 件の ±24 バイトにデータ表の目印 42 00 f1 ff を含む箇所は 0 件",
          not table, str([hex(a) for a in table]))

    def junk(m, o):
        return (m in ("int1", "(bad)") or (m == "add" and (o == "cl, sil" or (
            o.startswith("byte ptr [") and o.endswith("], al")))) or (m == "adc" and o == "al, 1"))

    addr_k = {a: k for k, (a, _, _) in enumerate(insns)}
    jl = [a for a in dyn if any(junk(m, o) for _, m, o in insns[max(0, addr_k[a] - 12):addr_k[a] + 4])]
    check("C3c 直前 12 命令 (後 3 命令) に誤デコード (junk) を含む箇所は 6 件 (いずれも関数本体内・REPORT §3)",
          sorted(jl) == sorted([0x50CF45, 0x7CE110, 0xACCA20, 0xACCA90, 0x1006B93, 0x12D7B0F]),
          str([hex(a) for a in jl]))

    regcalls = [k for k, (a, m, o) in enumerate(insns) if m == "call" and re.fullmatch(r"r\w+", o)]
    two = []
    for k in regcalls:
        reg = insns[k][2]
        if any(jm == "mov" and jo.startswith(reg + ", qword ptr [") and re.search(r" \+ (0x8|8)\]$", jo)
               for _, jm, jo in insns[max(0, k - 8):k]):
            two.append(insns[k][0])
    check("C11 call reg の直前 8 命令に mov reg, qword ptr [X+8] の 2 段形は 2 件 (0x479b83・0x1249553)",
          len(regcalls) == 1237 and sorted(two) == [0x479B83, 0x1249553],
          f"call reg {len(regcalls)} 件、2 段形 {[hex(a) for a in two]}")

    refs_vmt, refs_cls = [], []
    for k, (a, m, o) in enumerate(insns):
        mm = RIP.search(o)
        if not mm:
            continue
        d = int(mm.group(2), 16)
        nxt = insns[k + 1][0] if k + 1 < len(insns) else a + 7
        t = nxt + d if mm.group(1) == "+" else nxt - d
        if t == VMT:
            refs_vmt.append(a)
        if t == CLASSREF:
            refs_cls.append((a, fstart(a)))
    check("C4 RIP 相対で VMT VA を指す命令は 0 件 (生成は classref 経由)", not refs_vmt, str(refs_vmt))
    check("C5 classref 0x1012e78 の RIP 参照は 1 件 (0x101ca74、関数 0x101ca60)",
          refs_cls == [(0x101CA74, FN_REF)], str([(hex(a), hex(f)) for a, f in refs_cls]))

    pro = body(SLOT1, 60)
    zeroed = [o for a, m, o in pro if m == "lea" and o.startswith("rdi, [rbp + ")]
    check("C6 プロローグで [rbp+0x30]・[rbp+0x48]・[rbp+0x60] の 3 連続 24 バイトをゼロ化",
          all(x in zeroed for x in ("rdi, [rbp + 0x30]", "rdi, [rbp + 0x48]", "rdi, [rbp + 0x60]")),
          str(zeroed[:6]))

    def zero24(off):
        k = [i for i, (a, m, o) in enumerate(pro) if m == "lea" and o == f"rdi, [rbp + {off:#x}]"][0]
        return [(m, o) for _, m, o in pro[k + 1:k + 5]] == (
            [("xor", "eax, eax")] + [("stosq", "qword ptr [rdi], rax")] * 3)

    check("C6b [rbp+0x30]・[rbp+0x48]・[rbp+0x60] の各ゼロ化は xor eax,eax の後の stosq ×3 (24 バイト)",
          all(zero24(x) for x in (0x30, 0x48, 0x60)))

    def find(lo, hi, text):
        return [a for a, m, o in insns if lo <= a < hi and f"{m} {o}" == text]

    def arg30(call_va):
        k = addr_idx[call_va]
        return any(insns[j][2] == "rcx, [rbp + 0x30]" for j in range(k - 3, k))

    fill = [(hex(a), o) for a, m, o in insns if SLOT1 <= a < FN_END and m == "call"
            and o in ("0x45b480", "0x45c290", "0x416230")]
    check("C7 0x10219e0 の 0x45c290 と 0x1021a28 の 0x416230 は [rbp+0x30] を rcx で渡す",
          arg30(0x10219E0) and arg30(0x1021A28), str(fill))
    check("C7b 0x45b480 のうち [rbp+0x30] へのコピーは 0x10219c5・0x10219d7 の 2 箇所",
          sorted(a for a, o in fill if o == "0x45b480" and arg30(int(a, 16))) == ["0x10219c5", "0x10219d7"])

    ti_slot = 0x1021A1B + 7 - 0xC206BA
    ti = struct.unpack_from("<Q", raw, fo(ti_slot))[0]
    kind = raw[fo(ti)]
    tname = raw[fo(ti) + 2:fo(ti) + 2 + raw[fo(ti) + 1]].decode("latin1")
    check("C8 エピローグ 0x416230 の第 2 引数は tkVariant (kind 0x0c)、名前 Variant、第 3 引数 = 3",
          kind == 0x0C and tname == "Variant" and any(
              m == "mov" and o == "r8d, 3" for a, m, o in body(0x1021A17, 4)),
          f"kind={kind:#x} name={tname}")

    h45c = body(0x45C290, 12)
    check("C9 0x45c290 は引数の先頭 word (VType) で分岐する",
          any(m == "movzx" and o == "ecx, ax" for a, m, o in h45c), str([o for a, m, o in h45c[:6]]))
    h45b = body(0x45B480, 8)
    check("C10 0x45b480 は VType の managed 判定 (test ax, 0xbfe8) で分岐する (VarCopy 形)",
          any(m == "test" and o == "ax, 0xbfe8" for a, m, o in insns[addr_idx[0x45B480]:addr_idx[0x45B480] + 12]),
          str([o for a, m, o in h45b[:4]]))

    print(f"\nsummary: {'ALL PASS' if not FAILS else 'FAIL: ' + ', '.join(FAILS)}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
