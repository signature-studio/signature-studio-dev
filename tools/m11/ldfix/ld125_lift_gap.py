#!/usr/bin/env python3
"""ld125_lift_gap.py — #2705 (LD-125) `128f9e0` の lift 段で欠落した機械語区間の特定。

機械語の分岐先と fall-through (枝の境界) を、各段の IR (boot3.lift.ll / boot3.norm0.ll / boot3.drc.ll /
boot_final3.ll) の `dec_label_pc_*` と突き合わせ、IR に block が無い区間 (gap) を出す。
12 site (#2679 の未判定) が gap のどの区間にあるかを site ごとに記録する。
出力: results/ld125_lift_gap_128f9e0.tsv
使い方: python3 ld125_lift_gap.py     環境変数: M11_WORK (既定 tools/m11/work)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '../../..'))
sys.path.insert(0, HERE)
from ldmach_img import ImageMachine  # noqa: E402

FN, FN_END = 0x128f9e0, 0x1294ab8
NAME = 'function_128f9e0'
SITES = ['12906d1', '1291ac3', '1291b14', '1291b5f', '1291c20', '1293012',
         '1293063', '12930ae', '129312c', '129450c', '129455d', '12945a8']
STAGES = ['boot3.lift.ll', 'boot3.norm0.ll', 'boot3.drc.ll', 'boot_final3.ll']


def ir_labels(path):
    ll = open(path).read().splitlines()
    s = next(i for i, l in enumerate(ll) if re.match(r'define .*@%s\(' % NAME, l))
    e = next(i for i in range(s, len(ll)) if ll[i] == '}')
    return s, e, sorted(int(m.group(1), 16) for l in ll[s:e] for m in [re.match(r'dec_label_pc_([0-9a-f]+):', l)] if m)


def main():
    w = os.environ.get('M11_WORK', os.path.join(REPO, 'tools/m11/work'))
    mach = ImageMachine(os.path.join(w, 'm11_image.bin'), os.path.join(w, 'boot*.drc.config.json'))
    ins = [x for x in mach.cs.disasm(mach.read(FN - mach.base, FN_END - FN + 0x10), FN, FN_END - FN + 0x10)
           if x.address < FN_END]
    # 機械語の基本ブロック境界: 分岐先・分岐の直後
    leaders = {FN}
    for x in ins:
        if x.mnemonic.startswith('j') and x.op_str.startswith('0x'):
            leaders.add(int(x.op_str, 16))
            leaders.add(x.address + x.size)
    leaders = sorted(t for t in leaders if FN <= t < FN_END)

    stage = {}
    for p in STAGES:
        s, e, labs = ir_labels(os.path.join(w, p))
        stage[p] = (e - s, labs)
    lift_labs = stage['boot3.lift.ll'][1]

    # 欠落区間: 隣接する lift label の間で、機械語の leader が 1 つ以上あるのに IR label が無い区間
    gaps = []
    for a, b in zip(lift_labs, lift_labs[1:] + [FN_END]):
        inner = [t for t in leaders if a < t < b]
        if inner:
            gaps.append((a, b, len(inner)))
    out = os.path.join(HERE, 'results/ld125_lift_gap_128f9e0.tsv')
    rows = ['section\tstart\tend\tir_label_start\tmachine_leaders_inside\twhere']
    print('[ld125] lift labels %d / machine leaders %d / stages: %s'
          % (len(lift_labs), len(leaders), ', '.join('%s=%d' % (p, len(stage[p][1])) for p in STAGES)))
    for p in STAGES:
        print('[ld125] %s label %d, same set as lift: %s' % (p, len(stage[p][1]), stage[p][1] == lift_labs))
    for a, b, n in gaps:
        rows.append('gap\t%x\t%x\t%x\t%d\t' % (a, b, a, n))
        print('[ld125] gap %x..%x (IR label %x の block が次の label まで続き、機械 leader %d 件を含む)' % (a, b, a, n))
    for s in SITES:
        d = int(s, 16)
        hit = [(a, b) for a, b, _ in gaps if a <= d < b]
        where = ('gap %x..%x' % hit[0]) if hit else 'IR あり'
        rows.append('site\t%s\t\t\t\t%s' % (s, where))
        print('[ld125] site %s -> %s' % (s, where))
    with open(out, 'w') as fh:
        fh.write('\n'.join(rows) + '\n')
    print('[ld125] -> %s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
