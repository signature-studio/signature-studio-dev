#!/usr/bin/env python3
"""fa_nat.py FN_VA [--n N] [--seed S] [--path SlateCore.core_64] : Fresh Air SlateCore の関数を native 実機械語で実行し xmm0 raw 64bit を出す。
ottnat (OTT 用ローダ) を DLL パス指定で流用する。入力 = xmm0 に乱数 double、rcx..r9 = 0 (fn3_diff.py の gen_inputs と同形)。
既定 DLL: $FA_CORE、無ければ tools/targets/freshair/work/win/Fresh Air/.../SlateCore.core_64 (fetch.sh で展開)。"""
import sys, os, json, struct, random
HERE = os.path.dirname(os.path.abspath(__file__))
T = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(T, 'ott', 'native'))
import ottnat as N

DEFAULT = os.path.join(T, 'targets', 'freshair', 'work', 'win', 'Fresh Air', 'C__ProgramData_Slate Digital', 'Fresh Air', 'SlateCore.core_64')


def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def main():
    fn = int(sys.argv[1], 16)
    n = arg('--n', 8); seed = arg('--seed', 3)
    path = arg('--path', os.environ.get('FA_CORE', DEFAULT))
    N.load(path)
    random.seed(seed)
    out = []
    for _ in range(n):
        x = random.uniform(-4.0, 4.0)
        gpr = tuple(N.alloc(0x400) for _ in range(4))
        rax, xmm0 = N.call(fn, gpr=gpr, xmm=(N.f64b(x),))
        out.append({'x': x, 'rax': rax, 'xmm0': '%016x' % xmm0})
    print(json.dumps(out))


if __name__ == '__main__':
    main()
