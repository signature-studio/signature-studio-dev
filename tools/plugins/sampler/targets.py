#!/usr/bin/env python3
"""sampler 8 本 (PLG-G3 / #208) の対象定義。 e2e・judge・facts・突合の全スクリプトがここだけを参照する (対象の二重定義を避ける)。
usage: targets.py blocks | engines | allow-unimpl | monoliths
"""
import sys

# name, Delphi 殻の block, 殻から LoadLibrary される C++ engine の block (None = 無し)
SHELLS = [
    ('FL Keys', 22386, None),
    ('FPC', 23617, None),
    ('Fruity Granulizer', 23658, None),
    ('Fruity Slicer', 23662, None),
    ('Fruity Slicer 2', 23663, 23664),
    ('Slicex', 24172, None),
    ('Soundfont Player', 24175, None),
]
# Delphi 殻を持たない MSVC C++ 単体 DLL (framework 一致 0)
MONOLITHS = [('GMS', 23677)]
# 判定が許す未実装 __asm_* helper の上限 (block -> 件数) と、その名前の許可リスト。 ここに無い block は 0 件でなければ不合格
ALLOW_UNIMPL = {}
ALLOW_UNIMPL_NAMES = []


def shell_blocks():
    return [b for _, b, _ in SHELLS]


def engine_blocks():
    return [e for _, _, e in SHELLS if e] + [b for _, b in MONOLITHS]


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'blocks':
        print(' '.join(map(str, shell_blocks())))
    elif cmd == 'engines':
        print(' '.join(map(str, engine_blocks())))
    elif cmd == 'allow-unimpl':
        print(','.join('%d=%d' % kv for kv in ALLOW_UNIMPL.items()))
    else:
        sys.exit('usage: targets.py blocks|engines|allow-unimpl')
