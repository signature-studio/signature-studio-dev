#!/usr/bin/env python3
"""dump_tables.py <FLEngine_x64.dll> — print the constant tables the nfo/fst format code depends on (ImageBase 0x400000)."""
import struct, sys
import pefile

pe = pefile.PE(sys.argv[1], fast_load=True)
IB = pe.OPTIONAL_HEADER.ImageBase
rd = lambda va, n: pe.get_data(va - IB, n)

def ustr(va):
    n = struct.unpack('<I', rd(va - 4, 4))[0]
    return rd(va, n * 2).decode('utf-16le')

def bits(va, nbytes, base=0):
    m = int.from_bytes(rd(va, nbytes), 'little')
    return [i + base for i in range(nbytes * 8) if m >> i & 1]

print('# ImageBase', hex(IB))
print('# ps_file_arch names (fle:0x13e4fe8, index 0 = empty):', [ustr(struct.unpack('<Q', rd(0x13e4fe8 + 8 * i, 8))[0]) if struct.unpack('<Q', rd(0x13e4fe8 + 8 * i, 8))[0] else '' for i in range(4)])
print('# key index suffix (fle:0x913954, 0x91355c):', repr(ustr(0x913954)), repr(ustr(0x91355c)))
print('# list separators (fle:0x9150e0/0x9150f0) :', repr(ustr(0x9150e0)), repr(ustr(0x9150f0)))
print('# plugclass masks:')
for name, va, n, base in [
    ('folder Fruity\\   (fle:0x8f0444)', 0x8f0444, 1, 0), ('folder VST\\      (0x8f0464)', 0x8f0464, 1, 0),
    ('folder VST3\\     (0x8f047e)', 0x8f047e, 2, 0), ('folder AudioUnit\\(0x8f0498)', 0x8f0498, 1, 8), ('folder CLAP\\     (0x8f04be)', 0x8f04be, 1, 8),
    ('slot0/1 Fruity   (0x8f6ac4)', 0x8f6ac4, 1, 0), ('slot2/3 VST      (0x8f6ac5)', 0x8f6ac5, 1, 0), ('slot4/5 VST3     (0x8f6ac6)', 0x8f6ac6, 2, 0),
    ('slot6   AU 64    (0x8f6ac8)', 0x8f6ac8, 1, 8), ('slot7   CLAP 64  (0x8f6ac9)', 0x8f6ac9, 1, 8),
    ('is-fx classes    (0x8f63ec)', 0x8f63ec, 2, 0), ('is-gen classes   (0x8f655c)', 0x8f655c, 2, 0), ('legacy v1 fx     (0x910bca)', 0x910bca, 2, 0),
    ('ps_file_type ok  (0x9117de)', 0x9117de, 1, 0), ('VST2 pseudo-guid  (0x8f6e44)', 0x8f6e44, 2, 0),
]:
    print(f'  {name}: {bits(va, n, base)}')
print('# GUID string byte positions (fle:0x13ab018):', list(rd(0x13ab018, 16)))
print('# default scanflags (0x9145c4) / date (0x914390):', rd(0x9145c4, 1).hex(), rd(0x914390, 8).hex())
print('# 212 header u32@8 per kind index 0..15 (fle:0x14e11d0):', [hex(x) for x in struct.unpack('<16I', rd(0x14e11d0, 64))][:9], '...')
print('# 212 kind by isGen (fle:0x14e1cdc):', [hex(x) for x in struct.unpack('<2I', rd(0x14e1cdc, 8))])
print('# event 28 by flag (fle:0x14e11c8):', rd(0x14e11c8, 8).hex())
p = struct.unpack('<Q', rd(0x15e1818, 8))[0]
print('# bitness file suffix (fle:*0x15e1818):', [ustr(struct.unpack('<Q', rd(p + o, 8))[0]) if struct.unpack('<Q', rd(p + o, 8))[0] else '' for o in (0, 8)])
print('# FLhd magic / FLdt magic:', rd(0xaac498, 4), rd(0xaac4b6, 4), '; wrapper chunk stream flag byte (0xa9f3bc):', rd(0xa9f3bc, 1).hex())
print('# class names (fle:0x8ef860): see HOSTBRIDGE/FORMAT.md')
