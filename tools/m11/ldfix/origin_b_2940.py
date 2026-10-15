#!/usr/bin/env python3
"""origin_b_2940.py — #2940 (LD-141): spill 宛 TRUE_DROP の B 6 site (機械語の読み出し M > IR の K 読み出し I) の対応表。

site ごとに、機械語で X (= K + 0x400000) を rip 相対で読む命令 (M) と、IR の K 形式 (`inttoptr (i64 K to ptr)`) と
X 形式 (`inttoptr (i64 X to ptr)`) の行 (IR の絶対行番号) を並べる。
gap = M − (K 形式 + X 形式) > 0 は「IR に対応する読み出しが見えない」ことを示す。0 でも CSE で 1 本が 2 つの機械語の読みを兼ねることがあるため、
読みの対応 (どの機械語が どの IR 行か) は REPORT_2940.md の表で人が判定する。
K 形式だけを数える audit (I 計数) は X 形式を数えない (REPORT_2940 §2)。

使い方: M11_WORK=<tools/m11/work 相当の dir> python3 origin_b_2940.py
既定の site は REPORT_2940 §1 の 6 site。依存: capstone (ldmach_img.py が import する)。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach_img import ImageMachine  # noqa: E402
from capstone.x86 import X86_REG_RIP  # noqa: E402
import capstone  # noqa: E402

IMG_BASE = 0x400000
SITES = [  # (fn, store site, K)
    ('1003c20', '1003c73', '11e2218'),
    ('1046a30', '104c3f0', '11e36d8'),
    ('11f16b0', '11f1785', '11e14a8'),
    ('128c320', '128ca3f', '11e42e0'),
    ('12a4450', '12a4531', '11e26a0'),
    ('ff8b60', 'ff8c63', '11e0c60'),
]
DEF_RE = re.compile(r'^define [^@]*@function_([0-9a-f]+)\(([^)]*)\)[^{]*\{', re.M)


def rip_target(i):
    for op in i.operands:
        if op.type == capstone.CS_OP_MEM and op.mem.base == X86_REG_RIP:
            return i.address + i.size + op.mem.disp
    return None


def ir_range(text, fn):
    for m in DEF_RE.finditer(text):
        if m.group(1) == fn:
            return m.start(), text.index('\n}', m.end()) + 2
    return None


def main():
    w = os.environ.get('M11_WORK') or os.path.join(HERE, '..', 'work')
    text = open(os.path.join(w, 'boot_final3.ll')).read()
    m = ImageMachine(os.path.join(w, 'm11_image.bin'), os.path.join(w, 'boot*.drc.config.json'))
    for fn, store, k in SITES:
        K = int(k, 16)
        X = K + IMG_BASE
        ins = m.disasm_fn(int(fn, 16)) or []
        reads = [i for i in ins if rip_target(i) == X]
        rng = ir_range(text, fn)
        s, e = rng
        base_line = text.count('\n', 0, s) + 1
        body = text[s:e]
        kf = [(base_line + body.count('\n', 0, mm.start()), body.splitlines()[body.count('\n', 0, mm.start())].strip())
              for mm in re.finditer(r'inttoptr \(?i64 %d\b' % K, body)]
        xf = [(base_line + body.count('\n', 0, mm.start()), body.splitlines()[body.count('\n', 0, mm.start())].strip())
              for mm in re.finditer(r'inttoptr \(?i64 %d\b' % X, body)]
        print('== %s store=%s K=%s X=%#x  M=%d  K-form=%d  X-form=%d  gap=%d  IR fn lines %d-%d' % (
            fn, store, k, X, len(reads), len(kf), len(xf), len(reads) - len(kf) - len(xf), base_line, base_line + body.count('\n')))
        for i in reads:
            print('  M %x  %-6s %s' % (i.address, i.mnemonic, i.op_str))
        for ln, t in kf:
            print('  I(K) %d  %s' % (ln, t[:110]))
        for ln, t in xf:
            print('  I(X) %d  %s' % (ln, t[:110]))


if __name__ == '__main__':
    main()
