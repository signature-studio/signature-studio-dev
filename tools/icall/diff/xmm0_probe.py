#!/usr/bin/env python3
"""xmm0_probe.py FN_VA[,FN_VA...] [--n N] [--seed S]
ICALL-79 (#2674): fa_cmp.py と同じ入力 (seed 規約・heap 4 本) で native と wasm の xmm0 の値を並べて出す。
加えて heap probe: native の rdx 引数の heap ブロック [rdx+0x20] にパターンを書き、出力が変わるかを見る
(xmm0 がメモリ由来かの負の対照)。"""
import sys, os, random, ctypes
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', '..', 'ott', 'native'))
import fa_cmp as F
import ottnat as N


def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def main():
    vas = [int(v, 16) for v in sys.argv[1].split(',')]
    n = arg('--n', 8); seed = arg('--seed', 3)
    random.seed(seed)
    xs = [random.uniform(-4.0, 4.0) for _ in range(n)]
    N.load(F.FA)
    w = F.wasm_run([hex(v) for v in vas], xs)
    for va in vas:
        nat = []
        for x in xs:
            gpr = tuple(N.alloc(0x400) for _ in range(4))
            _, x0 = N.call(va, gpr=gpr, xmm=(N.f64b(x),))
            nat.append('%016x' % x0)
        print(hex(va), 'native', ' '.join(nat[:4]))
        print(hex(va), 'wasm  ', ' '.join(w.get(hex(va), [])[:4]))
        gpr = tuple(N.alloc(0x400) for _ in range(4))
        ctypes.memmove(gpr[1] + 0x20, (ctypes.c_uint64 * 2)(0x4142434445464748, 0x5152535455565758), 16)
        _, x0 = N.call(va, gpr=gpr, xmm=(N.f64b(xs[0]),))
        print(hex(va), 'native heap probe ([rdx+0x20] := pattern) xmm0 =', '%016x' % x0)


if __name__ == '__main__':
    main()
