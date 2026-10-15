#!/usr/bin/env python3
"""m11_setother_nonimm_cfg.py の判定規則の合成検査 (#3140 / M11-N172)。

命令列を capstone で組み、同じ Cfg の判定 (before → decide) を通す。実機の 1 行再現は REPORT_N172 §2-1。
使い方: python3 m11_setother_nonimm_cfg_check.py PE  (PE は fl-win64 の block00031_PE.bin でなくてもよい)
"""
import collections, importlib.util, os, sys, tempfile
import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
d = tempfile.mkdtemp()
for name, body in (('fixes.json', '[]'), ('nonimm_class_rows.json', '[]')):
    with open(os.path.join(d, name), 'w') as f:
        f.write(body)
sys.argv = [sys.argv[0], os.path.join(d, 'fixes.json'), '--pe', sys.argv[1]]
spec = importlib.util.spec_from_file_location('cfg', os.path.join(HERE, 'm11_setother_nonimm_cfg.py'))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True


class NoRw:
    def rw(self, x):
        return (set(), set())


def cfg(base, code):
    C = mod.Cfg.__new__(mod.Cfg)
    C.ins = list(md.disasm(code, base))
    C.addr = [x.address for x in C.ins]
    C.idx = {x.address: i for i, x in enumerate(C.ins)}
    C.indirect = False
    C.jsrc = collections.defaultdict(list)
    for i, x in enumerate(C.ins):
        if x.mnemonic.startswith('j') and x.operands and x.operands[0].type == capstone.CS_OP_IMM \
                and x.operands[0].imm in C.idx:
            C.jsrc[C.idx[x.operands[0].imm]].append(i)
    C.cf = NoRw()
    C.memo, C.busy, C.path, C.cut = {}, {}, [], 0
    return C


B = 0x1000
CASES = [
    ('A1 movzx dx,bl (16bit 宛先)', '31db' '660fb6d3' 'c3', 2, 'rdx'),
    ('A2 movsx dx,bl (16bit 宛先)', '31db' '660fbed3' 'c3', 2, 'rdx'),
    ('A3 movzx edx,bl (32bit 宛先)', '31db' '0fb6d3' 'c3', 2, 'rdx'),
    ('A4 movzx rdx,bl (64bit 宛先)', '31db' '480fb6d3' 'c3', 2, 'rdx'),
    ('B  循環・定義を含む (add ebx,1 が戻り辺の経路)', '31db' '89da' '83c301' '83fb02' '75f6' 'c3', 5, 'rdx'),
    ('C  循環・定義を含まない (mov ebx,5 が出口まで残る)', 'bb05000000' '89da' 'b901000000' '83f902' '75f4' 'c3', 5, 'rdx'),
    ('D  循環後に参照 (出口で ebx は常に 2)', '31db' '83c301' '83fb02' '75f8' '89da' 'c3', 5, 'rdx'),
]
for name, *parts, q, fam in CASES:
    C = cfg(B, bytes.fromhex(''.join(parts)))
    cls, why, val = mod.decide(C.before(q, fam))
    print('%-46s %s %s %s' % (name, cls, why, ('0x%x' % val) if val is not None else '-'))
