#!/usr/bin/env python3
"""PLG-F8 (#205) の対象 28 本 (name, Delphi 殻 block, 期待 Tier, C++ engine block)。 e2e / facts / judge / 検算が共有する唯一の一覧。
一覧と Tier は #205 本文の「対象」節 (Tier 規則推定の添字) から転記。 block と Tier は matrix_check.py が PLUGIN_MATRIX.json と突合する。
usage: targets.py blocks | names | json
"""
import json, sys

TARGETS = [
    ('Control Surface', 18797, 'T2', None),
    ('Edison', 18955, 'T1', None),
    ('Fruity Big Clock', 18986, 'T1', None),
    ('Fruity Formula Controller', 19012, 'T1', None),
    ('Fruity HTML NoteBook', 19016, 'T1', None),
    ('Fruity LSD', 19019, 'T2', None),
    ('Fruity NoteBook', 19052, 'T0', None),
    ('Fruity NoteBook 2', 19054, 'T0', None),
    ('Fruity Peak Controller', 19062, 'T0', None),
    ('Fruity Spectroman', 19080, 'T0', None),
    ('Fruity X-Y Controller', 19093, 'T0', None),
    ('Fruity X-Y-Z Controller', 19094, 'T0', None),
    ('Fruity dB meter', 19096, 'T0', None),
    ('Transmitter', 19253, 'T1', None),
    ('Transporter', 19254, 'T1', None),
    ('Tuner', 19255, 'T2', 19256),
    ('VFX Color Mapper', 19257, 'T0', None),
    ('VFX Envelope', 19258, 'T0', None),
    ('VFX Key Mapper', 19259, 'T0', None),
    ('VFX Keyboard Splitter', 19260, 'T0', None),
    ('VFX Level Scaler', 19261, 'T0', None),
    ('VFX Script', 19262, 'T1', None),
    ('VFX Sequencer', 19263, 'T2', 19264),
    ('Wave Candy', 19297, 'T1', None),
    ('Dashboard', 21206, 'T2', None),
    ('Fruity Envelope Controller', 23648, 'T3', None),
    ('Fruity Keyboard Controller', 23660, 'T1', None),
    ('Fruity Voltage Controller', 23675, 'T1', None),
]

if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'json'
    if what == 'blocks':
        print(' '.join(str(b) for _, b, _, _ in TARGETS))
    elif what == 'names':
        print('\n'.join(n for n, _, _, _ in TARGETS))
    else:
        print(json.dumps(TARGETS))
