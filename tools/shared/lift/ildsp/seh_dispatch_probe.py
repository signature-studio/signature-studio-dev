#!/usr/bin/env python3
"""ildsp の handler 0x1acf00 (0x1afbd4・0x1b009c の EHANDLER) を PE から確かめる (T-SH-158 / #5859)。

確かめる点:
  1. 0x1acf00 の中身 (/GS cookie wrapper か、EH scope 表か)
  2. 0x1afbd4・0x1b009c の unwind の handler データ (cookie オフセットか、scope 表か)
  3. 0x1acee0 (GS 検査の共通 tail) → 0x1ad668 の先頭 (EH dispatch か、GS 失敗通知か)
  4. 0x1b0d24・0x1b0f5c (例外の上位呼出元) の所属関数・直接 call 元 (と所属関数の handler)、
     .data の関数ポインタ表からの参照 (.pdata の関数開始 RVA は除く。値は RVA で出す)

usage: seh_dispatch_probe.py [PE]   (既定 PE: $FL_WIN64_DIR/extracted/block24360_PE.bin)
"""
import os, struct, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

PE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block24360_PE.bin")
HANDLER = 0x1ACF00
FNS = [0x1AFBD4, 0x1B009C]
UP = [0x1B0D24, 0x1B0F5C]


def load(path):
    d = open(path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    secs = {}
    for i in range(n):
        o = pe + 24 + opt + i * 40
        name = d[o:o + 8].rstrip(b"\0").decode()
        vs, va, rs, rp = struct.unpack_from("<IIII", d, o + 8)
        secs[name] = (va, rp, max(vs, rs))
    return d, secs


d, secs = load(PE)
tva, trp, tsz = secs[".text"]
tx = d[trp:trp + tsz]
pva, prp, psz = secs[".pdata"]
entries = [struct.unpack_from("<III", d, prp + i) for i in range(0, psz, 12)]
cs = Cs(CS_ARCH_X86, CS_MODE_64)


def r2o(rva):
    for va, rp, sz in secs.values():
        if va <= rva < va + sz:
            return rp + rva - va
    raise ValueError(hex(rva))


def pdata(fn):
    for b, e, u in entries:
        if b <= fn < e:
            return b, e, u
    return None


def handler_info(fn):
    ent = pdata(fn)
    if ent is None:
        return "no pdata"
    uo = r2o(ent[2])
    vf, prolog, ncodes, frame = struct.unpack_from("<BBBB", d, uo)
    flags = vf >> 3
    if not flags & 3:
        return "no handler"
    hoff = uo + 4 + ((ncodes + 1) & ~1) * 2
    h = struct.unpack_from("<I", d, hoff)[0]
    data = [struct.unpack_from("<I", d, hoff + 4 + 4 * k)[0] for k in range(3)]
    return "handler=%#x data=%s" % (h, [hex(x) for x in data])


def owner(addr):
    ent = pdata(addr)
    if ent is None:
        return "pdata なし"
    return "fn %#x (%s)" % (ent[0], handler_info(ent[0]))


def callers(target):
    ref = []
    for i in range(len(tx) - 5):
        if tx[i] in (0xE8, 0xE9):
            rel = struct.unpack_from("<i", tx, i + 1)[0]
            if tva + i + 5 + rel == target:
                ref.append(tva + i)
    return ref


def dis(addr, size):
    return list(cs.disasm(d[r2o(addr):r2o(addr) + size], addr))


def show(title, addr, size):
    print(title)
    for ins in dis(addr, size):
        print("  %#x  %-8s %s" % (ins.address, ins.mnemonic, ins.op_str))


def main():
    print("PE", PE)
    print("[1] handler %#x (関数・先頭 8 命令)" % HANDLER)
    show("", HANDLER, 0x1C)
    print("    pdata:", handler_info(HANDLER))
    print("[2] handler の参照元 (.text の直接 call)")
    for fn in FNS:
        print("    %#x %s" % (fn, handler_info(fn)))
        print("        直接 call 元: %s" % ([hex(c) for c in callers(fn)] or "なし"))
        for c in callers(fn):
            print("        %#x ← 所属 %s" % (c, owner(c)))
    print("[3] 共通 tail 0x1acee0 → 0x1ad668")
    show("", 0x1ACEE0, 0x1A)
    show("", 0x1AD668, 0x12)
    print("[4] 上位呼出元 (例外を送出した後の呼出し経路)")
    for up in UP:
        print("    %#x の所属: %s" % (up, owner(up)))
        ref = callers(up)
        print("    %#x 直接 call 元: %s" % (up, [hex(x) for x in ref] or "なし"))
        for c in ref:
            print("        %#x ← 所属 %s" % (c, owner(c)))
        slots = []
        for name, (va, rp, sz) in secs.items():
            if name in (".text", ".pdata"):
                continue
            blob = d[rp:rp + sz]
            for off in range(0, len(blob) - 3, 4):
                if struct.unpack_from("<I", blob, off)[0] == up:
                    slots.append("%s RVA %#x" % (name, va + off))
        print("    %#x の関数ポインタ参照 (データ・.pdata 除く): %s" % (up, slots or "なし"))


if __name__ == "__main__":
    main()
