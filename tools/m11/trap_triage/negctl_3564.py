#!/usr/bin/env python3
"""#3564 ネガティブコントロール: count 源 (G・オフセット・幅・段数) の照合器を 1 項目ずつ壊して確かめる。

使い方: python3 negctl_3564.py <block00031_PE.bin>
機械語側は PE から直接逆アセンブルして抽出する (ldmach は使わない)。照合の相手 (IR 側) は
REPORT_APPENDIX_3564.md §3 の記録値。work-m11 の boot_final.ll は使わない。
出力: 件ごとに抽出値・記録値との照合結果・1 項目ずつ壊した 4 通りの照合結果。
"""
import re
import sys

import capstone
import pefile

RIP = capstone.x86.X86_REG_RIP
IMAGE_BASE = 0x400000
MEM = capstone.x86.X86_OP_MEM
REG = capstone.x86.X86_OP_REG

# 記録値 (REPORT_APPENDIX_3564.md §3 の IR 側): kind, 値 (G または call 先), 参照オフセット, 幅, 段数
EXPECT = {
    51: ('G', 0x12bd510, 0x10, 32, 2),
    56: ('G', 0x153fc08, 0x14, 32, 2),
    64: ('call', 0x12f9ed0, None, 32, 1),
    41: ('G', 0x11e2218, 0x10, 32, 2),
}
ROWS = {
    51: ('function_12b52e0', 0x12b52fa),
    56: ('function_12ca540', 0x12ca5cd),
    64: ('function_12cb680', 0x12cb76b),
    41: ('function_127bc80', 0x127be05),
}
FIELDS = ('kind', 'val', 'off', 'width', 'stages')


def fam(name):
    m = re.fullmatch(r'r(\d+)d', name)
    if m:
        return 'r' + m.group(1)
    m = re.fullmatch(r'e([a-z]{2})', name)
    if m:
        return 'r' + m.group(1)
    return name


def writer(md, ins, i, r):
    for j in range(i - 1, -1, -1):
        if ins[j].mnemonic == 'call' and r == 'rax':
            return j
        for x in ins[j].regs_access()[1]:
            if fam(md.reg_name(x)) == r:
                return j
    return None


def origin(md, ins, i, r):
    """ins[i] が読む レジスタ r の出どころ (kind, 値, 段数) を返す。"""
    j = writer(md, ins, i, r)
    if j is None:
        return ('free', None, 0)
    x = ins[j]
    if x.mnemonic == 'call':
        return ('call', x.operands[0].imm, 1)
    if x.mnemonic == 'mov' and len(x.operands) == 2:
        src = x.operands[1]
        if src.type == MEM:
            m = src.mem
            if m.base == RIP:
                return ('G', x.address + x.size + m.disp - IMAGE_BASE, 1)
            if m.base:
                kind, val, depth = origin(md, ins, j, fam(md.reg_name(m.base)))
                return (kind, val, depth + 1)
        if src.type == REG:
            return origin(md, ins, j, fam(md.reg_name(src.reg)))
    return ('?', x.address, 0)


def count_src(md, ins, jcc):
    idx = next(k for k, x in enumerate(ins) if x.address == jcc)
    for i in range(idx - 1, -1, -1):
        x = ins[i]
        if x.mnemonic == 'mov' and len(x.operands) == 2 and x.operands[1].type == MEM:
            m = x.operands[1].mem
            if m.base and m.base != RIP and m.disp in (0x10, 0x14):
                kind, val, depth = origin(md, ins, i, fam(md.reg_name(m.base)))
                return dict(kind=kind, val=val, off=m.disp, width=32, stages=depth + 1)
    for i in range(idx - 1, -1, -1):
        x = ins[i]
        if x.mnemonic == 'mov' and len(x.operands) == 2 and x.operands[1].type == REG:
            kind, val, depth = origin(md, ins, i, fam(md.reg_name(x.operands[1].reg)))
            if kind == 'call':
                return dict(kind=kind, val=val, off=None, width=32, stages=depth)
    return None


def compare(got, exp):
    e = dict(zip(FIELDS, exp))
    return [f for f in FIELDS if got[f] != e[f]]


def main():
    pe = pefile.PE(sys.argv[1], fast_load=True)
    img = pe.get_memory_mapped_image()
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    for row, (fn, jcc) in ROWS.items():
        start = int(fn.split('_')[1], 16)
        code = img[start - base: jcc - base + 16]
        ins = [x for x in md.disasm(code, start) if x.address <= jcc]
        got = count_src(md, ins, jcc)
        exp = EXPECT[row]
        print('## 行 %d %s jcc %x' % (row, fn, jcc))
        for x in ins[-4:]:
            print('   %x: %s %s' % (x.address, x.mnemonic, x.op_str))
        if got is None:
            print('   抽出: 失敗 (count 読みが見つからない)')
            continue
        diff = compare(got, exp)
        print('   抽出: kind=%s val=0x%x off=%s width=%d stages=%d' % (
            got['kind'], got['val'], hex(got['off']) if got['off'] is not None else '-', got['width'], got['stages']))
        print('   記録: kind=%s val=0x%x off=%s width=%d stages=%d' % (
            exp[0], exp[1], hex(exp[2]) if exp[2] is not None else '-', exp[3], exp[4]))
        print('   照合: %s %s' % ('一致' if not diff else '不一致', diff if diff else ''))
        if diff:
            continue
        pert = [
            ('G/call 先 +8', dict(got, val=got['val'] + 8)),
            ('オフセット 0x10⇄0x14', dict(got, off=(0x14 if got['off'] == 0x10 else 0x10) if got['off'] is not None else None)),
            ('幅 32→16', dict(got, width=16)),
            ('段数 +1', dict(got, stages=got['stages'] + 1)),
        ]
        for name, g in pert:
            if g == got:
                print('   壊す (%s): 変化なし (対象外)' % name)
                continue
            d = compare(g, exp)
            print('   壊す (%s): %s %s' % (name, '不一致 (FAIL 期待どおり)' if d else '一致 (想定外)', d))


if __name__ == '__main__':
    main()
