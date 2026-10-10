#!/usr/bin/env python3
"""gen_stubs_sigs.py — 最終 .ll から (1) 未 lift callee (`declare ... @function_<VA>`) の fail-fast C スタブ
(2) harness 用 sigs.json (define された function_<VA> のパラメータ型) を生成する。
usage: gen_stubs_sigs.py FINAL.ll stubs.c sigs.json [shims.json]  (shims: {"<va hex>": "memmove|memset"} = CRT 関数を C 実装へ置換 (レジスタグローバル ABI))"""
import json
import re
import sys

CT = {'i128': 'u128', 'i64': 'u64', 'i32': 'u32', 'i16': 'unsigned short', 'i8': 'u8', 'float': 'float', 'double': 'double', 'void': 'void', 'ptr': 'void*'}


def main():
    src, stubs, sigs = sys.argv[1:4]
    shims = json.load(open(sys.argv[4])) if len(sys.argv) > 4 else {}
    out = ['#include "msimd6_core.h"', '#include <emscripten.h>']
    defined, sg = set(), {}
    text = open(src).read().split('\n')
    for l in text:
        m = re.match(r'^define (\S+) @function_([0-9a-f]+)\(([^)]*)\)', l)
        if m:
            defined.add(m.group(2))
            ps = [p.strip().split()[0] for p in m.group(3).split(',') if p.strip()]
            sg[m.group(2)] = {'params': ps, 'ret': m.group(1)}
    nstub = 0
    SH = {'memmove': 'memmove((void*)(u32)rcx, (void*)(u32)rdx, (u32)r8); rax = rcx;', 'memset': 'memset((void*)(u32)rcx, (int)(rdx & 0xff), (u32)r8); rax = rcx;'}
    SH['memcpy'] = 'memmove((void*)(u32)rcx, (void*)(u32)rdx, (u32)r8); rax = rcx;'
    SH['ident'] = 'rax = rcx;'
    SH['delete'] = 'rax = 0;'
    SH['subscribe'] = 'rax = 0;'
    # operator new (0x180f878e0): アリーナ先頭 qword をカーソルにする決定論的 bump アローカ。
    # trial 冒頭で scenario が cursor = NEW_BASE (アリーナ +0x100) を設定し、native 側 (scen_em.h の em_new)
    # と同一式で同じアドレス系列を出す。確保域はシナリオの newheap region 内 (= 比較対象)。
    SH['new'] = ('{ u64 cur = *(u64*)0x04000000ull; if (cur == 0) cur = 0x04001000ull;'
                 ' cur = (cur + 15ull) & ~(u64)15ull; u64 p = cur; cur += (rcx + 15ull) & ~(u64)15ull;'
                 ' *(u64*)0x04000000ull = cur; rax = p; }')
    # getManager (0x180107430): グローバル map の代替。out {mgr=0x0400F000, ctrl=NULL} を書くだけ。
    # mgr 実体は subscribe を no-op shim にしているため参照されない (native 側は同一動作の image パッチ)。
    SH['getManager'] = ('{ *(u64*)(u32)rcx = 0x0400F000ull; *(u64*)((u32)rcx + 8) = 0ull; rax = 0x0400F000ull; }')
    # CRT _dint / _fdint (modf 系: 小数部を切り捨て。ImageBase 相対の mask 表を引くため lift 不能 → 同一意味の C 実装。差分試験で検証)
    SH['dint'] = ('{ double* p = (double*)(u32)rcx; u64 b; memcpy(&b, p, 8); unsigned ex = (b >> 52) & 0x7ff; u64 sc = (unsigned short)rdx; u64 res;'
                  ' if (ex == 0x7ff) res = ((b & 0xfffffffffffffULL) == 0) ? 1 : 2;'
                  ' else if ((b & 0x7fffffffffffffffULL) == 0) res = sc;'
                  ' else { int r = (short)(0x433 - (int)ex - (int)sc); if (r <= 0) res = sc; else if (r >= 0x35) { b &= 0x8000000000000000ULL; memcpy(p, &b, 8); res = 0xffffffffULL; }'
                  ' else { u64 m = (1ULL << r) - 1; res = (b & m) ? 0xffff : 0; b &= ~m; memcpy(p, &b, 8); } } rax = res; }')
    SH['fint'] = ('{ float* p = (float*)(u32)rcx; u32 b; memcpy(&b, p, 4); unsigned ex = (b >> 23) & 0xff; u64 sc = (unsigned short)rdx; u64 res;'
                  ' if (ex == 0xff) res = ((b & 0x7fffff) == 0) ? 1 : 2;'
                  ' else if ((b & 0x7fffffffU) == 0) res = sc;'
                  ' else { int r = (short)(0x96 - (int)ex - (int)sc); if (r <= 0) res = sc; else if (r >= 0x18) { b &= 0x80000000U; memcpy(p, &b, 4); res = 0xffffffffULL; }'
                  ' else { u32 m = (1U << r) - 1; res = (b & m) ? 0xffff : 0; b &= ~m; memcpy(p, &b, 4); } } rax = res; }')
    if shims:
        out.append('extern u64 rax, rcx, rdx, r8;')
    for l in text:
        m = re.match(r'^declare (\S+) @function_([0-9a-f]+)\(([^)]*)\)', l)
        if m and m.group(2) in shims and m.group(2) not in defined:
            bd = SH[shims[m.group(2)]]
            if bd.startswith('{'):
                # ブロック本体は rax を設定して明示 return する (return 省略は clang に
                # 「値を返さない関数」として切られ、-O1 で呼出側が unreachable になる)
                body_c = bd.rstrip()
                if body_c.endswith('}'):
                    body_c = body_c[:-1] + ' return rax; }'
                out.append('EMSCRIPTEN_KEEPALIVE u64 function_%s(void) %s' % (m.group(2), body_c))
            else:
                out.append('EMSCRIPTEN_KEEPALIVE u64 function_%s(void) { %s return 0; }' % (m.group(2), bd))
            nstub += 1
            continue
        if m and m.group(2) not in defined:
            ps = [p.strip().split()[0] for p in m.group(3).split(',') if p.strip()]
            r = m.group(1)
            args = ', '.join('%s a%d' % (CT.get(t, 'u64'), i) for i, t in enumerate(ps)) or 'void'
            out.append('EMSCRIPTEN_KEEPALIVE %s function_%s(%s) { abort(); %s}' % (CT.get(r, 'u64'), m.group(2), args, '' if r == 'void' else 'return 0; '))
            nstub += 1
    out.append('unsigned char kh_stack[65536] __attribute__((aligned(16), used));')
    open(stubs, 'w').write('\n'.join(out) + '\n')
    json.dump(sg, open(sigs, 'w'), indent=1)
    print('[stubs/sigs] defined %d, stubs %d' % (len(sg), nstub))


if __name__ == '__main__':
    main()
