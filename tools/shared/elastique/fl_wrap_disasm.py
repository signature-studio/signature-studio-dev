#!/usr/bin/env python3
"""FL 本体 PE (block00031_PE.bin) の逆アセンブルと直接呼出元の列挙 (T-SH-150 / #5737)。

入力: FL_WIN64_DIR = 素材の展開先 (既定 $RUNNER_TEMP/fl-win64。extracted/ を含む)
使い方:
  python3 fl_wrap_disasm.py disasm <start_va_hex> <end_va_hex>   # 範囲を逆アセンブルして表示
  python3 fl_wrap_disasm.py callers <target_va_hex> [...]        # 直接 call/jmp (rel32) の呼出元
出力は標準出力のみ。命令境界は逆アセンブルの size で進め、不正命令は 1 byte 飛ばす。
"""
import os
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

FL_DIR = os.environ.get('FL_WIN64_DIR', os.path.join(os.environ.get('RUNNER_TEMP', '/tmp'), 'fl-win64'))
PE_PATH = os.path.join(FL_DIR, 'extracted', 'block00031_PE.bin')


def load():
    pe = pefile.PE(PE_PATH, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
    data = open(PE_PATH, 'rb').read()
    return pe, data


def va_to_off(pe, va):
    ib = pe.OPTIONAL_HEADER.ImageBase
    for s in pe.sections:
        a = ib + s.VirtualAddress
        if a <= va < a + s.Misc_VirtualSize:
            return s.PointerToRawData + (va - a), s
    raise SystemExit(f'VA {va:#x} は PE のセクション外')


def disasm(start, end):
    pe, data = load()
    off, _ = va_to_off(pe, start)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    for ins in md.disasm(data[off:off + (end - start)], start):
        print(f'{ins.address:#x}: {ins.mnemonic:8s} {ins.op_str}')


def callers(targets):
    pe, data = load()
    ib = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
    base = ib + text.VirtualAddress
    code = data[text.PointerToRawData:text.PointerToRawData + text.Misc_VirtualSize]
    hits = {t: [] for t in targets}
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    pos = 0
    while pos < len(code):
        ins_list = list(md.disasm(code[pos:pos + 16], base + pos, 1))
        if not ins_list:
            pos += 1
            continue
        ins = ins_list[0]
        if ins.mnemonic in ('call', 'jmp') and ins.op_str.startswith('0x'):
            try:
                t = int(ins.op_str, 16)
            except ValueError:
                t = None
            if t in hits:
                hits[t].append(ins.address)
        pos += ins.size
    for t in targets:
        print(f'{t:#x}: ' + ' '.join(f'{a:#x}' for a in hits[t]))


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if sys.argv[1] == 'disasm':
        disasm(int(sys.argv[2], 16), int(sys.argv[3], 16))
    elif sys.argv[1] == 'callers':
        callers([int(a, 16) for a in sys.argv[2:]])
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
