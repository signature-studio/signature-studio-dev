#!/usr/bin/env python3
"""FLEngine_x64.dll + プラグイン PE の import を採取し、FLEngine は IAT 参照 (call/jmp/load)
のコードサイト頻度を静的に数える。出力: data/imports.json (inventory 生成の入力)。

  python3 scripts/import_scan.py            # data/imports.json を再生成
"""
import json, os, re, struct, sys
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import REPO_ROOT, PLUGINS_DIR  # noqa: E402
OUT = os.path.join(HERE, '..', 'data', 'imports.json')
FLE = f'{REPO_ROOT}/tools/startup/work/FLEngine_x64.dll'
FLE_ALT = f'{REPO_ROOT}/tools/m2/work/block00031_PE.bin'
PLUGINS = {
    'OTT_vst2_win64.dll': f'{PLUGINS_DIR}/ott/binaries/OTT_vst2_win64.dll',
    'OTT_vst3_win64.dll': f'{PLUGINS_DIR}/ott/binaries/OTT_vst3_win64.dll',
    'Serum2_win64.vst3': f'{REPO_ROOT}/tools/targets/serum2/work/Serum2_win64.vst3',
    'FreshAir.dll': f'{REPO_ROOT}/tools/targets/freshair/work/win/Fresh Air/'
                    'C__Program Files_Steinberg_VSTPlugins_Slate Digital/Fresh Air.dll',
    'FL64.exe': f'{REPO_ROOT}/tools/startup/work/FL64.exe',
}


def dec(b):
    return b.decode('latin1') if isinstance(b, bytes) else b


def imports_of(pe):
    pe.parse_data_directories(directories=[
        pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT'],
        pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT']])
    st, dl = [], []
    for e in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        for i in e.imports:
            nm = dec(i.name) if i.name else 'ord%d' % i.ordinal
            st.append({'dll': dec(e.dll).lower(), 'name': nm, 'rva': i.address - pe.OPTIONAL_HEADER.ImageBase})
    for e in getattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', []):
        for i in e.imports:
            nm = dec(i.name) if i.name else 'ord%d' % i.ordinal
            dl.append({'dll': dec(e.dll).lower(), 'name': nm})
    return st, dl


def count_sites(pe, data, st):
    """Delphi は import を `jmp [IAT]` の薄い thunk 経由で呼ぶ。thunk 位置 (FF 25) を特定し、
    thunk への E8 (call) / E9 (jmp) / lea 参照の数を static 呼出頻度として数える。"""
    slot = {s['rva']: s for s in st}
    thunks = {}
    for s in st:
        s.update(calls=0, jmps=0, loads=0, thunks=0, callers=0)
    pending = []
    for sec in pe.sections:
        if not (sec.Characteristics & 0x20000000):  # IMAGE_SCN_MEM_EXECUTE
            continue
        raw = data[sec.PointerToRawData: sec.PointerToRawData + sec.SizeOfRawData]
        va = sec.VirtualAddress
        for m in re.finditer(rb'\xff[\x15\x25]', raw):
            p = m.start()
            if p + 6 > len(raw):
                continue
            rel, = struct.unpack_from('<i', raw, p + 2)
            tgt = va + p + 6 + rel
            s = slot.get(tgt)
            if s:
                s['calls' if raw[p + 1] == 0x15 else 'jmps'] += 1
                if raw[p + 1] == 0x25:
                    s['thunks'] += 1
                    thunks[va + p] = s
        for m in re.finditer(rb'[\x48\x4c]\x8b[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]', raw):
            p = m.start()
            if p + 7 > len(raw):
                continue
            rel, = struct.unpack_from('<i', raw, p + 3)
            s = slot.get(va + p + 7 + rel)
            if s:
                s['loads'] += 1
        # thunk への near call / jmp / lea (別パス: thunk 集合が必要)
        pending.append((va, raw))
    for va, raw in pending:
        for m in re.finditer(rb'[\xe8\xe9]', raw):
            p = m.start()
            if p + 5 > len(raw):
                continue
            rel, = struct.unpack_from('<i', raw, p + 1)
            s = thunks.get(va + p + 5 + rel)
            if s:
                s['callers'] += 1
        for m in re.finditer(rb'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]', raw):
            p = m.start()
            if p + 7 > len(raw):
                continue
            rel, = struct.unpack_from('<i', raw, p + 3)
            s = thunks.get(va + p + 7 + rel)
            if s:
                s['loads'] += 1


def main():
    path = FLE if os.path.exists(FLE) else FLE_ALT
    data = open(path, 'rb').read()
    pe = pefile.PE(data=data, fast_load=True)
    st, dl = imports_of(pe)
    count_sites(pe, data, st)
    out = {'flengine': {'file': 'FLEngine_x64.dll', 'size': len(data), 'static': st, 'delay': dl},
           'plugins': {}}
    for nm, p in PLUGINS.items():
        if not os.path.exists(p):
            print('skip (missing):', nm, file=sys.stderr)
            continue
        d = open(p, 'rb').read()
        q = pefile.PE(data=d, fast_load=True)
        s, dd = imports_of(q)
        out['plugins'][nm] = {'size': len(d), 'static': [{'dll': x['dll'], 'name': x['name']} for x in s],
                              'delay': dd}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, 'w'), indent=1)
    tot = sum(s['callers'] + s['calls'] for s in st)
    zero = sum(1 for s in st if s['callers'] + s['calls'] + s['loads'] == 0)
    print('FLEngine static=%d delay=%d sites=%d zero-site=%d' % (len(st), len(dl), tot, zero))
    for nm, v in out['plugins'].items():
        print('  %-22s static=%d delay=%d' % (nm, len(v['static']), len(v['delay'])))


if __name__ == '__main__':
    main()
