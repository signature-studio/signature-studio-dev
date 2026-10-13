"""LD-38 (#1193): ret=i128 の 39 関数について、機械語の戻り経路を RetDec の逆アセンブル (dsm) から判定する。

使い方: python3 tests/ld38_ret_convention.py [--sigs work/m11_ldfix/sigs.json] [--dsm-glob '../m11/work/*.dsm']
出力: 関数ごとの戻り経路 (xmm0 / rax_rdx / other / no_ret) と集計。

判定 (ret 命令直前 3 行の文字列):
  xmm0    : xmm0 を含む (浮動小数の戻り。IR の i128 型付けが誤り)
  rax_rdx : rdx を含む (i128 を rax:rdx で返す可能性)
  other   : それ以外 (rax のみ・sret 等。目視確認が要る)
  no_ret  : dsm 内に ret 命令が無い (分岐先・tail 呼出し・dsm 切れ)
"""
import argparse, glob, json, re, collections

ap = argparse.ArgumentParser()
ap.add_argument('--sigs', default='work/m11_ldfix/sigs.json')
ap.add_argument('--dsm-glob', default='../m11/work/*.dsm')
a = ap.parse_args()

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
    if b is None:
        kind = 'not_in_dsm'
    else:
        rets = [k for k, l in enumerate(b) if re.search(r'\tret\b', l)]
        if not rets:
            kind = 'no_ret'
        else:
            kinds = set()
            for k in rets:
                w = ' '.join(b[max(0, k - 3):k])
                kinds.add('xmm0' if 'xmm0' in w else 'rax_rdx' if 'rdx' in w else 'other')
            kind = '/'.join(sorted(kinds))
    cnt[kind] += 1
    print(name, ','.join(sigs[name]['params']) or '-', kind)
print('SUMMARY', dict(cnt), 'total', len(targets))
