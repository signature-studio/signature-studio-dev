#!/usr/bin/env python3
"""x86_64/arm64 dylib・win dll の export 集合と FL 要求 420 名を work/ に書く。"""
import subprocess, json, os, re, sys
import pefile
HERE = os.path.dirname(os.path.abspath(__file__)); W = f'{HERE}/work'
sys.path.insert(0, os.path.join(HERE, '..', 'shared')); from paths import FL_WIN64_DIR
def nm(path):
    o = subprocess.run(['llvm-nm', '-U', '--defined-only', path], capture_output=True, text=True).stdout
    return sorted(set(l.split()[2] for l in o.splitlines() if len(l.split()) == 3))
for arch, f in (('a64', 'dsp_ippv2.arm64'), ('x64', 'dsp_ippv2.x86_64')):
    open(f'{W}/{arch}.syms', 'w').write('\n'.join(nm(f'{W}/{f}')) + '\n')
pe = pefile.PE(f'{FL_WIN64_DIR}/extracted/block24356_PE.bin', fast_load=True); pe.parse_data_directories(directories=[0])
ex = [e.name.decode() for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name]
json.dump(ex, open(f'{W}/win_exports.json', 'w'))
names = json.load(open(f'{W}/flengine_ipp_names.json'))
req = [n for n in names['x86_64'] if n.startswith('ipp')]
json.dump({'req': sorted(set(req))}, open(f'{W}/req.json', 'w'))
print(f'arm64 exports {len(open(f"{W}/a64.syms").read().split())}, x86_64 exports {len(open(f"{W}/x64.syms").read().split())}, win exports {len(ex)}, FL requested ipp names {len(set(req))}')
