#!/usr/bin/env python3
"""#5311 (GUI-27 残件): icall miss 先 (既定 0xfa9390) になる InitTable 添字を、m11_image.bin の静的読解で列挙する。
 使い方: python3 inittable_find.py [TARGET_VA]   (既定 0xfa9390。実行は tools/m11/work/m11_image.bin が必要)
 手順: image 内で count (u32) と units (u64 = units 配列の LVA) の組を持つ InitTable ヘッダを探す。
   count=942 (boot.json の units_total) かつ units の全 proc が非 0 の表を候補にする。
   各 units[k].proc が TARGET に一致する k を列挙し、boot の初期化範囲 (k < init_count=111) との交差を出す。
 注意: 静的読解の結果。実行時の init 順・skip の計数 (m11_ov.c の g_units_skipped) とは照合していない。"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, '..', '..', 'm11', 'work', 'm11_image.bin')
TARGET = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0xfa9390
COUNT = 942        # boot.json units_total
BOOT_INIT = 111    # boot.json init_count (InitUnits のループ添字 0..110)

img = open(IMG, 'rb').read()
q = lambda o: struct.unpack_from('<Q', img, o)[0]
d = lambda o: struct.unpack_from('<I', img, o)[0]

hdrs = []
for X in range(0, len(img) - 16, 4):
    if d(X) != COUNT:
        continue
    u = q(X + 8)
    if 0 < u and u + 16 * COUNT <= len(img):
        procs = [q(u + 16 * k) for k in range(COUNT)]
        if all(procs[:BOOT_INIT]):
            hdrs.append((X, u, procs))

print('InitTable 候補: %d 件 (count=%d)' % (len(hdrs), COUNT))
for X, u, procs in hdrs:
    ks = [k for k, p in enumerate(procs) if p == TARGET]
    boot = [k for k in ks if k < BOOT_INIT]
    print('header RVA=%#x units=%#x target=%#x' % (X, u, TARGET))
    print('  全 %d 件 (添字): %s' % (len(ks), ks))
    print('  boot 範囲 (k<%d) の件数 %d: %s' % (BOOT_INIT, len(boot), boot))
