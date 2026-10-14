import sys, struct, pefile
pe = pefile.PE(sys.argv[1], fast_load=True)
IB = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
def u32(va): return struct.unpack_from('<I', img, va - IB)[0]
def u64(va): return struct.unpack_from('<Q', img, va - IB)[0]
cols = [int(x, 16) for x in sys.argv[2].split(',')]
for col in cols:
    off = u32(col + 4)
    rva_col = col - IB
    pat = struct.pack('<Q', col)
    i = img.find(pat)
    vts = []
    while i >= 0:
        if i % 8 == 0 and i + 8 <= len(img):
            vts.append(IB + i + 8)
        i = img.find(pat, i + 1)
    for vt in vts:
        slots = [u64(vt + 8 * k) for k in range(12)]
        print('COL 0x%x offset=0x%x vtable=0x%x' % (col, off, vt))
        for k, s in enumerate(slots):
            print('  slot %2d -> 0x%x' % (k, s))
