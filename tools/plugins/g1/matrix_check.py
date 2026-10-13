#!/usr/bin/env python3
"""再計算した閉包 (work/g1/facts.json) が PLUGIN_MATRIX.json の `lift` 欄と一致するか + 対象 14 本の block が matrix の win.modules と一致するか
+ matrix に `lift.batch` 欄がある plugin は status12.csv の lift_rc / emcc_c_rc / f80_funcs / declares_unimpl とも一致するか。
  python3 matrix_check.py [facts.json [status12.csv]]     (既定 work/g1/facts.json, work/g1/status12.csv)
不一致 / facts に対象 plugin が欠けている / 想定外の plugin がある → exit 1 (空の facts を合格にしない)。
matrix が `lift` 欄を持たない plugin は NOT_IN_MATRIX に明示した ones のみ許す (SimSynth: matrix は先頭 module = C++ engine で closure を作らなかった)。 それ以外で欠けたら不一致。
"""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import PLUGINS
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
M = {p['name']: p for p in json.load(open(os.path.join(P, 'PLUGIN_MATRIX.json')))['plugins'] if p['kind'] == 'Generators'}
F = json.load(open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(P, 'work', 'g1', 'facts.json')))
NOT_IN_MATRIX = {'SimSynth'}
keys = [('closure_funcs', 'closure_funcs'), ('closure_bytes', 'closure_bytes'), ('fw_frontier_funcs', 'frontier_funcs'),
        ('fw_frontier_bytes', 'frontier_bytes'), ('vcalls', 'vcall'), ('ptr_calls', 'ptr_or_vt0')]
bad = n = 0
want = {name for name, shell, _ in PLUGINS if shell is not None}
n += 1
if set(F) != want:
    bad += 1
    print('MISMATCH facts の plugin 集合: 余剰 %s / 欠落 %s' % (sorted(set(F) - want), sorted(want - set(F))))
# 対象の block 割当が matrix の win.modules に存在するか (shell = abi を持つ Delphi 殻、engine = それ以外の C++ DLL)
for name, shell, eng in PLUGINS:
    mods = {m['block']: m for m in M[name]['win']['modules']}
    n += 3
    if shell is not None and (shell not in mods or not mods[shell]['lang'].startswith('Delphi')):
        bad += 1
        print('MISMATCH block', name, 'shell', shell)
    if eng is not None and (eng not in mods or not mods[eng]['lang'].startswith('MSVC')):
        bad += 1
        print('MISMATCH block', name, 'engine', eng)
    if set(mods) != {b for b in (shell, eng) if b is not None}:
        bad += 1
        print('MISMATCH matrix の module 集合', name, sorted(mods), 'vs', (shell, eng))
S = {}
spath = sys.argv[2] if len(sys.argv) > 2 else os.path.join(P, 'work', 'g1', 'status12.csv')
for r in csv.DictReader(open(spath, newline='')):
    S[int(r['block'])] = r
n += 1
if not S:
    bad += 1
    print('MISMATCH status12.csv が空 / 不在:', spath)
for name, f in F.items():
    if name in NOT_IN_MATRIX and not M[name].get('lift'):
        print('NOTE matrix に lift 欄なし (想定済み・比較対象外):', name)
        continue
    if name not in M or not M[name].get('lift'):
        n += 1
        bad += 1
        print('MISMATCH matrix に lift 欄なし', name)
        continue
    bt = M[name]['lift'].get('batch')
    if bt:
        r = S.get(f['block'])
        for mk, sk in (('lift_rc', 'lift_rc'), ('emcc_c_rc', 'emcc_c_rc'), ('f80_funcs', 'f80_funcs'), ('unimpl_helpers', 'declares_unimpl')):
            n += 1
            if r is None or int(r[sk]) != bt[mk]:
                bad += 1
                print('MISMATCH batch', name, mk, bt[mk], None if r is None else r[sk])
    for mk, fk in keys:
        n += 1
        if M[name]['lift'][mk] != f[fk]:
            bad += 1
            print('MISMATCH', name, mk, M[name]['lift'][mk], f[fk])
print('matrix_check: %d/%d 項目一致 (%d plugin)' % (n - bad, n, len(F)))
sys.exit(1 if bad else 0)
