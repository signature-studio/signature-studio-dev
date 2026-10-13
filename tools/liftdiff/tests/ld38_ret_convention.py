"""LD-38 (#1193): ret=i128 の 39 関数について、機械語の戻り経路を RetDec の逆アセンブル (dsm) から判定する。

使い方: python3 tests/ld38_ret_convention.py [--sigs work/m11_ldfix/sigs.json] [--dsm-glob '../m11/work/*.dsm']
        python3 tests/ld38_ret_convention.py --control   (分類器のネガティブコントロール。実データ不要)
出力: 関数ごとの戻り経路 (xmm0 / rax_rdx / other / no_ret) と集計。

判定 (ret 命令直前 3 行の文字列):
  xmm0    : xmm0 を含む (浮動小数の戻り。IR の i128 型付けが誤り)
  rax_rdx : rdx を含む (i128 を rax:rdx で返す可能性)
  other   : それ以外 (rax のみ・sret 等。目視確認が要る)
  no_ret  : dsm 内に ret 命令が無い (分岐先・tail 呼出し・dsm 切れ)
"""
import argparse, glob, json, re, collections


WINDOW = 3


def classify(b, window=None):
    w_n = WINDOW if window is None else window
    rets = [k for k, l in enumerate(b) if re.search(r'\tret\b', l)]
    if not rets:
        return 'no_ret'
    kinds = set()
    for k in rets:
        w = ' '.join(b[max(0, k - w_n):k])
        kinds.add('xmm0' if 'xmm0' in w else 'rax_rdx' if 'rdx' in w else 'other')
    return '/'.join(sorted(kinds))


# 実在の xmm0 関数 function_cc32f0 (tools/m11/work/boot2.drc.dsm) の本体をそのまま使う。
REAL_XMM0 = [
    '0xcc32f0:    66 0f 28 c1                        \tmovapd xmm0, xmm1',
    '0xcc32f4:    f2 0f 59 81 90 10 00 00            \tmulsd xmm0, qword ptr [rcx + 0x1090]',
    '0xcc32fc:    c3                                 \tret ',
]


def control():
    cases = [
        ('real xmm0 body', REAL_XMM0, 'xmm0'),
        ('xmm0 removed from real body', [l.replace('xmm0', 'rax') for l in REAL_XMM0], 'other'),
        ('ret line deleted', REAL_XMM0[:2], 'no_ret'),
    ]
    ok = True
    for name, body, want in cases:
        got = classify(body)
        ok &= got == want
        print('CONTROL', name, 'got', got, 'want', want, 'OK' if got == want else 'FAIL')
    return 0 if ok else 1


ap = argparse.ArgumentParser()
ap.add_argument('--sigs', default='work/m11_ldfix/sigs.json')
ap.add_argument('--dsm-glob', default='../m11/work/*.dsm')
ap.add_argument('--control', action='store_true')
ap.add_argument('--window', type=int, default=3, help='ret 直前何行を見るか (既定 3)')
a = ap.parse_args()
WINDOW = a.window

if a.control:
    raise SystemExit(control())

sigs = json.load(open(a.sigs))
targets = sorted(k for k, v in sigs.items() if v['ret'] == 'i128')

bodies = {}
for f in sorted(glob.glob(a.dsm_glob)):
    cur, buf = None, []
    for l in open(f, errors='replace'):
        l = l.rstrip('\n')
        m = re.match(r'; function: (function_[0-9a-f]+) at', l)
        if m:
            if cur in targets and cur not in bodies:
                bodies[cur] = buf
            cur, buf = m.group(1), []
        elif cur and re.match(r'^0x[0-9a-f]+:', l):
            buf.append(l)
    if cur in targets and cur not in bodies:
        bodies[cur] = buf

cnt = collections.Counter()
for name in targets:
    b = bodies.get(name)
    kind = 'not_in_dsm' if b is None else classify(b, WINDOW)
    cnt[kind] += 1
    print(name, ','.join(sigs[name]['params']) or '-', kind)
print('SUMMARY', dict(cnt), 'total', len(targets))
