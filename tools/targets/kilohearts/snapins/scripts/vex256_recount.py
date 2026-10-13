#!/usr/bin/env python3
"""vex256_recount.py — vex256_census.py の生出力を、REPORT §12 の表と同じ単位で数え直す (読取専用)。

入力は vex256_census.py と同じ (work/closures_sets.pkl・work/callgraph.pkl・work/winpkg/HeartCore.core_64)。
出力: (a) snap-in ごとの重複込み件数 (census と同じ数え方) の mnemonic 別内訳 (ymm 形のみ / vf* 全形)、
  (b) VA 一意数 (snap-in 間で共有された VA は 1 件)、(c) vblend*/vperm* の有無。
usage (tools/targets/kilohearts から): python3 snapins/scripts/vex256_recount.py
"""
import collections, os, pickle, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capstone
from pe_dis import rd, BASE

KH = os.path.abspath(os.path.join(HERE, '..', '..'))
NS = ['convolver', 'filtertable', 'ladder', 'equalizer']
S = pickle.load(open(os.path.join(KH, 'work', 'closures_sets.pkl'), 'rb'))
RES = pickle.load(open(os.path.join(KH, 'work', 'callgraph.pkl'), 'rb'))['res']
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

all_cnt = collections.defaultdict(collections.Counter)
ymm_cnt = collections.defaultdict(collections.Counter)
va_cnt = collections.Counter()
for ns in NS:
    for f in S['sets'][ns]:
        if f not in RES:
            continue
        for i in md.disasm(rd(BASE + f, RES[f]['size']), BASE + f):
            is_ymm = 'ymm' in i.op_str
            if is_ymm or i.mnemonic.startswith('v'):
                all_cnt[i.mnemonic][ns] += 1
                va_cnt[i.address] += 1
                if is_ymm:
                    ymm_cnt[i.mnemonic][ns] += 1

print('mnemonic 数 %d / 重複込み合計 %d / VA 一意数 %d (snap-in 間で共有された VA %d)' % (
    len(all_cnt), sum(sum(c.values()) for c in all_cnt.values()), len(va_cnt),
    sum(1 for v in va_cnt.values() if v > 1)))
print('ymm 形 (重複込み) snap-in 別: %s / 合計 %d' % (
    {ns: sum(c[ns] for c in ymm_cnt.values()) for ns in NS}, sum(sum(c.values()) for c in ymm_cnt.values())))
print('xmm 形を含む全 v* 重複込み合計: %d' % sum(sum(c.values()) for c in all_cnt.values()))
print('--- ymm 形 mnemonic 別 (重複込み)')
for m in sorted(ymm_cnt):
    print('%-12s %s total=%d' % (m, {ns: ymm_cnt[m][ns] for ns in NS if ymm_cnt[m][ns]}, sum(ymm_cnt[m].values())))
print('--- vf* mnemonic 別 (全形・重複込み)')
for m in sorted(all_cnt):
    if m.startswith('vf'):
        print('%-12s %s total=%d' % (m, {ns: all_cnt[m][ns] for ns in NS if all_cnt[m][ns]}, sum(all_cnt[m].values())))
print('vblend*/vperm* (全形): %s' % sorted(m for m in all_cnt if m.startswith(('vblend', 'vperm'))))
