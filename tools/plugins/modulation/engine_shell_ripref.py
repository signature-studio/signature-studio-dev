#!/usr/bin/env python3
# 指定 VA を指す参照を総当たりで列挙する (#527 受入 5)。
#   python3 engine_shell_ripref.py <PE.bin> [-n <近傍バイト数>] <target_va_hex> [...]
# 出力: (1) 対象 VA を値として持つ 8 バイト slot (全セクション、コード内も含む)、
#       (2) 絶対 32 bit (VA < 4GiB) の出現 (命令境界は未検証)、
#       (3) rip 相対 disp32 または rel32 分岐で、対象 VA (-n 指定時は ±N バイト以内) を指す命令。
#           コード内の全バイト位置を候補にし、後続の即値長 0/1/2/4/8 を仮定して
#           capstone で命令境界を検証する。
# engine_shell_vst.py の線形逆アセンブルは .text 内のデータで同期を失うため、
# 取りこぼしを避けてこちらで再確認する。静的のみ。
import struct
import sys

import capstone
import pefile


def main(path, args):
    near = 0
    if args[:1] == ["-n"]:
        near = int(args[1], 16)
        args = args[2:]
    targets = [int(a, 16) for a in args]
    pe = pefile.PE(path, fast_load=True)
    data = open(path, "rb").read()
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = []
    for s in pe.sections:
        name = s.Name.rstrip(b"\0").decode(errors="replace")
        secs.append((name, base + s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData,
                     s.SizeOfRawData, s.Characteristics))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    for tgt in targets:
        print("target", hex(tgt), "near", hex(near))
        pat = struct.pack("<Q", tgt)
        for name, sva, vsz, rpa, rsz, ch in secs:
            raw = data[rpa:rpa + rsz]
            p = raw.find(pat)
            while p >= 0:
                if p % 8 == 0:
                    print("  slot", hex(sva + p), name, "(code)" if ch & 0x20000000 else "")
                p = raw.find(pat, p + 1)
        if tgt < 1 << 32:
            pat32 = struct.pack("<I", tgt)
            for name, sva, vsz, rpa, rsz, ch in secs:
                raw = data[rpa:rpa + rsz]
                p = raw.find(pat32)
                while p >= 0:
                    print("  abs32", hex(sva + p), name, "(code)" if ch & 0x20000000 else "")
                    p = raw.find(pat32, p + 1)
    wanted = set()
    for t in targets:
        for d in range(-near, near + 1):
            wanted.add(t + d)
    for name, sva, vsz, rpa, rsz, ch in secs:
        if not ch & 0x20000000:
            continue
        raw = data[rpa:rpa + rsz]
        for q in range(0, rsz - 4):
            disp = struct.unpack_from("<i", raw, q)[0]
            for imm in (0, 1, 2, 4, 8):
                end = q + 4 + imm
                if end > rsz:
                    break
                if sva + end + disp not in wanted:
                    continue
                hit = None
                for st in range(max(0, end - 15), end):
                    for ins in md.disasm(raw[st:end], sva + st):
                        if ins.address + ins.size != sva + end:
                            continue
                        for op in ins.operands:
                            if (op.type == capstone.x86.X86_OP_MEM
                                    and op.mem.base == capstone.x86.X86_REG_RIP
                                    and op.mem.disp == disp):
                                hit = ins
                            if op.type == capstone.x86.X86_OP_IMM and op.imm == sva + end + disp:
                                hit = ins
                if hit is not None:
                    tgt = sva + end + disp
                    print("  ref", hex(hit.address), hit.mnemonic, hit.op_str, "-> ", hex(tgt))
                break


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
