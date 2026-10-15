#!/usr/bin/env python3
"""ld118_show.py — #2583 (LD-118) held 9 site の機械語の引用番地を stdout に出す (作業用・results/ へ出力しない)。

REPORT_2583.md §2 の機械語列 (store と消費者・前段の二段参照) の番地を、降下 (audit_lsf.descend) の命令で出す。
入力: work-m11 の m11_image.bin・boot*.drc.config.json・boot_final3.ll (tools/m11/work/ に展開)。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_lsf as A  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
W = os.path.join(REPO, 'tools/m11/work')
mach = A.ImageMachine(os.path.join(W, 'm11_image.bin'), os.path.join(W, 'boot*.drc.config.json'))
IR = open(os.path.join(W, 'boot_final3.ll'), errors='replace').read()

HELD = [
    ('775340', ['77545c', '775678']),
    ('775340', ['77593b', '7759bb', '7759f6', '775a29']),
    ('815050', ['815216', '81521d', '815220', '815227', '815231', '815238']),
    ('6c3700', ['6c3c78', '6c3c80']),
    ('6c3d20', ['6c44bd', '6c44c5']),
    ('6c5930', ['6c6042', '6c6125', '6c612d']),
    ('1042d20', ['1043e24', '1043e2b', '1043e2d', '1043e34']),
    ('f3e050', ['f3e0c2', 'f3e0d7', 'f3e0f7', 'f3e10b']),
    ('12f9730', ['12f9748', '12f9750', '12f9752', '12f975e', '12f9842']),
]


def ir_labels(fn):
    m = re.search(r'^define [^\n]*@function_%s(__lifted)?\(' % fn, IR, re.M)
    if not m:
        return []
    end = IR.index('\n}', m.end()) + 2
    body = IR[m.start():end]
    return [int(x, 16) for x in re.findall(r'^dec_label_pc_([0-9a-f]+)[:.]', body, re.M)]


for fn, cited in HELD:
    by_va = {i.address: i for i in (A.descend(mach, int(fn, 16), ir_labels(fn)) or [])}
    print('== %s' % fn)
    for a in cited:
        i = by_va.get(int(a, 16))
        print('  %s  %s' % (a, '%s %s' % (i.mnemonic, i.op_str) if i else 'NOT_IN_DESCENT'))
