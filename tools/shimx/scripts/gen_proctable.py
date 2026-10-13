#!/usr/bin/env python3
"""GetProcAddress 用の組込み表 src/proctable.c を生成する。

  gen_proctable.py --nm <nm出力: 定義済みシンボル一覧> --out src/proctable.c

エントリ = (shimx オブジェクトに定義済み) ∩ (shimx.h で宣言済み) の関数。
DLL 帰属は data/imports.json (FLEngine 738+57 / プラグイン import) の dll 名、無ければ接頭辞規則、既定 kernel32.dll。
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')

PREFIX_DLL = [
    ('SHCreateMemStream', 'shlwapi.dll'), ('QISearch', 'shlwapi.dll'),          # SHX-T8: 接頭辞 'SH' (shell32) より先に判定
    ('CryptReleaseContext', 'advapi32.dll'),
    ('Reg', 'advapi32.dll'), ('OpenProcessToken', 'advapi32.dll'), ('GetTokenInformation', 'advapi32.dll'),
    ('Sys', 'oleaut32.dll'), ('Variant', 'oleaut32.dll'), ('Safe', 'oleaut32.dll'),
    ('Co', 'ole32.dll'), ('Ole', 'ole32.dll'), ('StringFrom', 'ole32.dll'), ('CLSIDFrom', 'ole32.dll'), ('ProgIDFrom', 'ole32.dll'),
    ('CreateStreamOnHGlobal', 'ole32.dll'), ('GetHGlobalFromStream', 'ole32.dll'), ('IsEqualGUID', 'ole32.dll'),
    ('RegisterDragDrop', 'ole32.dll'), ('RevokeDragDrop', 'ole32.dll'), ('DoDragDrop', 'ole32.dll'), ('PropVariantClear', 'ole32.dll'),
    ('ReleaseStgMedium', 'ole32.dll'), ('UuidCreate', 'rpcrt4.dll'),
    ('SH', 'shell32.dll'), ('IL', 'shell32.dll'), ('Shell', 'shell32.dll'), ('Drag', 'shell32.dll'), ('PathCleanupSpec', 'shell32.dll'),
    ('PathUnExpand', 'shlwapi.dll'),
    ('GetFileVersionInfo', 'version.dll'), ('VerQueryValue', 'version.dll'),
    ('Image', 'imagehlp.dll'),
    ('WNet', 'mpr.dll'), ('WinVerifyTrust', 'wintrust.dll'), ('Cert', 'crypt32.dll'), ('CryptMsg', 'crypt32.dll'),
    ('CryptQuery', 'crypt32.dll'), ('CryptDecode', 'crypt32.dll'),
    ('Internet', 'wininet.dll'), ('Http', 'wininet.dll'),
    ('WSA', 'ws2_32.dll'), ('closesocket', 'ws2_32.dll'), ('ioctlsocket', 'ws2_32.dll'),
    ('midi', 'winmm.dll'), ('time', 'winmm.dll'),
    ('acm', 'msacm32.dll'), ('GetOpenFileName', 'comdlg32.dll'), ('GetSaveFileName', 'comdlg32.dll'), ('CommDlg', 'comdlg32.dll'),
    ('OpenPrinter', 'winspool.drv'), ('ClosePrinter', 'winspool.drv'), ('EnumPrinters', 'winspool.drv'),
    ('GetDefaultPrinter', 'winspool.drv'), ('DocumentProperties', 'winspool.drv'),
    ('Lresult', 'oleacc.dll'), ('WTS', 'wtsapi32.dll'), ('PropVariant', 'propsys.dll'), ('VariantToPropVariant', 'propsys.dll'),
    ('Char', 'user32.dll'), ('MsgWait', 'user32.dll'),
    ('_', 'msvcrt.dll'),
]
# 序数/内部用で表に載せない
SKIP = {'shim_unimplemented', '__readgsqword', '__readgsdword', '__readgsword', '__readgsbyte', '__writegsqword', '__writegsdword'}
SKIP_PREFIX = ('shimx_', 'shx_', 'shim_', 'vreg_')   # vreg_ = 運用フック (CAB-214, JS 側 EXPORTED_FUNCTIONS 用)


def dll_for(name, mapping):
    if name in mapping:
        return mapping[name]
    for pre, dll in PREFIX_DLL:
        if name.startswith(pre):
            return dll
    return 'kernel32.dll'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--nm', required=True, help='llvm-nm --defined-only -g の出力 (行末が名前)')
    ap.add_argument('--out', default=os.path.join(ROOT, 'src', 'proctable.c'))
    a = ap.parse_args()

    defined = set()
    for ln in open(a.nm):
        p = ln.split()
        if len(p) >= 2 and p[-2] in ('T', 'W', 't', 'w'):
            defined.add(p[-1])
    hdr = open(os.path.join(ROOT, 'src', 'shimx.h')).read()
    declared = set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(', hdr))

    imp = json.load(open(os.path.join(ROOT, 'data', 'imports.json')))
    mapping = {}
    def add(lst):
        for e in lst:
            mapping.setdefault(e['name'], e['dll'])
    add(imp['flengine']['static']); add(imp['flengine']['delay'])
    for v in imp['plugins'].values():
        add(v['static']); add(v['delay'])
    # kernel32 に優先 (Rtl*/Interlocked* は複数 DLL に現れ得る)
    for e in imp['flengine']['static']:
        if e['dll'] == 'kernel32.dll':
            mapping[e['name']] = 'kernel32.dll'

    ents = []
    for n in sorted(defined):
        if n in SKIP or n.startswith(SKIP_PREFIX):
            continue
        if n not in declared:
            continue
        ents.append((dll_for(n, mapping), n))
    ents.sort()
    out = ['/* 自動生成: scripts/gen_proctable.py — 手編集禁止。GetProcAddress の組込み表 (shimx 実装済み API)。 */',
           '#include "shimx.h"', '',
           'typedef struct { const char* dll; const char* name; void* fn; } ShxProcEnt;',
           'const ShxProcEnt shx_proctable[] = {']
    for d, n in ents:
        out.append('    { "%s", "%s", (void*)%s },' % (d, n, n))
    out.append('};')
    out.append('const int shx_proctable_n = %d;' % len(ents))
    open(a.out, 'w').write('\n'.join(out) + '\n')
    print('proctable: %d entries -> %s' % (len(ents), a.out))


if __name__ == '__main__':
    main()
