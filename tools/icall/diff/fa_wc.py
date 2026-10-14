#!/usr/bin/env python3
"""fa_wc.py — BLK+0 (0x36319008) への書き込み元を IR store 単位で特定する watchpoint (ICALL-54 #1998)。

usage:
  fa_wc.py instr IN.ll OUT.ll   # 全 store の直前に __wchk(addr, size, val, line) を挿入する
  OUT.ll.fn.json                 # 行番号 -> 含まれる関数名 (instr が同時に出力)

対象: `store` 命令のうち整数・ptr・浮動小数・ベクタ型の全て (volatile / atomic 修飾を含む)。
値は bitcast / ptrtoint で整数化し、64bit を超える型は下位 64bit だけを渡す。
扱えない型 (集成体 [N x T] / {...}・vector of ptr・scalable vector) は挿入せず件数を出す。
監視の対象外: llvm.memcpy / llvm.memset などの intrinsic、cmpxchg / atomicrmw、
C 側 (oi.*.c・rt/*.c) の書込み、emscripten の libc (memcpy 等) による書込み。

__wchk は tools/icall/diff/fa_wc_rt.c が定義する。範囲 [WLO, WHI) と重なる store と、
値 "emsc" の store を "WC line=<OUT.ll 行> addr=<hex> sz=<n> val=<hex>" で出力する。
"""
import re, sys, json

DECL = 'declare void @__wchk(i64, i64, i64, i64)\n'
HEAD = re.compile(r'^(\s*)store (?:(?:atomic|volatile) )*')
VEC = re.compile(r'^<(\d+) x (\w+)>$')
FPBITS = {'half': 16, 'bfloat': 16, 'float': 32, 'double': 64,
          'x86_fp80': 80, 'fp128': 128, 'ppc_fp128': 128}
OPEN, CLOSE = '([{<', ')]}>'


def top_find(s, pat):
    d = 0
    for i, c in enumerate(s):
        if c in OPEN:
            d += 1
        elif c in CLOSE:
            d -= 1
        elif d == 0 and s.startswith(pat, i):
            return i
    return -1


def parse_store(s):
    m = HEAD.match(s)
    if not m:
        return None
    rest = s[m.end():]
    if rest[:1] in OPEN:
        d, j = 0, -1
        for i, c in enumerate(rest):
            d += (c in OPEN) - (c in CLOSE)
            if d == 0:
                j = i
                break
        if j < 0:
            return None
        ty, rest = rest[:j + 1], rest[j + 1:]
    else:
        ty, _, rest = rest.partition(' ')
    rest = rest.lstrip(' ')
    k = top_find(rest, ', ptr ')
    if k < 0:
        return None
    val, addr = rest[:k].strip(), rest[k + len(', ptr '):]
    c = top_find(addr, ',')
    if c >= 0:
        addr = addr[:c]
    return m.group(1), ty, val, addr.strip()


def elem_bits(t):
    if re.fullmatch(r'i\d+', t):
        return int(t[1:])
    return FPBITS.get(t)


def emit(ind, ln, ty, val):
    """(挿入行, i64 オペランド, サイズ) を返す。扱えない型は None。"""
    p = f'%__w{ln}'
    L = []
    if ty == 'ptr':
        L.append(f'{ind}{p}v = ptrtoint ptr {val} to i64\n')
        return L, f'{p}v', 8
    v = VEC.match(ty)
    if v:
        eb = elem_bits(v.group(2))
        if eb is None:
            return None
        bits = int(v.group(1)) * eb
    else:
        bits = elem_bits(ty)
        if bits is None:
            return None
    if re.fullmatch(r'i\d+', ty):
        opnd = val
    else:
        opnd = f'{p}b'
        L.append(f'{ind}{opnd} = bitcast {ty} {val} to i{bits}\n')
    size, need = 1, (bits + 7) // 8
    while size < need:
        size *= 2
    if bits == 64:
        return L, opnd, size
    t = f'{p}i'
    op = 'zext' if bits < 64 else 'trunc'
    L.append(f'{ind}{t} = {op} i{bits} {opnd} to i64\n')
    return L, t, size


def instr(src, dst):
    out, n, total, bad, fn_of, cur, decl = [], 0, 0, [], {}, '?', False
    for ln, line in enumerate(open(src), 1):
        s = line.rstrip('\n')
        if s.startswith('define '):
            m = re.match(r'define [^@]*@([^(]+)\(', s)
            cur = m.group(1) if m else '?'
        if s.startswith('target datalayout'):
            out.append(s + '\n' + DECL)
            decl = True
            continue
        if re.match(r'^\s*store\b', s):
            total += 1
            p = parse_store(s)
            e = emit(p[0], ln, p[1], p[2]) if p else None
            if e is None:
                bad.append(ln)
            else:
                ind, addr = p[0], p[3]
                L, v, size = e
                out.extend(L)
                out.append(f'{ind}%__wa{ln} = ptrtoint ptr {addr} to i64\n')
                out.append(f'{ind}call void @__wchk(i64 %__wa{ln}, i64 {size}, i64 {v}, i64 {ln})\n')
                n += 1
                fn_of[ln] = cur
        out.append(line)
    if n and not decl:
        out.insert(0, DECL)
    open(dst, 'w').write(''.join(out))
    json.dump(fn_of, open(dst + '.fn.json', 'w'))
    print(f'[fa_wc] store total={total} instrumented={n} unhandled={len(bad)}')
    if bad:
        print('[fa_wc] unhandled lines: ' + ' '.join(map(str, bad[:50])), file=sys.stderr)


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == 'instr':
        instr(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
