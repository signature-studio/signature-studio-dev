"""LD-158 (#3470): ret=i128 39 関数の戻り経路の件数表 (動的プローブ + 静的 dsm 判定) を集計する。

使い方: cd tools/liftdiff && python3 tests/ld158_summarize.py [--probe work/ld158_probe.json] [--tsv work/ld158_table.tsv]
前提: tests/ld158_ret_probe.py の出力 (work/ld158_probe.json)・tests/ld38_ret_convention.py (dsm 必要)。
出力: 動的分類の件数、静的 (窓 3 / 窓 8) 分類の件数、動的 xmm0 のみ分類と targets/m11.json の ret_override の一致確認。
"""
import argparse, collections, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(HERE)


def dyn_class(r):
    if r['n_ok'] == 0:
        return 'unexec'
    parts = [n for n, f in (('rax', r['rax_w']), ('rdx', r['rdx_w']), ('xmm0', r['x0_w'])) if f]
    return '+'.join(parts) or 'none'


def static(window):
    out = subprocess.run([sys.executable, 'tests/ld38_ret_convention.py', '--window', str(window)],
                         capture_output=True, text=True, check=True).stdout
    kinds = {}
    for l in out.splitlines():
        p = l.split()
        if len(p) == 3 and p[0].startswith('function_'):
            kinds[p[0]] = p[2]
    return kinds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--probe', default='work/ld158_probe.json')
    ap.add_argument('--tsv', default='work/ld158_table.tsv')
    a = ap.parse_args()
    P = json.load(open(a.probe))
    s3, s8 = static(3), static(8)
    dyn = {n: dyn_class(r) for n, r in P.items()}
    print('TOTAL', len(P))
    print('DYN', dict(collections.Counter(dyn.values())))
    print('STATIC_W3', dict(collections.Counter(s3[n] for n in P)))
    print('STATIC_W8', dict(collections.Counter(s8[n] for n in P)))
    xmm_only = sorted(n for n, r in P.items() if r['n_ok'] and not r['rax_w'] and not r['rdx_w'] and r['x0_w'])
    ov = sorted(json.load(open('targets/m11.json')).get('ret_override', {}).keys())
    print('XMM0_ONLY', len(xmm_only), xmm_only)
    print('OVERRIDE_MATCH', xmm_only == ov, len(ov))
    with open(a.tsv, 'w') as f:
        f.write('function\tparams\tn_ok\tdyn\tstatic_w3\tstatic_w8\toverride\n')
        for n in sorted(P):
            r = P[n]
            f.write('%s\t%s\t%d/%d\t%s\t%s\t%s\t%s\n' % (n, ','.join(r['params']) or '-', r['n_ok'], r['n_run'], dyn[n], s3[n], s8[n], 'yes' if n in ov else ''))
    print('wrote', a.tsv)


if __name__ == '__main__':
    main()
