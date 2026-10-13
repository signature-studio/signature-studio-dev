#!/usr/bin/env python3
"""fl-win64 素材 (extracted/ のみ) から inventory.py の入力 block_manifest.json / pe_metadata.json を再構成する。

Usage: mk_inputs.py <extracted_dir> <out_dir> [<offsets.json>]
  block_manifest.json: [{idx, path, kind, dsize, payload_off}]  (kind = ファイル名の拡張子前の種別: PE/DATA/PNG/...)
    payload_off は <offsets.json> (startup/loadpaths/mk_manifest.py の出力 [{idx, payload_off}]) を渡したときだけ入る。
    入ると recover_paths.py (payload_off を要求) と inventory.py (idx/kind/dsize を要求) の両方の入力になる
  pe_metadata.json:    [{file, machine}]           (PE ヘッダの Machine: 0x14c=x86, 0x8664=x64, それ以外は hex)
"""
import json, os, re, struct, sys

ext, out = sys.argv[1:3]
offs = {o['idx']: o['payload_off'] for o in json.load(open(sys.argv[3]))} if len(sys.argv) > 3 else {}
os.makedirs(out, exist_ok=True)
man, pe = [], []
for fn in sorted(os.listdir(ext)):
    m = re.match(r'block(\d{5})_(\w+)\.', fn)
    if not m:
        continue
    p = os.path.join(ext, fn)
    idx = int(m.group(1))
    ent = dict(idx=idx, path=p, kind=m.group(2), dsize=os.path.getsize(p))
    if idx in offs:
        ent['payload_off'] = offs[idx]
    man.append(ent)
    if m.group(2) == 'PE':
        with open(p, 'rb') as f:
            h = f.read(4096)
        o = struct.unpack_from('<I', h, 0x3c)[0]
        mach = struct.unpack_from('<H', h, o + 4)[0] if h[o:o + 4] == b'PE\0\0' else None
        pe.append(dict(file=fn, machine={0x14c: 'x86', 0x8664: 'x64'}.get(mach, hex(mach) if mach is not None else None)))
json.dump(man, open(os.path.join(out, 'block_manifest.json'), 'w'))
json.dump(pe, open(os.path.join(out, 'pe_metadata.json'), 'w'))
print('blocks', len(man), 'PE', len(pe), 'x86', sum(1 for x in pe if x['machine'] == 'x86'))
