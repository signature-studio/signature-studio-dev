#!/usr/bin/env python3
"""CAB-261 (IPP-6) 検収の独立再計算 (規則 37・別アルゴリズム)。

実装 (shim/impl/ipp_resize.c) を一切リンクせず、実 win64 dsp_ippv2_x64.dll の
spike ログ (work/resize/sw5.txt = interp 5, sw7.txt = interp 7) と
数式モデルを突き合わせる。

数え方の定義 (規則 36):
  - 「位相 64 点」= test/sweep2.c の P 0..63 (sx = p/64)。ログの 1 行 (P ...) の
    '|' 区切り 16 グループは src スパイク位置 k、各グループ内の "dst:値" は
    src[k]=255 を入れたときの dst 値 (= 255 * w_k(dst))。
  - 「タップ重み」= dst_x=6 に書き込まれる値。px = (dst_x + 0.5 - sx)/fx - srcRoi.x - 0.5
    (fx=1.0, srcRoi={0,0,96,1}, dstRoi={0,0,16,1} で採取したので dst_x=6 では px = 6 - sx)。
  - it=5 の一致判定 = round(255 * (5/6) * w_t) が DLL の値と一致すること
    (255*5/6 = 212.5 = 実 DLL のスパイク出力のゲイン)。

前提: work/resize/sw5.txt と sw7.txt が必要。再生成:
  gcc -O1 -I ../../src -I ../../ref -o /tmp/sw2 shim/test/sweep2.c ref/pe_load.c -lm
  FL_WIN64_DIR=<fl-win64 展開先> /tmp/sw2 5 > work/resize/sw5.txt ; FL_WIN64_DIR=<fl-win64 展開先> /tmp/sw2 7 > work/resize/sw7.txt

usage: FL_WIN64_DIR=<fl-win64 展開先> python3 verify_cab261_kernel.py
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # tools/ipp/shim
IPP = os.path.dirname(HERE)                                 # tools/ipp
GAIN = 255 * 5 / 6


def bspl3(d):
    a = abs(d)
    if a < 1.0:
        return 2.0 / 3.0 - a * a + a * a * a / 2.0
    if a < 2.0:
        q = 2.0 - a
        return q * q * q / 6.0
    return 0.0


def load(path):
    """P 行を [(phase, {src_k: dst_x=6 の値})] にする"""
    rows = []
    with open(path) as f:
        for line in f:
            if not line.startswith('P '):
                continue
            parts = line.strip().split('|')
            phase = int(parts[0].split()[1])
            sx = float(parts[0].split()[2])
            obs = {}
            for k, grp in enumerate(parts[1:]):
                for pair in grp.split():
                    pos, val = pair.split(':')
                    if int(pos) == 6:
                        obs[k] = int(val)
            rows.append((phase, sx, obs))
    return rows


def check_it5(rows):
    """it=5 の 4 タップ重みを 3 次 B-スプラインと比較 → 位相 64 点で一致するか"""
    bad = 0
    tot = 0
    for phase, sx, obs in rows:
        px = (6 + 0.5 - sx) - 0.5
        i0 = math.floor(px)
        s = 0.0
        mod = {}
        for src in range(i0 - 1, i0 + 3):
            v = bspl3(px - src)
            mod[src] = v
            s += v
        for src, v in mod.items():
            pred = round(GAIN * (v / s)) if s > 0 else 0
            tot += 1
            if pred != obs.get(src, 0):
                bad += 1
                if bad <= 5:
                    print(f'    不一致 ph={phase} src={src} pred={pred} obs={obs.get(src, 0)}')
    return bad, tot


def dump_it7(rows):
    """it=7: dst_x=6 のタップ重みを距離 d (1/8 刻み) で集計する"""
    tab = {}
    conflict = []
    support = 0.0
    for phase, sx, obs in rows:
        px = 6 + 0.5 - sx - 0.5
        clean = (phase % 8 == 0)     # sx が 1/8 の倍数の位相だけ表に使う (距離が 1/8 刻みになる)
        for src, val in obs.items():
            dist = abs(px - src)
            if dist > support:
                support = dist
            if not clean:
                continue
            eighth = round(dist * 8)
            if eighth > 10:          # サポート外 (d >= 1.25)
                continue
            d = eighth / 8.0
            if d in tab and tab[d] != val:
                conflict.append((d, tab[d], val))
            tab[d] = val
    return tab, support, conflict


def peaks_it7(rows):
    """正規化ピーク (その位相で px に最も近いタップの重み / その位相のタップ重み和)"""
    out = []
    for phase, sx, obs in rows:
        if phase % 8 or not obs:
            continue
        px = 6 + 0.5 - sx - 0.5
        tot = 0
        near = None
        near_d = 1e9
        for src, val in obs.items():
            tot += val
            dist = abs(px - src)
            if dist < near_d:
                near_d, near = dist, val
        if tot:
            out.append(near / tot)
    return out


def main():
    sw5 = os.path.join(IPP, 'work', 'resize', 'sw5.txt')
    sw7 = os.path.join(IPP, 'work', 'resize', 'sw7.txt')
    for p in (sw5, sw7):
        if not os.path.exists(p):
            sys.exit(f'[ERROR] {p} がありません (再生成コマンドは本スクリプトの docstring)')
    r5, r7 = load(sw5), load(sw7)
    print(f'it=5 ログ: 位相 {len(r5)} 点 / it=7 ログ: 位相 {len(r7)} 点')

    bad, tot = check_it5(r5)
    print(f'[it=5] 3 次 B-スプライン (bspl3, 正規化, ゲイン 255*5/6) vs DLL スパイク: {tot} 点中 不一致 {bad}')
    print('      -> 64/64 位相一致' if bad == 0 else '      -> 不一致あり (要調査)')

    tab, support, conflict = dump_it7(r7)
    keys = [i / 8.0 for i in range(0, 10)]
    print('[it=7] dst_x=6 の未正規化重み (d = |px - タップ|):')
    print('   d :', '  '.join(f'{k:7.3f}' for k in keys))
    print('   w :', '  '.join(f'{tab.get(k, 0):7d}' for k in keys))
    print(f'   d >= 1.25 の重み = {tab.get(10/8.0, 0)} (0 = サポート外)')
    print(f'   非ゼロとなる最大 |d| = {support:.6f} (REPORT §14-3 は 1.2031)')
    print(f'   位相間の矛盾 = {len(conflict)} 件 (同じ d で異なる重みが出た回数)')
    peaks = peaks_it7(r7)
    print('   正規化ピーク (位相 0,8,...,40):', ' '.join(f'{p:.4f}' for p in peaks[:5]))
    print('   REPORT §14-3 の値 195,189,173,151,123,94,65,39,19,6,0 と一致:',
          [tab.get(k, 0) for k in keys] == [195, 189, 173, 151, 123, 94, 65, 39, 19, 6] and tab.get(1.25, 0) == 0)


if __name__ == '__main__':
    main()
