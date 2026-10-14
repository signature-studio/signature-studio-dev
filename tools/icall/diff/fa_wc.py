#!/usr/bin/env python3
"""fa_wc.py — BLK+0 (0x36319008) への書き込み元を IR store 単位で特定する watchpoint (ICALL-54 #1998)。

usage:
  fa_wc.py instr IN.ll OUT.ll   # 全 IR store の直前に __wchk(addr, size, val, line) を挿入する
  OUT.ll.fn.json                 # 行番号 -> 含まれる関数名 (instr が同時に出力)

__wchk は tools/icall/diff/fa_wc_rt.c が定義する。範囲 [WATCH_LO, WATCH_HI) と重なる store だけ
"WC line=<OUT.ll 行> addr=<hex> sz=<n> val=<hex>" を出力する。
"""
import re, sys, json

WATCH = 'store'
STORE = re.compile(r'^(\s*)store (i\d+|ptr|float|double) (.*), ptr (.*)$')
DECL = 'declare void @__wchk(i64, i64, i64, i64)\n'
SIZE = {'i8': 1, 'i16': 2, 'i32': 4, 'i64': 8, 'i128': 16, 'ptr': 8, 'float': 4, 'double': 8}


def split_val(rest):
    # "<val>, ptr <addr>" 形式の rest はここに来る前に分割済み。val は値部のみ。
    return rest


def instr(src, dst):
    out, n, fn_of, cur = [], 0, {}, '?'
    for ln, line in enumerate(open(src), 1):
        s = line.rstrip('\n')
        if s.startswith('define '):
            m = re.match(r'define [^@]*@([^(]+)\(', s)
            cur = m.group(1) if m else '?'
        if s.startswith('target datalayout'):
            out.append(s + '\n' + DECL)
            continue
        m = STORE.match(s)
        if m and not s.rstrip().endswith('volatile'):
            ind, ty, val_and_addr = m.group(1), m.group(2), m.group(3)
            addr_part = m.group(4)
            addr = re.sub(r', align \d+$', '', addr_part)
            if ty in SIZE and ty in ('ptr', 'i8', 'i16', 'i32', 'i64', 'i128'):
                size = SIZE[ty]
                t = f'%__wv{ln}'
                if ty == 'ptr':
                    cast = f'{ind}{t} = ptrtoint ptr {val_and_addr} to i64\n'
                elif ty == 'i64':
                    cast = None
                    t = val_and_addr
                elif ty == 'i128':
                    cast = f'{ind}{t} = trunc i128 {val_and_addr} to i64\n'
                else:
                    cast = f'{ind}{t} = zext {ty} {val_and_addr} to i64\n'
                a = f'%__wa{ln}'
                out.append(f'{ind}{a} = ptrtoint ptr {addr} to i64\n')
                if cast:
                    out.append(cast)
                out.append(f'{ind}call void @__wchk(i64 {a}, i64 {size}, i64 {t}, i64 {ln})\n')
                n += 1
                fn_of[ln] = cur
        out.append(line)
    open(dst, 'w').write(''.join(out))
    json.dump(fn_of, open(dst + '.fn.json', 'w'))
    print(f'[fa_wc] instrumented stores: {n}')


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == 'instr':
        instr(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
