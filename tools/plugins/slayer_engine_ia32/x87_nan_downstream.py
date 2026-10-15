#!/usr/bin/env python3
"""x87_nan_downstream.py: NaN どうしのビット差が後段の算術 (四則・符号・絶対値・比較・連鎖) に出るかを native と wasm で突合する (#5264 PLG-G2-73)。

  python3 x87_nan_downstream.py          native (-m32 freestanding・x87 命令) と wasm (emcc・tier 固定) を実行して突合
  python3 x87_nan_downstream.py --nega   ネガコン: wasm 出力の数値の 1 行を壊し、判定が FAIL することを確かめる

判定: 非 NaN の結果・比較 (cmp) の差は 0 件でなければ FAIL。 NaN どうしの差は分類して数える (合否に入れない)。
NaN と数値の混在 (nan-num) は 0 件でなければ FAIL。
"""
import os, subprocess, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work', 'nan_down')
SRC = os.path.join(HERE, 'x87_nan_downstream.c')
TIER = '--liftoff-only'


def run(cmd, what, timeout=600):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-1500:] + r.stderr[-1500:])
        sys.exit('[nan_down] FAIL: %s rc %d' % (what, r.returncode))


def build():
    os.makedirs(WORK, exist_ok=True)
    run(['gcc', '-m32', '-O1', '-fno-pic', '-fno-pie', '-fno-stack-protector', '-fcf-protection=none',
         '-fno-asynchronous-unwind-tables', '-ffp-contract=off', '-ffreestanding', '-nostdlib', '-static', '-no-pie',
         '-DNATIVE', '-o', os.path.join(WORK, 'native'), SRC], 'native build')
    run(['emcc', '-O1', '-ffp-contract=off', '-fno-fast-math', '-w', '-sENVIRONMENT=node',
         '-o', os.path.join(WORK, 'wasm_nd.cjs'), SRC], 'wasm build (emcc)')


def execute():
    nat = os.path.join(WORK, 'native.txt')
    wasm = os.path.join(WORK, 'wasm.txt')
    with open(nat, 'w') as f:
        subprocess.run([os.path.join(WORK, 'native')], stdout=f, check=True, timeout=60)
    r = subprocess.run(['node', TIER, os.path.join(WORK, 'wasm_nd.cjs')], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        sys.exit('[nan_down] FAIL: wasm run rc %d' % r.returncode)
    open(wasm, 'w').write(r.stdout)
    return nat, wasm


def isnan(u):
    return (u & 0x7F800000) == 0x7F800000 and (u & 0x007FFFFF) != 0


def parse(p):
    out = []
    for ln in open(p):
        t = ln.split()
        if not t:
            continue
        out.append((t[0], t[1], dict(x.split('=', 1) for x in t[2:])))
    return out


def compare(nat_rows, wasm_rows, quiet=False):
    cnt = collections.Counter()
    bad = 0
    for a, b in zip(nat_rows, wasm_rows):
        assert a[:2] == b[:2], 'row key mismatch'
        for k in a[2]:
            x, y = a[2][k], b[2][k]
            if x == y:
                continue
            if k == 'cmp':
                cls = 'cmp'
            else:
                xi, yi = int(x, 16), int(y, 16)
                if isnan(xi) and isnan(yi):
                    cls = 'nan-nan'
                elif isnan(xi) or isnan(yi):
                    cls = 'nan-num'
                else:
                    cls = 'num'
            cnt[(k, cls)] += 1
            if cls != 'nan-nan':
                bad += 1
    if not quiet:
        for key in sorted(cnt):
            print('[compare] %s %s: %d 件' % (key[0], key[1], cnt[key]))
    return bad, cnt


def main():
    if '--nega' in sys.argv:
        nat_p = os.path.join(WORK, 'native.txt')
        wasm_p = os.path.join(WORK, 'wasm.txt')
        if not (os.path.isfile(nat_p) and os.path.isfile(wasm_p)):
            sys.exit('[nan_down] FAIL: 先に python3 x87_nan_downstream.py を実行する')
        lines = open(wasm_p).read().splitlines()
        # 数値の結果 (add) を 1 ビット壊す。 NaN ではない行を選ぶ。
        for i, ln in enumerate(lines):
            t = ln.split()
            kv = dict(x.split('=', 1) for x in t[2:])
            if not isnan(int(kv['add'], 16)) and kv['add'] != '00000000':
                v = int(kv['add'], 16) ^ 1
                lines[i] = ln.replace('add=' + kv['add'], 'add=%08x' % v)
                break
        neg = os.path.join(WORK, 'wasm_nega.txt')
        open(neg, 'w').write('\n'.join(lines) + '\n')
        bad, _ = compare(parse(nat_p), parse(neg), quiet=True)
        if bad == 0:
            sys.exit('[nan_down] FAIL: ネガコンを検出できない')
        print('[nan_down] ネガコン: 数値の 1 bit 反転を検出 (非 NaN の差 %d 件)。 ネガコン OK' % bad)
        return
    build()
    nat, wasm = execute()
    bad, cnt = compare(parse(nat), parse(wasm))
    rows = len(parse(nat))
    nan_only = sum(v for (k, c), v in cnt.items() if c == 'nan-nan')
    print('[nan_down] 組 %d 行。 NaN どうしの差 %d 件 (合否に入れない)。 非 NaN・比較・混在の差 %d 件' % (rows, nan_only, bad))
    if bad:
        sys.exit('[nan_down] FAIL')
    print('[nan_down] PASS')


if __name__ == '__main__':
    main()
