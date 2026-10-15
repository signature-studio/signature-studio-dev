#!/usr/bin/env python3
"""dbg_lift.py — FLE-5: lift 生成 C に診断用トレースを埋め込んだ copy を作る。

chk variant の `fle_chk` が報告する `__LINE__` は **lift 生成 C の行番号** という
FLE-4 の知見を拡張し、任意の guest アドレスの C 行を `grep -n` で逆引きして
その直前に `fprintf` を挿入できるようにする。

使い方:
    python3 boot/dbg_lift.py --src work/boot/lift/fle_lifted.c \
        --out work/boot/dbgout/fle_lifted_dbg.c \
        --at 0x8157c1,0x6c7610  (待機対象の guest アドレス or 関数エントリ)
"""
import argparse
import re
import sys

FUNC_RE = re.compile(r'^void (f_([0-9a-f]+))\(void\) \{')
STMT_RE = re.compile(r'^  /\* ([0-9a-f]+): (.*) \*/$')


def resolve(lines, target):
    """target (guest VA 16進 or 関数名) -> (行 index, 関数名)"""
    if target.startswith('f_'):
        for i, l in enumerate(lines):
            if l == 'void %s(void) {' % target:
                return i, target
        return None, None
    va = int(target, 16)
    cur = None
    for i, l in enumerate(lines):
        m = FUNC_RE.match(l)
        if m:
            cur = m.group(1)
        m2 = STMT_RE.match(l)
        if m2 and int(m2.group(1), 16) == va:
            return i, cur
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--at', required=True,
                    help='guest VA (0x...) または関数名 (f_xxxx) のカンマ区切り')
    ap.add_argument('--marker', default='dbg_at')
    ap.add_argument('--c', default=None,
                    help='挿入する C 文 (既定は R[4]/R[5] の fprintf)。{tgt} は VA、{fn} は関数名に置換する')
    a = ap.parse_args()
    lines = open(a.src, errors='replace').read().split('\n')
    out = []
    hits = 0
    for tgt in a.at.split(','):
        tgt = tgt.strip()
        idx, fn = resolve(lines, tgt)
        if idx is None:
            print('[dbg_lift] %s  unresolved' % tgt, file=sys.stderr)
            continue
        if a.c:
            lines.insert(idx, '  ' + a.c.replace('{tgt}', tgt).replace('{fn}', str(fn)))
        else:
            lines.insert(idx, '  if (g_dbg_6c) fprintf(stderr, "[%s] %s @ %s\\n", '
                              '(unsigned long long)R[4], (unsigned long long)R[5]);'
                         % (a.marker, fn, tgt))
        hits += 1
        print('[dbg_lift] %s -> line %d in %s' % (tgt, idx + 1, fn))
    s = '\n'.join(lines)
    if 'extern int g_dbg_6c;' not in s:
        s = s.replace('#include "fle_cpu.h"\n',
                      '#include "fle_cpu.h"\nextern int g_dbg_6c;\n', 1)
    open(a.out, 'w', errors='replace').write(s)
    print('[dbg_lift] %d probes -> %s (%d lines)' % (hits, a.out, len(lines)))
    return 0 if hits else 1


if __name__ == '__main__':
    sys.exit(main())
