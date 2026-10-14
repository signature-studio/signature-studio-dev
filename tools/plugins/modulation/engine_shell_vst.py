#!/usr/bin/env python3
# 殻の VST 系名 (VSTPluginMain) の参照経路を静的に追う (#527 受入 5)。
#   python3 engine_shell_vst.py <block_PE.bin> <string_va_hex>
# 出力: (1) 文字列 VA を指す .data の 8 バイト slot、(2) slot 周辺の名前表 (8 バイト単位)、
#       (3) slot を rip 相対で読む命令、(4) 名前表の要素を読む関数の呼出元 (direct call / jmp)、
#       (5) その関数 VA を値として持つ slot (間接呼出の候補)。
# 制限: 静的のみ。間接呼出の読み手は (5) の slot を rip 相対で読む命令まで辿らない。
import struct
import sys

import capstone
import pefile


def _secs(pe):
    base = pe.OPTIONAL_HEADER.ImageBase
    out = []
    for s in pe.sections:
        out.append((s.Name.rstrip(b"\0").decode(errors="replace"), base + s.VirtualAddress,
                    s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData, s.Characteristics))
    return base, out


def _slots_of(data, secs, value):
    pat = struct.pack("<Q", value)
    res = []
    for name, sva, vsz, rpa, rsz, ch in secs:
        raw = data[rpa:rpa + rsz]
        p = raw.find(pat)
        while p >= 0:
            if p % 8 == 0:
                res.append(sva + p)
            p = raw.find(pat, p + 1)
    return res


def _code(md, secs, data):
    for name, sva, vsz, rpa, rsz, ch in secs:
        if ch & 0x20000000:
            yield sva, md.disasm(data[rpa:rpa + rsz], sva)


def main(path, va_hex):
    pe = pefile.PE(path, fast_load=True)
    data = open(path, "rb").read()
    base, secs = _secs(pe)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    md.skipdata = True
    target = int(va_hex, 16)
    slots = [s for s in _slots_of(data, secs, target) if not any(
        ch & 0x20000000 and sva <= s < sva + vsz for _, sva, vsz, _, _, ch in secs)]
    print("string", hex(target), "data slots:", [hex(s) for s in slots])
    for slot in slots:
        for name, sva, vsz, rpa, rsz, ch in secs:
            if sva <= slot < sva + rsz:
                print("table around", hex(slot))
                for k in range(slot - 0x40, slot + 0x40, 8):
                    if sva <= k < sva + rsz:
                        v = struct.unpack_from("<Q", data, rpa + (k - sva))[0]
                        print("  ", hex(k), hex(v), "<==" if k == slot else "")
        for sva, insns in _code(md, secs, data):
            for ins in insns:
                try:
                    ops = ins.operands
                except capstone.CsError:
                    continue
                for op in ops:
                    if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                        if ins.address + ins.size + op.mem.disp == slot:
                            print("  rip-ref", hex(ins.address), ins.mnemonic, ins.op_str)
    # 名前表の解決関数: slot の近傍 (±0x40) の要素を読む lea/rip 参照の先頭を求める
    table_refs = set()
    for slot in slots:
        for sva, insns in _code(md, secs, data):
            for ins in insns:
                try:
                    ops = ins.operands
                except capstone.CsError:
                    continue
                for op in ops:
                    if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                        t = ins.address + ins.size + op.mem.disp
                        if slot - 0x40 <= t <= slot + 0x40 and t != slot:
                            table_refs.add(t)
    print("table refs (lea/rip) to slot neighbourhood:", sorted(hex(t) for t in table_refs))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
