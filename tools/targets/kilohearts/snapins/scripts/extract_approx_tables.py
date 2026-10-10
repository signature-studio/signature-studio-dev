#!/usr/bin/env python3
"""extract_approx_tables.py — 実機 (AMD Ryzen 9 9950X) の rcpps / rsqrtps 近似表を抽出し
gen_simd.py が参照する 1 ファイル (scripts/approx_tables.b64) を生成する。

定義 (規則 36):
  - 表 = 「e=127 基準の mantissa field (下位 23bit)」を exponent field の偶奇で分けた 3 表。
      rcp    : rcpps  用, m = mantissa 上位 12bit (0..4095)
      rsq_odd : rsqrtps 用, 入力の exponent field が奇数のとき
      rsq_even: rsqrtps 用, 入力の exponent field が偶数のとき (√2 因子が入るため別表)
  - サイズ = 3 表 × 4096 エントリ × 4B (uint32, 上位 9bit は 0) = 49,152 B → base64 65,536 文字。
  - 検証 = approx_probe.c の verify モード (全グリッド 1,040,384 + 乱数 N) で
    emu_* (本表と同じ構造) と実機命令が bit 一致すること。不一致 0 であることを出力する。
  - 本スクリプトは approx_probe.c をコンパイルして動かすだけ (近似表の値は実機から取る)。
    CPU 非依存の closed form では再現できないことを formula モードで併記する。

usage: extract_approx_tables.py [--rand N]   (既定 rand=500000)
"""
import argparse
import base64
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE_SRC = os.path.join(HERE, 'approx_probe.c')
PROBE_BIN = os.path.join(HERE, '..', 'work', 'approx_probe')
OUT = os.path.join(HERE, 'approx_tables.b64')
NENT = 4096


def build_probe():
    r = subprocess.run(['cc', '-O2', '-msse', '-mno-avx', '-o', PROBE_BIN, PROBE_SRC],
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stdout, r.stderr)
        raise SystemExit('compile failed')
    return PROBE_BIN


def run(binpath, *args):
    r = subprocess.run([binpath] + list(args), capture_output=True, text=True)
    if r.returncode:
        raise SystemExit('probe failed: %s\n%s' % (' '.join(args), r.stderr))
    return r.stdout


def parse_tab(txt):
    v = [int(x) for x in txt.strip().strip('[]').split(',')]
    assert len(v) == NENT, len(v)
    for x in v:
        assert 0 <= x < (1 << 23), x
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rand', type=int, default=500000)
    a = ap.parse_args()
    binpath = build_probe()

    # 1) closed form では再現できないことの実測 (近似式精緻化の否定材料)
    fx = run(binpath, 'formula').strip()
    print('[formula]', fx)

    # 2) 3 表抽出
    tabs = {}
    for key, idx in (('rcp', '0'), ('rsq_odd', '1'), ('rsq_even', '2')):
        tabs[key] = parse_tab(run(binpath, 'table', idx))
        print('[table] %-9s entries=%d distinct=%d' % (key, NENT, len(set(tabs[key]))))

    # 3) 表サイズの実測
    print('[size]', run(binpath, 'size').strip())

    # 4) 分解モデル (= gen_simd ヘルパと同一構造) の実機照合
    for line in run(binpath, 'verify', str(a.rand)).strip().split('\n'):
        print('[verify]', line)

    # 5) base64 出力 (3 表連結, little-endian uint32)
    blob = b''
    for key in ('rcp', 'rsq_odd', 'rsq_even'):
        blob += b''.join(struct.pack('<I', x) for x in tabs[key])
    assert len(blob) == 3 * NENT * 4, len(blob)
    b64 = base64.b64encode(blob).decode()
    with open(OUT, 'w') as f:
        f.write('# rcpps / rsqrtps 近似表 (AMD Ryzen 9 9950X 実機抽出, 2026-10-11)\n')
        f.write('# 生成: python3 scripts/extract_approx_tables.py  (approx_probe.c 経由)\n')
        f.write('# 構造: T[idx] = (e=127 基準の mantissa field, 23bit)。')
        f.write('rcp=mantissa>>11 / rsq_odd,rsq_even = rsqrtps の e 奇/偶\n')
        f.write('# 並び: rcp[4096] ++ rsq_odd[4096] ++ rsq_even[4096], little-endian uint32\n')
        f.write('# サイズ: 12288 エントリ / 49152 B → base64 %d 文字\n' % len(b64))
        for i in range(0, len(b64), 76):
            f.write(b64[i:i + 76] + '\n')
    print('[out]', OUT, os.path.getsize(OUT), 'B')


if __name__ == '__main__':
    main()
