#!/usr/bin/env python3
"""Extract the zstd-compressed VSTGUI uidesc JSON from the Win64 Serum2.vst3 .rsrc section.
usage: extract_uidesc.py <Serum2_win64.vst3> <out.json>"""
import sys, json
import pefile, zstandard

pe = pefile.PE(sys.argv[1])
rs = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.rsrc'][0]
d = rs.get_data()
MAGIC = bytes([0x28, 0xB5, 0x2F, 0xFD])
i = d.find(MAGIC)
while i != -1:
    try:
        out = zstandard.ZstdDecompressor().decompressobj().decompress(d[i:i + 3000000])
    except zstandard.ZstdError:
        out = b''
    if out[:1] == b'{':
        json.loads(out)
        open(sys.argv[2], 'wb').write(out)
        print('uidesc bytes', len(out))
        break
    i = d.find(MAGIC, i + 1)
else:
    print('no uidesc JSON frame'); raise SystemExit(1)
