#!/usr/bin/env python3
"""PY-49 (#1828): FLEngine PE の指定 VA を直接 call する全呼出し元を列挙する (実機不要).

  python3 analysis/py49_callers.py <PE.bin> <target VA hex>

.text 全体の E8 rel32 を走査し、呼出し直前の最大 12 命令から ecx/edx/r8d を
最後に代入した式を拾う (ヒューリスティック。分岐をまたぐ代入は拾えない)。
出力は TSV: call 元 VA / ecx / edx / r8d。
"""
import sys

import capstone
import pefile


def main():
    path = sys.argv[1]
    target = int(sys.argv[2], 16)
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    data = open(path, "rb").read()
    code = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    start = base + text.VirtualAddress
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    alias = {"rcx": "ecx", "rdx": "edx", "r8": "r8d"}
    print("call_va\tecx\tedx\tr8d")
    n = 0
    for i in range(len(code) - 4):
        if code[i] != 0xE8:
            continue
        rel = int.from_bytes(code[i + 1:i + 5], "little", signed=True)
        ea = start + i
        if ea + 5 + rel != target:
            continue
        n += 1
        win = []
        for back in range(0x60, 0, -1):
            off = i - back
            ins = [x for x in md.disasm(code[off:off + 0x70], ea - back) if x.address < ea]
            if ins and ins[-1].address + ins[-1].size == ea:
                win = ins
                break
        setv = {"ecx": "-", "edx": "-", "r8d": "-"}
        for x in win[-12:]:
            reg = x.op_str.split(",")[0].strip() if "," in x.op_str else ""
            reg = alias.get(reg, reg)
            if x.mnemonic in ("mov", "lea", "xor") and reg in setv:
                setv[reg] = x.op_str.split(",", 1)[1].strip() if x.mnemonic != "xor" else "0"
        print(f"{ea:#x}\t{setv['ecx']}\t{setv['edx']}\t{setv['r8d']}")
    print(f"# total {n}", file=sys.stderr)


if __name__ == "__main__":
    main()
