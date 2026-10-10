#!/usr/bin/env python3
"""M11 IR 後処理: boot_final.ll → boot_final3.ll

 1. function_* の define を weak 化 (tools/m11/m11_ov.c の強シンボルで差替可能にする。
    RetDec が落とす間接 call / stack 引数の取りこぼしを関数単位で手修正するための仕組み)
 2. 間接 call 用トランポリン m11_tr_<fn> (全 i64×8 引数, i64 返り) と VA→トランポリン表を IR 末尾に付加
    (RetDec は IR から間接 call を全て落とす: 実測 boot closure 7416 fn 中 0 件。
     Delphi の unit init ループ / VMT / TLS hook は C override 側で m11_icall(va,...) 経由で呼ぶ)
 使い方: python3 m11_post.py IN.ll OUT.ll [--report REPORT.json]
"""
import re, sys, json

src, dst = sys.argv[1], sys.argv[2]
rep = {}
if '--report' in sys.argv:
    rep_path = sys.argv[sys.argv.index('--report') + 1]
else:
    rep_path = None
text = open(src).read()

def ptypes(args):
    out = []
    depth = 0
    cur = ''
    for ch in args:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    tys = []
    for p in out:
        toks = p.split()
        tys.append(toks[0])
    return tys


def_re = re.compile(r'^define (?P<ret>[^@]*?)@(?P<nm>function_[0-9a-f]+)\((?P<args>[^)]*)\)(?P<rest>.*)$', re.M)
fns = []

# 呼出し計数 probe (FastMM4 の入口): 計数 wrapper を weak で被せ, 本体は __lifted に改名
PROBES = {0x409410: 'GetMem', 0x409440: 'FreeMem', 0x407a50: 'FastMM_GetMem(407a50)', 0x407e20: 'FastMM_FreeMem(407e20)',
          0x4120c0: 'InitUnits', 0x4128b0: 'Halt0'}
probe_wrappers = []


def weaken(m):
    ret = m.group('ret').strip()
    nm = m.group('nm')
    args = m.group('args')
    fns.append((nm, ret, args))
    va = int(nm.split('_')[1], 16)
    if va in PROBES:
        idx = list(PROBES).index(va)
        pnames = ['%%p%d' % i for i in range(len(ptypes(args)))]
        ptys = ptypes(args)
        plist = ', '.join('%s %s' % (t, pn) for t, pn in zip(ptys, pnames))
        clist = ', '.join('%s %s' % (t, pn) for t, pn in zip(ptys, pnames))
        rt = ret.split()[0]
        w = ['define weak %s @%s(%s) {' % (ret, nm, plist), '  call void @m11_probe(i32 %d)' % idx]
        if rt == 'void':
            w += ['  call void @%s__lifted(%s)' % (nm, clist), '  ret void']
        else:
            w += ['  %%r = call %s @%s__lifted(%s)' % (rt, nm, clist), '  ret %s %%r' % rt]
        w.append('}')
        probe_wrappers.append('\n'.join(w))
        return 'define %s @%s__lifted(%s)%s' % (ret, nm, args, m.group('rest'))
    return 'define weak %s @%s(%s)%s' % (ret, nm, args, m.group('rest'))

text = def_re.sub(weaken, text)

