#!/usr/bin/env python3
"""FLEngine PE の VMT (Delphi 仮想メソッド表) を指定 VA から確定する (PY-177 / #3267 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_vmt_probe.py <VMT VA(16進)> [<仮想メソッド VA(16進)> ...] [--disp <slot オフセット(16進)>]

- VMT: 仮想メソッドの先頭 (slot 0) の VA。ヘッダの vmtClassName (VMT-0x88 の ShortString へのポインタ) を読む。
- 仮想メソッドの slot 位置 (VMT 内のアドレス) を渡すと、slot 番号と、そこに入っている関数 VA を出す。
- クラス参照: VMT の VA を値として格納する 8 バイトのスロット (型判定・生成で読まれる) と、そのスロットを
  RIP 相対で読む命令を列挙する。
- --disp: `call qword ptr [reg + disp]` (仮想呼出し) の箇所数と先頭の箇所を出す。

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> extracted/block00031_PE.bin
"""
import os
import re
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
CALL_DISP = re.compile(r"qword ptr \[(r\w+) \+ (0x[0-9a-f]+)\]")


def main():
    args = sys.argv[1:]
    disp = None
    if "--disp" in args:
        i = args.index("--disp")
        disp = int(args[i + 1], 16)
        del args[i:i + 2]
    vmt = int(args[0], 16)
    methods = [int(a, 16) for a in args[1:]]
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    text_lo = base + text.VirtualAddress

    def fo(va):
        for s in pe.sections:
            lo = base + s.VirtualAddress
            if lo <= va < lo + s.SizeOfRawData:
                return va - lo + s.PointerToRawData
        raise ValueError(f"{va:#x} is not in a file-backed section")

    def qword(va):
        return struct.unpack_from("<Q", raw, fo(va))[0]

    name_ptr = qword(vmt - 0x88)
    n = raw[fo(name_ptr)]
    name = raw[fo(name_ptr) + 1:fo(name_ptr) + 1 + n].decode("latin1")
    print(f"VMT {vmt:#x}: vmtClassName ptr {name_ptr:#x} -> {name!r}")
    for m in methods:
        if (m - vmt) % 8 or not 0 <= m - vmt < 0x1000:
            print(f"slot {m:#x}: not a slot of this VMT")
        else:
            print(f"slot {m:#x}: index {(m - vmt) // 8} (offset {m - vmt:#x}) -> function {qword(m):#x}")
    pat = struct.pack("<Q", vmt)
    locs = []
    pos = raw.find(pat)
    while pos != -1:
        for s in pe.sections:
            if s.PointerToRawData <= pos < s.PointerToRawData + s.SizeOfRawData:
                locs.append(base + s.VirtualAddress + pos - s.PointerToRawData)
                break
        pos = raw.find(pat, pos + 1)
    print("qword slots holding this VMT value (VA):", [hex(x) for x in locs])

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    data = raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    targets = set(locs)
    rip_hits = []
    call_hits = []
    pos = 0
    while pos < len(data):
        chunk = data[pos:pos + 0x10000 + 32]
        last = None
        for ins in md.disasm(chunk, text_lo + pos):
            if ins.address - text_lo - pos >= 0x10000:
                break
            last = ins
            m = RIP.search(ins.op_str)
            if m:
                d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
                if ins.address + ins.size + d in targets:
                    rip_hits.append((ins.address, ins.mnemonic + " " + ins.op_str))
            if disp is not None and ins.mnemonic == "call":
                c = CALL_DISP.search(ins.op_str)
                if c and int(c.group(2), 16) == disp:
                    call_hits.append((ins.address, ins.op_str))
        if last is None:
            pos += 1
        else:
            pos = last.address - text_lo + last.size
    print("RIP reads of those slots:", len(rip_hits))
    for a, s in rip_hits[:40]:
        print(f"  {a:#x} {s}")
    if disp is not None:
        print(f"call [reg + {disp:#x}] (virtual slot {disp // 8}):", len(call_hits))
        for a, s in call_hits[:40]:
            print(f"  {a:#x} {s}")


if __name__ == "__main__":
    main()
