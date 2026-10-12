#!/usr/bin/env python3
"""p0c4_nega.py — CAB-253 の負論対照 (規則 41: 主要な修正を 1 件ずつ外して FAIL/劣化を確認)。

  python3 tools/plugins/p0c/p0c4_nega.py [cases]      # 既定 200

対照 (外す修正 → 観測される劣化):
  NC1 prototype 無し : k80_diff.py の thunk prototype を出さない。
        → float 引数が default argument promotion で double 化し thunk の movss が
          double の下 4 byte を読む (値が不一致)。bit-exact kernel の buf_diff が 0 から
          数百万に劣化する (0x5e0980 等で実測)。
  NC2 struct-copy 修飾なし (K80_NO_STRUCTD=1) : [D] パターンを外す。
        → 0x5e05b0 は record{ptr,ptr} の第 2 ポインタが placeholder のまま NULL 書込 →
          sig11 (修正後は buf_diff=0)。
  NC3 clip_index 非負制約なし (K80_NO_NNEGF=1) : fp scalar の nnegf/有限ゲートを外す。
        → 負の gain で trunc が負 → 負添字の OOB read で 0x5e0d80 が sig11。
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
D3 = os.path.join(HERE, 'work', 'diff3')
TARGETS = '0x5de710,0x5df610,0x5e05b0,0x5e0d80,0x5dfb60,0x5e0980,0x5e0ea0,0x5e1330'


def run(cmd, env=None, **kw):
    e = dict(os.environ)
    if env:
        e.update(env)
    r = subprocess.run(cmd, capture_output=True, text=True, env=e, **kw)
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-2000:] + r.stderr[-2000:])
        raise SystemExit('[FAIL] %s' % ' '.join(cmd))
    return r.stdout


def sweep(cases, label, env=None):
    out = run(['python3', os.path.join(HERE, 'k80_diff.py'),
               '--ir', os.path.join(D3, 'k80.x87fix.ll'), '--cases', str(cases),
               '--only', TARGETS], env=env)
    rows = {}
    for ln in out.split('\n'):
        f = ln.split(',')
        if len(f) >= 8 and f[0].startswith('0x'):
            rows[f[0]] = f
    print('[%s]' % label)
    for k in sorted(rows):
        print('   %-10s ret=%-5s buf=%-9s %s' % (rows[k][0], rows[k][3], rows[k][4], rows[k][7]))
    return rows


def main():
    cases = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    os.environ['TMPDIR'] = os.path.join(HERE, 'work', 'tmp')
    os.makedirs(os.environ['TMPDIR'], exist_ok=True)
    if not os.path.exists(os.path.join(D3, 'k80.x87fix.ll')):
        raise SystemExit('[FAIL] work/diff3/k80.x87fix.ll が無い。先に p0c4_abi_e2e.py を実行')

    print('== ベースライン (全修正 ON) ==')
    base = sweep(cases, 'base')

    print('== NC1: thunk prototype を外す (K80_NO_PROTO=1) ==')
    nc1 = sweep(cases, 'NC1', env={'K80_NO_PROTO': '1'})
    degraded = [k for k in nc1 if k in base and base[k][4] == '0' and nc1[k][4] != '0']
    print('   → buf_diff=0 が崩れた kernel: %s' % (degraded or 'なし'))

    print('== NC2: [D] struct-copy 修復を外す (argfix 再適用 K80_NO_STRUCTD=1) ==')
    run(['python3', os.path.join(HERE, 'k80_argfix.py'),
         os.path.join(D3, 'k80.lower.ll'), os.path.join(D3, 'k80.argfix.nc2.ll'),
         '--abi', os.path.join(HERE, 'work', 'k80abi.json')], env={'K80_NO_STRUCTD': '1'})
    run(['python3', os.path.join(HERE, 'x87fix.py'),
         os.path.join(D3, 'k80.argfix.nc2.ll'), os.path.join(D3, 'k80.x87fix.nc2.ll'),
         '--funcs', 'function_5de820,function_5dedf0,function_5dfb60,function_5dfbe0,'
                    'function_5dfc90,function_5dfd30,function_5dfdb0',
         '--chop-f32-fns', 'function_5dfbe0,function_5dfc90,function_5dfdb0'])
    out = run(['python3', os.path.join(HERE, 'k80_diff.py'),
               '--ir', os.path.join(D3, 'k80.x87fix.nc2.ll'), '--cases', str(cases),
               '--only', TARGETS])
    nc2 = {}
    for ln in out.split('\n'):
        f = ln.split(',')
        if len(f) >= 8 and f[0].startswith('0x'):
            nc2[f[0]] = f
    print('   [NC2]')
    for k in sorted(nc2):
        print('   %-10s ret=%-5s buf=%-9s %s' % (nc2[k][0], nc2[k][3], nc2[k][4], nc2[k][7]))
    print('   → 0x5e05b0: base=%s / NC2=%s' % (base.get('0x5e05b0', ['-']*8)[7:],
                                                nc2.get('0x5e05b0', ['-']*8)[7:]))

    print('== NC3: clip_index の非負制約を外す (K80_NO_NNEGF=1) ==')
    nc3 = sweep(cases, 'NC3', env={'K80_NO_NNEGF': '1'})

    ok = True
    if not degraded:
        print('[FAIL] NC1: prototype を外しても劣化が観測できない')
        ok = False
    if nc2.get('0x5e05b0', ['-'] * 8)[7] == 'ok' and base.get('0x5e05b0', ['-'] * 8)[7] == 'ok':
        print('[FAIL] NC2: [D] を外しても 0x5e05b0 が動作したまま (対照にならない)')
        ok = False
    if nc3.get('0x5e0d80', ['-'] * 8)[7] == 'ok':
        print('[FAIL] NC3: 非負制約を外しても 0x5e0d80 が動作したまま (対照にならない)')
        ok = False
    if not ok:
        raise SystemExit('[FAIL] negative control')
    print('== p0c4 negative control OK ==')
    return 0


if __name__ == '__main__':
    sys.exit(main())
