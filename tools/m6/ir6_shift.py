#!/usr/bin/env python3
# M6 #6: IR アドレスリマップ (RetDec IR の VA 0x180000000+RVA → 0x30000000+RVA):
#   1. @global_var_18xxxxxx シンボル名を @global_var_<SHIFTEDVA-hex> に rename (整合)
#   2. IR 整数定数 0x180000000-0x1803FFFFF (VA 直値) を SHIFT
#   3. m6_data.c (m6_data_gen.py) は 0x30000000+RVA に敷設する形に対応
import sys, re

BASE = 0x180000000
NEWBASE = 0x30000000
MAXV = 0x1803FFFFF
SHIFT = BASE - NEWBASE

def shiftva(v):
    if BASE <= v <= MAXV:
        return v - SHIFT
    return None


def main():
    src, dst = sys.argv[1], sys.argv[2]
    text = open(src).read()
    # 1. global var rename (base placed)
    def rename_sym(m):
        h = m.group(1)
        v = int(h, 16)
        nv = shiftva(v)
        if nv is None:
            return m.group(0)
        return '@global_var_%x' % nv
    text = re.sub(r"@global_var_(18[0-9a-fA-F]{6,10})\b", rename_sym, text)
    # 2. 数値定数 (inttoptr / store i64 / etc.)
    n = [0]
    def rep_num(m):
        if m.group(1) == '0':
            return m.group(0)
        (lit,) = m.groups()
        v = int(lit, 0)
        nv = shiftva(v)
        if nv is None:
            return m.group(0)
        n[0] += 1
        return 'i64 ' + str(nv)
    text = re.sub(r"i64 (0x1[0-9a-fA-F]{8,12}|[0-9]{9,11})", rep_num, text)
    print('[shift] numeric replaced:', n[0])
    open(dst, 'w').write(text)


if __name__ == '__main__':
    main()
