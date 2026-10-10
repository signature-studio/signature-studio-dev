#!/usr/bin/env python3
"""LLVM IR (lift 産物) の外部参照を shim の提供面と突き合わせ、未提供の Win32/CRT API に fail-fast スタブを生成する。

  ir_undef.py <ir.ll> [--nm work/nm_MT.txt] [--emit-stubs out.c] [--json out.json]

分類:
  shimx      : shimx が定義済み (nm)
  libc       : Emscripten libc / compiler-rt 側が解決する既知名 (memset 等) と llvm.* intrinsic
  lifter     : function_*/__asm_*/__zext*/entry_point 等の lift 由来名 (shim の担当外)
  win_other  : FLEngine/プラグイン import 名 (data/imports.json) だが shimx 未提供 (GUI/audio 担当 DLL か、未実装)
  unknown    : 上記以外
--emit-stubs : win_other + unknown の関数それぞれに「名前を出して abort」するスタブ C を出力
               (署名は IR の declare から導出。-sERROR_ON_UNDEFINED_SYMBOLS=0 での黙った trap を防ぐ)
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
LIBC = set('''memset memcpy memmove memcmp memchr strlen strcmp strncmp strcpy strncpy strcat strchr strrchr strstr
malloc free calloc realloc abort exit atexit printf fprintf sprintf snprintf puts putchar fputs fwrite fread fflush
sin cos tan atan atan2 exp log pow sqrt floor ceil fabs fmod log10 log2 sinf cosf tanf expf logf powf sqrtf floorf ceilf fabsf
toupper tolower isalpha isdigit isspace qsort bsearch rand srand time clock getenv
socket bind listen accept connect send recv sendto recvfrom select setsockopt getsockopt getsockname ntohs htons ntohl htonl
gethostbyname getaddrinfo freeaddrinfo shutdown'''.split())
LIFTER = re.compile(r'^(function_|__asm_|__zext|entry_point|m\d+_|sub_|loc_|llvm\.)')
CT = {'i1': 'int', 'i8': 'int', 'i16': 'int', 'i32': 'int', 'i64': 'long long', 'float': 'float', 'double': 'double',
      'ptr': 'void*', 'void': 'void', 'i128': 'void*'}


def split_args(a):
    out, depth, cur = [], 0, ''
    for ch in a:
        if ch in '<[{(':
            depth += 1
        elif ch in '>]})':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def ctype(t):
    t = t.strip().split()[0] if t.strip() else 'i64'
    return CT.get(t, 'long long')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('--nm', default=os.path.join(ROOT, 'work', 'nm_MT.txt'))
    ap.add_argument('--emit-stubs')
    ap.add_argument('--json')
    a = ap.parse_args()
    src = open(a.ir, errors='replace').read()
    decls = {}
    for m in re.finditer(r'^declare\s+(?:[\w.]+\s+)*?(void|i\d+|float|double|ptr|<[^>]+>|%[\w.$-]+|\{[^}]*\})\s+@([\w.$-]+)\((.*?)\)', src, re.M):
        decls.setdefault(m.group(2), (m.group(1), m.group(3)))
    defined = set(re.findall(r'^define\s+[^@\n]*@([\w.$-]+)\(', src, re.M))
    shimx = set()
    for l in open(a.nm):
        p = l.split()
        if len(p) >= 2 and p[-2] in 'TWtw':
            shimx.add(p[-1])
    imp = json.load(open(os.path.join(ROOT, 'data', 'imports.json')))
    winnames = {e['name'] for e in imp['flengine']['static']} | {e['name'] for e in imp['flengine']['delay']}
    for v in imp['plugins'].values():
        winnames |= {e['name'] for e in v['static']} | {e['name'] for e in v['delay']}
    cls = {}
    for n0 in decls:
        n = re.sub(r'\.\d+$', '', n0) if re.match(r'^[A-Za-z_]\w*\.\d+$', n0) else n0   # 'SHGetFolderPathW.1' のような重複 declare 名
        if n0 in defined:
            continue
        if n in shimx:
            cls[n0] = 'shimx'
        elif LIFTER.match(n):
            cls[n0] = 'lifter'
        elif n in LIBC:
            cls[n0] = 'libc'
        elif n in winnames:
            cls[n0] = 'win_other'
        else:
            cls[n0] = 'unknown'
    cnt = {}
    for k in cls.values():
        cnt[k] = cnt.get(k, 0) + 1
    print('%s: declare %d (IR 内定義を除く外部参照 %d)' % (os.path.basename(a.ir), len(decls), len(cls)))
    for k in ('shimx', 'libc', 'lifter', 'win_other', 'unknown'):
        names = sorted(n for n, c in cls.items() if c == k)
        print('  %-9s %4d %s' % (k, len(names), (' '.join(names) if k in ('win_other', 'unknown') else '')[:1500]))
    if a.json:
        json.dump({'counts': cnt, 'classes': {k: sorted(n for n, c in cls.items() if c == k) for k in cnt}}, open(a.json, 'w'), indent=1)
    if a.emit_stubs:
        out = ['/* 自動生成: scripts/ir_undef.py — shim 未提供 API の fail-fast スタブ (呼ばれたら名前を出して abort) */',
               '#include <stdio.h>', '#include <stdlib.h>', 'extern void shim_unimplemented(const char*);']
        n = 0
        for name in sorted(cls):
            if cls[name] not in ('win_other', 'unknown'):
                continue
            ret, args = decls[name]
            params = [ctype(x) for x in split_args(args) if x.strip() != '...']
            plist = ', '.join('%s a%d' % (t, i) for i, t in enumerate(params)) or 'void'
            rt = ctype(ret)
            safe = re.sub(r'\.(\d+)', r'_D\1', name)
            body = '    shim_unimplemented("%s");' % name
            body += '\n    return;' if rt == 'void' else '\n    return 0;'
            out.append('%s %s(%s) {\n%s\n}' % (rt, safe, plist, body))
            n += 1
        open(a.emit_stubs, 'w').write('\n'.join(out) + '\n')
        print('  -> fail-fast スタブ %d 本を %s に出力' % (n, a.emit_stubs))


if __name__ == '__main__':
    main()
