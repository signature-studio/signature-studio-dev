#!/usr/bin/env python3
"""静的走査: Reverb.dll の全 .text で、`this+0xbc+8i` (i=0..13) の 14 本の遅延線ポインタに当たる書き込み命令を列挙する (依存: capstone・標準ライブラリ)。
usage: scan_writes.py <image.bin (locate.py の出力)>
出力: 候補 (base+disp が 0xbc..0x124 の 8 刻み位置・qword 書き込み) の件数と、その命令。
判定の読み: qword の候補が 0 件なら、14 本は直接の qword 命令では埋められていない (別経路・別オブジェクト経由を疑う)。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locate
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_MEM
from capstone.x86 import X86_REG_INVALID

PTR_OFFS = {0xbc + 8 * i for i in range(14)}
NON_DST = ('cmp', 'test', 'push', 'call', 'jmp', 'bt')


def main():
    img, _, _, _, _ = locate.parse(sys.argv[1])
    pe = int.from_bytes(img[0x3c:0x40], 'little')
    nsec = int.from_bytes(img[pe + 6:pe + 8], 'little')
    optsz = int.from_bytes(img[pe + 20:pe + 22], 'little')
    so = pe + 24 + optsz
    text_va = text_sz = None
    for i in range(nsec):
        o = so + 40 * i
        name = img[o:o + 8].rstrip(b'\0').decode()
        vs = int.from_bytes(img[o + 8:o + 12], 'little')
        va = int.from_bytes(img[o + 12:o + 16], 'little')
        if name == '.text':
            text_va, text_sz = va, vs
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    qword_hits, other_hits, n_ins = [], [], 0
    for ins in md.disasm(bytes(img[text_va:text_va + text_sz]), text_va):
        n_ins += 1
        if ins.mnemonic in NON_DST or not ins.operands:
            continue
        op = ins.operands[0]
        if op.type != CS_OP_MEM or op.mem.base == X86_REG_INVALID or op.mem.index != X86_REG_INVALID:
            continue
        if op.mem.disp not in PTR_OFFS:
            continue
        row = (ins.address, ins.mnemonic, ins.op_str, op.size)
        (qword_hits if op.size == 8 else other_hits).append(row)
    print('TEXT_RVA=%#x TEXT_SIZE=%#x INSNS=%d' % (text_va, text_sz, n_ins))
    print('PTR_QWORD_WRITES=%d' % len(qword_hits))
    for a, m, s, _ in qword_hits:
        print('  QW %#x %s %s' % (a, m, s))
    print('PTR_OTHER_SIZE_WRITES=%d' % len(other_hits))
    for a, m, s, _ in other_hits:
        print('  SZ %#x %s %s' % (a, m, s))


if __name__ == '__main__':
    main()
