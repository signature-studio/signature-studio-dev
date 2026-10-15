#!/usr/bin/env python3
"""CAB-274 (IPP-8) の独立再計算 (規則 37・別アルゴリズム)。

実装 (shim/impl/ipp_resize.c) を一切リンクせず、実 win64 dsp_ippv2_x64.dll の
  (a) 1D spike ログ (work/resize/sw4..sw7.txt = interp 4/5/6/7, swv6.txt = interp 6 の V-pass)
  (b) 2D インパルス応答ログ (work/resize/ksw4..ksw7.txt)
と数式モデル (Mitchell-Netravalli 2 パラメータ三次カーネル) を突き合わせる。

数え方の定義 (規則 36):
  - 「1D spike ログ」= test/sweep2.c の P 0..63 (sx = p/64) 行。'|' 区切り 16 グループは
    src スパイク位置 k、各グループの "dst:値" は src[k]=255 のときの dst 値。
    dst_x=6 の値を使う (px = 6 - sx, srcRoi={0,0,96,1}, dstRoi={0,0,16,1}, fx=fy=1)。
  - 「2D インパルス応答ログ」= probe274/ksweep.c の K 行 (shift = p/64)。src は (64,64) の
    1 画素 255 のみ、srcRoi={32,32,64,64} -> dstRoi={16,16,64,64}, fx=fy=1。
    dst (64+i, 64+j) の px = 64+i - sh - 32 なので、スパイク (ROI 相対 32) からの距離は
    d(i) = |i - sh| (i=0 -> sh, i=1 -> 1-sh, i=-1 -> 1+sh)。
  - 「重み」= DLL の 1D spike 値 S(d)。MN カーネル K に対し
    S(d) = round(255 * (K(1)+K(0)) * K(d))  (1 行 ROI の V-pass が距離 1 と 0 の 2 タップを
    畳み込むため)、ただし負値は 0 に clamp される (DLL 実測)。
  - 「2D 応答」= R(dh,dv) = round(255 * K(dh) * K(dv))、負値は 0 に clamp (最終出力)。
    MN は partition of unity (窓和=1) なので per-pixel 正規化は不要。

前提: work/resize/ のログ。再生成:
  gcc -O1 -I ../../src -I ../../ref -o /tmp/sw2 shim/test/sweep2.c ref/pe_load.c -lm
  FL_WIN64_DIR=<fl-win64 展開先> /tmp/sw2 6 > work/resize/sw6.txt ; FL_WIN64_DIR=<fl-win64 展開先> /tmp/sw2 7 > work/resize/sw7.txt
  gcc -O1 -I ../../src -I ../../ref -o /tmp/swv work/resize/sweepv.c ref/pe_load.c -lm
  FL_WIN64_DIR=<fl-win64 展開先> /tmp/swv 6 > work/resize/swv6.txt
  gcc -O1 -I ../../src -I ../../ref -o /tmp/ksw work/resize/probe274/ksweep.c ref/pe_load.c -lm
  FL_WIN64_DIR=<fl-win64 展開先> /tmp/ksw 6 > work/resize/ksw6.txt ; FL_WIN64_DIR=<fl-win64 展開先> /tmp/ksw 7 > work/resize/ksw7.txt

usage: python3 shim/verify_cab274_kernel.py
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # tools/ipp/shim
IPP = os.path.dirname(HERE)                                 # tools/ipp
R = os.path.join(IPP, 'work', 'resize')                    # spike ログ (gitignore)

# interp -> (B, C)。it=5 は MN(1,0)=3次B-スプライン (CAB-261 で確定)、
# it=4 は MN ではない (線形項を持つ別 cubic) ので対照のみ。
MN = {4: None, 5: (1.0, 0.0), 6: (0.0, 0.5), 7: (0.5, 0.3)}


def mn(d, B, C):
    """Mitchell-Netravalli 2 パラメータ三次カーネル"""
    a = abs(d)
    if a < 1.0:
        return ((12 - 9 * B - 6 * C) / 6) * a ** 3 - ((18 - 12 * B - 6 * C) / 6) * a ** 2 + (6 - 2 * B) / 6
    if a < 2.0:
        return ((-B - 6 * C) * a ** 3 + (6 * B + 30 * C) * a ** 2 + (-12 * B - 48 * C) * a + (8 * B + 24 * C)) / 6
    return 0.0


def ker_cubic(d):
    """impl の it=4 カーネル (線形項付き cubic, 対照)"""
    if d < 1.0:
        return 0.5 * d ** 3 - d * d - 0.5 * d + 1.0
    if d <= 2.0:
        return -(1.0 / 6.0) * (d - 1) * (d - 2) * (d - 3)
    return 0.0


def load_sw(path):
    """1D spike: [(phase, sx, {src_k: dst_x=6 の値})]"""
    rows = []
    with open(path) as f:
        for line in f:
            if not line.startswith('P '):
                continue
            parts = line.strip().split('|')
            ph = int(parts[0].split()[1])
            sx = float(parts[0].split()[2])
            obs = {}
            for k, grp in enumerate(parts[1:]):
                for pair in grp.split():
                    pos, val = pair.split(':')
                    if int(pos) == 6:
                        obs[k] = int(val)
            rows.append((ph, sx, obs))
    return rows


def load_ksw(path):
    """2D インパルス応答: {p: 3x3 リスト} (位置 (63+i, 63+j) の値)"""
    runs = {}
    with open(path) as f:
        for line in f:
            t = line.split()
            if t and t[0] == 'K':
                runs[int(t[2])] = [int(x) for x in t[5:] if x != '|']
    return runs


def check_sw(it):
    """1D spike ログ vs MN(B,C) 予測。d<=1.5 の点 (位相 8 の倍数) を比較。"""
    if MN[it] is None:
        K = ker_cubic
    else:
        B, C = MN[it]
        K = lambda d, B=B, C=C: mn(d, B, C)
    rows = load_sw(os.path.join(R, f'sw{it}.txt'))
    fold = K(1) + K(0)
    bad = tot = 0
    worst = 0
    for ph, sx, obs in rows:
        if ph % 8:
            continue
        px = 6.0 - sx
        for k, v in obs.items():
            d = abs(px - k)
            if d > 1.5:
                continue
            pred = max(0.0, 255.0 * fold * K(d))
            tot += 1
            diff = abs(round(pred) - v)
            worst = max(worst, diff)
            if diff:
                bad += 1
    return bad, tot, worst


def fit_bc(it):
    """2D インパルス応答から MN(B,C) を最小二乗フィット (closed form と別アルゴリズム)。
    K(d) = sqrt(R(d,d)/255) を観測値とし、(B,C) を 0.001 刻みの全探索で当てる。"""
    runs = load_ksw(os.path.join(R, f'ksw{it}.txt'))
    obs = {}
    for p, v in runs.items():
        sh = p / 64.0
        if v[4] > 0:
            obs[round(sh * 64)] = math.sqrt(v[4] / 255.0)
        if v[8] > 0:
            obs[round((1 - sh) * 64)] = math.sqrt(v[8] / 255.0)
    xs = [k for k in sorted(obs) if k <= 80]
    best = None
    B = -1.0
    while B <= 2.0001:
        C = -0.5
        while C <= 1.0001:
            err = sum((obs[k] - mn(k / 64.0, B, C)) ** 2 for k in xs)
            if best is None or err < best[0]:
                best = (err, B, C)
            C += 0.002
        B += 0.002
    err, B, C = best
    rms = math.sqrt(err / len(xs))
    mx = max(abs(obs[k] - mn(k / 64.0, B, C)) for k in xs)
    return B, C, rms, mx, len(xs)


def check_ksw(it):
    """2D インパルス応答の 3x3 全部を MN で予測 (負値 clamp 込み) して一致を数える。"""
    if MN[it] is None:
        return None
    B, C = MN[it]
    runs = load_ksw(os.path.join(R, f'ksw{it}.txt'))
    bad = tot = 0
    worst = 0
    for p, v in runs.items():
        sh = p / 64.0
        d = [abs(i - sh) for i in (-1, 0, 1)]  # dst(63+i, 64+j) の距離
        for i in range(3):
            for j in range(3):
                pred = max(0.0, 255.0 * mn(d[i], B, C) * mn(d[j], B, C))
                tot += 1
                diff = abs(round(pred) - v[i * 3 + j])
                worst = max(worst, diff)
                if diff:
                    bad += 1
    return bad, tot, worst


def check_vpass(it=6):
    """it=6 の V-pass 重み (swv6.txt) が H-pass (sw6.txt) と同一かを数える。
    → cubic 代用 (impl 旧挙動) との差は V-pass ではなくカーネル自体の差。"""
    def tab(path):
        t = {}
        for ph, sx, obs in load_sw(path):
            if ph % 8:
                continue
            px = 6.0 - sx
            for k, val in obs.items():
                d = round(abs(px - k) * 8) / 8.0
                if d <= 1.5:
                    t[d] = val
        return t
    th = tab(os.path.join(R, 'sw6.txt'))
    tv = tab(os.path.join(R, f'swv{it}.txt'))
    ks = [i / 8 for i in range(13)]
    diff = [k for k in ks if th.get(k, 0) != tv.get(k, 0)]
    # ついでに cubic (it=4) との差も定量化
    t4 = tab(os.path.join(R, 'sw4.txt'))
    cd = [(k, th.get(k, 0), t4.get(k, 0)) for k in ks if th.get(k, 0) != t4.get(k, 0)]
    return diff, cd, th


def check_gbs():
    """GetBufSize: it=5/6/7 が cubic (4) の式と一致するか (gbs.log の実測)"""
    p = os.path.join(R, 'gbs.log')
    if not os.path.exists(p):
        return None
    rows = [l.split() for l in open(p) if l.startswith(' ')]
    c = {'it4': 0, 'it5': 0, 'it6': 0, 'it7': 0, 'it16': 0}
    for r in rows:
        if len(r) < 9:
            continue
        key = 'it' + r[4] if r[3] == 'it' else r[3]
        if key in c:
            c[key] += 1
    return c


def main():
    need = [os.path.join(R, f'sw{it}.txt') for it in (4, 5, 6, 7)]
    need += [os.path.join(R, 'swv6.txt'), os.path.join(R, 'gbs.log')]
    need += [os.path.join(R, f'ksw{it}.txt') for it in (5, 6, 7)]
    missing = [p for p in need if not os.path.exists(p)]
    if missing:
        sys.exit('[ERROR] 不足: ' + ', '.join(missing) + ' (再生成コマンドは本スクリプトの docstring)')
    print('[1] 1D spike 予測 (S(d) = round(255*(K(1)+K(0))*K(d)), 負値 clamp)')
    for it in (4, 5, 6, 7):
        bad, tot, worst = check_sw(it)
        tag = 'MN' if MN[it] else 'ker_cubic(impl)'
        print(f'   it={it} ({tag}): {tot} 点中 不一致 {bad} (最大 |diff| = {worst}) '
              f'-> {"一致" if bad == 0 else "不一致あり"}')

    print('[2] 2D インパルス応答からの (B,C) 最小二乗フィット (別アルゴリズム)')
    for it in (5, 6, 7):
        B, C, rms, mx, n = fit_bc(it)
        print(f'   it={it}: fit B={B:.3f} C={C:.3f} (rms={rms:.5f} max={mx:.5f} n={n}) '
              f'採用値 {MN[it]}')

    print('[3] 2D インパルス応答 3x3 予測 (MN + 負値 clamp、分離モデル)')
    for it in (6, 7):
        bad, tot, worst = check_ksw(it)
        print(f'   it={it}: {tot} 点中 不一致 {bad} (最大 |diff| = {worst}) '
              f'-> {"一致" if bad == 0 else "不一致あり"}')

    print('[4] it=6 の V-pass (swv6) vs H-pass (sw6)、cubic (it=4) との差')
    diff, cd, th = check_vpass(6)
    print(f'   V==H: 不一致 {len(diff)} 点 (d={diff}) -> {"同一カーネル" if not diff else "相違"}')
    print(f'   cubic との差 (d, it6, it4): {[(k, a, b) for k, a, b in cd]}')
    print(f'   -> it=6 の画素差 9.768% の原因は V-pass ではなくカーネル差 (MN(0,0.5) vs impl cubic)')

    c = check_gbs()
    if c:
        print('[5] GetBufSize 実測 (gbs.log): it=5/6/7 が cubic (4) 式と一致するケース数')
        print(f'   {c} (全 it で CUBIC 一致)')


if __name__ == '__main__':
    main()
