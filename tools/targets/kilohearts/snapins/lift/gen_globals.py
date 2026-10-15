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
    wmap = {}
    if '--window-map' in sys.argv:
        wmap = json.load(open(sys.argv[sys.argv.index('--window-map') + 1]))
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
    # ---- D16 検出器: --window-map 経路で map 非該当の VA が IR 型サイズ (>8B) のまま載る件数。
    #      旧実装では `max(n, window)` の window が 0 (per-VA map 経路) で falsy になり、
    #      非該当 VA の窓が 1B/2B に縮んで定数読みが壊れた (DEFECTS.md D16 / KH-6 phaser/limiter 実測)。
    #      修復後は 64B 床が効くが、「map に載らず かつ IR が 8B 超を要求する VA」は
    #      64B でも足りない可能性がある = 静的に数えて可視化する (規則 36: 単位と併記)。
    d16 = []
    for line in open(src):
        m = G.match(line.strip())
        if not m:
            continue
        va = int(m.group(1), 16)
        raw = size_of(m.group(3))
        if raw is not None and wmap and '%x' % va not in wmap and raw > 8:
            d16.append('%x %s raw=%dB' % (va, m.group(3), raw))
    for line in open(src):
        m = G.match(line.strip())
        if not m:
            continue
        va = int(m.group(1), 16)
        n = size_of(m.group(3))
        if n is not None:
            # 窓幅: IR 型サイズ (直接 load) と [rdataest] 推定 (base+可変 index) の最大値
            # 既定窓 64B: map 非該当の静的参照 (定数プール 1 個読み) も従来どおり 64B を保証する
            # (--window-map 経路で window=0 の時, 非該当が 1B に縮んで定数読みが壊れた [KH-6 実測])
            n = max(n, window or 64, int(wmap.get('%x' % va, 0)))
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
    if d16:
        print('[gen_globals] D16 detector: map-uncovered VA with IR type > 8B = %d %s' % (len(d16), d16[:6]))


if __name__ == '__main__':
    main()
