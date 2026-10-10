#!/usr/bin/env python3
"""win64 全 PE (313) を走査して実測インベントリを work/win_pe_scan.json に出力。

出力は PE ごとに: machine/size/timestamp/exports/imports(DLL毎の関数)/sections/PDB/
version info/Delphi・FPC・MSVC 判定材料/文字列ヒント。
"""
import json, os, re, sys, hashlib
from multiprocessing import Pool
import pefile

EXT = '/home/ubuntu/work/analysis/win64/extracted'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'work', 'win_pe_scan.json')

DELPHI_MARKS = [b'Embarcadero', b'Borland', b'SOFTWARE\\Borland\\Delphi\\RTL', b'System.SysUtils',
                b'FastMM', b'TObject', b'System.Classes', b'Vcl.']
FPC_MARKS = [b'FPC ', b'FPC_', b'Free Pascal']
MSVC_MARKS = [b'MSVCP', b'VCRUNTIME', b'api-ms-win-crt', b'_CxxThrowException', b'std::']
HINTS = {
    'FP_DelphiPlug': b'FP_DelphiPlug',
    'TDelphiFruityPlug': b'TDelphiFruityPlug',
    'TFruityPlug': b'TFruityPlug',
    'TFruityPlugHost': b'TFruityPlugHost',
    'CreateFruityInstance': b'CreateFruityInstance',
    'FruityWrapper': b'Fruity Wrapper',
    'ippv2': b'dsp_ippv2',
    'ippcore': b'ippcore',
    'elastique': b'elastique',
    'Intel_IPP': b'ippsMalloc',
    'OpenGL': b'opengl32',
    'ZGE': b'ZGameEditor',
    'FFmpeg': b'avcodec',
    'sqlite': b'sqlite3',
    'python': b'python3',
    'wininet': b'WININET',
    'ws2': b'WS2_32',
    'FLEX': b'engineV2',
    'DirectWave': b'DirectWave',
    'Artwork': b'Artwork',
}


def scan(fn):
    p = os.path.join(EXT, fn)
    d = open(p, 'rb').read()
    r = {'file': fn, 'size': len(d), 'sha1': hashlib.sha1(d).hexdigest()[:12]}
    try:
        pe = pefile.PE(data=d, fast_load=True)
    except Exception as e:
        r['error'] = str(e)[:100]
        return r
    D = pefile.DIRECTORY_ENTRY
    pe.parse_data_directories(directories=[
        D['IMAGE_DIRECTORY_ENTRY_IMPORT'], D['IMAGE_DIRECTORY_ENTRY_EXPORT'],
        D['IMAGE_DIRECTORY_ENTRY_RESOURCE'], D['IMAGE_DIRECTORY_ENTRY_DEBUG'],
        D['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT']])
    fh = pe.FILE_HEADER
    r['machine'] = {0x8664: 'x64', 0x14c: 'x86', 0xAA64: 'arm64'}.get(fh.Machine, hex(fh.Machine))
    r['ts'] = fh.TimeDateStamp
    r['dll'] = bool(fh.Characteristics & 0x2000)
    oh = pe.OPTIONAL_HEADER
    r['subsystem'] = oh.Subsystem
    r['linker'] = '%d.%d' % (oh.MajorLinkerVersion, oh.MinorLinkerVersion)
    r['image_base'] = hex(oh.ImageBase)
    r['sections'] = [{'n': s.Name.rstrip(b'\0').decode('latin1'), 'vs': s.Misc_VirtualSize,
                      'rs': s.SizeOfRawData, 'ch': hex(s.Characteristics)} for s in pe.sections]
    text = [s for s in pe.sections if s.Characteristics & 0x20000000]
    r['code_bytes'] = sum(s.SizeOfRawData for s in text)
    r['sec_names'] = [s['n'] for s in r['sections']]
    ex = []
    if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT'):
        for s in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            ex.append(s.name.decode('latin1') if s.name else '#%d' % s.ordinal)
        r['export_dll_name'] = (pe.get_string_at_rva(pe.DIRECTORY_ENTRY_EXPORT.struct.Name) or b'').decode('latin1')
    r['exports'] = ex
    imp = {}
    for ent in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        dn = ent.dll.decode('latin1').lower()
        imp[dn] = [(i.name.decode('latin1') if i.name else '#%d' % i.ordinal) for i in ent.imports]
    r['imports'] = imp
    dimp = {}
    for ent in getattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', []):
        dn = ent.dll.decode('latin1').lower()
        dimp[dn] = [(i.name.decode('latin1') if i.name else '#%d' % i.ordinal) for i in ent.imports]
    r['delay_imports'] = dimp
    pdb = None
    for dbg in getattr(pe, 'DIRECTORY_ENTRY_DEBUG', []):
        if dbg.struct.Type == 2:
            try:
                raw = d[dbg.struct.PointerToRawData + 24: dbg.struct.PointerToRawData + dbg.struct.SizeOfData]
                pdb = raw.split(b'\0')[0].decode('latin1')
            except Exception:
                pass
    r['pdb'] = pdb
    vi = {}
    try:
        if hasattr(pe, 'FileInfo'):
            for fi in pe.FileInfo:
                for e in fi:
                    if hasattr(e, 'StringTable'):
                        for st in e.StringTable:
                            for k, v in st.entries.items():
                                vi[k.decode('latin1')] = v.decode('latin1')
    except Exception:
        pass
    r['version'] = vi
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata']
    r['pdata_funcs'] = (pd[0].Misc_VirtualSize // 12) if pd else 0
    r['delphi_marks'] = [m.decode() for m in DELPHI_MARKS if m in d]
    r['fpc'] = [m.decode() for m in FPC_MARKS if m in d]
    r['msvc'] = [m.decode() for m in MSVC_MARKS if m in d]
    r['hints'] = [k for k, m in HINTS.items() if m in d]
    urls = set(re.findall(rb'https?://[\x21-\x7e]{4,80}', d))
    r['urls'] = sorted(u.decode('latin1') for u in urls)[:12]
    names = set()
    for m in re.finditer(rb'(Fruity [A-Za-z0-9 \-!]{2,30})', d):
        names.add(m.group(1).decode('latin1'))
    r['name_strings'] = sorted(names)[:30]
    return r


def main():
    files = sorted(f for f in os.listdir(EXT) if f.endswith('_PE.bin'))
    with Pool(16) as pool:
        res = pool.map(scan, files, chunksize=4)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, 'w'), indent=0)
    print('scanned', len(res), 'PEs ->', os.path.normpath(OUT))
    print('errors', sum(1 for r in res if 'error' in r))


if __name__ == '__main__':
    main()
