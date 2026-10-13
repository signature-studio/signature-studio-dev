#!/usr/bin/env python3
"""KH-7 (#59) 別アルゴリズム検算: IAT 経由の call/jmp の件数を、khlib のバイト走査 (FF15/FF25) と llvm-objdump の線形逆アセンブルで独立に数えて全 import で突合する。
usage: xcheck_xref.py <HeartCore.core_64> <llvm-objdump -d --no-show-raw-insn --section=.text の出力>
終了コード: 0 = 全 import で一致 (かつネガコン OK) / 1 = 不一致またはネガコン失敗
"""
import sys, os, re, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from khlib import Core


def count_objdump(path, slots):
    pat = re.compile(r'^\s*[0-9a-f]+:\s+(?:call|jmp)q?\s+\*0x[0-9a-f]+\(%rip\)\s+# 0x([0-9a-f]+)')
    cnt = collections.Counter()
    for line in open(path, encoding='utf-8', errors='ignore'):
        if '(%rip)' not in line:
            continue
        m = pat.match(line)
        if m and int(m.group(1), 16) in slots:
            cnt[int(m.group(1), 16)] += 1
    return cnt


def main():
    core = Core(sys.argv[1])
    slots = {core.base + r: v for r, v in core.iat.items()}
    od = count_objdump(sys.argv[2], slots)
    mine = collections.Counter()
    xr = core.xrefs()
    byname = {v: k for k, v in slots.items()}
    for key, sites in xr.items():
        mine[byname[key]] = sum(1 for _, k in sites if k in ('call', 'jmp'))
    diff = {slots[s]: (mine.get(s, 0), od.get(s, 0)) for s in set(mine) | set(od) if mine.get(s, 0) != od.get(s, 0)}
    tot_m, tot_o = sum(mine.values()), sum(od.values())
    print('call/jmp via IAT: byte-scan=%d objdump=%d, imports=%d, 不一致 import=%d %s' % (tot_m, tot_o, len(slots), len(diff), diff if diff else ''))
    for nm in (('gdi32.dll', 'SetDIBitsToDevice'), ('user32.dll', 'UpdateLayeredWindow'), ('user32.dll', 'RegisterClassW')):
        s = byname[nm]; print('  %s!%s byte-scan=%d objdump=%d' % (nm[0], nm[1], mine.get(s, 0), od.get(s, 0)))
    ok = not diff and tot_m == tot_o and tot_m > 0
    # ネガコン: byte-scan 側から 1 件消すと不一致を検出できること
    s0 = byname[('gdi32.dll', 'SetDIBitsToDevice')]
    m2 = collections.Counter(mine); m2[s0] -= 1
    nc = {slots[s]: (m2.get(s, 0), od.get(s, 0)) for s in set(m2) | set(od) if m2.get(s, 0) != od.get(s, 0)}
    print('  [nc %s] SetDIBitsToDevice の件数を 1 減らす → 不一致 import = %d (期待 1)' % ('ok' if len(nc) == 1 else 'NG', len(nc)))
    return 0 if ok and len(nc) == 1 else 1


if __name__ == '__main__':
    sys.exit(main())
