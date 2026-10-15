#!/usr/bin/env python3
"""ILTools_x64.dll の export (.text 内) だけを roots にした entries JSON を生成する (閉包 gate の入口)。
usage: gen_entries.py PE out.json [--extra-root VA]
  --extra-root は陰性対照専用: 閉包の root に 1 本追加する (x87 関数を渡すと gate が FAIL することを確かめる)。"""
import argparse, json, pefile

ap = argparse.ArgumentParser()
ap.add_argument('pe')
ap.add_argument('out')
ap.add_argument('--extra-root', action='append', default=[])
a = ap.parse_args()
pe = pefile.PE(a.pe)
base = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
lo, hi = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize
roots = {base + s.address for s in pe.DIRECTORY_ENTRY_EXPORT.symbols if lo <= s.address < hi}
n_export = len(roots)
roots |= {int(x, 16) for x in a.extra_root}
json.dump({'roots': sorted(roots), 'calltgt': []}, open(a.out, 'w'))
print('[iltools entries] export roots %d, extra %d' % (n_export, len(roots) - n_export))
