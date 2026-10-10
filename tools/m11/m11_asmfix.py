#!/usr/bin/env python3
# M11 #6: __asm_* helper 名衝突の解消 (chunkマージ後に同名異签名 decl が共存する問題).
# 使い方: python3 m11_asmfix.py IN.ll OUT.ll
import re
from collections import Counter


def main():
    src, dst = sys.argv[1], sys.argv[2]
    text = open(src).read()
    patd = re.compile(r'^declare (\S+) (@__asm_[\w.$-]+)\((.*?)\) local_unnamed_addr$', re.M)
    pata = re.compile(r'call (\S+) (@__asm_[\w.$-]+)\(([^()]*?)\)')
    decls = patd.findall(text)
    vals = [(nm.replace("@", "", 1), ret, tuple(x.strip().split()[0] for x in args.split(',') if x.strip()))
            for (ret, nm, args) in decls]
    combos, seen = [], set()
    for v in vals:
        if v not in seen:
            seen.add(v)
            combos.append(v)
    used, suffix_of = {}, {}
    for (nm, ret, tys) in combos:
        used.setdefault(nm, 0)
        used[nm] += 1
        suffix_of[(nm, ret, tys)] = nm if used[nm] == 1 else '%s__11%d' % (nm, used[nm])
    names = Counter()
    for k in suffix_of:
        names[suffix_of[k]] += 1
    dupnames = [n for n, v in names.items() if v > 1]
    print('[asmfix] combos: %d / suffix assigned: %d / dup names: %d %s'
          % (len(combos), len([k for k, v in suffix_of.items() if v != k[0]]),
             len(dupnames), dupnames[:4]))

    def rep_call(m):
        ret, nm, args = m.group(1), m.group(2)[1:], m.group(3)
        tys = tuple(x.strip().split()[0] for x in args.split(',') if x.strip())
        new = suffix_of.get((nm, ret, tys))
        if new is None or new == nm:
            return m.group(0)
        return 'call %s @%s(%s)' % (ret, new, args)

    def rep_decl(m):
        ret, nm, args = m.group(1), m.group(2)[1:], m.group(3)
        tys = tuple(x.strip().split()[0] for x in args.split(',') if x.strip())
        new = suffix_of.get((nm, ret, tys))
        if new is None or new == nm:
            return m.group(0)
        return 'declare %s @%s(%s) local_unnamed_addr' % (ret, new, args)

    text = patd.sub(rep_decl, text)
    text = pata.sub(rep_call, text)
    open(dst, 'w').write(text)
    ds = patd.findall(open(dst).read())
    c = Counter(x[1] for x in ds)
    rem = [k for k, v in c.items() if v > 1]
    print('[asmfix] remaining dup-decl:', len(rem))


import sys
if __name__ == '__main__':
    main()
