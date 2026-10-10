#!/usr/bin/env python3
"""PE summary: sections, imports (dll + count), exports, version info, timestamp."""
import sys, pefile, hashlib
def info(p, imports=True, maxexp=40):
    pe = pefile.PE(p, fast_load=False)
    print("FILE", p)
    print(" machine=%#x ts=%s subsys=%d imagebase=%#x ep=%#x size=%d" % (pe.FILE_HEADER.Machine, pe.FILE_HEADER.TimeDateStamp, pe.OPTIONAL_HEADER.Subsystem, pe.OPTIONAL_HEADER.ImageBase, pe.OPTIONAL_HEADER.AddressOfEntryPoint, pe.OPTIONAL_HEADER.SizeOfImage))
    for s in pe.sections:
        print("  sec %-8s va=%#09x vsz=%9d rawsz=%9d ent=%.2f" % (s.Name.rstrip(b'\0').decode(), s.VirtualAddress, s.Misc_VirtualSize, s.SizeOfRawData, s.get_entropy()))
    if imports and hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
        for d in pe.DIRECTORY_ENTRY_IMPORT:
            print("  imp %-28s %3d: %s" % (d.dll.decode(), len(d.imports), ",".join((i.name.decode() if i.name else "#%d"%i.ordinal) for i in d.imports[:100])))
    if hasattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT'):
        for d in pe.DIRECTORY_ENTRY_DELAY_IMPORT:
            print("  dimp %-27s %3d" % (d.dll.decode(), len(d.imports)))
    if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT'):
        ex = pe.DIRECTORY_ENTRY_EXPORT.symbols
        print("  exports %d: %s" % (len(ex), ",".join((e.name.decode() if e.name else "#%d"%e.ordinal) for e in ex[:maxexp])))
    if hasattr(pe, 'FileInfo'):
        for fi in pe.FileInfo:
            for e in fi:
                if hasattr(e, 'StringTable'):
                    for st in e.StringTable:
                        d = getattr(st, 'entries', {})
                        print("  ver", {(k.decode() if isinstance(k, bytes) else k): (v.decode(errors='replace') if isinstance(v, bytes) else v) for k, v in d.items()})
    sec = pe.get_section_by_rva(pe.OPTIONAL_HEADER.DATA_DIRECTORY[3].VirtualAddress) if pe.OPTIONAL_HEADER.DATA_DIRECTORY[3].VirtualAddress else None
    print("  pdata size=%d (funcs=%d)" % (pe.OPTIONAL_HEADER.DATA_DIRECTORY[3].Size, pe.OPTIONAL_HEADER.DATA_DIRECTORY[3].Size // 12))
    sc = pe.OPTIONAL_HEADER.DATA_DIRECTORY[4]
    print("  security(authenticode) off=%#x size=%d" % (sc.VirtualAddress, sc.Size))
    tls = pe.OPTIONAL_HEADER.DATA_DIRECTORY[9]; print("  tls dir rva=%#x size=%d" % (tls.VirtualAddress, tls.Size))
    print("  dll_characteristics=%#x" % pe.OPTIONAL_HEADER.DllCharacteristics)
if __name__ == "__main__":
    for p in sys.argv[1:]:
        info(p)
