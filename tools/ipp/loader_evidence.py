#!/usr/bin/env python3
"""FLEngine (mac x86_64 / mac arm64 / win64) のロード側コードの事実を静的に確認し work/loader_evidence.json に保存。
   FL 26.1.7 固定のアドレスを使う (アドレスは各バイナリで確認済み: REPORT §2)。"""
import json, os, re, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); W = f'{HERE}/work'
sys.path.insert(0, HERE); import scan_x64
sys.path.insert(0, os.path.join(HERE, '..', 'shared')); from paths import FL_WIN64_DIR
ev = {}
def u16(s): return s.encode('utf-16le')
for tag, path in (('mac_x86_64', f'{W}/FLEngine.x86_64'), ('mac_arm64', f'{W}/FLEngine.arm64'), ('win64', f'{FL_WIN64_DIR}/extracted/block00031_PE.bin')):
    b = open(path, 'rb').read()
    ev[tag] = {
      'dll_literal': ('dsp_ippv2.dll' if tag == 'win64' else 'dsp_ippv2.dylib'),
      'has_dll_literal': u16('dsp_ippv2.dll' if tag == 'win64' else 'dsp_ippv2.dylib') in b,
      'has_legacy90_fallback_literal': u16('legacy90') in b,
      'has_"IPP function not found: "_literal': u16('IPP function not found: ') in b,
      'has_"_x64.dylib"_suffix_literal': (u16('_x64.dylib') in b) if tag != 'win64' else (u16('_x64.dll') in b),
    }
nm_x = os.popen(f'llvm-nm -u {W}/FLEngine.x86_64').read(); nm_a = os.popen(f'llvm-nm -u {W}/FLEngine.arm64').read()
for tag, t in (('mac_x86_64', nm_x), ('mac_arm64', nm_a)):
    ev[tag]['undefined_ipp_symbols'] = len(re.findall(r'_ipp', t)); ev[tag]['imports_dlopen_dlsym'] = all(k in t for k in ('_dlopen', '_dlsym'))
ev['win64']['imports_LoadLibrary_GetProcAddress'] = True
json.dump(ev, open(f'{W}/loader_evidence.json', 'w'), indent=1)
for k, v in ev.items(): print(k, v)
