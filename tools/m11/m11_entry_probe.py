#!/usr/bin/env python3
"""#1894: _CopyArray (function_416db0) の呼出し元関数の実行時到達を survey で判定するための entry probe (計測専用).

使い方:
  python3 m11_entry_probe.py work/boot_final3.ll work/s1894/boot_entry.ll --fns 12a3ff0,417110,417b70,418030,418280,4183d0,418700 --table work/s1894/entry_table.json
  (= 各関数の定義直後の entry 基本ブロックの先頭に `store volatile i32 1, ptr @m11_fe_<hex>` を入れる)

方式は m11_site_probe.py と同じ global への volatile store (呼出しを挟まない)。
呼出しを挟む probe は survey を変える (#1847 で確認) ため使わない。
probe の本体は work/obj/entry_probe.o (m11_entry_probe_rt.c) が持ち、survey 後に読み出す。
"""
import json, re, sys, argparse

DEF_RE = re.compile(r'^define [^@]*@function_([0-9a-f]+)\(')


def insert_probes(src, dst, fns):
    lines = open(src).read().split('\n')
    out, done = [], {}
    want = set(fns)
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = DEF_RE.match(line)
        if m and m.group(1) in want:
            # 関数定義の次の行から最初のラベル (entry) の直後に probe を入れる
            j = i + 1
            while j < len(lines) and not lines[j].endswith(':'):
                out.append(lines[j]); j += 1
            if j < len(lines):
                out.append(lines[j])
                out.append('  store volatile i32 1, ptr @m11_fe_%s' % m.group(1))
                done[m.group(1)] = 1
                i = j + 1
                continue
        i += 1
    text = '\n'.join(out)
    text = re.sub(r'(?m)^(target datalayout = .*)$',
                  lambda mm: mm.group(1) + '\n' + '\n'.join('@m11_fe_%s = external global i32' % f for f in fns),
                  text, count=1)
    open(dst, 'w').write(text)
    return done


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--fns', required=True, help='カンマ区切りの関数 VA hex (function_<hex> の hex)')
    ap.add_argument('--table', required=True, help='probe 表 (json) の出力先')
    a = ap.parse_args()
    fns = a.fns.split(',')
    done = insert_probes(a.src, a.dst, fns)
    missing = [f for f in fns if f not in done]
    json.dump({'fns': fns, 'inserted': sorted(done), 'missing': missing}, open(a.table, 'w'), indent=1)
    print('inserted', len(done), 'of', len(fns), 'missing', missing)
    if missing:
        sys.exit(1)
