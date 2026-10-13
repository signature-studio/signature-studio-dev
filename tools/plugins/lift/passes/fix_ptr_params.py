#!/usr/bin/env python3
"""[P-T1] 定義済み関数の `ptr %argN` 仮引数を `i64` に統一 (plugins 追加 pass)。
観測: RetDec が `define i64 @function_72bae0(i64 %arg1, ptr %arg2, ptr %arg3)` と ptr 型で引数を宣言する一方、
本体は `inttoptr i64 %arg2 to ptr` (i64 前提) で使うため clang が "'%arg2' defined with type 'ptr' but expected 'i64'" で拒否
(T1 バッチ 45 本中 7 本)。 module 内で define された関数のみ対象:
  - define / declare の `ptr %argN` / `ptr` 引数型 → i64
  - module 内 call site の `ptr X` 実引数 → `ptrtoint ptr X to i64` を直前に挿入して `i64` で渡す
使い方: fix_ptr_params.py IN.ll OUT.ll"""
import re, sys

src = open(sys.argv[1]).read().split('\n')
sig = {}   # name -> list of arg types
for l in src:
    m = re.match(r'^define (\S+) @([\w.$]+)\((.*)\)', l)
    if m:
        args = [a.strip() for a in re.split(r',\s*(?![^()]*\))', m.group(3)) if a.strip()]
        types = [a.split()[0] for a in args]
        if 'ptr' in types:
            sig[m.group(2)] = types
out = []
nd = nc = 0
uid = 0
for l in src:
    m = re.match(r'^(define|declare) (\S+) @([\w.$]+)\((.*?)\)(.*)$', l)
    if m and m.group(3) in sig:
        args = [a.strip() for a in re.split(r',\s*(?![^()]*\))', m.group(4)) if a.strip()]
        args2 = []
        for a in args:
            t = a.split(' ', 1)
            args2.append(('i64 ' + t[1].split()[-1]) if t[0] == 'ptr' and len(t) > 1 and t[1].split()[-1].startswith('%') else ('i64' if a == 'ptr' else ('i64 ' + t[1] if t[0] == 'ptr' and len(t) > 1 else a)))
        l = '%s %s @%s(%s)%s' % (m.group(1), m.group(2), m.group(3), ', '.join(args2), m.group(5))
        nd += 1
        out.append(l)
        continue
    mc = re.match(r'^(\s*)((?:%[\w.\-]+ = )?)(call|tail call) (\S+) @([\w.$]+)\((.*)\)(.*)$', l)
    if mc and mc.group(5) in sig:
        args = [a.strip() for a in re.split(r',\s*(?![^()]*\))', mc.group(6)) if a.strip()]
        new = []
        for a in args:
            t = a.split(' ', 1)
            if t[0] == 'ptr' and len(t) > 1:
                uid += 1
                nm = '%%pt1_%d' % uid
                val = re.sub(r'^(?:(?:nonnull|noundef|readonly|writeonly|noalias|nocapture)\s+|align\s+\d+\s+|dereferenceable\(\d+\)\s+)+', '', t[1].strip())
                out.append('%s%s = ptrtoint ptr %s to i64' % (mc.group(1), nm, val))
                new.append('i64 ' + nm)
                nc += 1
            else:
                new.append(a)
        l = '%s%s%s %s @%s(%s)%s' % (mc.group(1), mc.group(2), mc.group(3), mc.group(4), mc.group(5), ', '.join(new), mc.group(7))
    out.append(l)
# 本体: 変更した関数内で ptr 文脈の `%argN` 使用 (`ptr %argN`) を inttoptr 経由に置換
res = []
cur = None
curptr = set()
nu = 0
uid2 = 0
for l in out:
    m = re.match(r'^define (\S+) @([\w.$]+)\((.*)\)', l)
    if m:
        cur = m.group(2)
        curptr = {i + 1 for i, t in enumerate(sig.get(cur, [])) if t == 'ptr'}
        res.append(l)
        continue
    if l.startswith('}'):
        cur = None
        curptr = set()
        res.append(l)
        continue
    if cur in sig and curptr:
        for i in sorted(curptr):
            # `icmp P ptr %a, %argN` / `icmp P ptr %argN, %b`: 型が先頭オペランドにしか付かず `ptr %argN` に一致しない (E1)
            mi = re.match(r'^(\s*)(%[\w.\-]+) = icmp (\w+) ptr (\S+), (\S+)(.*)$', l)
            if mi and not l.lstrip().startswith('phi'):
                ind, dst, pred, a, b, tail = mi.groups()
                a2, b2, pre = a, b, []
                for k, v in (('a', a), ('b', b)):
                    if v == '%%arg%d' % i:
                        uid2 += 1
                        nm = '%%pt1p_%d' % uid2
                        pre.append('%s%s = inttoptr i64 %s to ptr' % (ind, nm, v))
                        if k == 'a':
                            a2 = nm
                        else:
                            b2 = nm
                if pre:
                    res.extend(pre)
                    l = '%s%s = icmp %s ptr %s, %s%s' % (ind, dst, pred, a2, b2, tail)
                    nu += 1
            pat = re.compile(r'\bptr (?:nonnull |noundef |readonly )*%arg' + str(i) + r'\b')
            if pat.search(l) and not l.lstrip().startswith('phi') and 'inttoptr i64 %%arg%d to ptr' % i not in l:
                uid2 += 1
                nm = '%%pt1p_%d' % uid2
                res.append('  %s = inttoptr i64 %%arg%d to ptr' % (nm, i))
                l = pat.sub('ptr ' + nm, l)
                nu += 1
    res.append(l)
out = res
print('[P-T1] 本体の ptr 文脈 %%argN 使用 → inttoptr: %d 件' % nu, file=sys.stderr)
open(sys.argv[2], 'w').write('\n'.join(out))
print('[P-T1] ptr 仮引数→i64: sig %d 件 / call site %d 件' % (nd, nc), file=sys.stderr)
