#!/usr/bin/env python3
# 殻 (Delphi 4 本) の KERNEL32 動的ロード呼出を静的に列挙する (#527 受入 5)。
#   python3 modulation/engine_shell_gpa.py <block_PE.bin>     例: block18978_PE.bin
# 出力: LoadLibrary* / GetProcAddress の呼出箇所 (thunk 経由)、GetProcAddress の lea rdx 文字列 (取れたもの)、
#       殻内の engine export 名 (UTF-16 / ASCII) の出現位置。
# 制限: 引数がレジスタ経由で渡るラッパー呼出は文字列を取れない (name=None)。
import re
import sys

import capstone
import pefile

TARGET = {"GetProcAddress", "LoadLibraryExW", "LoadLibraryW", "LoadLibraryA", "FreeLibrary"}
EXPORTS = ["dispatch", "DispatchToEngine", "VSTPluginMain", "vstpluginmain", "Engine_x64.dll", "engine_x64.dll"]
RIP = re.compile(r"\[rip\s*([+-])\s*(0x[0-9a-f]+)\]")
LEA = re.compile(r"lea rdx, \[rip \+ (0x[0-9a-f]+)\]")


def main(path):
    pe = pefile.PE(path, fast_load=False)
    base = pe.OPTIONAL_HEADER.ImageBase
    slots = {}
    for e in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        for imp in e.imports:
            if imp.name and imp.name.decode(errors="replace") in TARGET:
                slots[imp.address] = imp.name.decode()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.skipdata = True
    thunks, sites = {}, []
    secs = [s for s in pe.sections if s.Characteristics & 0x20000000]
    insns = {}
    for s in secs:
        va = base + s.VirtualAddress
        insns[s] = list(md.disasm(s.get_data()[: s.SizeOfRawData], va))
        for i in insns[s]:
            if i.mnemonic == "jmp" and "rip" in i.op_str:
                m = RIP.search(i.op_str)
                if m:
                    t = i.address + i.size + int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
                    if t in slots:
                        thunks[i.address] = slots[t]
    for s in secs:
        ins = insns[s]
        for k, i in enumerate(ins):
            if i.mnemonic == "call" and i.op_str.startswith("0x") and int(i.op_str, 16) in thunks:
                nm = thunks[int(i.op_str, 16)]
                name = None
                if nm == "GetProcAddress":
                    for j in range(k - 1, max(0, k - 6), -1):
                        m = LEA.search(ins[j].mnemonic + " " + ins[j].op_str)
                        if m:
                            a = ins[j].address + ins[j].size + int(m.group(1), 16)
                            name = pe.get_data(a - base, 80).split(b"\0")[0].decode(errors="replace")
                            break
                sites.append((hex(i.address), nm, name))
    print("thunks", {hex(k): v for k, v in thunks.items()})
    for site in sites:
        print("call", *site)
    for e in EXPORTS:
        d = open(path, "rb").read()
        a, u = d.find(e.encode() + b"\0"), d.find(e.encode("utf-16le") + b"\0\0")
        print("string", e, "ascii", hex(a) if a >= 0 else -1, "utf16", hex(u) if u >= 0 else -1)


if __name__ == "__main__":
    main(sys.argv[1])
