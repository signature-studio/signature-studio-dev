#!/usr/bin/env python3
# 殻の engine export 名参照 (lea rip 相対) と、その直後の呼出先を列挙する (#527 受入 5)。
#   python3 modulation/engine_shell_chain.py <block_PE.bin>
# 出力: 各 export 名 (UTF-16) の文字列 VA、それを rip 相対 lea で参照する命令、直後の call 先。
# 制限: 静的のみ。引数の値は lea の対象文字列を読んだものだけ。絶対アドレス参照 (.data の pointer 表) は見ない。
import re
import struct
import sys

import capstone
import pefile

NAMES = ["Engine_x64.dll", "engine_x64.dll", "dispatch", "DispatchToEngine", "VSTPluginMain"]
LEA = re.compile(r"rip \+ (0x[0-9a-f]+)")


def utf16_at(pe, va):
    base = pe.OPTIONAL_HEADER.ImageBase
    for s in pe.sections:
        sva = base + s.VirtualAddress
        if sva <= va < sva + s.Misc_VirtualSize:
            raw = s.get_data()[va - sva: va - sva + 160]
            return raw.decode("utf-16le", errors="replace").split("\0")[0]
    return None


def main(path):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, "rb").read()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for name in NAMES:
        enc = name.encode("utf-16le") + b"\0\0"
        offs = []
        p = data.find(enc)
        while p >= 0:
            offs.append(p)
            p = data.find(enc, p + 1)
        if not offs:
            print("string", name, "not found")
            continue
        for off in offs:
            sva = None
            for s in pe.sections:
                if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
                    sva = base + s.VirtualAddress + (off - s.PointerToRawData)
            if sva is None:
                continue
            print("string", name, "VA", hex(sva))
            for s in pe.sections:
                if not (s.Characteristics & 0x20000000):
                    continue
                s_va = base + s.VirtualAddress
                body = s.get_data()[: s.SizeOfRawData]
                for k in range(len(body) - 7):
                    if body[k] in (0x48, 0x4C) and body[k + 1] == 0x8D and (body[k + 2] & 0xC7) == 0x05:
                        disp = struct.unpack_from("<i", body, k + 3)[0]
                        if s_va + k + 7 + disp != sva:
                            continue
                        ins_va = s_va + k
                        nxt = list(md.disasm(body[k + 7: k + 7 + 64], ins_va + 7))[:2]
                        tail = " ; ".join(f"{hex(i.address)} {i.mnemonic} {i.op_str}" for i in nxt)
                        print("  lea", hex(ins_va), "->", repr(utf16_at(pe, sva)), "| next:", tail)


if __name__ == "__main__":
    main(sys.argv[1])
