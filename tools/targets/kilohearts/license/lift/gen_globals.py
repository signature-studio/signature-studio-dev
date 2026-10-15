#!/usr/bin/env python3
"""gen_globals.py — lift IR が extern 宣言した `@global_var_<VA>` (DLL .rdata/.data 実体) を C 定義として PE 実データから生成する。
(PoC では手転記していた abs mask 等の自動化。RetDec は VA 名の extern とだけ宣言し中身を持たない。)
usage: gen_globals.py IN.ll HeartCore.core_64 OUT.c [--window N] [--report OUT.json]
  --window N: `external global i8` を N バイト窓 (kh_lower の rdata 窓) として埋める
型 (iN / float / double / [N x iK]) から必要サイズを決め、PE の対応 RVA の実バイトをそのまま埋める。"""
import json
import re
import struct
import sys
import pefile

G = re.compile(r'^@global_var_([0-9a-f]+) = external (?:local_unnamed_addr )?(?:unnamed_addr )?(constant|global) (.+?)(?:, align \d+)?$')


def size_of(ty):
    ty = ty.strip()
    m = re.match(r'^i(\d+)$', ty)
    if m:
        return max(1, int(m.group(1)) // 8)
    if ty == 'float':
        return 4
    if ty == 'double':
        return 8
    m = re.match(r'^\[(\d+) x (.+)\]$', ty)
    if m:
        return int(m.group(1)) * size_of(m.group(2))
    return None


def main():
    src, core, dst = sys.argv[1:4]
    window = int(sys.argv[sys.argv.index('--window') + 1]) if '--window' in sys.argv else 0
    pe = pefile.PE(core, fast_load=True)
    data = open(core, 'rb').read()
    base = pe.OPTIONAL_HEADER.ImageBase

    def rd(va, n):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                o = s.PointerToRawData + rva - s.VirtualAddress
                avail = max(0, min(n, s.PointerToRawData + s.SizeOfRawData - o))
                return data[o:o + avail] + b'\0' * (n - avail)
        if rva < pe.OPTIONAL_HEADER.SizeOfHeaders:
            return data[rva:rva + n] + b'\0' * max(0, n - (len(data) - rva))
        raise ValueError(hex(va))

    out = ['/* 自動生成 (gen_globals.py): DLL 実データ */', '#include <stdint.h>']
    rep = []
    for line in open(src):
        m = G.match(line.strip())
        if not m:
            continue
        va = int(m.group(1), 16)
        n = size_of(m.group(3))
        if window and n is not None:
            n = max(n, window)
        if n is None:
            rep.append('unsupported type %s @%x' % (m.group(3), va))
            continue
        b = rd(va, n)
        al = 16 if n >= 16 else (8 if n >= 8 else 4)
        out.append('const unsigned char global_var_%x[%d] __attribute__((aligned(%d), used)) = {%s};' % (va, n, al, ','.join(str(x) for x in b)))
        rep.append('%x %s %dB' % (va, m.group(3), n))
    open(dst, 'w').write('\n'.join(out) + '\n')
    if '--report' in sys.argv:
        json.dump(rep, open(sys.argv[sys.argv.index('--report') + 1], 'w'), indent=1)
    print('[gen_globals] %d globals' % len([r for r in rep if not r.startswith('unsupported')]), [r for r in rep if r.startswith('unsupported')])


if __name__ == '__main__':
    main()
