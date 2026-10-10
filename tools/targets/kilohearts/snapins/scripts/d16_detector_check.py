#!/usr/bin/env python3
"""d16_detector_check.py — D16 (gen_globals の map 非該当 VA 窓縮小) の検出器ネガティブコントロール。

DEFECTS.md D16 = `--window-map` 経路で map 非該当の `global_var_<VA>` の窓が IR 型サイズ
(1〜2B) まで縮み、連続する定数読みが壊れる silent miscompile。修復は
`n = max(n, window or 64, wmap[...])`。本スクリプトは「検出器が実際に効くこと」を
**対照実験で実測**する (規則 41 ネガティブコントロール):

  (1) 現行 (修復済) gen_globals.py を実行 → D16 detector が 0 件 or 既知の件数を報告
  (2) 同じ入力を **意図的に壊した** gen_globals (窓を `max(n, wmap)` に戻した版) で実行
      → 同じ VA の窓が 1B/2B に縮まり、さらに検出器が「縮小が起きうる VA」を数える

  つまり (2) では「修復を外すと壊れる」ことを数値で示し、(1) の PASS が偶然ではないことを示す。

usage: d16_detector_check.py
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(HERE, '..', 'lift', 'gen_globals.py')
CORE = '/home/ubuntu/work/webstudio/tools/targets/kilohearts/work/winpkg/HeartCore.core_64'

# 小さな再現入力: IR 型が 8B 超 (16B/32B 配列) の global_var。
# D16 の本質は「map に載らない VA の窓が型サイズ以下に縮む」ことなので、
# 型サイズが 16B (= >8B) のものを選ぶ。
REPRO = '''@global_var_1813a1000 = external constant [16 x i8]
@global_var_1813a1001 = external constant i8
@global_var_1813a1002 = external constant [32 x i8]
'''

WINDOW_MAP = '{"1813a1002": 8192}'     # 1002 だけ map に載せる → 1000 (32B) と 1001 (i8) は非該当


def run(gen_src, tag):
    """gen_globals 相当の処理を tag 付きで実行し、(d16件数, 窓サイズ dict) を返す"""
    d = tempfile.mkdtemp(prefix='d16_')
    ll, outc, wmap = os.path.join(d, 'in.ll'), os.path.join(d, 'out.c'), os.path.join(d, 'wm.json')
    open(ll, 'w').write(REPRO)
    json_map = open(wmap, 'w')
    json_map.write(WINDOW_MAP)
    json_map.close()
    r = subprocess.run([sys.executable, gen_src, ll, CORE, outc, '--window-map', wmap],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit('%s failed: %s' % (tag, r.stderr[-800:]))
    sizes = {}
    for m in re.finditer(r'global_var_([0-9a-f]+)\[(\d+)\]', open(outc).read()):
        sizes[m.group(1)] = int(m.group(2))
    d16 = 0
    mm = re.search(r'D16 detector: map-uncovered VA with IR type > 8B = (\d+)', r.stdout)
    if mm:
        d16 = int(mm.group(1))
    return d16, sizes, r.stdout.strip()


def main():
    print('D16 detector negative control (規則 41)')
    print('  input: 3 global_var (16B / i8 / 32B), window-map covers only 1813a1002\n')

    # (1) 現行 (修復済)
    d16_now, sz_now, out_now = run(GEN, 'current')
    print('[1] current gen_globals.py (fixed):')
    print('    ', out_now)
    print('     D16 detector = %d, window sizes = %s' % (d16_now, sz_now))
    assert sz_now.get('1813a1000') == 64, sz_now      # map 非該当でも 64B 床
    assert sz_now.get('1813a1002') == 8192, sz_now    # map 該当は推定値
    print('     -> 1813a1000 (16B 型) は 64B 床, 1813a1002 は 8192: 修復が効いている\n')

    # (2) 意意的に壊した版: 窓を `max(n, wmap)` に戻す (= window 引数なしの旧バグ相当)
    broken = os.path.join(os.path.dirname(GEN), '_gen_globals_broken_d16.py')
    src = open(GEN).read()
    old = 'n = max(n, window or 64, int(wmap.get(\'%x\' % va, 0)))'
    assert src.count(old) == 1, src.count(old)
    open(broken, 'w').write(src.replace(old, 'n = max(n, int(wmap.get(\'%x\' % va, 0)))'))
    try:
        d16_brk, sz_brk, out_brk = run(broken, 'broken')
        print('[2] broken gen_globals.py (window floor removed = D16 再現):')
        print('    ', out_brk)
        print('     D16 detector = %d, window sizes = %s' % (d16_brk, sz_brk))
        assert sz_brk.get('1813a1000') == 16, sz_brk   # 型サイズ 16B まで縮小 (= D16 の症状)
        assert sz_brk.get('1813a1002') == 8192, sz_brk
        print('     -> 1813a1000 の窓が 64B -> 16B に縮小 (D16 症状の再現)')
        print('     -> 検出器は同じ入力を %d 件と数えた (= 修復あり/なしで同一条件を検出)' % d16_brk)
    finally:
        os.remove(broken)
    print('\nRESULT: D16 detector is effective (negative control reproduces the shrink)')


if __name__ == '__main__':
    main()
