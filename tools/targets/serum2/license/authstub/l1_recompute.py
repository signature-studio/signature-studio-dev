"""L1 復元 pass の前後 census を再計算する (#1009 受入 2・3)。

使い方: python3 l1_recompute.py <PE> <raw.ll> <outdir>
  raw.ll: RetDec raw IR (e2e.sh step [1] の work/lift/authstub.drc.ll)。
  出力: <outdir>/raw_base.ll (base 修復のみ = pass 無し = 脱落状態・ネガコン)
        <outdir>/raw_l1.ll   (base 修復 + liftlib.passes.l1_restore = pass 有り)
  各 IR に l1_census.py を実行し、期待する向き (pass 無し 0 / pass 有り 1 以上) を fail-closed で照合する。
  pass 有りの IR は llvm-as-18 で検査し、同じ pass の二重適用が SystemExit で拒否されることも確認する。
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', '..', '..', 'liftlib'))
from liftlib.passes import base as B  # noqa: E402
from liftlib.passes import l1_restore as L  # noqa: E402

PE, RAW, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
BASE_LL = os.path.join(OUT, 'raw_base.ll')
L1_LL = os.path.join(OUT, 'raw_l1.ll')


def write_base_and_l1():
    text = open(RAW).read()
    out, _ = B.run_base(text, B.make_args(infile=RAW, outfile=BASE_LL))
    open(BASE_LL, 'w').write(out)
    lines = out.splitlines()
    rep = L.restore_l1(lines)
    open(L1_LL, 'w').write('\n'.join(lines) + '\n')
    try:
        L.restore_l1(lines)
    except SystemExit as e:
        print('negctl 二重適用: SystemExit ->', e)
    else:
        raise SystemExit('negctl FAIL: 二重適用が拒否されなかった')
    print('l1_restore:', rep)


def census(ll):
    res = subprocess.run([sys.executable, os.path.join(HERE, 'l1_census.py'), PE, ll],
                         capture_output=True, text=True, check=True)
    d = {}
    for line in res.stdout.splitlines():
        k, v = line.rsplit('=', 1)
        d[k.strip()] = v.strip()
    return d


def llvm_as(ll):
    subprocess.run(['llvm-as-18', ll, '-o', os.devnull], check=True)


def expect(name, d, key, want):
    got = d[key]
    if got != str(want):
        raise SystemExit('%s: %s = %s (期待 %s)' % (name, key, got, want))


def main():
    write_base_and_l1()
    llvm_as(BASE_LL)
    llvm_as(L1_LL)
    off = census(BASE_LL)
    on = census(L1_LL)
    for k in sorted(off):
        print('%-48s pass無し=%-6s pass有り=%s' % (k, off[k], on.get(k)))
    machine = [k for k in off if k.startswith('machine')]
    for k in machine:
        if off[k] != on[k]:
            raise SystemExit('machine 側が pass で変化: %s' % k)
    ir_block = 'IR: block dec_label_pc_1800c2ef4 present'
    expect('pass無し', off, ir_block, 'False')
    expect('pass有り', on, ir_block, 'True')
    expect('pass無し', off, 'IR: insn.addr entries covering site', 0)
    expect('pass無し', off, 'IR: direct call in site range', 0)
    expect('pass無し', off, 'IR: edges (br/switch) into site block', 0)
    if int(on['IR: insn.addr entries covering site']) == 0:
        raise SystemExit('pass有り: insn.addr 被覆が 0 のまま')
    expect('pass有り', on, 'IR: direct call in site range', 1)
    if int(on['IR: edges (br/switch) into site block']) < 1:
        raise SystemExit('pass有り: 入口 edge が無い')
    print('l1_recompute OK')


if __name__ == '__main__':
    main()
