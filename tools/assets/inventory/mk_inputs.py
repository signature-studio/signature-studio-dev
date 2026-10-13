#!/usr/bin/env python3
"""fl-win64 素材 (extracted/ のみ) から inventory.py の入力 block_manifest.json / pe_metadata.json を再構成する。

Usage: mk_inputs.py <extracted_dir> <out_dir>
  block_manifest.json: [{idx, path, kind, dsize}]  (kind = ファイル名の拡張子前の種別: PE/DATA/PNG/...)
  pe_metadata.json:    [{file, machine}]           (PE ヘッダの Machine: 0x14c=x86, 0x8664=x64, それ以外は hex)
"""
import json, os, re, struct, sys

ext, out = sys.argv[1:3]
os.makedirs(out, exist_ok=True)
man, pe = [], []
for fn in sorted(os.listdir(ext)):
    m = re.match(r'block(\d{5})_(\w+)\.', fn)
    if not m:
        continue
    p = os.path.join(ext, fn)
    man.append(dict(idx=int(m.group(1)), path=p, kind=m.group(2), dsize=os.path.getsize(p)))
    if m.group(2) == 'PE':
        with open(p, 'rb') as f:
            h = f.read(4096)
        o = struct.unpack_from('<I', h, 0x3c)[0]
        mach = struct.unpack_from('<H', h, o + 4)[0] if h[o:o + 4] == b'PE\0\0' else None
        pe.append(dict(file=fn, machine={0x14c: 'x86', 0x8664: 'x64'}.get(mach, hex(mach) if mach is not None else None)))
json.dump(man, open(os.path.join(out, 'block_manifest.json'), 'w'))
json.dump(pe, open(os.path.join(out, 'pe_metadata.json'), 'w'))
print('blocks', len(man), 'PE', len(pe), 'x86', sum(1 for x in pe if x['machine'] == 'x86'))
