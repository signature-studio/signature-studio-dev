#!/usr/bin/env python3
"""LD-62 (#1767): m11 0x417b70 の除算入力 (stride, count) を native (符号付き idiv) で走らせ、
trap helper 0x409730 に入るかを実測する。予測 (site1 = idiv 結果 != stride ≙ 0x417c62、
site2 = product+0x10 < 0 ≙ 0x417c75) と突き合わせる。

  FL_WIN64_DIR=<fl-win64 展開先> python3 tools/liftdiff/tests/trace_417b70_trap.py > tools/liftdiff/results/m11_417b70_trap_inputs.md

stride は movsxd (32bit 符号付き)、count は qword。native は work/ld_native が必要 (cwd 非依存)。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from ldlib.session import Session  # noqa: E402
from ldlib.runners import Runner  # noqa: E402

FN = 0x417b70
TRAP = 0x409730
M64 = (1 << 64) - 1
GRID = [(16, 1), (-16, 1), (16, 2), (-16, 2), (-16, 3), (16, 1 << 60), (-16, 1 << 60), (2147483647, 3)]


def s64(v):
    v &= M64
    return v - (1 << 64) if v >> 63 else v


def predict(st, cnt):
    p = s64(st * cnt)
    a = abs(p) // abs(cnt)  # idiv は 0 方向への切り捨て (浮動小数点を使わない)
    q = -a if (p < 0) != (cnt < 0) else a
    site1 = q != st
    site2 = s64(p + 0x10) < 0
    return site1, site2


def le(v, n):
    return (v & ((1 << (8 * n)) - 1)).to_bytes(n, 'little').hex()


def main():
    s = Session(os.path.join(ROOT, 'targets/m11.json'), build=False, trace=True)
    nat = Runner('native', ['setarch', '-R', os.path.join(ROOT, 'work/ld_native'), s.t['pe']],
                 s.init_lines('native') + [s.tracelines()], timeout=10.0)
    lines = []
    for st, cnt in GRID:
        patch = ';'.join(['a:0x102:%s' % le(st, 4), 'a:0x106:q=a:0x400', 'a:0x200:%s' % le(cnt, 8)])
        lines.append('id=%x:st%d_c%d fn=%x blob=- args=i:a:0x300,i:a:0x100,i:0x0,i:a:0x200 trace=1 xfill=0 '
                     'sig=i64,i64,i64,i64 rt=i64 p=%s' % (FN, st & M64, cnt & M64, FN, patch))
    out = nat.run_cases(lines, ['%d_%d' % g for g in GRID])
    nat.close()
    print('<!-- 自動生成: python3 tools/liftdiff/tests/trace_417b70_trap.py (LD-62, #1767) -->')
    print('| stride | count | 予測 site1 (0x417c62) | 予測 site2 (0x417c75) | native status | 0x409730 進入 | FN 直後が 0x409730 |')
    print('|---:|---:|:---:|:---:|---|:---:|:---:|')
    raw = []
    for (st, cnt), r in zip(GRID, out):
        vas = [int(t[0], 16) for t in r.get('trace', [])]
        s1, s2 = predict(st, cnt)
        direct = any(vas[i] == FN and i + 1 < len(vas) and vas[i + 1] == TRAP for i in range(len(vas)))
        print('| %d | %d | %s | %s | %s | %s | %s |' % (st, cnt, s1, s2, r.get('status'), TRAP in vas, direct))
        raw.append('- stride %d count %d: trace[0:8] = %s' % (st, cnt, [t[0] for t in r.get('trace', [])[:8]]))
    print()
    print('生の trace 先頭 (t[0] は hex 文字列):')
    print('\n'.join(raw))


if __name__ == '__main__':
    main()
