import sys, struct, pefile
pe = pefile.PE(sys.argv[1], fast_load=True)
IB = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
def u32(va):
    return struct.unpack_from('<I', img, va - IB)[0]
def u64(va):
    return struct.unpack_from('<Q', img, va - IB)[0]
def cstr(va):
    return img[va-IB:va-IB+200].split(b'\0')[0].decode('latin1')
cols = [int(x, 16) for x in sys.argv[2:]]
for col in cols:
    off = u32(col + 4)
    cd = IB + u32(col + 16)
    td = IB + u32(col + 12)
    n = u32(cd + 8)
    arr = IB + u32(cd + 12)
    print('COL 0x%x offset=0x%x type=%s' % (col, off, cstr(td + 0x10)))
    for i in range(n):
        bcd = IB + u32(arr + 4 * i)
        btd = IB + u32(bcd)
        mdisp = struct.unpack_from('<i', img, bcd + 8 - IB)[0]
        print('   base[%d] %s mdisp=%d' % (i, cstr(btd + 0x10), mdisp))
