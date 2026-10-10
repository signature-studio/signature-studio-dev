#!/usr/bin/env python3
"""fw_rep.py — `__asm_rep_*` (rep movsb/movsq/stosb/stosq) 呼出しを固定署名の fw_rep_* へ正規化する.

RetDec は rep string 命令を `call void @__asm_rep_<op>(dst, src, len)` 系 helper 呼出しにするが,
chunk 毎に引数個数 (3/4/5/1) と型 (ptr/i64) が揺れる → liftlib simd gen の canon 名が崩れ
(`__v??q` 等の不正シンボル)、helper 意味も呼出し毎に不定になる。
本 pass は全 call site を 3 引数の固定名へ揃え, 実装は fw_rt.c 側に置く:
    fw_rep_movsb(dst, src, bytes) / fw_rep_movsq(dst, src, qwords)
    fw_rep_stosb(dst, val8, bytes) / fw_rep_stosq(dst, val64, qwords)
  (m11 REPORT #2 の実測: movsq/stosq の len は qword 数)

  python3 fw_rep.py IN.ll OUT.ll
"""
import re, sys

OPS = ('movsb_memcpy', 'movsq_memcpy', 'stosb_memset', 'stosq_memset')
CALL_RE = re.compile(r'(call void @__asm_rep_(\w+)\()')


def split_args(s):
    parts, depth, last = [], 0, 0
    for i, c in enumerate(s):
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif c == ',' and depth == 0:
            parts.append(s[last:i])
            last = i + 1
    parts.append(s[last:])
    return [p.strip() for p in parts if p.strip()]


def norm_arg(a, op, pos):
    """引数に型接頭辞が無ければ付ける (mov 系: pos0/1=ptr, pos2=i64 / stosb: pos1=i8)"""
    if ' ' in a:
        return a
    if op.startswith('mov') or op == 'stosq_memset':
        return ('ptr ' + a) if pos < 2 else ('i64 ' + a)
    if op == 'stosb_memset':
        return ('ptr ' + a) if pos == 0 else (('i8 ' + a) if pos == 1 else ('i64 ' + a))
    return a


def main():
    src, dst = sys.argv[1], sys.argv[2]
    lines = open(src, errors='replace').read().split('\n')
    n = 0
    decl_needed = set()
    out = []
    for l in lines:
        if l.startswith('declare ') and '@__asm_rep_' in l:
            continue        # 旧 declare は捨てる (固定 declare を生成し直す)
        m = CALL_RE.search(l)
        if m and m.group(2) in OPS:
            op = m.group(2)
            head = l[:m.start(1)]
            j = m.end(1)                      # '(' の次
            depth, k = 1, j
            for k in range(j, len(l)):
                if l[k] == '(':
                    depth += 1
                elif l[k] == ')':
                    depth -= 1
                    if depth == 0:
                        break
            args = split_args(l[j:k])
            tail = l[k + 1:]
            while len(args) < 3:
                args.append('null' if len(args) < 2 else '0')
            args = [norm_arg(a, op, i) for i, a in enumerate(args[:3])]
            nm = 'fw_rep_' + op.split('_')[0]
            if op.startswith('mov'):
                decl_needed.add('declare void @%s(ptr, ptr, i64) local_unnamed_addr' % nm)
            elif op == 'stosb_memset':
                decl_needed.add('declare void @%s(ptr, i8, i64) local_unnamed_addr' % nm)
            else:
                decl_needed.add('declare void @%s(ptr, i64, i64) local_unnamed_addr' % nm)
            out.append(head + 'call void @%s(%s)%s' % (nm, ', '.join(args), tail))
            n += 1
            continue
        out.append(l)
    # declare を挿入 (最初の define の前)
    ins = sorted(decl_needed)
    for i, l in enumerate(out):
        if l.startswith('define '):
            out[i:i] = ins
            break
    open(dst, 'w').write('\n'.join(out))
    print('[rep] normalized call sites: %d / declares added: %d' % (n, len(decl_needed)))


if __name__ == '__main__':
    main()
