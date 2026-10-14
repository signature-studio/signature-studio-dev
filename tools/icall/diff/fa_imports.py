#!/usr/bin/env python3
"""fa_imports.py — SlateCore の IAT のうち ott_native.c の IMPL 表に無い import (= 実行時に missing_import で即 exit(99)) を列挙する。
用法: python3 tools/icall/diff/fa_imports.py [--md]   (--md で REPORT 貼り付け用の表を出す)
入力: $FA_CORE (既定 targets/freshair/work/win/.../SlateCore.core_64)。出力は DLL ごとの件数と未実装 import 名。"""
import os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
T = os.path.abspath(os.path.join(HERE, '..', '..'))
FA = os.environ.get('FA_CORE', os.path.join(T, 'targets', 'freshair', 'work', 'win', 'Fresh Air',
                                            'C__ProgramData_Slate Digital', 'Fresh Air', 'SlateCore.core_64'))


def imports(f):
    pe = struct.unpack_from('<I', f, 0x3c)[0]
    osz = struct.unpack_from('<H', f, pe + 20)[0]
    so = pe + 24 + osz
    secs = []
    for i in range(struct.unpack_from('<H', f, pe + 6)[0]):
        vs, va, rs, rp = struct.unpack_from('<IIII', f, so + i * 40 + 8)
        secs.append((va, max(vs, rs), rp))

    def off(r):
        for va, sz, rp in secs:
            if va <= r < va + sz:
                return r - va + rp
        raise ValueError(hex(r))

    out = []
    o = off(struct.unpack_from('<I', f, pe + 24 + 112 + 8)[0])
    while True:
        oft, _, _, nm, ft = struct.unpack_from('<IIIII', f, o)
        if nm == 0:
            break
        dll = f[off(nm):f.index(b'\0', off(nm))].decode()
        t = off(oft or ft)
        while True:
            v = struct.unpack_from('<Q', f, t)[0]
            if v == 0:
                break
            if not v >> 63:
                out.append((dll, f[off(v & 0x7fffffff) + 2:].split(b'\0')[0].decode()))
            t += 8
        o += 20
    return out


def main():
    f = open(FA, 'rb').read()
    src = open(os.path.join(HERE, '..', '..', 'ott', 'native', 'ott_native.c')).read()
    impl = set(re.findall(r'\{"([A-Za-z_0-9]+)", k_', src))
    imps = imports(f)
    miss = [(d, n) for d, n in imps if n not in impl]
    print('total %d implemented %d fail-fast %d' % (len(imps), len(imps) - len(miss), len(miss)))
    per = {}
    for d, _ in miss:
        per[d] = per.get(d, 0) + 1
    for d in sorted(per):
        print('%-14s %d' % (d, per[d]))
    if '--md' in sys.argv:
        print()
        print('| DLL | 未実装 import |')
        print('|---|---|')
        for d in sorted(per):
            print('| %s | %s |' % (d, ', '.join(n for dd, n in miss if dd == d)))
    else:
        for d, n in miss:
            print(d, n)


if __name__ == '__main__':
    main()
