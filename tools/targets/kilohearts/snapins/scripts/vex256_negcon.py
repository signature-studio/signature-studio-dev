#!/usr/bin/env python3
"""vex256_census.py の filter のネガティブコントロール (素材不要)。

既知の VEX 符号化命令 7 件を合成バイト列で並べ、現行 filter (ymm を含む or mnemonic が v) と
旧 filter (ymm を含む or mnemonic が vf) が何件検出するかを出す。
usage: python3 snapins/scripts/vex256_negcon.py
"""
import capstone

CASES = [
    ('vblendps xmm', bytes.fromhex('c4e3710cc205')),
    ('vblendvps xmm', bytes.fromhex('c4e3714ac200')),
    ('vpermilps xmm', bytes.fromhex('c4e2790cc1')),
    ('vperm2f128 ymm', bytes.fromhex('c4e37d06c220')),
    ('vaddps ymm', bytes.fromhex('c5fc58c1')),
    ('vaddps xmm', bytes.fromhex('c5f858c1')),
    ('vfmadd231ps xmm', bytes.fromhex('c4e271b8c2')),
]


def old(i):
    return 'ymm' in i.op_str or i.mnemonic.startswith('vf')


def new(i):
    return 'ymm' in i.op_str or i.mnemonic.startswith('v')


md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
for name, b in CASES:
    ins = list(md.disasm(b, 0x1000))
    assert sum(i.size for i in ins) == len(b), name
    print('%-16s n=%d old=%d new=%d | %s' % (name, len(ins), sum(map(old, ins)), sum(map(new, ins)), ' '.join(i.mnemonic for i in ins)))
blob = b''.join(b for _, b in CASES)
ins = list(md.disasm(blob, 0x1000))
assert sum(i.size for i in ins) == len(blob)
print('blob n=%d old_detect=%d new_detect=%d' % (len(ins), sum(map(old, ins)), sum(map(new, ins))))
print('new only:', sorted({i.mnemonic for i in ins if new(i) and not old(i)}))
