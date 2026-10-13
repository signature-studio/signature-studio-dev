#!/usr/bin/env python3
"""SR-8 (#1030) L1 復元 pass の実行と census。

使い方: python3 l1_restore.py <raw.ll> <out.ll> [--negctl]
  --negctl: pass を適用せず census だけ出す (ネガコン: 脱落が戻らないことを示す)。
census は REPORT §13b の手確認列 (直接 call / edx 即値 / 入口 edge) と同じ 4 指標を IR 側で数える。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'liftlib'))
from liftlib.passes import serum2_l1 as P  # noqa: E402


def main():
    src, dst = sys.argv[1], sys.argv[2]
    negctl = '--negctl' in sys.argv
    lines = open(src).read().splitlines()
    before = P.count(lines)
    print('census before =', before)
    if not negctl:
        lines = P.restore(lines)
        after = P.count(lines)
        print('census after  =', after)
    open(dst, 'w').write('\n'.join(lines) + '\n')
    print('wrote', dst, 'negctl' if negctl else 'restored')


if __name__ == '__main__':
    main()
