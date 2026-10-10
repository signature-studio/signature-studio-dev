#!/usr/bin/env python3
"""[P-C1] RetDec の `or.cond` 誤畳み込み (XNOR 化) の opt-in 修復 (plugins 追加 pass)。

観測 (Fruity Balance mix kernel 0x5dee90, block 5def32):
    cmp eax,[1.0f] ; jne general    ; ← 条件 B
    cmp rdx,rdi    ; je  ret        ; ← 条件 A (rdx==rdi)
  原義:  早期 return = (B が等しい) AND (A)
  RetDec IR: %or.cond = icmp eq i1 %A, %B ; br i1 %or.cond, label %ret, label %general
  → A,B がともに偽の場合も ret になる (XNOR)。 差分試験 (native 機械語比較) で A=false,B=false の入力で検出。
本 pass は **指定関数内の `%or.cond = icmp eq i1 %a, %b` のみ** `and i1 %a, %b` に置換する (opt-in; 無差別適用は不可)。
使い方: fix_orcond_xnor.py IN.ll OUT.ll --func function_5dee90 [--func ...]
"""
import re, sys

def main():
    inp, outp = sys.argv[1], sys.argv[2]
    funcs = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--func']
    lines = open(inp).read().split('\n')
    cur = None
    n = 0
    for i, l in enumerate(lines):
        m = re.match(r'^define \S+ @([\w.$]+)\(', l)
        if m:
            cur = m.group(1)
        if cur in funcs:
            mm = re.match(r'^(\s*)(%or\.cond\w*) = icmp eq i1 (%[\w.\-]+), (%[\w.\-]+)\s*$', l)
            if mm:
                lines[i] = '%s%s = and i1 %s, %s' % mm.groups()
                n += 1
    open(outp, 'w').write('\n'.join(lines))
    print('[P-C1] or.cond XNOR→AND: %d 件 (funcs=%s)' % (n, funcs), file=sys.stderr)

if __name__ == '__main__':
    main()
