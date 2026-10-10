#!/usr/bin/env python3
"""PE survey: sections/entropy/imports/exports/resources/TLS/debug/signature. usage: pe_survey.py <pe> [...]"""
import sys, math, collections, pefile

def entropy(b):
    if not b: return 0.0
    c = collections.Counter(b); n = len(b)
    return -sum(v/n*math.log2(v/n) for v in c.values())

for path in sys.argv[1:]:
    pe = pefile.PE(path)
    fh, oh = pe.FILE_HEADER, pe.OPTIONAL_HEADER
    print(f"## {path}")
    print(f"machine=0x{fh.Machine:x} nsec={fh.NumberOfSections} ts={fh.TimeDateStamp} imgbase=0x{oh.ImageBase:x} entry=0x{oh.AddressOfEntryPoint:x} size_of_image={oh.SizeOfImage} linker={oh.MajorLinkerVersion}.{oh.MinorLinkerVersion} subsys={oh.Subsystem} dllchar=0x{oh.DllCharacteristics:x}")
    ep = oh.AddressOfEntryPoint
    for s in pe.sections:
        name = s.Name.rstrip(b'\0').decode(errors='replace')
        data = s.get_data()
        flag = s.Characteristics
        perm = ('R' if flag & 0x40000000 else '-') + ('W' if flag & 0x80000000 else '-') + ('X' if flag & 0x20000000 else '-')
        mark = ' <-EP' if s.VirtualAddress <= ep < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData) else ''
        print(f"  {name:<8} va=0x{s.VirtualAddress:08x} vsz={s.Misc_VirtualSize:>9} raw={s.SizeOfRawData:>9} {perm} entropy={entropy(data):.3f}{mark}")
    # data dirs
    for d in pe.OPTIONAL_HEADER.DATA_DIRECTORY:
        if d.VirtualAddress or d.Size:
            print(f"  dir {d.name:<32} va=0x{d.VirtualAddress:x} size={d.Size}")
    # exports
    if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT'):
        print("  exports:", [ (e.name.decode() if e.name else f'#{e.ordinal}') for e in pe.DIRECTORY_ENTRY_EXPORT.symbols])
    # imports
    if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
        tot = 0
        for imp in pe.DIRECTORY_ENTRY_IMPORT:
            names = [(i.name.decode() if i.name else f'#{i.ordinal}') for i in imp.imports]
            tot += len(names)
            print(f"  import {imp.dll.decode()} ({len(names)})")
        print(f"  total imports: {tot}")
    if hasattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT'):
        for imp in pe.DIRECTORY_ENTRY_DELAY_IMPORT:
            print(f"  delay-import {imp.dll.decode()} ({len(imp.imports)})")
    if hasattr(pe, 'DIRECTORY_ENTRY_TLS'):
        t = pe.DIRECTORY_ENTRY_TLS.struct
        print(f"  TLS callbacks va=0x{t.AddressOfCallBacks:x}")
    if hasattr(pe, 'DIRECTORY_ENTRY_DEBUG'):
        for d in pe.DIRECTORY_ENTRY_DEBUG:
            print(f"  debug type={d.struct.Type} size={d.struct.SizeOfData}")
            try:
                raw = pe.get_data(d.struct.AddressOfRawData, d.struct.SizeOfData)
                if raw[:4] == b'RSDS': print("   pdb:", raw[24:].split(b'\0')[0].decode(errors='replace'))
            except Exception as e: pass
    pe.close()
