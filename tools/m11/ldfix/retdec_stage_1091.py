#!/usr/bin/env python3
"""#1091 (LD-33): RetDec の LLVM パス段ごとに、関数内の 1 命令 (機械語アドレス) の値が変わる最初の段を出す。

使い方:
  RETDEC=<retdec-decompiler> PE=<block00031_PE.bin> python3 retdec_stage_1091.py <func_hex> <lo_hex> <hi_hex> <insn_hex> [--out DIR]
例 (41a670 の 41a6a0 = `mov rax,[rax]`):
  RETDEC=... PE=... python3 retdec_stage_1091.py 41a670 41a670 41a6f4 41a6a0
出力: 段ごとに、指定命令の `; 0x<insn>` 区間 (次の命令の直前まで) の IR が変わった段を列挙する。
"""
import os
import re
import subprocess
import sys
import tempfile


def main():
    func, lo, hi, insn = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    out = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else tempfile.mkdtemp(prefix='ld33_')
    os.makedirs(out, exist_ok=True)
    retdec = os.environ['RETDEC']
    pe = os.environ['PE']
    dump = os.path.join(out, 'dump.err')
    with open(dump, 'w') as ferr:
        subprocess.run(
            [retdec, pe, '-o', os.path.join(out, 'f.c'), '--select-ranges', f'0x{lo}-0x{hi}',
             '--select-decode-only', '--timeout', '200', '--print-after-all'],
            stdout=subprocess.DEVNULL, stderr=ferr, check=True, env=dict(os.environ, TMPDIR=out))
    txt = open(dump, encoding='utf-8', errors='replace').read()
    parts = re.split(r'^\*\*\* IR Dump After (.*?) \*\*\*$', txt, flags=re.M)
    pat = re.compile(rf'define [^\n]*@function_{func}\(.*?\n\}}', re.S)
    tag = f'; 0x{insn}'
    prev = None
    for i in range(1, len(parts), 2):
        k = i // 2
        m = pat.search(parts[i + 1])
        if not m:
            continue
        f = m.group(0)
        j = f.find(tag)
        if j < 0:
            continue
        e = f.find('; 0x', j + len(tag))
        seg = re.sub(r'%\d+', '%N', f[j:e if e > 0 else None])
        seg = re.sub(r'!\d+', '', seg)
        if seg != prev:
            print(f'stage {k:3d}  {parts[i]}')
            print('\n'.join('    ' + l for l in f[j:e if e > 0 else None].splitlines() if l.strip()))
            prev = seg


if __name__ == '__main__':
    main()
