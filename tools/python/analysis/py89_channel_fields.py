#!/usr/bin/env python3
"""PY-89 (#2805): channels の 2 関数が読む channel レコードの field の書込み元を PE 全体から探す (実機不要)。

  python3 analysis/py89_channel_fields.py <PE.bin> [<offset hex> ...]

既定の offset は getChannelMidiInPort の +0x2f8 (MIDI-in port) と getChannelIndex の +0x794 (global index)。
.text を先頭から線形に逆アセンブルし、その field への memory 書込み (mov の宛先) を一覧する。
即値で書く命令は値を併記する。線形走査なので誤認はありうる (周辺の命令で確認する)。
PE は fl-win64 素材の extracted/block00031_PE.bin を使う。
"""
import sys

import capstone
import pefile


def main():
    path = sys.argv[1]
    offs = sys.argv[2:] or ["0x2f8", "0x794"]
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    data = pe.get_memory_mapped_image()[text.VirtualAddress:text.VirtualAddress + text.Misc_VirtualSize]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False
    marks = [f"+ {int(o, 16):#x}]" for o in offs] + [f"+{int(o, 16):#x}]" for o in offs]
    print(f"text: {text.Misc_VirtualSize:#x} bytes, base {base + text.VirtualAddress:#x}")
    blob = bytes(data)
    start = base + text.VirtualAddress
    pos = 0
    while pos < len(blob):
        last = 0
        for ins in md.disasm(blob[pos:pos + 0x10000], start + pos):
            last = ins.address - (start + pos) + ins.size
            if ins.mnemonic not in ("mov", "and", "or", "add", "sub", "xor", "inc", "dec"):
                continue
            ops = ins.op_str
            dst = ops.split(",")[0] if "," in ops else ops
            if "ptr [" not in dst or not any(m in dst for m in marks):
                continue
            print(f"{ins.address:#x}: {ins.mnemonic} {ops}")
        pos += last if last else 1


if __name__ == "__main__":
    main()
