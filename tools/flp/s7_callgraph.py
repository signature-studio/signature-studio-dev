#!/usr/bin/env python3
# #5718 (PY-5384): FLEngine_x64.dll の直接 call 関係を objdump -d から逆にたどる (上位呼出し元の列挙)。
# 使い方: python3 tools/flp/s7_callgraph.py <objdump -d 出力> <target VA hex>... [--depth N]
# 関数の先頭は「ret/int3/nop/jmp の直後の push %rbp」で近似する。関数ポインタ経由の呼出しは見ない (未確認と書く)。
import bisect
import re
import sys


def load(path):
    ins = []
    with open(path) as f:
        for ln in f:
            m = re.match(r'^\s*([0-9a-f]+):\t(.*)$', ln.rstrip('\n'))
            if m:
                ins.append((int(m.group(1), 16), m.group(2)))
    return ins


def function_starts(ins):
    starts = []
    for i, (a, t) in enumerate(ins):
        if t.startswith('push   %rbp') and i > 0 and re.match(r'(ret|int3|nop|jmp)', ins[i - 1][1]):
            starts.append(a)
    return sorted(starts)


def main(argv):
    depth = 3
    if '--depth' in argv:
        k = argv.index('--depth')
        depth = int(argv[k + 1])
        argv = argv[:k] + argv[k + 2:]
    ins = load(argv[1])
    starts = function_starts(ins)
    calls = {}
    for a, t in ins:
        m = re.match(r'call +0x([0-9a-f]+)$', t)
        if m:
            calls.setdefault(int(m.group(1), 16), []).append(a)

    def func_of(a):
        i = bisect.bisect_right(starts, a) - 1
        return starts[i] if i >= 0 else None

    def climb(fn, d, seen):
        if d == 0 or fn is None:
            return
        for c in calls.get(fn, []):
            up = func_of(c)
            print('  ' * (depth - d + 1) + f'{fn:#x} <- call@{c:#x} in func {up:#x}' if up else f'{fn:#x} <- call@{c:#x}')
            if up is not None and up not in seen:
                climb(up, d - 1, seen | {up})

    for t in argv[2:]:
        fn = int(t, 16)
        print(f'== callers of {fn:#x} (depth {depth})')
        climb(fn, depth, {fn})


if __name__ == '__main__':
    main(sys.argv)
