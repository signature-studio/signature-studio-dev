#!/usr/bin/env python3
# 殻の関数を .pdata の境界で切り出し、直接呼出元と関数ポインタ slot を列挙する (#527 受入 5)。
#   python3 engine_shell_func.py <PE.bin> <va_hex> [--dump]
# 出力: (1) va を含む RUNTIME_FUNCTION の範囲、(2) 関数先頭への rel32 call / jmp の位置、
#       (3) 関数先頭を値として持つ 8 バイト slot (全セクション)、(4) --dump 時は関数の逆アセンブル。
# 静的のみ。rel32 の候補は engine_shell_ripref.py と同じく全バイト位置から総当たりで検証する。
import struct
import sys

import capstone
import pefile


def main(path, va_hex, dump):
    va = int(va_hex, 16)
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"],
                                          pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    data = open(path, "rb").read()
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = []
    for s in pe.sections:
        name = s.Name.rstrip(b"\0").decode(errors="replace")
        secs.append((name, base + s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData,
                     s.SizeOfRawData, s.Characteristics))
    start = end = None
    for rf in pe.DIRECTORY_ENTRY_EXCEPTION:
        b = base + rf.struct.BeginAddress
        e = base + rf.struct.EndAddress
        if b <= va < e:
            start, end = b, e
            break
    if start is None:
        start, end = va, va + 0x20
        print("no .pdata range for", hex(va), "-> 先頭 0x20 バイトを扱う (thunk 等)")
    else:
        print("function", hex(start), "..", hex(end), "size", hex(end - start))
    iat = {}
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for ent in pe.DIRECTORY_ENTRY_IMPORT:
            for imp in ent.imports:
                if imp.name:
                    iat[imp.address] = imp.name.decode()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    for name, sva, vsz, rpa, rsz, ch in secs:
        if not ch & 0x20000000:
            continue
        raw = data[rpa:rpa + rsz]
        for q in range(0, rsz - 4):
            disp = struct.unpack_from("<i", raw, q)[0]
            e4 = q + 4
            if sva + e4 + disp != start:
                continue
            for st in range(max(0, e4 - 15), e4):
                hit = None
                for ins in md.disasm(raw[st:e4], sva + st):
                    if ins.address + ins.size == sva + e4 and ins.mnemonic in ("call", "jmp"):
                        hit = ins
                if hit is not None:
                    print("  caller", hex(hit.address), hit.mnemonic, hit.op_str)
                    break
    pat = struct.pack("<Q", start)
    for name, sva, vsz, rpa, rsz, ch in secs:
        raw = data[rpa:rpa + rsz]
        p = raw.find(pat)
        while p >= 0:
            if p % 8 == 0:
                print("  slot", hex(sva + p), name, "(code)" if ch & 0x20000000 else "")
            p = raw.find(pat, p + 1)
    if dump:
        for name, sva, vsz, rpa, rsz, ch in secs:
            if sva <= start < sva + rsz:
                code = data[rpa + (start - sva):rpa + (end - sva)]
                for ins in md.disasm(code, start):
                    imp = ""
                    for op in ins.operands:
                        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                            slot = ins.address + ins.size + op.mem.disp
                            if slot in iat:
                                imp = "  -> IAT " + iat[slot]
                    print("  ", hex(ins.address), ins.mnemonic, ins.op_str + imp)
                break


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--dump" in sys.argv[3:])
