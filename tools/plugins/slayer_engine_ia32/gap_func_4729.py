#!/usr/bin/env python3
"""gap_func_4729.py: (c) 中身ありの未被覆区間を、関数らしさ (F) とデータらしさ (D) の根拠で並べる (#4729 / 親 #3546 / 祖先 #2814)。

  python3 gap_func_4729.py <block22434_PE.bin> <分類表.md> --md

分類表は gap_classify.py --md の出力 (`| n | 0xVA | B | c | ... |`)。 gap_indirect.py と同じ区間の読み方をする。
根拠 (区間ごと):
  P  先頭 4 B が関数の prologue (push ebp; mov ebp,esp / push reg / sub esp / mov reg,[esp+d])。
  C  .text 内の直接 call/jmp rel32 が区間の先頭 VA を指す数 (呼ばれている = 関数の強い根拠)。
  X  線形 decode が区間の終わりまで命令境界で一致し、命令が不正 (decode 失敗) で止まらない。
  E  区間の最後の命令が ret / jmp / ud2 で終わる (関数の末尾の形)。
  Z  0x00 の割合 (data 側の根拠)。
  N  線形 decode の不正バイト数 (decode 失敗で飛ばした回数)。
判定 (機械的・根拠の並べ替えのみ):
  func : (P or C>0) and N==0 and E
  data : (Z>=50% もしくは N/B>=25%) かつ 直接 call/jmp/jcc を含まない
  hold : それ以外 (根拠不足・c のまま)
"""
import re, struct, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
from capstone.x86 import X86_OP_IMM

PAD = {0x90, 0xCC, 0x00}
PRO = (b'\x55\x8b\xec', b'\x53', b'\x56', b'\x57', b'\x83\xec', b'\x81\xec', b'\x8b\x44\x24', b'\x8b\x4c\x24', b'\x8b\x54\x24')


def gap_rows(md_path):
    rows = []
    for line in open(md_path, encoding='utf-8'):
        m = re.match(r'\| (\d+) \| 0x([0-9a-f]+) \| (\d+) \| (\w) \| (.*?) \|', line)
        if m and m.group(4) == 'c' and not m.group(5).startswith('padding'):
            rows.append(dict(no=int(m.group(1)), va=int(m.group(2), 16), size=int(m.group(3))))
    return rows


def main():
    import pefile
    pe_path, md_path = sys.argv[1], sys.argv[2]
    pe = pefile.PE(pe_path)
    IMG = pe.OPTIONAL_HEADER.ImageBase
    text = pe.sections[0]
    T0 = IMG + text.VirtualAddress
    TS = text.Misc_VirtualSize
    img = pe.get_memory_mapped_image()
    code = img[text.VirtualAddress:text.VirtualAddress + TS]
    md = Cs(CS_ARCH_X86, CS_MODE_32); md.detail = True

    regs = gap_rows(md_path)
    starts = {r['va']: r for r in regs}
    for r in regs:
        r['C'] = []
    # C: 直接 call/jmp rel32 の先頭
    for ins in md.disasm(code, T0):
        if ins.mnemonic in ('call', 'jmp') and ins.operands and ins.operands[0].type == X86_OP_IMM:
            t = ins.operands[0].imm & 0xffffffff
            if t in starts:
                starts[t]['C'].append('0x%x' % ins.address)

    for r in regs:
        off = r['va'] - IMG
        bs = bytes(img[off:off + r['size']])
        head = bs[:4]
        r['P'] = any(head.startswith(p) for p in PRO)
        r['Z'] = sum(1 for b in bs if b == 0) * 100 // r['size']
        # 線形 decode: 命令境界が区間末まで一致したか、不正で止まったか
        pos, n, bad, last, flow = 0, 0, 0, '', False
        while pos < len(bs):
            ins = next(md.disasm(bs[pos:pos + 16], r['va'] + pos, 1), None)
            if ins is None:
                bad += 1; pos += 1; continue
            n += 1; pos += ins.size; last = ins.mnemonic
            flow = flow or ins.mnemonic in ('call', 'jmp') or ins.mnemonic.startswith('j')
        r['has_flow'] = flow
        r['n'], r['N'], r['last'] = n, bad, last
        r['X'] = bad == 0
        r['E'] = last in ('ret', 'jmp', 'ud2', 'retf')
        if (r['P'] or r['C']) and r['N'] == 0 and r['E']:
            r['J'] = 'func'
        elif (r['Z'] >= 50 or r['N'] * 4 >= r['size']) and not r['has_flow']:
            r['J'] = 'data'
        else:
            r['J'] = 'hold'

    print('| # | VA | B | 判定 | P prologue | C 直接 call/jmp 先頭 | X 境界一致 | E 末尾 | Z 0x00 % | N 不正 | 線形命令数 | 最後 | 先頭 4 B | C 参照元 |')
    print('|---:|---|---:|---|---|---:|---|---|---:|---:|---:|---|---|---|')
    for r in regs:
        head = bytes(img[r['va'] - IMG:r['va'] - IMG + 4]).hex(' ')
        print('| %d | 0x%x | %d | %s | %s | %d | %s | %s | %d | %d | %d | %s | `%s` | %s |' % (
            r['no'], r['va'], r['size'], r['J'], 'Y' if r['P'] else '-', len(r['C']), 'Y' if r['X'] else '-',
            'Y' if r['E'] else '-', r['Z'], r['N'], r['n'], r['last'], head, ', '.join(r['C'][:3]) or '-'))
    from collections import Counter
    c = Counter(r['J'] for r in regs)
    print('\n集計: ' + ' / '.join('%s %d' % (k, c[k]) for k in ('func', 'data', 'hold')) + ' (計 %d 区間)' % len(regs))


if __name__ == '__main__':
    main()
