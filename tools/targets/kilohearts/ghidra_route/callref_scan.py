#!/usr/bin/env python3
"""HeartCore.core_64 の実行セクションを走査し、指定 VA への call (E8) / jmp (E9) rel32 の参照元を出す (#5829 KH-176)。

  callref_scan.py <core.pe> <target_va_hex> [<target_va_hex> ...]

rel32 の解決は命令の次アドレス基準 (VA = 命令 + 5 + disp)。素の rel32 の byte 検索は誤ヒットするので使わない。
出力: セクション名・命令 (call/jmp)・参照元 VA・対象 VA。
"""
import struct
import sys

import pefile


def main():
    if len(sys.argv) < 3:
        sys.exit('usage: callref_scan.py <core.pe> <target_va_hex> [...]')
    targets = {int(a, 16): a for a in sys.argv[2:]}
    pe = pefile.PE(sys.argv[1], fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    img = pe.get_memory_mapped_image()
    for sec in pe.sections:
        if not sec.Characteristics & 0x20000000:  # IMAGE_SCN_MEM_EXECUTE
            continue
        start = sec.VirtualAddress
        code = img[start:start + min(sec.Misc_VirtualSize, len(img) - start)]
        name = sec.Name.rstrip(b'\0').decode(errors='replace')
        for i in range(len(code) - 5):
            op = code[i]
            if op not in (0xE8, 0xE9):
                continue
            tgt = base + start + i + 5 + struct.unpack_from('<i', code, i + 1)[0]
            if tgt in targets:
                print('%s  %s  at 0x%x  -> %s' % (name, 'call' if op == 0xE8 else 'jmp', base + start + i, targets[tgt]))


if __name__ == '__main__':
    main()
