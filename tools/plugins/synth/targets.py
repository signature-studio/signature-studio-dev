#!/usr/bin/env python3
"""#207 (PLG-G2 synth 14 本) の対象モジュールを PLUGIN_MATRIX.json から導出する (block 番号を手書きしない)。

role: shell = Delphi(FP_DelphiPlug) の x64 殻 (固有閉包を lift)
      cpp   = MSVC C++ の x64 DLL (engine 分離型の engine / 単体型の本体。全 .pdata 関数を lift)
      x86   = x64 の .pdata を持たない PE (RetDec+pass 鎖の対象外。外形のみ記録)
usage: targets.py shell|cpp|x86|all|names   → stdout: block 番号の空白区切り (all は "role:block:name" の行)
       targets.py --check                   → 14 本が揃い、役割に分類できることを検査 (不合格 exit 1)
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = ['Autogun', 'BooBass', 'FL Slayer', 'Harmless', 'Kepler', 'Kepler Exo', 'Morphine', 'Ogun',
         'PoiZone', 'Sakura', 'Sawer', 'Toxic Biohazard', 'Transistor Bass', 'Wave Traveller']


def load():
    M = {p['name']: p for p in json.load(open(os.path.join(HERE, '..', 'PLUGIN_MATRIX.json')))['plugins']
         if p['kind'] == 'Generators'}
    out = []
    for n in NAMES:
        p = M[n]
        mods = p['win']['modules']
        has_shell = any(m['lang'].startswith('Delphi') for m in mods)
        for m in mods:
            if m['lang'].startswith('Delphi') and m['machine'] == 'x64':
                role = 'shell'
            elif m['lang'].startswith('MSVC C++') and m['machine'] == 'x64':
                role = 'cpp'
            else:
                role = 'x86' if m['machine'] != 'x64' else 'other'
            out.append({'name': n, 'tier': p['tier'], 'block': m['block'], 'file': m['file'], 'role': role,
                        'kind': ('engine' if has_shell else 'single') if role == 'cpp' else role,
                        'pdata_funcs': m['pdata_funcs'], 'lang': m['lang'], 'machine': m['machine'],
                        'lift': p['lift'] if role == 'shell' else None})
    return out


if __name__ == '__main__':
    T = load()
    a = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if a == '--check':
        names = {t['name'] for t in T}
        other = [t for t in T if t['role'] == 'other']
        cnt = {r: sum(1 for t in T if t['role'] == r) for r in ('shell', 'cpp', 'x86', 'other')}
        print('targets: %d plugins, %d modules: %s' % (len(names), len(T), cnt))
        sys.exit(0 if len(names) == 14 and not other and cnt['shell'] and cnt['cpp'] else 1)
    elif a == 'all':
        for t in T:
            print('%s:%d:%s' % (t['role'], t['block'], t['name']))
    elif a == 'names':
        print('\n'.join(NAMES))
    else:
        print(' '.join(str(t['block']) for t in T if t['role'] == a))
