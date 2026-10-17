#!/usr/bin/env python3
"""#6212 (PY-5419): Q を this に持つ間接 call のうち 0x4100d1・0x4100df・0x4100ed・0x415ca8 の呼出し先を PE 上で確定する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_q_icall_6212.py

判定:
- 0x410090 (TObject.Dispatch 相当) は obj の vptr から message map を引く (0x40ff70)。
  Q の vptr 0x9764d8 から親 VMT 鎖を辿り、message map (vptr-0x90) が全段で 0 なら 0x40ff70 は 0 を返し、
  0x4100d1 (handler call) は到達しない。
- 0x4100df・0x4100ed は call [vptr-0x38] (= 0x410060)。vptr が Q の VMT なら呼出し先は一意。
- 0x415ca8 は call [rbx+0x11] (rbx = 入力構造体の値)。PE 上の定数からは決まらないため判定しない。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
Q_VPTR = 0x9764D8
X86 = capstone.x86


def load():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData), s.PointerToRawData, s.SizeOfRawData)
            for s in pe.sections]

    def read(va, n):
        rva = va - base
        for v, vs, praw, rs in secs:
            if v <= rva < v + vs:
                off = praw + (rva - v)
                return raw[off:off + n]
        return None

    return read


def qword(read, va):
    b = read(va, 8)
    if b is None or len(b) < 8:
        raise SystemExit(f"read fail 0x{va:x}")
    return int.from_bytes(b, "little")


def call_at(md, read, va):
    b = read(va, 16)
    ins = next(md.disasm(b, va, 1))
    return ins.mnemonic, ins.op_str


def main():
    read = load()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    # 0x40ff70 の message map 引き当てを Q の VMT 鎖で模擬 (0x40ff73: rcx=[rax-0x90], 0x40ffcb: rax=[rax-0x78])
    vmt = Q_VPTR
    reachable_handler = False
    depth = 0
    while vmt and depth < 16:
        tab = qword(read, vmt - 0x90)
        if tab:
            n = int.from_bytes(read(tab, 2), "little")
            if n:
                reachable_handler = True
            print(f"depth {depth} vmt=0x{vmt:x} msgtab=0x{tab:x} count={n}")
        parent = qword(read, vmt - 0x78)
        if not parent:
            break
        vmt = qword(read, parent)
        depth += 1
    print(f"0x4100d1 (handler call) reachable from Q VMT chain: {reachable_handler}")

    for va in (0x4100D1, 0x4100DF, 0x4100ED, 0x415CA8):
        m, o = call_at(md, read, va)
        print(f"0x{va:x}: {m} {o}")

    tgt = qword(read, Q_VPTR - 0x38)
    print(f"Q VMT[-0x38] = 0x{tgt:x} (0x4100df / 0x4100ed の呼出し先)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
