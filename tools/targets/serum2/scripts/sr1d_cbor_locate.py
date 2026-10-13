#!/usr/bin/env python3
"""SR-1d (#340): locate nlohmann::json binary_reader (CBOR/UBJSON/BJData/MessagePack/BSON) functions in Serum2 Win64
by the exact error-message literals of nlohmann json v3.12 binary_reader, then map them to referencing functions and to
the XferJson reader/writer call chain.
usage: sr1d_cbor_locate.py <pe> <index.npz>   (index from sr3_index.py)
Each literal is a (format, tag, bytes). A literal with 0 hits is printed (negative evidence is kept)."""
import sys, bisect
import numpy as np
import pefile

PATH, IDX = sys.argv[1:3]
pe = pefile.PE(PATH, fast_load=True)
data = open(PATH, 'rb').read()
IMG = pe.OPTIONAL_HEADER.ImageBase
secs = [(s.Name.rstrip(b'\0').decode(), s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData) for s in pe.sections]
z = np.load(IDX)
funcs = z['funcs']; refs = z['refs']
fstarts = funcs[:, 0].tolist()
rip = refs[refs[:, 2] == 0]
order = np.argsort(rip[:, 1], kind='stable')
rt = rip[order, 1]; rs = rip[order, 0]


def fn_of(rva):
    i = bisect.bisect_right(fstarts, rva) - 1
    if i >= 0 and funcs[i][0] <= rva < funcs[i][1]:
        return int(funcs[i][0])
    return -1


def off2rva(off):
    for n, va, vs, po, ps in secs:
        if po <= off < po + ps:
            return va + off - po
    return None


# (format, tag, literal). Source: nlohmann/json v3.12 binary_reader.hpp error strings
L = [
    ('cbor', 'get_cbor_string', b'expected length specification (0x60-0x7B) or indefinite string type (0x7F); last byte: 0x'),
    ('cbor', 'get_cbor_binary', b'expected length specification (0x40-0x5B) or indefinite binary array type (0x5F); last byte: 0x'),
    ('msgpack', 'get_msgpack_string', b'expected length specification (0xA0-0xBF, 0xD9-0xDB); last byte: 0x'),
    ('common', 'sax_parse_internal_invalid_byte', b'invalid byte: 0x'),
    ('common', 'unexpect_eof', b'unexpected end of input'),
    ('common', 'after_parse_expected_eoi', b'expected end of input; last byte: 0x'),
    ('ubjson', 'get_ubjson_size_type', b'expected length type specification (U, i, I, l, L) after \'#\'; last byte: 0x'),
    ('ubjson', 'get_ubjson_size_value', b'expected length type specification (U, i, I, l, L); last byte: 0x'),
    ('ubjson', 'get_ubjson_type', b"expected '#' after type information; last byte: 0x"),
    ('bjdata', 'get_ubjson_size_value_bjdata', b'expected length type specification (U, i, u, I, m, l, M, L); last byte: 0x'),
    ('bjdata', 'get_ubjson_size_type_bjdata', b"expected length type specification (U, i, u, I, m, l, M, L) after '#'; last byte: 0x"),
    ('bjdata', 'bjdata_ndarray', b'BJData object does not support ND-array size in optimized format'),
    ('bson', 'bson_record', b'Unsupported BSON record type 0x'),
    ('msgpack', 'name_msgpack', b'MessagePack\0'),
    ('cbor', 'name_cbor', b'CBOR\0'),
    ('ubjson', 'name_ubjson', b'UBJSON\0'),
    ('bson', 'name_bson', b'BSON\0'),
    ('bjdata', 'name_bjdata', b'BJData\0'),
    ('text', 'lexer_parse_error', b'syntax error while parsing '),
]
print('format\ttag\tfile_off\trva\tsection\tref_funcs')
for fmt, tag, lit in L:
    hits = []
    p = 0
    while True:
        p = data.find(lit, p)
        if p < 0:
            break
        hits.append(p); p += 1
    if not hits:
        print(f'{fmt}\t{tag}\t-\t-\t-\t(0 hits)')
    for h in hits:
        rva = off2rva(h)
        sec = next((n for n, va, vs, po, ps in secs if po <= h < po + ps), '?')
        lo = np.searchsorted(rt, rva, 'left'); hi = np.searchsorted(rt, rva + len(lit), 'left')
        fl = sorted({fn_of(int(s)) for s in rs[lo:hi]} - {-1})
        print(f'{fmt}\t{tag}\t{h:#x}\t{rva + IMG:#x}\t{sec}\t' + ','.join(hex(f + IMG) for f in fl))
