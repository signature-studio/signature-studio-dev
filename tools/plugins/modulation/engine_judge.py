#!/usr/bin/env python3
"""engine lift の到達性 gate (judge 相当・exit code 化)。 engine_lift.sh の出力 (work/modulation/engine<B>/) を判定する。

usage: engine_judge.py <outdir>     判定 (exit 0/1/2)
       engine_judge.py --selftest   合成入力のネガティブコントロール (NC) を実行 (全 NC が期待どおりなら exit 0)

合格条件 (1 つでも欠ければ exit 1):
  - lift_rc == 0 (RetDec 鎖)
  - erc3 == 0 (f80 段後の emcc -c rc)
  - 名前で照合しても define の無い range が 0 件 (engine_name_gap.py の rest と rest_bytes が 0)
入力不正 (summary.csv の欠落・列数・非整数、name_gap の失敗) は exit 2。
出力行には stub 件数 (unimpl_helpers) を必ず併記する。stub を含む emcc -c 通過は正しさを示さない。
"""
import csv
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
COLS = ['block', 'pdata_funcs', 'lift_rc', 'defines', 'f80_funcs', 'unimpl_helpers', 'emcc_c_rc', 'fixcmp_patched',
        'emcc_c_rc_after_fixcmp', 'lift_s', 'missing_define', 'missing_bytes', 'missing_ref', 'extra_inside',
        'function_defines', 'erc3']


def read_row(outdir):
    try:
        rows = [r for r in csv.reader(open(os.path.join(outdir, 'summary.csv'))) if r]
    except OSError as e:
        return None, 'summary.csv を読めない: %s' % e
    if not rows or len(rows[-1]) != len(COLS):
        return None, 'summary.csv の列数が %d でない: %r' % (len(COLS), rows[-1] if rows else None)
    try:
        return {k: int(v) for k, v in zip(COLS, rows[-1])}, None
    except ValueError:
        return None, 'summary.csv に整数でない値: %r' % rows[-1]


def name_gap(outdir):
    r = subprocess.run([sys.executable, os.path.join(HERE, 'engine_name_gap.py'), outdir],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None, 'engine_name_gap.py が失敗: %s' % r.stderr.strip()
    try:
        f = r.stdout.strip().split(',')
        return (int(f[0]), int(f[1]), int(f[2])), None
    except (ValueError, IndexError):
        return None, 'engine_name_gap.py の出力が想定外: %r' % r.stdout


def judge(outdir):
    """(exit_code, 1 行の報告) を返す。"""
    v, err = read_row(outdir)
    if err:
        return 2, 'engine_judge: %s' % err
    gap, err = name_gap(outdir)
    if err:
        return 2, 'engine_judge: %s' % err
    _, rest, rest_bytes = gap
    why = []
    if v['lift_rc'] != 0:
        why.append('lift_rc=%d' % v['lift_rc'])
    if v['erc3'] != 0:
        why.append('emcc_c_rc(erc3)=%d' % v['erc3'])
    if rest or rest_bytes:
        why.append('define 無し range %d 件 (%d B)' % (rest, rest_bytes))
    head = 'block=%d pdata=%d define=%d stub=%d' % (v['block'], v['pdata_funcs'], v['defines'], v['unimpl_helpers'])
    if why:
        return 1, 'engine_judge: FAIL %s; %s' % (head, '; '.join(why))
    return 0, 'engine_judge: PASS %s (到達性のみ。stub を含む、正しさは未確認)' % head


def write_fixture(d, row, ll, c, ranges):
    with open(os.path.join(d, 'summary.csv'), 'w') as f:
        f.write(row + '\n')
    with open(os.path.join(d, 'e.final.ll'), 'w') as f:
        f.write(ll)
    with open(os.path.join(d, 'e.drc.c'), 'w') as f:
        f.write(c)
    with open(os.path.join(d, 'ranges.txt'), 'w') as f:
        f.write(ranges)


def selftest():
    base = '18977,418,0,442,0,70,0,0,0,17,2,777,0,24,440,0'
    ll = ('define i32 @function_1000() {\n  ret i32 0\n}\n'
          'define i32 @function_2000() {\n  ret i32 0\n}\n')
    c = ('// Address range: 0x1000 - 0x1010\nint function_1000(void)\n{\n}\n'
         '// Address range: 0x2000 - 0x2010\nint function_2000(void)\n{\n}\n')
    ranges = '0x1000-0x1010,0x2000-0x2010'
    ll_one_entry = 'define i32 @entry_point() {\n  ret i32 0\n}\n'
    c_same_name = ('// Address range: 0x1000 - 0x1010\nint entry_point(void)\n{\n}\n'
                   '// Address range: 0x2000 - 0x2010\nint entry_point(void)\n{\n}\n')
    cases = [
        ('good', base, ll, c, 0, 'PASS'),
        ('NC lift_rc=1', base.replace(',418,0,', ',418,1,'), ll, c, 1, 'lift_rc=1'),
        ('NC erc3=1', base[:-1] + '1', ll, c, 1, 'emcc_c_rc(erc3)=1'),
        ('NC 欠落 range', base, ll.replace('function_2000', 'other_2000'), c, 1, 'define 無し'),
        ('NC 同名 2 range', base, ll_one_entry, c_same_name, 1, 'define 無し range 2 件'),
        ('NC 列数不足', base[:base.rfind(',')], ll, c, 2, '列数'),
        ('NC 非整数', base.replace(',418,', ',x,', 1), ll, c, 2, '整数'),
    ]
    ok = True
    for name, row, fl, fc, want, must in cases:
        with tempfile.TemporaryDirectory() as d:
            write_fixture(d, row, fl, fc, ranges)
            rc, line = judge(d)
            good = rc == want and must in line
            ok = ok and good
            print('%-14s exit=%d (want %d) %s | %s' % (name, rc, want, 'OK' if good else 'NG', line))
    with tempfile.TemporaryDirectory() as d:
        rc, line = judge(d)
        good = rc == 2 and 'summary.csv' in line
        ok = ok and good
        print('%-14s exit=%d (want 2) %s | %s' % ('NC 無し', rc, 'OK' if good else 'NG', line))
    print('selftest: %s' % ('OK' if ok else 'NG'))
    return 0 if ok else 1


def main(argv):
    if len(argv) == 2 and argv[1] == '--selftest':
        return selftest()
    if len(argv) != 2:
        print('usage: engine_judge.py <outdir> | --selftest', file=sys.stderr)
        return 2
    rc, line = judge(argv[1])
    print(line)
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv))
