#!/usr/bin/env python3
"""WIN-33 (#3556): 実カタログ供給後の止まり (範囲検査 rva 0x17bcd) の値 V の出所を、命令 trace から示す。

使い方:
  python3 win33_trace.py trace <step.cfi>      # V の履歴・範囲検査の各入口 (win33_catalog.sh が作る trace)
  python3 win33_trace.py dis <rva_lo> <rva_hi> # FLEngine の逆アセンブル (rva 16 進)。素材 FL_WIN64_DIR 必須

trace の各行は `rva rax rcx rdx rbx rsp rbp rsi rdi r8 r9` (16 進、実行前のレジスタ)。
`MEM` 行は LD_STEP_MEM で指定した 8B の変化 (writer_last_img_rva = その変化の直前に実行した image 命令の rva)。
"""
import os, sys

CHECK_ENTRY = 0x17b70   # 範囲検査 helper の入口 (r9 = V のアドレス)
CHECK_V = 0x17bb8       # 直前の `mov rax,[rax]` の後 (rax = V)


def trace(path):
    entries, vals, mems = [], [], []
    with open(path) as f:
        for ln, line in enumerate(f, 1):
            if line.startswith('MEM '):
                mems.append((ln, line.strip()))
                continue
            p = line.split()
            if len(p) != 11:
                continue
            rva = int(p[0], 16)
            if rva == CHECK_ENTRY:
                entries.append((ln, p[10]))
            elif rva == CHECK_V:
                vals.append((ln, int(p[1], 16), int(p[6], 16)))
    print('[win33] 範囲検査 helper 0x%x の入口 (trace 行, r9=V のアドレス): %d 回' % (CHECK_ENTRY, len(entries)))
    for ln, r9 in entries:
        print('  line %d r9=0x%s' % (ln, r9))
    print('[win33] 0x%x 直後の V (= [[rbp+0xc8]]):' % CHECK_V)
    for ln, v, rbp in vals:
        tag = 'negative -> RunError 201' if v >> 63 else 'ok'
        print('  line %d V=%#018x rbp=%#x %s' % (ln, v, rbp, tag))
    print('[win33] MEM (監視した 8B の変化):')
    for ln, s in mems:
        print('  line %d %s' % (ln, s))


def dis(lo, hi):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    import pefile
    pe = pefile.PE(os.path.join(os.environ['FL_WIN64_DIR'], 'extracted/block00031_PE.bin'), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = pe.get_data(lo, hi - lo)
    for ins in Cs(CS_ARCH_X86, CS_MODE_64).disasm(data, base + lo):
        print('%x: %s %s' % (ins.address - base, ins.mnemonic, ins.op_str))


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == 'trace':
        trace(sys.argv[2])
    elif len(sys.argv) >= 4 and sys.argv[1] == 'dis':
        dis(int(sys.argv[2], 16), int(sys.argv[3], 16))
    else:
        print(__doc__)
