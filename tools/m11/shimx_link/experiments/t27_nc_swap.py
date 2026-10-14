#!/usr/bin/env python3
"""#1630 SHX-T27 ネガコン: fresh IR の指定関数だけを stale IR (work-m11 素材の boot_final3.ll) の本体に差し替える。
  python3 t27_nc_swap.py <stale.ll> <fresh.ll> <out.ll> <hex VA>...   (例: 44bae0)
差し替え後の out.ll を work/boot_final3.ll に置いて build.sh --trace --soft すると、その関数の alloca 拡幅の有無だけが違う IR で比べられる。
"""
import re,sys
stale_p, fresh_p, out_p = sys.argv[1:4]
fns = sys.argv[4:]
st=open(stale_p).read(); fr=open(fresh_p).read()
def span(s,n):
    m=re.search(r'^define [^\n]*@function_%s\(.*?^}\n'%n,s,re.M|re.S)
    return m
for n in fns:
    a=span(st,n); b=span(fr,n)
    fr=fr[:b.start()]+a.group(0)+fr[b.end():]
open(out_p,'w').write(fr)
print('swapped',fns)
