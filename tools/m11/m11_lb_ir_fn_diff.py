#!/usr/bin/env python3
# M11 LB 依存差の IR 突合 (#3188): 2 本の boot_final.ll (LB=0 と LB=0x10000) で指定関数の本体を比べ、行ごとの差と
# 整数定数の変化量 (LB=0x10000 側 - LB=0 側) を出す。LB 由来の再配置 (VA→LVA) の定数は +0x10000 になる。
# それ以外の変化 (0 でも +0x10000 でもない) は再配置の漏れ・誤りの候補。
#   使い方: python3 tools/m11/m11_lb_ir_fn_diff.py <LB=0 の boot_final.ll> <LB=0x10000 の boot_final.ll> function_412e40 [...]
import re
import sys

CONST = re.compile(r'\bi(?:8|16|32|64)\s+(-?\d+)\b')


def body(path, name):
    lines = open(path, errors='replace').read().split('\n')
    start = None
    for k, ln in enumerate(lines):
        if ln.startswith('define ') and ('@%s(' % name) in ln:
            start = k
            break
    if start is None:
        return None
    out = []
    for ln in lines[start:]:
        out.append(ln)
        if ln == '}':
            break
    return out


def shifts(a, b):
    ca = [int(x) for x in CONST.findall(a)]
    cb = [int(x) for x in CONST.findall(b)]
    return [y - x for x, y in zip(ca, cb)] if len(ca) == len(cb) else None


def main():
    if len(sys.argv) < 4:
        print(__doc__.strip())
        return 2
    p0, p1 = sys.argv[1], sys.argv[2]
    for name in sys.argv[3:]:
        b0, b1 = body(p0, name), body(p1, name)
        if b0 is None or b1 is None:
            print('%s: 定義が無い (LB=0: %s, LB=0x10000: %s)' % (name, b0 is not None, b1 is not None))
            continue
        print('%s: lines LB=0=%d LB=0x10000=%d' % (name, len(b0), len(b1)))
        if len(b0) != len(b1):
            print('  行数が違う (構造が変わっている)')
        import difflib
        sm = difflib.SequenceMatcher(a=b0, b=b1, autojunk=False)
        n = 0
        for tag, i0, i1, j0, j1 in sm.get_opcodes():
            if tag == 'equal':
                continue
            for x, y in zip(b0[i0:i1], b1[j0:j1]):
                n += 1
                sh = shifts(x, y)
                tail = ' 定数変化量=%s' % sh if sh is not None else ''
                print('  L0: %s' % x.strip()[:200])
                print('  L1: %s%s' % (y.strip()[:200], tail))
            if (i1 - i0) != (j1 - j0):
                print('  [%s] LB=0 %d 行 / LB=0x10000 %d 行' % (tag, i1 - i0, j1 - j0))
        print('  差分行 %d' % n)
    return 0


if __name__ == '__main__':
    sys.exit(main())
