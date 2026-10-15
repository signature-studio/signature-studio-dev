#!/usr/bin/env python3
"""residual_3195.py — #3195 (LD-149): first-deref-not-entry の見送り組を、本体 ldfix.py と同じ Machine (PE 直読) で判定し直す。
dom_1325.py は ImageMachine で測っていたため、本体の fix_f3c_use の門と食い違う組がある (6905f0 の raw-after 等)。
判定は fix_f3c_use の門の順 (raw-after / w32 / no-ir-block / no-rep-use / rep-not-dominated / dominated) と、
fix_f3c_use 単独の適用結果 (applied / not_dom / silent) を出す。
使い方 (tools/m11 で実行): python3 ldfix/residual_3195.py <block00031_PE.bin> [VA 16進,... (省略時は既定の 14 関数)]"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ldfix  # noqa: E402
from ldfix import Machine  # noqa: E402
from ldmach import FnMach  # noqa: E402

DEFAULT = '10077a0,101a2a0,101d180,1050f90,105f2e0,10626e0,10628d0,12f9730,41a670,6905f0,786d50,787380,784790,dc1a30'


def main():
    pe = sys.argv[1]
    vas = [int(x, 16) for x in (sys.argv[2] if len(sys.argv) > 2 else DEFAULT).split(',')]
    text = open('work/boot_final3.ll', errors='replace').read()
    for x in ldfix.DEF_RE.finditer(text):
        ldfix.F3C_ARITY[int(x.group('name')[9:], 16)] = len([p for p in x.group('args').split(',') if p.strip()])
    mach = Machine(pe)
    for m in ldfix.DEF_RE.finditer(text):
        va = int(m.group('name')[9:], 16)
        if va not in vas:
            continue
        end = text.index('\n}', m.end()) + 2
        body = text[m.start():end]
        fn = ldfix.Fn('function_%x' % va, va, body)
        blk_vas = [bva for (bva, _l) in fn.blocks() if bva is not None]
        if hasattr(mach, 'cover'):
            mach.cover(va, max(blk_vas))
        fv = FnMach(mach, va, blk_vas)
        _lsf, _ptr, uses, blk0 = ldfix.f3c_track(fv)
        for n in sorted({u[2] for u in uses if u[0] == 'deref' and u[4] == 'arg'}):
            ds = [u for u in uses if u[0] == 'deref' and u[2] == n and u[4] == 'arg']
            first = min(u[1] for u in ds)
            if first in blk0:
                continue
            raws = [u for u in uses if u[0] == 'raw' and u[2] == n]
            raw_after = sum(1 for u in raws if u[1] > first)
            w32 = not all(u[3] == 64 for u in ds)
            bstart = max([x for x in ldfix._f3c_leaders(fv.ins) if x <= first], default=None)
            blocks = fn.blocks()
            has_ir = any(bva == bstart for (bva, _ls) in blocks)
            argre = re.compile(r'(?<![\w.$-])%arg' + str(n) + r'(?![\w.$-])')
            idx = [k for k in range(1, len(body.split('\n'))) if argre.search(body.split('\n')[k])]
            rep_idx = idx[len(raws):]
            if raw_after:
                reason = 'raw-after(%d)' % raw_after
            elif w32:
                reason = 'w32'
            elif not has_ir:
                reason = 'no-ir-block'
            elif not rep_idx:
                reason = 'no-rep-use'
            else:
                at = ldfix.f3c_use_dom_at(fn, fv, first, rep_idx)
                reason = 'dominated' if at is not None else 'rep-not-dominated'
            print('%x arg%d first=%x block=%s keep=%d rep=%d reason=%s' % (
                va, n, first, '%x' % bstart if bstart is not None else '-', len(raws), len(rep_idx), reason))
        rep = {}
        ldfix.fix_f3c_use(ldfix.Fn('function_%x' % va, va, body), fv, rep, [0])
        print('  fn %x: fix_f3c_use (関数単位) replaced=%s dom=%s not_dom=%s' % (
            va, rep.get('f3c_use_replaced', 0), rep.get('f3c_use_dom', 0), rep.get('f3c_use_not_dom', 0)))


if __name__ == '__main__':
    main()
