#!/usr/bin/env python3
"""#3122: 基準 (7e149974 全再生成 IR) の unit 別 survey と本 A/B (main・同一 IR 内の既定 0 / opt-in 1) の unit 別 survey を対応付ける.
使い方: python3 m11_unit_map.py BASE.json ARM0.json ARM1.json
出力: 状態別件数, 基準と arm0 の unit 別差, arm0 と arm1 の unit 別差. 基準の件数が ok 872 / trap 23 / miss 46 / noproc 1 でなければ終了 1.
"""
import json
import sys
from collections import Counter

EXPECT_BASE = {'ok': 872, 'trap': 23, 'miss': 46, 'noproc': 1}


def main():
    base, arm0, arm1 = (json.load(open(p)) for p in sys.argv[1:4])
    assert len(base) == len(arm0) == len(arm1) == 942, (len(base), len(arm0), len(arm1))
    for name, lab in (('base(7e149974)', base), ('arm0(main 既定)', arm0), ('arm1(main opt-in)', arm1)):
        c = Counter(lab)
        print('[%s] ok %d / trap %d / miss %d / noproc %d' % (name, c['ok'], c['trap'], c['miss'], c['noproc']))
    d = [(i, base[i], arm0[i]) for i in range(942) if base[i] != arm0[i]]
    print('[map] 基準と arm0 の unit 別差 %d 件: %s' % (len(d), ' '.join('%d:%s->%s' % x for x in d) or '0'))
    d01 = [i for i in range(942) if arm0[i] != arm1[i]]
    print('[map] arm0 と arm1 の unit 別差 %d 件: %s' % (len(d01), d01 or '0'))
    ok = dict(Counter(base)) == EXPECT_BASE
    print('[map] 基準の件数 = 872/23/46/1: %s' % ('OK' if ok else 'NG'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
