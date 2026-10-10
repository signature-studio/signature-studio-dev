#!/usr/bin/env python3
"""universal Mach-O (fat) を各スライスに分割して work/ に書く。lipo 代用。"""
import struct, sys, os
def split(path, outdir, tag):
    b = open(path,'rb').read()
    magic = struct.unpack('>I', b[:4])[0]
    assert magic in (0xcafebabe, 0xcafebabf), hex(magic)
    n = struct.unpack('>I', b[4:8])[0]
    out = []
    for i in range(n):
        if magic == 0xcafebabe:
            ct, st, off, size, al = struct.unpack('>iiIII', b[8+i*20:28+i*20])
        else:
            ct, st, off, size, al = struct.unpack('>iiQQI', b[8+i*32:8+i*32+28])
        name = {0x01000007:'x86_64', 0x0100000c:'arm64', 7:'i386', 12:'arm'}.get(ct & 0xffffffff, hex(ct))
        o = os.path.join(outdir, f'{tag}.{name}')
        open(o,'wb').write(b[off:off+size])
        out.append((name, off, size, o))
        print(f'{tag} {name} off={off} size={size} -> {o}')
    return out
if __name__ == '__main__':
    split(sys.argv[1], sys.argv[2], sys.argv[3])
