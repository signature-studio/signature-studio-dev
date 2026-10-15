#!/usr/bin/env python3
"""xmm 入力 slot の 2 つの機械語解析を同じ関数に当てて比べる (PLG-F2-8 #2726)。

  python3 xmm_slot_probe.py PE VA [VA ...]      例: block18982_PE.bin 6b0ef0

(a0) p0c/k80abi.scan_function の read-before-write (線形順。#2850 の修正前に fix_xmm_args が使っていた)
(a) lift/passes/fix_xmm_args.py の cfg_xmm_slots (現行の pass が使う slot 集合 = pe.py を zero_idiom=True で呼んだ結果)
(b) liftdiff ldlib/pe.py Analyzer (arity_x 用・既定): CFG 上で全経路に定義の無い xmm 読み。ゼロ化イディオムを除かない
(a) と (b) は、同一レジスタのゼロ化イディオム (xorps r,r 等) の除外分だけ異なる。(a) と (b) は定義上の関係であり、
差し替えの正しさの証拠ではない (証拠は lift 結果 = REPORT_APPENDIX_2726 §8)。(a0) が (b) より小さければ線形順の見落とし。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))  # tools/plugins
sys.path.insert(0, os.path.join(ROOT, 'p0c'))
sys.path.insert(0, os.path.join(ROOT, '..', 'liftdiff'))
sys.path.insert(0, os.path.join(ROOT, 'lift', 'passes'))
import capstone  # noqa: E402
import k80abi as K  # noqa: E402
from ldlib.pe import PE, Analyzer  # noqa: E402
from fix_xmm_args import cfg_xmm_slots  # noqa: E402


def main():
    path = sys.argv[1]
    base, F, tva, td = K.load_pe(path)
    MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    MD.detail = True
    an = Analyzer(PE(path))
    for a in sys.argv[2:]:
        va = int(a, 16)
        if va not in F:
            print('0x%x (no pdata)' % va)
            continue
        ka = K.scan_function(MD, td, tva, va, F[va])
        a0_slots = sorted(s for s in ka[1] if int(s[3:]) < 4)
        a_slots, trunc = cfg_xmm_slots(an, va)
        b = an.analyze(va)
        b_slots = ['xmm%d' % n for n in b['xmm_slots']]
        flag = '' if set(a_slots) == set(b_slots) else '  <- 不一致 (a) != (b)'
        print('0x%x (a0) k80abi=%s (a) pass=%s (b) pe.py=%s%s' % (va, ','.join(a0_slots) or '-', ','.join(a_slots) or '-', ','.join(b_slots) or '-', flag))


if __name__ == '__main__':
    main()
