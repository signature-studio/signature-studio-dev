#!/usr/bin/env python3
"""trap114_src_5280.py: trap 114 (halt0) で call site B の直前 memcpy の源 (%53) の 6 番目 qword を採る IR 変種 (#5280 受入 1 の残り・診断用)。
  使い方: python3 trap114_src_5280.py <in.ll> <out.ll>
  in.ll は prod fix の IR (prod_order_3608.sh h_nor8b fix ... が作る work/p3608/h_nor8b/prod.ll) を想定する。
  記録 (guest 線形メモリ 0x11FF8300 以降。trap114_probe_5280.py の 0x11FF8200 と重ならない):
    +0  memcpy 直前 (118010 行の直前) の通過回数
    +8  源 %53 のアドレス (ptr を i64 化)
    +16 源の 0 番目 qword (= 18787456 へ入る先頭)
    +24 源の 6 番目 qword (= 18787504 へ入る値)
    +32 源の 1 番目 qword (対照)
"""
import re, sys

BASE = 0x11FF8300
ENTRY_FN = 'function_4129'  # 注: 関数名は下で完全一致で探す
TARGET_FN = 'function_4128b0__lifted'
MEMCPY_LINE = 'call void @__asm_rep_movsq_memcpy(ptr inttoptr (i64 18787456 to ptr), ptr %53, i64 37)'


def slot(off):
    return 'inttoptr (i64 %d to ptr)' % (BASE + off)


def main(src, dst):
    lines = open(src, errors='replace').read().split('\n')
    start = next(i for i, l in enumerate(lines) if re.match(r'^define .*@%s\(' % re.escape(TARGET_FN), l))
    end = next(i for i in range(start, len(lines)) if lines[i] == '}')
    out = []
    n = 0
    for i, l in enumerate(lines):
        if start <= i <= end and l.strip() == MEMCPY_LINE:
            indent = l[:len(l) - len(l.lstrip())]
            out += [
                indent + '%w114_cnt = load i64, ptr ' + slot(0) + ', align 8',
                indent + '%w114_cnt1 = add i64 %w114_cnt, 1',
                indent + 'store i64 %w114_cnt1, ptr ' + slot(0) + ', align 8',
                indent + '%w114_src = ptrtoint ptr %53 to i64',
                indent + 'store i64 %w114_src, ptr ' + slot(8) + ', align 8',
                indent + '%w114_p0 = load i64, ptr %53, align 8',
                indent + 'store i64 %w114_p0, ptr ' + slot(16) + ', align 8',
                indent + '%w114_p6p = getelementptr i64, ptr %53, i64 6',
                indent + '%w114_p6 = load i64, ptr %w114_p6p, align 8',
                indent + 'store i64 %w114_p6, ptr ' + slot(24) + ', align 8',
                indent + '%w114_p1p = getelementptr i64, ptr %53, i64 1',
                indent + '%w114_p1 = load i64, ptr %w114_p1p, align 8',
                indent + 'store i64 %w114_p1, ptr ' + slot(32) + ', align 8',
            ]
            n += 1
        out.append(l)
    if n != 1:
        sys.exit('[trap114_src_5280] memcpy 行が 1 つでない (%d)' % n)
    open(dst, 'w').write('\n'.join(out))
    print('[trap114_src_5280] memcpy 直前の源を計装 -> %s' % dst)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
