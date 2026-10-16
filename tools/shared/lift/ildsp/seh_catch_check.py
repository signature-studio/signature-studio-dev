#!/usr/bin/env python3
"""ildsp の RaiseException (0xe06d7363) の catch 先を PE から確かめる (T-SH-156 / #5795)。

確かめる点:
  1. .pdata の SEH 入口 (EHANDLER) 関数 0x1b8e68 の scope 表: try 範囲・filter・except 本体
  2. try 範囲の中の命令 (call の先)
  3. filter の許可する例外コード (cmp dword [rax], imm32 の比較値)
  4. 0xe06d7363 を投げる helper 0x1aedc0 の .text 内の直接 call/jmp 元

usage: seh_catch_check.py PE    (既定 PE: $FL_WIN64_DIR/extracted/block24360_PE.bin)
"""
import os, struct, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

PE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block24360_PE.bin")
FN = 0x1B8E68
THROW = 0x1AEDC0
CXX = 0xE06D7363


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    out = {}
    for i in range(n):
        o = pe + 24 + opt + i * 40
        name = d[o:o + 8].rstrip(b"\0").decode()
        vs, va, rs, rp = struct.unpack_from("<IIII", d, o + 8)
        out[name] = (va, rp, max(vs, rs))
    return out


def rva2off(secs, rva):
    for va, rp, sz in secs.values():
        if va <= rva < va + sz:
            return rp + rva - va
    raise ValueError(hex(rva))


def main():
    d = open(PE, "rb").read()
    secs = sections(d)
    pva, prp, psz = secs[".pdata"]
    unwind = None
    for i in range(0, psz, 12):
        b, e, u = struct.unpack_from("<III", d, prp + i)
        if b == FN:
            unwind = u
    assert unwind is not None, "no pdata entry for FN"
    uo = rva2off(secs, unwind)
    ver_flags, _, ncodes, _ = struct.unpack_from("<BBBB", d, uo)
    assert ver_flags >> 3 & 1, "EHANDLER not set"
    hoff = uo + 4 + ((ncodes + 1) & ~1) * 2
    handler = struct.unpack_from("<I", d, hoff)[0]
    so = hoff + 4
    count = struct.unpack_from("<I", d, so)[0]
    print("UNWIND %#x EHANDLER handler=%#x scope_count=%d" % (unwind, handler, count))
    scopes = []
    for k in range(count):
        b, e, h, t = struct.unpack_from("<IIII", d, so + 4 + k * 16)
        scopes.append((b, e, h, t))
        print("SCOPE try=[%#x,%#x) filter_or_handler=%#x target=%#x" % (b, e, h, t))

    cs = Cs(CS_ARCH_X86, CS_MODE_64)
    for b, e, f, t in scopes:
        body = d[rva2off(secs, b):rva2off(secs, b) + (e - b)]
        print("TRY-BODY", " ; ".join("%#x %s %s" % (i.address, i.mnemonic, i.op_str)
                                    for i in cs.disasm(body, b)))

    fo = rva2off(secs, scopes[0][2])
    codes = []
    for ins in cs.disasm(d[fo:fo + 0x40], scopes[0][2]):
        if ins.mnemonic == "ret":
            break
        if ins.mnemonic == "cmp" and "dword ptr" in ins.op_str:
            codes.append(int(ins.op_str.rsplit(",", 1)[1].strip(), 16))
    print("FILTER %#x accepts codes: %s" % (scopes[0][2], ", ".join("%#x" % c for c in codes)))
    print("FILTER accepts %#x: %s" % (CXX, CXX in codes))

    text_va, text_rp, text_sz = secs[".text"]
    tx = d[text_rp:text_rp + text_sz]
    hits = []
    for i in range(len(tx) - 5):
        if tx[i] in (0xE8, 0xE9):
            rel = struct.unpack_from("<i", tx, i + 1)[0]
            if text_va + i + 5 + rel == THROW:
                hits.append(text_va + i)
    print("DIRECT rel32 call/jmp to %#x in .text (byte scan): %d %s" % (THROW, len(hits), [hex(h) for h in hits]))


if __name__ == "__main__":
    main()
