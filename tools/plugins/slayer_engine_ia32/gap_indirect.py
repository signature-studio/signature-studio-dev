#!/usr/bin/env python3
"""gap_indirect.py: (c) 中身ありの未被覆区間に、間接参照 (表引き call/jmp・即値・reloc) があるかを調べる (#4729 / 親 #3546 / 祖先 #2814)。

  python3 gap_indirect.py <block22434_PE.bin> [GAP_CLASSES_2814.md] [--json out.json]

入力の区間は GAP_CLASSES_2814.md の表 (分類 c で padding でない行)。 VA は絶対値。
調べる参照:
  T  表引き間接 jmp/call: `ff /4` `ff /2` で memory operand の disp が絶対アドレス (イメージ内)。 表の先頭 32 要素を読み、
     要素 (dword) が区間を指すかを見る。 表が .text 内の jump table (jt) なら jt として別扱い。
  I  .text 内の命令の即値・disp が区間の先頭以外も含めて区間内を指す (mov/push/lea/memory operand)。
  R  .text 以外を含む全 section の reloc 値 (vtable・関数ポインタ表) が区間を指す。 reloc 位置の section を記録する。
  D  区間の先頭から線形に decode した命令数と終端 (ret/jmp/ud で止まるか)。 関数らしさの補助。
"""
import json, os, re, struct, sys
from collections import defaultdict

PAD = {0x90, 0xCC, 0x00}


def gap_rows(md_path):
    rows = []
    for line in open(md_path, encoding='utf-8'):
        m = re.match(r'\| (\d+) \| 0x([0-9a-f]+) \| (\d+) \| (\w) \| (.*?) \|', line)
        if m and m.group(4) == 'c' and not m.group(5).startswith('padding'):
            rows.append(dict(no=int(m.group(1)), va=int(m.group(2), 16), size=int(m.group(3)), why=m.group(5)))
    return rows


def main():
    import pefile
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    from capstone.x86 import X86_OP_IMM, X86_OP_MEM
    pe_path = sys.argv[1]
    md_path = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'GAP_CLASSES_2814.md')
    out_json = sys.argv[sys.argv.index('--json') + 1] if '--json' in sys.argv else None

    pe = pefile.PE(pe_path)
    IMG = pe.OPTIONAL_HEADER.ImageBase
    SIZE = pe.OPTIONAL_HEADER.SizeOfImage
    text = pe.sections[0]
    T0 = IMG + text.VirtualAddress
    TS = text.Misc_VirtualSize
    img = pe.get_memory_mapped_image()
    code = img[text.VirtualAddress:text.VirtualAddress + TS]
    md = Cs(CS_ARCH_X86, CS_MODE_32); md.detail = True

    regs = gap_rows(md_path)
    for r in regs:
        r['end'] = r['va'] + r['size']
        r['T'] = []; r['I'] = []; r['R'] = []

    def region_of(v):
        for r in regs:
            if r['va'] <= v < r['end']:
                return r
        return None

    # I・T: .text 全体の命令
    jt_ranges = []
    for ins in md.disasm(code, T0):
        for op in ins.operands:
            if op.type == X86_OP_IMM:
                r = region_of(op.imm & 0xffffffff)
                if r and ins.mnemonic not in ('call', 'jmp') and not ins.mnemonic.startswith('j'):
                    r['I'].append('0x%x %s' % (ins.address, ins.mnemonic))
            elif op.type == X86_OP_MEM:
                disp = op.mem.disp & 0xffffffff
                r = region_of(disp)
                if r:
                    r['I'].append('0x%x %s [disp]' % (ins.address, ins.mnemonic))
        if ins.mnemonic in ('call', 'jmp') and ins.operands and ins.operands[0].type == X86_OP_MEM:
            disp = ins.operands[0].mem.disp & 0xffffffff
            if IMG <= disp < IMG + SIZE:
                ent = []
                for k in range(32):
                    off = disp - IMG + 4 * k
                    if off + 4 > len(img):
                        break
                    v = struct.unpack_from('<I', img, off)[0]
                    if not (IMG <= v < IMG + SIZE):
                        break
                    ent.append(v)
                    rr = region_of(v)
                    if rr:
                        rr['T'].append('0x%x %s table 0x%x[%d]=0x%x' % (ins.address, ins.mnemonic, disp, k, v))
                if ent and not any(region_of(x) for x in ent) and T0 <= ent[0] < T0 + TS:
                    jt_ranges.append((ins.address, disp, len(ent)))

    # R: 全 section の reloc 値
    for b in pe.DIRECTORY_ENTRY_BASERELOC:
        for e in b.entries:
            if e.type != 3:
                continue
            v = struct.unpack_from('<I', img, e.rva)[0]
            rr = region_of(v)
            if rr:
                sec = next((s.Name.rstrip(b'\0').decode() for s in pe.sections
                            if s.VirtualAddress <= e.rva < s.VirtualAddress + max(s.Misc_VirtualSize, 1)), '?')
                rr['R'].append('0x%x(%s)' % (IMG + e.rva, sec))

    # D: 先頭からの線形 decode (ret の数と、最後の命令)
    for r in regs:
        bs = bytes(img[r['va'] - IMG:r['end'] - IMG])
        n, last, rets = 0, '', 0
        for ins in md.disasm(bs, r['va']):
            n += 1; last = ins.mnemonic
            rets += ins.mnemonic == 'ret'
        r['decode'] = dict(n=n, last=last, rets=rets, head=bs[:8].hex(' '))

    if '--md' in sys.argv:
        print('| # | VA | B | 間接 T | 即値・disp I | reloc R | 線形 decode 命令数 | ret | 先頭 8 B |')
        print('|---:|---|---:|---:|---:|---:|---:|---:|---|')
        for r in regs:
            print('| %d | 0x%x | %d | %d | %d | %d | %d | %d | `%s` |' % (r['no'], r['va'], r['size'], len(r['T']), len(r['I']),
                  len(r['R']), r['decode']['n'], r['decode']['rets'], r['decode']['head']))
        return

    print('[gap_indirect] 対象 (c) 中身あり %d 区間 / 表引き jmp/call %d 件 (jt 候補)' % (len(regs), len(jt_ranges)))
    hits = 0
    for r in regs:
        if r['T'] or r['I'] or r['R']:
            hits += 1
    print('[gap_indirect] 何らかの参照がある区間 %d / %d' % (hits, len(regs)))
    for r in regs:
        print('0x%x %3dB T=%d I=%d R=%d decode=%s head=%s' % (r['va'], r['size'], len(r['T']), len(r['I']), len(r['R']),
              r['decode']['n'], r['decode']['head']))
        for k in ('T', 'I', 'R'):
            for x in r[k][:4]:
                print('    %s %s' % (k, x))
    if out_json:
        json.dump(dict(regions=regs, indirect_tables=[dict(at='0x%x' % a, disp='0x%x' % d, n=n) for a, d, n in jt_ranges]),
                  open(out_json, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
