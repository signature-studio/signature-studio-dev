"""PE の entry point を「EAX=1; RET」に置き換えた複製を作る (DllMain のヘッドレス環境での停止を回避)。
usage: patch_entry.py <src PE> <dst PE>
"""
import struct
import sys

src, dst = sys.argv[1], sys.argv[2]
d = bytearray(open(src, "rb").read())
pe = struct.unpack_from("<I", d, 0x3C)[0]
opt = pe + 24
ep = struct.unpack_from("<I", d, opt + 16)[0]
nsec = struct.unpack_from("<H", d, pe + 6)[0]
optsz = struct.unpack_from("<H", d, pe + 20)[0]
sec = opt + optsz
off = None
for i in range(nsec):
    s = sec + i * 40
    vsz, va, rsz, rp = struct.unpack_from("<IIII", d, s + 8)
    if va <= ep < va + max(vsz, rsz):
        off = rp + (ep - va)
        break
assert off is not None, "entry point not in any section"
d[off:off + 6] = bytes([0xB8, 1, 0, 0, 0, 0xC3])  # mov eax,1; ret
open(dst, "wb").write(d)
print("entry rva", hex(ep), "file off", hex(off))
