#!/usr/bin/env python3
"""trap114_probe_5280.py: trap 114 (halt0) が function_4128b0__lifted のどちらの call site を通るかを採る IR 変種 (#5280 受入 1・診断用)。
 使い方: python3 trap114_probe_5280.py <in.ll> <out.ll>
   in.ll は prod fix の IR (prod_order_3608.sh h_nor8b fix ... が作る work/p3608/h_nor8b/prod.ll) を想定する。
 記録 (guest 線形メモリ 0x11FF8200 以降。既存 probe の 0x11FF8000・0x11FF9000 と重ならない):
   +0  entry 通過回数 (function_4128b0__lifted の entry)
   +8  entry 時の global 18787760 (flag・0 なら 4128d6 から分岐)
   +16 entry 時の global 18787504 (i8 の状態)
   +24 entry 時の global 18768032
   +32 call site A (IR 117917 相当: 18787752 を渡す) の通過回数
   +40 call site B (IR 118017 相当: 18787456 を渡す) の通過回数
   +48 最後に通過した call site (1 = A・2 = B・0 = 無し)
 call site の特定は、元 IR の `call i64 @function_412770(ptr ... 18787752 ...)` と `... 18787456 ...` の行で行う。"""
import re, sys

BASE = 0x11FF8200
ENTRY_FN = 'function_4128b0__lifted'
SITE_A = 'inttoptr (i64 18787752 to ptr)'
SITE_B = 'inttoptr (i64 18787456 to ptr)'
GLOBALS = (18787760, 18787504, 18768032)


def slot(off):
    return 'inttoptr (i64 %d to ptr)' % (BASE + off)


def bump(tag, off):
    return [
        '  %%p%s_ld = load i64, ptr %s, align 8' % (tag, slot(off)),
        '  %%p%s_nx = add i64 %%p%s_ld, 1' % (tag, tag),
        '  store i64 %%p%s_nx, ptr %s, align 8' % (tag, slot(off)),
    ]


def main(src, dst):
    lines = open(src, errors='replace').read().split('\n')
    start = next(i for i, l in enumerate(lines) if re.match(r'^define .*@%s\(' % re.escape(ENTRY_FN), l))
    end = next(i for i in range(start, len(lines)) if lines[i] == '}')
    out = []
    n_site = 0
    for i, l in enumerate(lines):
        if start <= i <= end and l.lstrip().startswith('dec_label_pc_4128b0:'):
            out.append(l)
            out.append('  ; trap114_probe entry')
            out += bump('e', 0)
            for k, g in enumerate(GLOBALS):
                out.append('  %%pg%d = load i64, ptr inttoptr (i64 %d to ptr), align 8' % (k, g))
                out.append('  store i64 %%pg%d, ptr %s, align 8' % (k, slot(8 + 8 * k)))
            continue
        if start <= i <= end and 'call i64 @function_412770(' in l and (SITE_A in l or SITE_B in l):
            tag = 'sa' if SITE_A in l else 'sb'
            off, mark = (32, 1) if SITE_A in l else (40, 2)
            n_site += 1
            indent = l[:len(l) - len(l.lstrip())]
            out += ['  ; trap114_probe site %s' % tag]
            out += bump(tag, off)
            out.append('%sstore i64 %d, ptr %s, align 8' % (indent, mark, slot(48)))
            out.append(l)
            continue
        out.append(l)
    if n_site != 2:
        sys.exit('[trap114_probe_5280] call site が 2 つでない (%d)' % n_site)
    open(dst, 'w').write('\n'.join(out))
    print('[trap114_probe_5280] entry 1・call site 2 を計装 -> %s' % dst)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
