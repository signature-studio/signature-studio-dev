#!/usr/bin/env python3
"""PLG-G1 (#206) 対象の正本 (name / Delphi 殻 block / C++ engine block)。 他の g1 スクリプトと g1_e2e.sh はここから読む。

  python3 common.py shells    → 重複なしの Delphi 殻 block (空白区切り)
  python3 common.py engines   → C++ DLL block (engine 6 本 + MiniSynth 単体 DLL; 空白区切り)
"""
import sys

# name, Delphi 殻 block (None = 殻なし), 付随 C++ engine block (None = 無し)。 PLUGIN_MATRIX.json の win.modules と一致させる (matrix_check.py が検算)
PLUGINS = [
    ('3x Osc', 21148, 21149),
    ('BassDrum', 21182, 21183),
    ('BeepMap', 21194, None),
    ('Drumaxx', 21297, 21298),
    ('Drumpad', 22383, 22384),
    ('Fruit Kick', 23634, None),
    ('Fruity DX10', 23636, None),
    ('Fruity Dance', 23638, None),
    ('Fruity DrumSynth Live', 23644, 23645),
    ('MiniSynth', None, 23921),          # 単体の C++ DLL (Delphi 殻なし)
    ('Plucked!', 24157, None),
    ('SimSynth', 24170, 24168),
    ('Wasp', 24302, None),
    ('Wasp XT', 24302, None),            # Wasp と同一 block (同一 PE)
]


def shells():
    out = []
    for _, s, _ in PLUGINS:
        if s is not None and s not in out:
            out.append(s)
    return out


def engines():
    return [e for _, _, e in PLUGINS if e is not None]


if __name__ == '__main__':
    print(' '.join(str(b) for b in {'shells': shells, 'engines': engines}[sys.argv[1]]()))
