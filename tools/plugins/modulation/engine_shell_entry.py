#!/usr/bin/env python3
# 殻の engine 名参照 (lea rip-relative で engine export 名の文字列を指す箇所) と、
# その直後の GetProcAddress 系ラッパー呼出を列挙する (#527 受入 5)。
#   python3 modulation/engine_shell_entry.py <block_PE.bin>
# 出力: 名前参照の VA・名前・直後 8 命令内の call 先 (ラッパー VA)。
# 制限: 静的な参照のみ。ラッパー先の GetProcAddress 引数の実値は本スクリプトでは取らない。
import re
import sys

import capstone
import pefile

NAMES = ["dispatch", "DispatchToEngine", "VSTPluginMain", "Engine_x64.dll", "engine_x64.dll"]
LEA = re.compile(r"rip \+ (0x[0-9a-f]+)")


def main(path):
    pe = pefile.PE(path, fast_load=False)
    base = pe.OPTIONAL_HEADER.ImageBase
    raw = open(path, "rb").read()
    strva = {}
    for e in NAMES:
        for enc in (e.encode() + b"\0", e.encode("utf-16le") + b"\0\0"):
            o = raw.find(enc)
            while o >= 0:
                for s in pe.sections:
                    if s.PointerToRawData <= o < s.PointerToRawData + s.SizeOfRawData:
                        strva.setdefault(base + s.VirtualAddress + (o - s.PointerToRawData), e)
                o = raw.find(enc, o + 1)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.skipdata = True
    text = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    ins = list(md.disasm(text.get_data()[: text.SizeOfRawData], base + text.VirtualAddress))
    for k, i in enumerate(ins):
        if i.mnemonic != "lea" or "rip" not in i.op_str:
            continue
        m = LEA.search(i.op_str)
        if not m:
            continue
        a = i.address + i.size + int(m.group(1), 16)
        if a not in strva:
            continue
        calls = [x.op_str for x in ins[k + 1 : k + 9] if x.mnemonic == "call"]
        print("ref", hex(i.address), strva[a], "calls", calls[:1])


if __name__ == "__main__":
    main(sys.argv[1])
