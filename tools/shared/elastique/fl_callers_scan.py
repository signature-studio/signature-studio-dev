#!/usr/bin/env python3
"""FL 素材の中で élastique の export を呼ぶ箇所を静的に探す (T-SH-69 / #3334・付録 §9.2)。

入力: FL_WIN64_DIR = 素材の展開先 (既定 $RUNNER_TEMP/fl-win64。`extracted/` を含む。REPORT §2 の手順で展開)
手順:
  1. extracted/ の全ファイルのうち、先頭が MZ で pefile が読めるものを PE とし、import 表を走査する。
     import の DLL 名が elastique_x64.dll、または関数名が EXPORT_PREFIXES のいずれかで始まる PE を数える。
  2. extracted/ の全ファイルのバイト列を NEEDLES で検索し、文字列ごと・和集合のヒットファイル数を出す。
出力: 標準出力 (PE 件数・import の一致件数・文字列ごとのヒットファイル数と和集合)。
"""
import os

import pefile

FL_DIR = os.environ.get('FL_WIN64_DIR', os.path.join(os.environ.get('RUNNER_TEMP', '/tmp'), 'fl-win64'))
EXPORT_PREFIXES = ('Auftakt_', 'ElPro', 'ElAllocator', 'Declicker_', 'Denoiser_', 'Metering_',
                   'SolPitchAn_', 'ElResampleSource')
DLL_NAME = b'elastique_x64.dll'
NEEDLES = [b'Auftakt_CreateInstance', b'ElPro_CreateInstance', b'ElProV3_CreateInstance',
           b'ElAllocator_SetFunctions', b'ElResampleSource_CreateInstance', b'elastique_x64',
           b'ElastiquePro']


def main():
    root = os.path.join(FL_DIR, 'extracted')
    files = []
    for dp, _, fns in os.walk(root):
        files += [os.path.join(dp, f) for f in fns]
    pe_n, pe_hit = 0, []
    hits = {n: set() for n in NEEDLES}
    union = set()
    for path in sorted(files):
        with open(path, 'rb') as f:
            data = f.read()
        for n in NEEDLES:
            if n in data:
                hits[n].add(path)
                union.add(path)
        if data[:2] != b'MZ':
            continue
        try:
            pe = pefile.PE(data=data, fast_load=True)
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
        except pefile.PEFormatError:
            continue
        pe_n += 1
        for ent in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
            if ent.dll.lower() == DLL_NAME:
                pe_hit.append((path, 'dll'))
            for imp in ent.imports:
                if imp.name and imp.name.decode(errors='replace').startswith(EXPORT_PREFIXES):
                    pe_hit.append((path, imp.name.decode(errors='replace')))
    print(f'extracted のファイル: {len(files)} / PE (pefile が読めたもの): {pe_n}')
    print(f'élastique の import (DLL 名 または export 接頭): {len(pe_hit)} 件 {sorted(set(pe_hit))[:5]}')
    for n in NEEDLES:
        print(f'  文字列 {n.decode()}: {len(hits[n])} ファイル')
    print(f'文字列のいずれかを含むファイル (和集合): {len(union)}')
    for p in sorted(union):
        print(f'  {os.path.relpath(p, root)}: {[n.decode() for n in NEEDLES if p in hits[n]]}')


if __name__ == '__main__':
    main()
