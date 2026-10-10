#!/usr/bin/env python3
"""Fruity Wrapper の GetProcAddress 名前表 (VA 0x8e5d08, 26 エントリの UTF-16 文字列ポインタ) を復元する."""
import pefile, struct, sys
pe = pefile.PE(sys.argv[1]); ib = pe.OPTIONAL_HEADER.ImageBase
def ustr(va):
    d = pe.get_data(va - ib, 128); s = b''; i = 0
    while i < len(d) - 1 and d[i:i + 2] != b'\0\0': s += d[i:i + 2]; i += 2
    return s.decode('utf-16le')
for i in range(26):
    p = struct.unpack('<Q', pe.get_data(0x8e5d08 + 8 * i - ib, 8))[0]
    print(i, ustr(p))
