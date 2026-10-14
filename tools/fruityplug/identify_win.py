#!/usr/bin/env python3
"""FruityPlug_x64.dll を内部名に持つ win PE (Fruity プラグイン DLL 群) の内訳を実測する (T-SH-12 #154)。

入力: FL_WIN64_DIR/extracted/block*_PE.bin (fl-win64 素材)。
出力: work/identify.tsv (gitignore 対象) と標準出力の集計。判定 (gate) は行わない。
tools/shared/scripts/classify.py の SGv2 ↔ block24353 推定の検証に使う。 結果と解釈は REPORT.md。
"""
import collections
import glob
import os
import sys

import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
FL = os.environ.get('FL_WIN64_DIR')
if not FL:
    sys.exit('FL_WIN64_DIR を設定してください (fl-win64 の展開先)')
TARGET = 'block24353_PE.bin'  # tools/shared/scripts/classify.py が SGv2 の win 候補として固定している block
TMPL = frozenset(['CreatePlugInstance', '__dbk_fcall_wrapper', 'dbkFCallWrapperAddr'])
VI_KEYS = ('ProductName', 'InternalName', 'FileDescription', 'OriginalFilename')


def info(path):
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(directories=[
        pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT'],
        pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE'],
    ])
    dll = ''
    exps = []
    if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT'):
        dll = pe.get_string_at_rva(pe.DIRECTORY_ENTRY_EXPORT.struct.Name).decode('latin1', 'replace')
        exps = [s.name.decode('latin1') if s.name else 'ord%d' % s.ordinal
                for s in pe.DIRECTORY_ENTRY_EXPORT.symbols]
    vi = {}
    for fi in getattr(pe, 'FileInfo', []) or []:
        for f in fi:
            for st in getattr(f, 'StringTable', []) or []:
                for k, v in st.entries.items():
                    vi[k.decode('latin1')] = v.decode('latin1')
    return dll, exps, vi


rows = []
for p in sorted(glob.glob(os.path.join(FL, 'extracted', 'block*_PE.bin'))):
    try:
        dll, exps, vi = info(p)
    except pefile.PEFormatError:
        continue
    if dll.lower() != 'fruityplug_x64.dll':
        continue
    rows.append(dict(
        block=os.path.basename(p), size=os.path.getsize(p), n_exp=len(exps),
        expset=frozenset(exps), tmpl3=frozenset(exps) == TMPL,
        has_create=('CreatePlugInstance' in exps),
        **{k: vi.get(k, '') for k in VI_KEYS}))

os.makedirs(os.path.join(HERE, 'work'), exist_ok=True)
with open(os.path.join(HERE, 'work', 'identify.tsv'), 'w') as f:
    f.write('\t'.join(['block', 'size', 'n_exp', 'tmpl3', 'has_create'] + list(VI_KEYS)) + '\n')
    for r in rows:
        f.write('\t'.join([r['block'], str(r['size']), str(r['n_exp']), str(r['tmpl3']),
                           str(r['has_create'])] + [r[k] for k in VI_KEYS]) + '\n')

print('FruityPlug_x64.dll 内部名の PE: %d 本' % len(rows))
print('CreatePlugInstance を持つ: %d / export 組が tmpl3 と一致: %d / export 組の種類: %d' % (
    sum(r['has_create'] for r in rows), sum(r['tmpl3'] for r in rows),
    len(set(r['expset'] for r in rows))))
tgt = [r for r in rows if r['block'] == TARGET]
print('target %s: %s' % (TARGET, tgt[0] if tgt else 'not found'))
same_size = [r['block'] for r in rows if tgt and r['size'] == tgt[0]['size']]
print('同サイズ (%d B) の FruityPlug 名 PE: %s' % (tgt[0]['size'] if tgt else 0, same_size))
pc = collections.Counter(r['ProductName'] or '(none)' for r in rows)
print('ProductName 種類: %d / VERSIONINFO なし: %d' % (
    len(pc), sum(1 for r in rows if not r['ProductName'] and not r['InternalName'])))
print('ProductName 上位: %s' % pc.most_common(40))
