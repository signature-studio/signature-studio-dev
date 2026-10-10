#!/usr/bin/env python3
"""fat_slice.py <universal> <arch: x86_64|arm64> <out> — universal Mach-O から slice を切り出す。"""
import struct, sys
src, arch, out = sys.argv[1:4]
d = open(src, 'rb').read()
magic = struct.unpack('>I', d[:4])[0]
assert magic in (0xcafebabe, 0xcafebabf), hex(magic)
n = struct.unpack('>I', d[4:8])[0]
CPU = {0x01000007: 'x86_64', 0x0100000c: 'arm64'}
for i in range(n):
    cputype, sub, off, size, al = struct.unpack('>iiIII', d[8 + i * 20: 28 + i * 20])
    nm = CPU.get(cputype & 0xffffffff)
    print(nm, off, size)
    if nm == arch:
        open(out, 'wb').write(d[off:off + size]); print('wrote', out, size)
