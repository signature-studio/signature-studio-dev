#!/usr/bin/env python3
"""PE スタブ (poc/pe_stub.mjs 産) が Fruity Wrapper の事前検査を通ることを pefile で確認する.
  - fw:0x5c0200/0x7a9030 相当: export 名を小文字化し main / vstpluginmain / hint のいずれかを含む
  - fw:0x5bfc30 相当: MZ(0x5a4d) → PE → machine==0x8664 (x64)"""
import sys, pefile
pe = pefile.PE(sys.argv[1])
names = [e.name.decode() for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name]
low = [n.lower() for n in names]
ok_exp = ('main' in low) or ('vstpluginmain' in low)
ok_arch = pe.FILE_HEADER.Machine == 0x8664 and pe.DOS_HEADER.e_magic == 0x5a4d and pe.is_dll()
print('exports:', names, '| machine: 0x%x' % pe.FILE_HEADER.Machine)
print('OK  S1 pefile が PE32+ DLL として解釈 / export 名復元' if names == ['VSTPluginMain', 'main'] else 'FAIL S1')
print('OK  S2 Wrapper 事前検査 (lower(export)∋main|vstpluginmain)' if ok_exp else 'FAIL S2')
print('OK  S3 bitness 判定 (MZ + machine 0x8664 + DLL)' if ok_arch else 'FAIL S3')
sys.exit(0 if (names == ['VSTPluginMain', 'main'] and ok_exp and ok_arch) else 1)
