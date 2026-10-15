#!/usr/bin/env python3
"""xmm 入力 slot の 2 つの機械語解析を同じ関数に当てて比べる (PLG-F2-8 #2726)。

  python3 xmm_slot_probe.py PE VA [VA ...]      例: block18982_PE.bin 6b0ef0

(a) p0c/k80abi.scan_function (lift/passes/fix_xmm_args.py が使う): read-before-write を命令のアドレス順に数える
(b) liftdiff ldlib/pe.py Analyzer (arity_x): CFG 上で全経路に定義の無い xmm 読みを数える
(a) が (b) より小さければ、線形順では見えない経路 (前方分岐) で読まれる xmm 入力を見落としている。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))  # tools/plugins
sys.path.insert(0, os.path.join(ROOT, 'p0c'))
sys.path.insert(0, os.path.join(ROOT, '..', 'liftdiff'))
import capstone  # noqa: E402
import k80abi as K  # noqa: E402
from ldlib.pe import PE, Analyzer  # noqa: E402


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
        a_slots = sorted(s for s in ka[1] if int(s[3:]) < 4)
        b = an.analyze(va)
        b_slots = ['xmm%d' % n for n in b['xmm_slots']]
        flag = '' if set(a_slots) == set(b_slots) else '  <- 不一致 (a) < (b)' if set(a_slots) < set(b_slots) else '  <- 不一致'
        print('0x%x (a) k80abi=%s (b) pe.py=%s%s' % (va, ','.join(a_slots) or '-', ','.join(b_slots) or '-', flag))


if __name__ == '__main__':
    main()