NMAX = 8
tr = []
tab = []
maxargs = 0
for (nm, ret, args) in fns:
    tys = ptypes(args)
    maxargs = max(maxargs, len(tys))
    if len(tys) > NMAX:
        continue
    ret = ret.split()[0] if ret else 'void'
    va = int(nm.split('_')[1], 16)
    L = ['define i64 @m11_tr_%s(i64 %%a0, i64 %%a1, i64 %%a2, i64 %%a3, i64 %%a4, i64 %%a5, i64 %%a6, i64 %%a7) {' % nm]
    cargs = []
    for i, t in enumerate(tys):
        v = '%%a%d' % i
        if t == 'i64':
            cargs.append('i64 %s' % v)
        elif t in ('i32', 'i16', 'i8', 'i1'):
            L.append('  %%c%d = trunc i64 %s to %s' % (i, v, t))
            cargs.append('%s %%c%d' % (t, i))
        elif t == 'ptr':
            L.append('  %%c%d = inttoptr i64 %s to ptr' % (i, v))
            cargs.append('ptr %%c%d' % i)
        elif t == 'i128':
            L.append('  %%c%d = zext i64 %s to i128' % (i, v))
            cargs.append('i128 %%c%d' % i)
        elif t == 'double':
            L.append('  %%c%d = bitcast i64 %s to double' % (i, v))
            cargs.append('double %%c%d' % i)
        elif t == 'float':
            L.append('  %%t%d = trunc i64 %s to i32' % (i, v))
            L.append('  %%c%d = bitcast i32 %%t%d to float' % (i, i))
            cargs.append('float %%c%d' % i)
        else:
            L.append('  ; unsupported param %s' % t)
            cargs.append('%s zeroinitializer' % t)
    callexpr = 'call %s @%s(%s)' % (ret, nm, ', '.join(cargs))
    if ret == 'void':
        L.append('  ' + callexpr)
        L.append('  ret i64 0')
    elif ret == 'i64':
        L.append('  %r = ' + callexpr)
        L.append('  ret i64 %r')
    elif ret in ('i32', 'i16', 'i8', 'i1'):
        L.append('  %r = ' + callexpr)
        L.append('  %%z = zext %s %%r to i64' % ret)
        L.append('  ret i64 %z')
    elif ret == 'ptr':
        L.append('  %r = ' + callexpr)
        L.append('  %p = ptrtoint ptr %r to i32')
        L.append('  %z = zext i32 %p to i64')
        L.append('  ret i64 %z')
    elif ret == 'i128':
        L.append('  %r = ' + callexpr)
        L.append('  %z = trunc i128 %r to i64')
        L.append('  ret i64 %z')
    else:
        L.append('  %r = ' + callexpr)
        L.append('  ret i64 0')
    L.append('}')
    tr.append('\n'.join(L))
    tab.append((va, nm))

tab.sort()
# C prototype header: IR の署名そのまま (C override が呼ぶ extern を署名ずれさせない: ずれると wasm-ld が trap thunk を生成する)
CT = {'i64': 'unsigned long long', 'i32': 'unsigned int', 'i16': 'unsigned int', 'i8': 'unsigned int', 'i1': 'unsigned int',
      'ptr': 'void*', 'void': 'void', 'i128': 'unsigned __int128', 'double': 'double', 'float': 'float'}
hdr = ['/* auto-gen by m11_post.py: IR function_* の C 署名 */']
for (nm, ret, args) in fns:
    rt = CT.get(ret.split()[0], 'unsigned long long')
    ats = ', '.join(CT.get(t, 'unsigned long long') for t in ptypes(args)) or 'void'
    hdr.append('extern %s %s(%s);' % (rt, nm, ats))
open(dst.replace('.ll', '_sigs.h'), 'w').write('\n'.join(hdr) + '\n')
ent = ', '.join('{ i32, ptr } { i32 %d, ptr @m11_tr_%s }' % (va, nm) for va, nm in tab)
tail = ['', 'declare void @m11_probe(i32)'] + probe_wrappers + ['', '; ---- m11_post.py: 間接 call トランポリン + VA 表 ----']
tail.extend(tr)
tail.append('@m11_disp_n = constant i32 %d' % len(tab))
tail.append('@m11_disp_tab = constant [%d x { i32, ptr }] [%s]' % (len(tab), ent))
text = text.rstrip('\n') + '\n' + '\n'.join(tail) + '\n'
open(dst, 'w').write(text)
import json as _j
open(dst.replace('.ll', '_probes.json'), 'w').write(_j.dumps(list(PROBES.values())))
rep = {'weak_defines': len(fns), 'trampolines': len(tab), 'max_args': maxargs}
print('[m11_post] weak defines: %d, trampolines: %d, max params: %d -> %s' % (len(fns), len(tab), maxargs, dst))
if rep_path:
    json.dump(rep, open(rep_path, 'w'))
