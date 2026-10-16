#!/usr/bin/env python3
"""hs_disp_refs.py — FLE TFruityHost.Dispatcher (0x13173a0) の間接参照を探す (#5663 / PLG-P0b-HostTag)。

直接の call/jmp が無い (hs_disp_callers.py は 0 件) ため、次の 2 種を探す:
  (a) データ内の絶対 qword (ImageBase + 0x13173a0) — 関数ポインタ表・vtable への格納
  (b) 命令内の rip 相対 disp32 が 0x13173a0 を指す lea/mov — 関数ポインタの取得
出力は参照箇所の VA と、その前後の命令。

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn/pefile/capstone> python3 hs_disp_refs.py
"""
import os
import sys
import struct

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'shared'))
from paths import FL_WIN64_DIR

PE_PATH = os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
DISP = 0x13173a0


def main():
    pe = pefile.PE(PE_PATH, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    image = pe.get_memory_mapped_image()
    target_abs = struct.pack('<Q', DISP)
    print(f'ImageBase=0x{base:x} target_abs=0x{DISP:x}')
    # (a) 絶対 qword
    pos = image.find(target_abs)
    abs_hits = []
    while pos != -1:
        abs_hits.append(pos)
        pos = image.find(target_abs, pos + 1)
    print(f'(a) absolute qword refs: {len(abs_hits)}')
    for off in abs_hits:
        sec = next((s for s in pe.sections if s.VirtualAddress <= off < s.VirtualAddress + s.Misc_VirtualSize), None)
        name = sec.Name.rstrip(b'\0').decode(errors='replace') if sec else '?'
        print(f'  0x{base + off:x} (section {name})')
    # (b) rip 相対
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    rip_hits = []
    for sec in pe.sections:
        if not (sec.Characteristics & 0x20000000):
            continue
        start = sec.VirtualAddress
        code = image[start:start + sec.Misc_VirtualSize]
        for ins in md.disasm(code, base + start):
            if '[rip' not in ins.op_str:
                continue
            # capstone は rip 相対の解決先を返さないため、disp を読んで算出する
            disp_txt = ins.op_str.split('[rip')[1].split(']')[0]
            try:
                disp = int(disp_txt.replace(' ', '').replace('+', ''), 16) if '0x' in disp_txt else int(disp_txt.replace(' ', ''), 10)
            except ValueError:
                continue
            if disp_txt.strip().startswith('-'):
                disp = -int(disp_txt.strip()[1:].split(']')[0].strip(), 16)
            tgt = ins.address + ins.size + disp
            if tgt == DISP:
                rip_hits.append(ins)
    print(f'(b) rip-relative refs: {len(rip_hits)}')
    for ins in rip_hits:
        print(f'  0x{ins.address:x}: {ins.mnemonic} {ins.op_str}')


if __name__ == '__main__':
    main()
