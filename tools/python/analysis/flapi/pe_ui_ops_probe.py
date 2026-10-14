#!/usr/bin/env python3
"""ui の操作・キー・ジョグ系ハンドラ (PY-120 / #2981) の呼出し契約を PE から抜く解析補助。

関数先頭から ret までを逆アセンブルし、PyArg 書式文字列・既定値 (mov dword [rbp+...], 1)・
型記述子への RIP 相対参照 (mov rdx, [rip+X] の X 解決先)・ディスパッチ呼出し (call 0xd84680 / 0xd843d0)
の直前の r8/r9 を出す。 entry・fn・flags は pe_handler_probe.py で引く。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_ui_ops_probe.py <名前:fn VA(16進)> [...]
"""
import os
import re
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
DISPATCH = {0xD84680: "d84680", 0xD843D0: "d843d0"}


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData)
            for s in pe.sections]

    def v2o(va):
        rva = va - base
        for vaddr, vsz, praw, rsz in secs:
            if vaddr <= rva < vaddr + max(vsz, rsz):
                return praw + (rva - vaddr)
        return None

    def cstr(va):
        fo = v2o(va)
        end = raw.find(b"\0", fo, fo + 64)
        return raw[fo:end].decode() if fo is not None and end != -1 else None

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for arg in sys.argv[1:]:
        name, fn = arg.split(":")
        va = int(fn, 16)
        fo = v2o(va)
        ins = []
        for i in md.disasm(raw[fo:fo + 4096], va):
            ins.append(i)
            if i.mnemonic == "ret":
                break
        print(f"[{name}] fn={va:#x} instructions={len(ins)}")
        r8 = r9 = None
        for i in ins:
            s = i.op_str
            m = re.search(r"\[rip ([+-]) (0x[0-9a-f]+)\]", s)
            if m:
                disp = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
                tgt = i.address + i.size + disp
            if i.mnemonic == "lea" and m and s.startswith("rdx"):
                print(f"  {i.address:#x} lea rdx -> {tgt:#x} {cstr(tgt)!r}")
            elif i.mnemonic == "lea" and m:
                print(f"  {i.address:#x} lea {s.split(',')[0]} -> {tgt:#x}")
            if i.mnemonic == "mov" and m and s.startswith("rdx"):
                print(f"  {i.address:#x} mov rdx <- [{tgt:#x}] (型記述子)")
            if re.match(r"(mov|xor)\s", i.mnemonic + " ") and re.match(r"(r8|r9)", s):
                if s.startswith("r8"):
                    r8 = s.split(",", 1)[1].strip()
                else:
                    r9 = s.split(",", 1)[1].strip()
            if i.mnemonic == "mov" and s == "dword ptr [rbp + 0x6c], 1":
                print(f"  {i.address:#x} 既定値 [rbp+0x6c] = 1")
            if i.mnemonic == "call":
                t = int(i.op_str, 16) if i.op_str.startswith("0x") else None
                if t in DISPATCH:
                    print(f"  {i.address:#x} call {DISPATCH[t]} r8={r8} r9={r9}")


if __name__ == "__main__":
    main()
