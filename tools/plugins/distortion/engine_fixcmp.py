#!/usr/bin/env python3
"""[engine-local] `icmp P ptr %a, %b` で片辺が i64 値 (仮引数 / i64 を返す命令) の型不整合を `inttoptr` 挿入で解消する。
観測: C++ engine の lift IR で `%11 = icmp eq ptr %10, %arg3` (%arg3 は i64 仮引数) → clang "'%arg3' defined with type 'i64' but expected 'ptr'"。
fix_ptr_params.py (T1 用) は仮引数型と call site のみを直し、ptr 同士の比較に混入した i64 被演算子は扱わない。
本 pass は distortion (PLG-F6 #203) の engine lift 専用 (共有 lift 鎖には入れていない)。
usage: engine_fixcmp.py IN.ll OUT.ll   (stderr: 修正箇所数)
"""
import re, sys
src = open(sys.argv[1]).read().split('\n')
out, n = [], 0
i64 = set()
uid = 0
for l in src:
    m = re.match(r'^define .*?@[\w.$]+\((.*)\)', l)
    if m:
        i64 = set(re.findall(r'i64 (%[\w.$]+)', m.group(1)))
    else:
        d = re.match(r'^\s*(%[\w.$]+) = (?:ptrtoint .* to i64|(?:add|sub|mul|and|or|xor|shl|lshr|ashr|select|load|zext|sext|trunc|call) (?:i1 [^,]+, )?i64\b)', l)
        if d:
            i64.add(d.group(1))
    c = re.match(r'^(\s*)(%[\w.$]+) = icmp (\w+) ptr (\S+), (\S+)$', l)
    if c:
        ind, dst, pred, a, b = c.groups()
        new = []
        for k, v in (('a', a), ('b', b)):
            if v in i64:
                uid += 1
                t = '%s.ip%d' % (v, uid)
                new.append('%s%s = inttoptr i64 %s to ptr' % (ind, t, v))
                if k == 'a':
                    a = t
                else:
                    b = t
        if new:
            out.extend(new)
            l = '%s%s = icmp %s ptr %s, %s' % (ind, dst, pred, a, b)
            n += len(new)
    out.append(l)
open(sys.argv[2], 'w').write('\n'.join(out))
print('engine_fixcmp: patched operands =', n, file=sys.stderr)
