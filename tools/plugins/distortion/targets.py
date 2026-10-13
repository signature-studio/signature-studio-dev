#!/usr/bin/env python3
"""PLG-F6 (#203) distortion + multi-fx 9 本の対象表 (単一の正本)。 他のスクリプトはここから block を読む。
  targets.py shells    → Delphi 殻の block (空白区切り)
  targets.py engines   → C++ / 別 DLL の block (空白区切り)
"""
import sys

# 閉包 lift の対象 = Delphi (FP_DelphiPlug) の DLL。 (表示名, block, Tier, PLUGIN_MATRIX.json の name / 突合しないなら None)
# Distructor の module_x64.dll (18916) も Delphi 製で同じ vtable を持つので殻と同じ手順で測る。
# PLUGIN_MATRIX の `lift` 欄は各 plugin の先頭 module のみの記録なので 18916 は突合対象外 (今回初測定)。
SHELLS = [
    ('Distructor', 18914, 'T2', 'Distructor'),
    ('Distructor module', 18916, 'T2', None),
    ('Effector', 18972, 'T2', 'Effector'),
    ('Fruity Blood Overdrive', 18987, 'T0', 'Fruity Blood Overdrive'),
    ('Fruity Fast Dist', 19004, 'T0', 'Fruity Fast Dist'),
    ('Fruity Love Philter', 19024, 'T1', 'Fruity Love Philter'),
    ('Fruity Soft Clipper', 19078, 'T0', 'Fruity Soft Clipper'),
    ('Fruity Squeeze', 19082, 'T0', 'Fruity Squeeze'),
    ('Fruity WaveShaper', 19089, 'T0', 'Fruity WaveShaper'),
]
# 全 .pdata 関数を lift する MSVC C++ DLL。 (表示名, block, 属する plugin, 種別)
ENGINES = [
    ('Effector engine', 18973, 'Effector', 'MSVC C++'),
    ('Hardcore', 19101, 'Hardcore', 'MSVC C++ 単体'),
]
# 未実装 helper の許容は無い (#535 で Love Philter の rep_stosb_memset も実装済み。 許容を残すと再び未実装になっても検出できない)

if __name__ == '__main__':
    if sys.argv[1:] == ['shells']:
        print(' '.join(str(b) for _, b, _, _ in SHELLS))
    elif sys.argv[1:] == ['engines']:
        print(' '.join(str(b) for _, b, _, _ in ENGINES))
    else:
        sys.exit('usage: targets.py shells|engines')
