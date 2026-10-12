#!/usr/bin/env python3
"""ir_fix_mask.py IN.ll OUT.ll — RetDec が 64bit 上位 32bit mask (`and r, 0xffffffff00000000`) を
   `icmp ult X, -4294967295 ; add X, 4294967295 ; select c, X, add` に誤 lower した箇所を `and X, -4294967296` に直す。
   (Dekker 風の hi 切り出し。OTT CRT 1801aa1a0 の r8!=0 経路 = tan/atan 系。症状: 入力 ~25% で 1ulp 差)
   出力: 修復件数を stdout に JSON 1 行。0 件でも正常終了 (対象 PE に該当が無いだけ)。"""
import json, re, sys

PAT = re.compile(
    r'^(?P<i>\s*)(?P<c>%[\w.]+) = icmp ult i64 (?P<x>%[\w.]+), -4294967295\n'
    r'\s*(?P<a>%[\w.]+) = add i64 (?P=x), 4294967295\n'
    r'\s*(?P<d>%[\w.]+) = select i1 (?P=c), i64 (?P=x), i64 (?P=a)(?P<md>, !insn\.addr !\d+)?[ \t]*$', re.M)


def main():
    src, dst = sys.argv[1:3]
    text = open(src, errors='replace').read()
    n = 0

    def sub(m):
        nonlocal n
        n += 1
        return '%s%s = and i64 %s, -4294967296%s' % (m.group('i'), m.group('d'), m.group('x'), m.group('md') or '')
    text = PAT.sub(sub, text)
    open(dst, 'w').write(text)
    print(json.dumps({'hi32_mask_fixed': n}))


if __name__ == '__main__':
    main()
