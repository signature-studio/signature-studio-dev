#!/usr/bin/env python3
"""ld98_dump.py — #2265 (LD-98) 後半 23 site の機械語後続読み出しを TSV に出す (作業用・results/ へ出力)。"""
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

SITES = [
    ('4fa3d0', '4fa681'), ('4fa3d0', '4fa7aa'), ('4fad10', '4faf0b'), ('4fb780', '4fb7d9'),
    ('5c00e0', '5c013f'), ('5c0270', '5c030d'), ('6c3700', '6c3a63'), ('6c3700', '6c3c78'),
    ('6c3d20', '6c44bd'), ('6c5930', '6c6125'), ('76e720', '76e74f'), ('775340', '77545c'),
    ('775340', '77593b'), ('815050', '815220'), ('c57a00', 'c57e24'), ('f3e050', 'f3e0c2'),
    ('f67400', 'f67560'), ('101d180', '101d2b4'), ('101d180', '101d423'), ('1042d20', '1043e2d'),
    ('1221290', '1221676'), ('127d420', '127d881'), ('12f9730', '12f9752'),
]


def ir_labels(fn):
    m = re.search(r'^define [^\n]*@function_%s(__lifted)?\(' % fn, IR, re.M)
    if not m:
        return [], False
    end = IR.index('\n}', m.end()) + 2
    body = IR[m.start():end]
    return [int(x, 16) for x in re.findall(r'^dec_label_pc_([0-9a-f]+)[:.]', body, re.M)], True


out = sys.stdout
out.write('fn\tsite\tstore_text\t後続読み出し件数\t後続書き込み件数\tlea件数\t先頭3件 (後続の同一 frame slot memop・全種別)\n')
for fn, site in SITES:
    labels, _ = ir_labels(fn)
    ins = A.descend(mach, int(fn, 16), labels)
    sva = int(site, 16)
    st = [i for i in (ins or []) if i.address == sva]
    if not st:
        out.write('%s\t%s\t-\t-\t-\t-\tNO_MACHINE_SITE\n' % (fn, site))
        continue
    st = st[0]
    text = '%s %s' % (st.mnemonic, st.op_str)
    m = re.search(r'\[(rbp|rsp) ?\+ ?(0x[0-9a-f]+|\d+)\]', st.op_str)
    if not m:
        out.write('%s\t%s\t%s\t-\t-\t-\tNO_FRAME_OPERAND\n' % (fn, site, text))
        continue
    base, disp = m.group(1), int(m.group(2), 0)
    pat = re.compile(r'\[%s ?\+ ?0x%x\]' % (base, disp))
    reads, writes, leas, hits = 0, 0, 0, []
    for i in ins:
        if i.address <= sva or not pat.search(i.op_str):
            continue
        hits.append('%x %s %s' % (i.address, i.mnemonic, i.op_str))
        dst = i.op_str.split(', ', 1)[0]
        if i.mnemonic == 'lea':
            leas += 1
        elif i.mnemonic == 'mov' and pat.search(dst):
            writes += 1
        elif pat.search(dst) and i.mnemonic not in ('cmp', 'test'):
            reads += 1
            writes += 1
        else:
            reads += 1
    out.write('%s\t%s\t%s\t%d\t%d\t%d\t%s\n' % (fn, site, text, reads, writes, leas, ' | '.join(hits[:3]) or '-'))
